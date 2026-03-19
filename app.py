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

# ==========================================
# 1. AYARLAR VE STİL (CSS) FONKSİYONLARI
# ==========================================
def setup_page():
    st.set_page_config(page_title="Fay Mesafe Sorgu & Risk Analizi", layout="wide", initial_sidebar_state="collapsed")
    st.markdown("""
        <style>
        .block-container { padding-top: 1.5rem !important; padding-bottom: 0.5rem !important; }
        h1 { margin-bottom: 0rem !important; padding-bottom: 0.2rem !important; font-size: 1.8rem !important; }
        .leaflet-interactive { outline: none !important; }
        p { margin-bottom: 0.3rem !important; }
        [data-testid="stMetricValue"] { height: auto !important; min-height: 50px !important; }
        div[data-testid="stMetricValue"] > div { font-size: 1.1rem !important; white-space: normal !important; line-height: 1.3 !important; overflow-wrap: break-word !important; font-weight: 500 !important; }
        div[data-testid="stMetricLabel"] { font-size: 0.9rem !important; margin-bottom: 2px !important; }
        </style>
    """, unsafe_allow_html=True)

def init_session_state():
    defaults = {"current_lat": None, "current_lon": None, "last_map_click": None, "last_gps_data": None, "current_address": "Adres aranıyor..."}
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

# ==========================================
# 2. VERİ ÇEKME VE HESAPLAMA FONKSİYONLARI
# ==========================================
@st.cache_data
def load_data():
    if not os.path.exists("TurkiyeFaults.geojson"):
        st.error("GeoJSON dosyası bulunamadı.")
        return None, None
    gdf = gpd.read_file("TurkiyeFaults.geojson")
    return gdf, gdf.to_crs(epsg=5259)

def get_address(lat, lon):
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=tr"
        req = requests.get(url, timeout=5)
        if req.status_code == 200:
            data = req.json()
            adres_parcalari = [p for p in [data.get("locality", ""), data.get("city", ""), data.get("principalSubdivision", "")] if p]
            return ", ".join(adres_parcalari) if adres_parcalari else "Bölge bilgisi bulunamadı."
        return f"Adres API Hatası (Kod: {req.status_code})"
    except Exception as e:
        return f"Adres Çekme Hatası: {e}"

def get_historical_quakes(lat, lon):
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={lat}&longitude={lon}&maxradiuskm=50&minmagnitude=5.0&starttime=1900-01-01"
    try:
        req = requests.get(url, timeout=5)
        return req.json().get('features', []) if req.status_code == 200 else []
    except:
        return []

def analyze_location(lat, lon, faults_display, faults_utm):
    """Mesafe ve fay tipi hesaplamalarını yapan ana motor."""
    p_utm = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=5259).iloc[0]
    distances = faults_utm.distance(p_utm)
    nearest_idx = distances.idxmin()
    dist_km = distances.min() / 1000

    nearest_fault_geom = faults_utm.geometry.iloc[nearest_idx]
    pts = nearest_points(p_utm, nearest_fault_geom)
    line_coords = [(p[1], p[0]) for p in gpd.GeoSeries([LineString([pts[0], pts[1]])], crs="EPSG:5259").to_crs(epsg=4326).iloc[0].coords]
    
    raw_slip = faults_display.iloc[nearest_idx].get("slip_type", "Bilinmiyor").lower()
    
    if "right" in raw_slip or "dextral" in raw_slip: fay_tipi = "Sağ Yönlü Doğrultu Atımlı Fay"
    elif "left" in raw_slip or "sinistral" in raw_slip: fay_tipi = "Sol Yönlü Doğrultu Atımlı Fay"
    elif "strike" in raw_slip: fay_tipi = "Doğrultu Atımlı Fay"
    elif "normal" in raw_slip: fay_tipi = "Normal Atımlı Fay"
    elif "reverse" in raw_slip or "thrust" in raw_slip: fay_tipi = "Ters / Bindirme Fayı"
    elif "transform" in raw_slip: fay_tipi = "Transform Fay"
    else: fay_tipi = raw_slip.title() if raw_slip != "bilinmiyor" else "Bilinmiyor"

    return dist_km, fay_tipi, line_coords

def get_risk_info(distance_km):
    if distance_km <= 1.0: return "Çok Yüksek", "🔴"
    if distance_km <= 5.0: return "Yüksek", "🟠"
    if distance_km <= 15.0: return "Orta", "🟡"
    return "Düşük", "🟢"

# ==========================================
# 3. HARİTA OLUŞTURMA FONKSİYONU
# ==========================================
def draw_map(lat, lon, faults_display, historical_quakes, line_coords):
    start_loc = [lat, lon] if lat and lon else [39.75, 39.50]
    m = folium.Map(location=start_loc, zoom_start=11 if lat else 8, control_scale=True, tiles=None, click_for_marker=False)
    
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Uydu Görüntüsü', overlay=False).add_to(m)
    folium.TileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', attr='OpenTopoMap', name='Topografik Harita', overlay=False).add_to(m)
    folium.TileLayer('OpenStreetMap', name='Sokak Haritası', overlay=False).add_to(m)
    
    folium.GeoJson(faults_display, style_function=lambda x: {'color': 'black', 'weight': 1.5, 'opacity': 0.8}, interactive=False, name='Aktif Fay Hatları').add_to(m)

    if lat and lon:
        folium.Circle(location=start_loc, radius=15000, color='yellow', fill=True, fill_opacity=0.1, weight=1, interactive=False).add_to(m)
        folium.Circle(location=start_loc, radius=5000, color='orange', fill=True, fill_opacity=0.15, weight=1, interactive=False).add_to(m)
        folium.Circle(location=start_loc, radius=1000, color='red', fill=True, fill_opacity=0.2, weight=1, interactive=False).add_to(m)
        
        for q in historical_quakes:
            coords, mag = q['geometry']['coordinates'], q['properties']['mag']
            yil = datetime.datetime.fromtimestamp(q['properties']['time'] / 1000.0).year if q['properties']['time'] else ""
            folium.CircleMarker([coords[1], coords[0]], radius=float(mag)*2.5, color="purple", fill=True, tooltip=f"Yıl: {yil} | {mag} Mw").add_to(m)

        folium.Marker(start_loc, tooltip="Seçili Konum", icon=folium.Icon(color='red', icon='info-sign')).add_to(m)
        folium.PolyLine(line_coords, color="red", weight=3, opacity=0.8, dash_array='5, 5', interactive=False).add_to(m)

    folium.LayerControl(position='topright').add_to(m)
    return m

# ==========================================
# 4. ANA UYGULAMA AKIŞI
# ==========================================
def main():
    setup_page()
    init_session_state()
    st.title("📍 Konuma Bağlı Fay Hattına Uzaklık Sorgulama")

    faults_display, faults_utm = load_data()
    if faults_display is None: return

    col_panel, col_map = st.columns([1, 2.5])

    # SOL PANEL
    with col_panel:
        st.write("**Konumunuzu Bulun:**")
        location_data = streamlit_geolocation()

        if location_data and location_data.get('latitude') is not None:
            if st.session_state.last_gps_data != location_data:
                st.session_state.last_gps_data = location_data
                st.session_state.current_lat, st.session_state.current_lon = location_data['latitude'], location_data['longitude']
                st.rerun()

        if st.session_state.current_lat and st.session_state.current_lon:
            lat, lon = st.session_state.current_lat, st.session_state.current_lon
            
            with st.spinner("Konum analiz ediliyor..."):
                if st.session_state.current_address == "Adres aranıyor..." or st.session_state.get("current_address_coords") != (lat, lon):
                    st.session_state.current_address = get_address(lat, lon)
                    st.session_state.current_address_coords = (lat, lon)

                dist_km, fay_tipi, line_coords = analyze_location(lat, lon, faults_display, faults_utm)
                historical_quakes = get_historical_quakes(lat, lon)
                risk_level, risk_color = get_risk_info(dist_km)

                fault_images = {"Sağ Yönlü Doğrultu Atımlı Fay": "SagYanalDogrultuAtimliFay.png", "Sol Yönlü Doğrultu Atımlı Fay": "SolYanalDogrultuAtimliFay.png", "Ters / Bindirme Fayı": "TersFay.png", "Normal Atımlı Fay": "NormalFay.png"}
                selected_image = fault_images.get(fay_tipi)

            st.markdown("---")
            st.markdown(f"<h3 style='text-align: center; margin-top: 0;'>{risk_color} Risk: {risk_level}</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='text-align: center; color: gray; font-size: 0.9rem;'>📍 {st.session_state.current_address}</p>", unsafe_allow_html=True)
            
            if historical_quakes:
                # HATANIN DÜZELTİLDİĞİ TEMİZ PYTHON YÖNTEMİ
                max_quake = max(historical_quakes, key=lambda q: float(q['properties']['mag']))
                max_mag = float(max_quake['properties']['mag'])
                max_year = datetime.datetime.fromtimestamp(max_quake['properties']['time'] / 1000.0).year
                
                st.warning(f"Sismik Geçmiş: Son 120 yılda 50km çapında Mw≥5.0 büyüklüğünde **{len(historical_quakes)}** deprem yaşanmış. En büyüğü **{max_mag} Mw** ({max_year}).")
            else:
                st.success("Sismik Geçmiş: Son 120 yılda 50km çapında Mw≥5.0 büyüklüğünde deprem yaşanmamış.")

            st.markdown("---")
            st.metric("📏 Faya Mesafe", f"{dist_km:.2f} km")
            st.metric("⚙️ Fay Tipi", fay_tipi)
            
            if selected_image and os.path.exists(selected_image):
                with st.expander("🔎 Fay Mekanizması Görseli"):
                    st.image(selected_image, use_container_width=True)
            
            rapor_icerik = f"AFET BILINCI - RİSK ANALİZ RAPORU\nTarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n--- SORGULANAN KONUM ---\nAcik Adres: {st.session_state.current_address}\nKoordinatlar: Enlem {lat:.5f}, Boylam {lon:.5f}\n\n--- ANALIZ SONUCLARI ---\nEn Yakin Faya Mesafe : {dist_km:.2f} km\nFay Tipi (Kinematigi): {fay_tipi}\nRisk Seviyesi        : {risk_level}\n\n* Sadece farkindalik amaclidir."
            st.download_button("📄 Detaylı Raporu İndir", data=rapor_icerik, file_name="Risk_Raporu.txt", mime="text/plain", use_container_width=True)
            st.link_button("🏢 Toplanma Alanı Sorgula", "https://www.turkiye.gov.tr/afet-ve-acil-durum-yonetimi-acil-toplanma-alani-sorgulama", use_container_width=True)
            
            addr_share = st.session_state.current_address.split(',')[0].strip() or "Bilinmeyen Konum"
            wp_text = f"{addr_share} konumundaki sorgu sonucum: Faya Mesafe {dist_km:.2f} km, Risk {risk_color} {risk_level}. Sen de riskini öğren: https://deprem-tools-gm2d2cwzijowgjprvwpusd.streamlit.app/"
            st.link_button("📲 WhatsApp'ta Paylaş", f"https://wa.me/?text={quote(wp_text)}", use_container_width=True)

        else:
            st.info("Haritadan bir noktaya tıklayın veya konumunuzu bulun.")
            historical_quakes, line_coords = [], []

    # SAĞ PANEL (HARİTA)
    with col_map:
        m = draw_map(st.session_state.current_lat, st.session_state.current_lon, faults_display, historical_quakes if st.session_state.current_lat else [], line_coords if st.session_state.current_lat else [])
        map_output = st_folium(m, use_container_width=True, height=600, key="main_map", returned_objects=["last_clicked"])
        st.caption("ℹ️ **Bilgi:** Renkli çemberler (🔴 1 km | 🟠 5 km | 🟡 15 km) risk alanlarını; mor daireler USGS verilerine göre Mw≥5.0 büyüklüğünden büyük depremleri gösterir.")

        if map_output and map_output.get("last_clicked"):
            click_tuple = (map_output["last_clicked"]["lat"], map_output["last_clicked"]["lng"])
            if st.session_state.last_map_click != click_tuple:
                st.session_state.last_map_click = click_tuple
                st.session_state.current_lat, st.session_state.current_lon = click_tuple
                st.rerun()

if __name__ == "__main__":
    main()