import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points
import os
import requests
import datetime
from streamlit_geolocation import streamlit_geolocation
from urllib.parse import quote

# Sayfa Ayarları (Tam ekran genişliği)
st.set_page_config(page_title="Fay Mesafe Sorgu & Risk Analizi", layout="wide", initial_sidebar_state="collapsed")

# --- ÖZEL CSS (Gereksiz boşlukları silme, metrik boyutları ve kompakt tasarım) ---
# artifactleri engellemek için etkileşim ayarları
st.markdown("""
    <style>
    /* Uygulamanın üstündeki devasa boşluğu siler */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 0.5rem !important;
    }
    h1 {
        margin-bottom: 0rem !important;
        padding-bottom: 0.2rem !important;
        font-size: 1.8rem !important;
    }
    .leaflet-interactive {
        outline: none !important;
    }
    /* Metin aralıklarını daralt */
    p {
        margin-bottom: 0.3rem !important;
    }
    /* Metric kutularının tamamını kapsayan alanı esnek yap */
    [data-testid="stMetricValue"] {
        height: auto !important;
        min-height: 50px !important;
    }
    
    /* Metric içindeki ana metnin boyutunu küçült ve sığdır (Kesilmeyen kibar boyut) */
    div[data-testid="stMetricValue"] > div {
        font-size: 1.1rem !important; 
        white-space: normal !important; /* Kesmeyi engelle, alt satıra geç */
        line-height: 1.3 !important;
        overflow-wrap: break-word !important; /* Kelime çok uzunsa böl */
        font-weight: 500 !important;
    }
    
    /* Metric başlıklarının (Etiketlerin) boyutunu ayarla */
    div[data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
        margin-bottom: 2px !important;
    }
    </style>
""", unsafe_allow_html=True)

# Üst Başlık (CSS ile üst boşluk traşlandı)
st.title("📍 Kapsamlı Fay Hattı & Deprem Sorgulama")

# --- HAFIZA (STATE) YÖNETİMİ ---
if "current_lat" not in st.session_state:
    st.session_state.current_lat = None
    st.session_state.current_lon = None
if "last_map_click" not in st.session_state:
    st.session_state.last_map_click = None
if "last_gps_data" not in st.session_state:
    st.session_state.last_gps_data = None
if "current_address" not in st.session_state:
    st.session_state.current_address = "Adres aranıyor..."

@st.cache_data
def load_data():
    geojson_file = "TurkiyeFaults.geojson"
    if not os.path.exists(geojson_file):
        st.error(f"GeoJSON dosyası {geojson_file} bulunamadı.")
        return None, None
    gdf = gpd.read_file(geojson_file)
    gdf_utm = gdf.to_crs(epsg=5259) # Metrik hesap için UTM
    return gdf, gdf_utm

def get_historical_quakes(lat, lon):
    # USGS API: Son 120 yılda, 50km yarıçapta, 5.0 ve üzeri depremler
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={lat}&longitude={lon}&maxradiuskm=50&minmagnitude=5.0&starttime=1900-01-01"
    try:
        req = requests.get(url, timeout=5)
        if req.status_code == 200:
            return req.json().get('features', [])
    except:
        pass
    return []

# BigDataCloud API ile Reverse Geocoding
def get_address(lat, lon):
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=tr"
        req = requests.get(url, timeout=5)
        
        if req.status_code == 200:
            data = req.json()
            # Anlamlı bir adres metni oluşturma
            mahalle = data.get("locality", "")
            ilce = data.get("city", "")
            il = data.get("principalSubdivision", "")
            adres_parcalari = [p for p in [mahalle, ilce, il] if p]
            if adres_parcalari:
                return ", ".join(adres_parcalari)
            else:
                return "Bölge bilgisi bulunamadı."
        else:
            return f"Adres API Hatası (Kod: {req.status_code})"
    except Exception as e:
        return f"Adres Çekme Hatası: {e}"

def translate_slip_type(raw_type):
    if not isinstance(raw_type, str):
        return "Bilinmiyor"
    raw_lower = raw_type.lower()
    
    # Akademik terimleri Türkçe halk diline çeviriyoruz (Örnekler çıkarıldı)
    if "dextral" in raw_lower or "right-lateral" in raw_lower or "right lateral" in raw_lower:
        return "Sağ Yönlü Doğrultu Atımlı Fay"
    elif "sinistral" in raw_lower or "left-lateral" in raw_lower or "left lateral" in raw_lower:
        return "Sol Yönlü Doğrultu Atımlı Fay"
    elif "strike-slip" in raw_lower or "strike slip" in raw_lower:
        return "Doğrultu Atımlı Fay"
    elif "normal" in raw_lower:
        return "Normal Atımlı Fay"
    elif "reverse" in raw_lower or "thrust" in raw_lower:
        return "Ters / Bindirme Fayı"
    elif "oblique" in raw_lower or "verev" in raw_lower:
        return "Verev / Oblique Atımlı Fay"
    elif "transform" in raw_lower:
        return "Transform Fay"
    else:
        return raw_type.title()

# ==========================================
# ANA YERLEŞİM (SÜTUNLAR)
# ==========================================
col_panel, col_map = st.columns([1, 2.5]) # Sol panel daha dar (1 birim), Harita daha geniş (2.5 birim)

with col_panel:
    st.write("**Konumunuzu Bulun:**")
    location_data = streamlit_geolocation()

    # GPS Tetiklemesi
    if location_data and location_data.get('latitude') is not None:
        if st.session_state.last_gps_data != location_data:
            st.session_state.last_gps_data = location_data
            st.session_state.current_lat = location_data['latitude']
            st.session_state.current_lon = location_data['longitude']
            st.rerun()

    # Analiz Sonuçları Alanı
    if st.session_state.current_lat and st.session_state.current_lon:
        lat = st.session_state.current_lat
        lon = st.session_state.current_lon
        
        # Etkileşimli Yükleme Çubuğu (Spinner)
        with st.spinner("Konum analiz ediliyor..."):
            if st.session_state.current_address == "Adres aranıyor..." or "current_address_coords" not in st.session_state or st.session_state.current_address_coords != (lat, lon):
                st.session_state.current_address = get_address(lat, lon)
                st.session_state.current_address_coords = (lat, lon)

            faults_display, faults_utm = load_data()
            if faults_display is not None:
                p_geom = Point(lon, lat)
                p_utm_series = gpd.GeoSeries([p_geom], crs="EPSG:4326").to_crs(epsg=5259)
                p_utm = p_utm_series.iloc[0] 

                # En Yakın Fayı Bul
                distances = faults_utm.distance(p_utm)
                nearest_idx = distances.idxmin()
                distance_km = distances.min() / 1000

                nearest_fault_geom = faults_utm.geometry.iloc[nearest_idx]
                pts = nearest_points(p_utm, nearest_fault_geom) 
                
                # Kesikli Çizgi Koordinatları
                line_geom = LineString([pts[0], pts[1]])
                line_gdf = gpd.GeoSeries([line_geom], crs="EPSG:5259").to_crs(epsg=4326)
                line_coords = [(p[1], p[0]) for p in line_gdf.iloc[0].coords]

                # Fay Kinematiği (Tipi) Çıkarımı
                raw_slip = faults_display.iloc[nearest_idx].get("slip_type", "Bilinmiyor")
                fay_tipi = translate_slip_type(raw_slip)
                
                # Tarihsel Depremleri USGS'den Çek
                historical_quakes = get_historical_quakes(lat, lon)

                if distance_km <= 1.0:
                    risk_level, risk_color = "Çok Yüksek", "🔴"
                elif distance_km <= 5.0:
                    risk_level, risk_color = "Yüksek", "🟠"
                elif distance_km <= 15.0:
                    risk_level, risk_color = "Orta", "🟡"
                else:
                    risk_level, risk_color = "Düşük", "🟢"

        # Sonuçları Sol Panele Yazdırma (Kompakt ve Sade)
        st.markdown("---")
        st.markdown(f"<h3 style='text-align: center; margin-top: 0;'>{risk_color} Risk: {risk_level}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center; color: gray; font-size: 0.9rem;'>📍 {st.session_state.current_address}</p>", unsafe_allow_html=True)
        
        # 2. Sismik Geçmiş Özeti (Dinamik Metin - Sarı Kutuda)
        if len(historical_quakes) > 0:
            max_mag = 0.0
            max_year = ""
            for q in historical_quakes:
                mag = float(q['properties']['mag'])
                if mag > max_mag:
                    max_mag = mag
                    max_year = datetime.datetime.fromtimestamp(q['properties']['time'] / 1000.0).year
            
            sismik_ozet = f"Son 120 yılda bu bölgede 5.0 büyüklüğü üzerinde **{len(historical_quakes)}** deprem yaşanmış. Bölgedeki en büyük deprem {max_year} yılında **{max_mag} Mw** büyüklüğündedir."
            st.warning(f"Bölgesel Deprem Geçmişi: {sismik_ozet}")
        else:
            st.success("Bölgesel Deprem Geçmişi: Son 120 yılda 50km çapında 5.0 üzeri deprem yaşanmamış.")

        st.markdown("---")
        
        # Mesafeyi traşlanmış kibar metriklerle basıyoruz (Örn: Kuzey Anadolu Fayı... yazmıyor)
        st.markdown(f"**📏 En Yakın Faya Mesafe:** {distance_km:.2f} km")
        st.markdown(f"**⚙️ Fay Tipi (Kinematiği):** {fay_tipi}")
        
        # 1. Fay Tipi Bilgi Kartları ve Görseli (Expander)
        with st.expander("Nasıl Hareket Eder? (Görsel ve Bilgi)"):
            if os.path.exists("image_4.png"):
                st.image("image_4.png", caption="Fay Mekanizmaları Şekli", use_column_width=True)
            else:
                st.info("Fay Mekanizmaları görseli image_4.png bulunamadı.")
            
            # Fay Tipi metnine göre Türkçe bir mekanik açıklama yaz:
            if fay_tipi == "Sağ Yönlü Doğrultu Atımlı Fay":
                explanation = "Bloklar yatay olarak birbirine sürtünerek zıt yönlerde hareket eder. Karşı blok sağa hareket eder."
            elif fay_tipi == "Sol Yönlü Doğrultu Atımlı Fay":
                explanation = "Bloklar yatay olarak birbirine sürtünerek zıt yönlerde hareket eder. Karşı blok sola hareket eder."
            elif fay_tipi == "Doğrultu Atımlı Fay":
                explanation = "Bloklar yatay olarak birbirine sürtünerek zıt yönlerde hareket eder."
            elif fay_tipi == "Normal Atımlı Fay":
                explanation = "Bloklar düşey olarak birbirinden uzaklaşır (çekilme). Üstteki blok aşağı kayar."
            elif fay_tipi == "Ters / Bindirme Fayı":
                explanation = "Bloklar birbirine doğru sıkışır (sıkışma). Üstteki blok diğerinin üzerine itilir."
            elif fay_tipi == "Verev / Oblique Atımlı Fay":
                explanation = "Hem düşey hem de yatay yönlü hareket vardır."
            else:
                explanation = ""
            if explanation:
                st.write(explanation)

        # Rapor İçeriği (Koordinat ve Adres Korundu)
        rapor_icerik = f"""AFET BILINCI - RİSK ANALİZ RAPORU
Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

--- SORGULANAN KONUM ---
Acik Adres: {st.session_state.current_address}
Koordinatlar: Enlem {lat:.5f}, Boylam {lon:.5f}

--- ANALIZ SONUCLARI ---
En Yakin Faya Mesafe : {distance_km:.2f} km
Fay Tipi (Kinematigi): {fay_tipi}
Risk Seviyesi        : {risk_level}

* Bu analiz USGS tarihsel deprem verileri ve aktif fay haritasi baz alinarak hesaplanmistir. Sadece farkindalik amaclidir.
"""
        st.download_button("📄 Detaylı Raporu İndir", data=rapor_icerik, file_name="Risk_Raporu.txt", mime="text/plain", use_container_width=True)

        # 3. e-Devlet Toplanma Alanı Yönlendirmesi
        edevlet_link = "https://www.turkiye.gov.tr/afet-ve-acil-durum-yonetimi-baskanligi-afet-ve-acil-durum-toplanma-alani-sorgulama"
        st.link_button("🏢 Toplanma Alanı Sorgula", edevlet_link, use_container_width=True)
        
        # 4. WhatsApp Paylaş Butonu (Dinamik Metin)
        address_for_share = st.session_state.current_address.split(',')[0].strip() # Sadece mahalle-ilçe
        if not address_for_share:
            address_for_share = "Bilinmeyen Konum"
        paylasilacak_metin = f"{address_for_share} konumundaki sorgu sonucum: Faya Mesafe {distance_km:.2f} km, Risk {risk_color} {risk_level}. Sen de riskini öğren: https://mehmetsafa.streamlit.app" # URL encode edilmeli
        whatsapp_share_url = f"https://wa.me/?text={quote(paylasilacak_metin)}"
        st.link_button("📲 Sonuçları WhatsApp'ta Paylaş", whatsapp_share_url, use_container_width=True, help="Mobil cihazda WhatsApp yüklüyse uygulamayı açar; bilgisayarda WhatsApp Web yüklüyse tarayıcıda açar.")

    else:
        # Konum seçilmediyse sol panelde görünecek mesaj
        st.info("Haritadan bir noktaya tıklayın veya konumunuzu bulun.")
        faults_display, faults_utm = load_data()
        historical_quakes = []
        line_coords = []

with col_map:
    # Harita Ayarları
    if st.session_state.current_lat and st.session_state.current_lon:
        start_loc = [st.session_state.current_lat, st.session_state.current_lon]
        start_zoom = 11
    else:
        start_loc = [39.75, 39.50]
        start_zoom = 8

    if faults_display is not None:
        # Harita Ortasındaki Gri Kutu (x box) artifact'ini (Problemler 1'in çözümü) koru.
        # click_for_marker=False ve dummy objeleri returned_objects'e ekleyerek.
        m = folium.Map(location=start_loc, zoom_start=start_zoom, control_scale=True, tiles=None, click_for_marker=False)
        
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Uydu Görüntüsü', overlay=False
        ).add_to(m)
        folium.TileLayer(
            tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            attr='OpenTopoMap', name='Topografik Harita', overlay=False
        ).add_to(m)
        # Menüdeki bozuk openstreetmap yazısını düzelten çözüm (Problemler 2'nin çözümü)
        folium.TileLayer('OpenStreetMap', name='Sokak Haritası', overlay=False).add_to(m)

        # Fay Çizgileri (Kalınlaştırılmış 1.5, opacity 0.8)
        folium.GeoJson(
            faults_display, 
            style_function=lambda x: {'color': 'black', 'weight': 1.5, 'opacity': 0.8},
            interactive=False, name='Aktif Fay Hatları'
        ).add_to(m)

        if st.session_state.current_lat and st.session_state.current_lon:
            folium.Circle(location=start_loc, radius=15000, color='yellow', fill=True, fill_opacity=0.1, weight=1, interactive=False).add_to(m)
            folium.Circle(location=start_loc, radius=5000, color='orange', fill=True, fill_opacity=0.15, weight=1, interactive=False).add_to(m)
            folium.Circle(location=start_loc, radius=1000, color='red', fill=True, fill_opacity=0.2, weight=1, interactive=False).add_to(m)
            
            # Depremler (Mor Halkalar)
            if historical_quakes:
                for q in historical_quakes:
                    coords = q['geometry']['coordinates']
                    mag = q['properties']['mag']
                    yil = datetime.datetime.fromtimestamp(q['properties']['time'] / 1000.0).year if q['properties']['time'] else ""
                    folium.CircleMarker(
                        location=[coords[1], coords[0]], radius=float(mag) * 2.5,
                        color="purple", fill=True, tooltip=f"Yıl: {yil} | {mag} Mw",
                        interactive=True # Depremlerin üzerine gelince bilgi çıksın
                    ).add_to(m)

            folium.Marker(start_loc, tooltip="Seçili Konum", icon=folium.Icon(color='red', icon='info-sign')).add_to(m)
            folium.PolyLine(line_coords, color="red", weight=3, opacity=0.8, dash_array='5, 5', interactive=False).add_to(m)

        folium.LayerControl(position='topright').add_to(m)

        # Haritayı Sağ Sütuna Bas (CBS Dashboard Formatı)
        # Artifactleri engellemek içinreturned_objects'e sadece last_clicked iste, dummy popup'ları kapat.
        map_output = st_folium(m, use_container_width=True, height=600, key="main_map", returned_objects=["last_clicked"])

        st.caption("ℹ️ **Bilgi:** Renkli çemberler (🔴 1 km | 🟠 5 km | 🟡 15 km) risk alanlarını; mor daireler USGS verilerine göre 5.0 büyüklüğünden büyük geçmiş depremleri gösterir.")

        # Harita Tıklama Yakalama
        if map_output and map_output.get("last_clicked"):
            click_lat = map_output["last_clicked"]["lat"]
            click_lon = map_output["last_clicked"]["lng"]
            click_tuple = (click_lat, click_lon)
            
            if st.session_state.last_map_click != click_tuple:
                st.session_state.last_map_click = click_tuple
                st.session_state.current_lat = click_lat
                st.session_state.current_lon = click_lon
                st.rerun()