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

# Sayfa Ayarları
st.set_page_config(page_title="Fay Mesafe Sorgu & Risk Analizi", layout="wide")

st.title("📍 Kapsamlı Fay Hattı & Deprem Sorgulama")
st.markdown("Haritadan bir nokta seçin veya GPS ile mevcut konumunuzu bulun. Sistem size en yakın fayı, tehlike çemberlerini ve bölgedeki tarihsel depremleri (Mw > 5.0) sunacaktır.")

# --- HAFIZA (STATE) YÖNETİMİ ---
# Harita tıklaması ile GPS butonunun çakışmasını engellemek için
if "current_lat" not in st.session_state:
    st.session_state.current_lat = None
    st.session_state.current_lon = None
if "last_map_click" not in st.session_state:
    st.session_state.last_map_click = None
if "last_gps" not in st.session_state:
    st.session_state.last_gps = None

# GPS Butonu
st.write("Mevcut konumunuzu kullanarak hızlı sorgu yapabilirsiniz:")
location_data = streamlit_geolocation()

@st.cache_data
def load_data():
    geojson_file = "TurkiyeFaults.geojson"
    if not os.path.exists(geojson_file):
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

try:
    faults_display, faults_utm = load_data()

    if faults_display is not None:
        
        # İlk Harita (Kullanıcının yer seçmesi için)
        m = folium.Map(location=[39.75, 39.50], zoom_start=8)
        folium.GeoJson(
            faults_display,
            style_function=lambda x: {'color': 'black', 'weight': 1.0, 'opacity': 0.5}
        ).add_to(m)

        map_output = st_folium(m, width="100%", height=500, key="initial_map")

        # --- ETKİLEŞİM KONTROLÜ ---
        # 1. GPS verisi geldiyse ve yeniyse onu kullan
        if location_data and location_data.get('latitude') is not None:
            gps_tuple = (location_data['latitude'], location_data['longitude'])
            if st.session_state.last_gps != gps_tuple:
                st.session_state.last_gps = gps_tuple
                st.session_state.current_lat = gps_tuple[0]
                st.session_state.current_lon = gps_tuple[1]

        # 2. Haritaya tıklandıysa ve yeniyse onu kullan (GPS'i ezer)
        if map_output and map_output.get("last_clicked"):
            click_tuple = (map_output["last_clicked"]["lat"], map_output["last_clicked"]["lng"])
            if st.session_state.last_map_click != click_tuple:
                st.session_state.last_map_click = click_tuple
                st.session_state.current_lat = click_tuple[0]
                st.session_state.current_lon = click_tuple[1]

        # Hesaplamalar için hafızadaki son koordinatları al
        clicked_lat = st.session_state.current_lat
        clicked_lon = st.session_state.current_lon

        # Eğer bir koordinat elde edildiyse (Tıklama veya GPS ile) hesaplamalara başla
        if clicked_lat and clicked_lon:
            p_geom = Point(clicked_lon, clicked_lat)
            p_utm_series = gpd.GeoSeries([p_geom], crs="EPSG:4326").to_crs(epsg=5259)
            p_utm = p_utm_series.iloc[0] 

            # En Yakın Fayı Bul
            distances = faults_utm.distance(p_utm)
            nearest_idx = distances.idxmin()
            distance_km = distances.min() / 1000

            nearest_fault_geom = faults_utm.geometry.iloc[nearest_idx]
            
            pts = nearest_points(p_utm, nearest_fault_geom) 
            pt1 = pts[0] 
            pt2 = pts[1] 
            
            line_geom = LineString([pt1, pt2])
            line_gdf = gpd.GeoSeries([line_geom], crs="EPSG:5259").to_crs(epsg=4326)
            line_coords = [(p[1], p[0]) for p in line_gdf.iloc[0].coords]

            # Risk Seviyesi
            if distance_km <= 1.0:
                risk_level, risk_color = "Çok Yüksek (Tehlikeli)", "🔴"
            elif distance_km <= 5.0:
                risk_level, risk_color = "Yüksek", "🟠"
            elif distance_km <= 15.0:
                risk_level, risk_color = "Orta", "🟡"
            else:
                risk_level, risk_color = "Düşük", "🟢"

            # Sonuç Arayüzü
            st.divider()
            st.subheader("📊 Analiz Sonuçları")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("📏 En Yakın Faya Mesafe", f"{distance_km:.2f} km")
            with c2:
                st.metric("⚠️ Risk Derecesi", f"{risk_color} {risk_level}")
            with c3:
                # Rapor Hazırlama
                rapor_icerik = f"""AFET BILINCI - FAY HATTI VE RİSK ANALİZ RAPORU
Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}
--------------------------------------------------
Sorgulanan Koordinatlar: Enlem: {clicked_lat:.5f}, Boylam: {clicked_lon:.5f}
En Yakin Aktif Fay Hattina Kus Ucusu Mesafe: {distance_km:.2f} km
Tahmini Yakinlik Risk Seviyesi: {risk_level}

* Bu analiz USGS tarihsel deprem verileri ve aktif fay haritasi baz alinarak hesaplanmistir. Kesin resmi belge niteligi tasimaz.
"""
                st.download_button(
                    label="📄 Sonuç Raporunu İndir",
                    data=rapor_icerik,
                    file_name="Fay_Risk_Raporu.txt",
                    mime="text/plain"
                )

            # Tarihsel Depremleri Çek
            with st.spinner('Çevredeki tarihsel depremler (Mw > 5.0) USGS veritabanından çekiliyor...'):
                historical_quakes = get_historical_quakes(clicked_lat, clicked_lon)

            # İkinci Harita (Sonuç Haritası)
            m2 = folium.Map(location=[clicked_lat, clicked_lon], zoom_start=11)
            
            # Faylar
            folium.GeoJson(
                faults_display, 
                style_function=lambda x: {'color': 'black', 'weight': 1.0, 'opacity': 0.6}
            ).add_to(m2)
            
            # Tehlike Çemberleri (Buffer Zones)
            folium.Circle(location=[clicked_lat, clicked_lon], radius=15000, color='yellow', fill=True, fill_opacity=0.1, weight=1, tooltip="15 km Çemberi").add_to(m2)
            folium.Circle(location=[clicked_lat, clicked_lon], radius=5000, color='orange', fill=True, fill_opacity=0.15, weight=1, tooltip="5 km Çemberi").add_to(m2)
            folium.Circle(location=[clicked_lat, clicked_lon], radius=1000, color='red', fill=True, fill_opacity=0.2, weight=1, tooltip="1 km Çemberi").add_to(m2)
            
            # Tarihsel Depremleri Haritaya Ekle
            if historical_quakes:
                st.info(f"📍 50 km yarıçapında, büyüklüğü 5.0 ve üzeri olan **{len(historical_quakes)}** adet tarihsel deprem bulundu. (Mor halkalar)")
                for q in historical_quakes:
                    coords = q['geometry']['coordinates'] # [lon, lat, depth]
                    mag = q['properties']['mag']
                    t_ms = q['properties']['time']
                    yil = datetime.datetime.fromtimestamp(t_ms / 1000.0).year if t_ms else "Bilinmiyor"
                    
                    folium.CircleMarker(
                        location=[coords[1], coords[0]],
                        radius=float(mag) * 2.5, # Büyüklüğe göre daire çapı
                        color="purple",
                        fill=True,
                        tooltip=f"Yıl: {yil} | Büyüklük: {mag} Mw"
                    ).add_to(m2)

            # Tıklanan Nokta ve Çizgi
            folium.Marker([clicked_lat, clicked_lon], tooltip="Sorgulanan Konum", icon=folium.Icon(color='red', icon='info-sign')).add_to(m2)
            folium.PolyLine(line_coords, color="red", weight=3, opacity=0.8, dash_array='5, 5').add_to(m2)

            st_folium(m2, width="100%", height=650, key="result_map")

    else:
        st.error("GeoJSON dosyası yüklenemedi.")

except Exception as e:
    st.error(f"Sistemsel bir hata oluştu: {e}")