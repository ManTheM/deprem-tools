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
from geopy.geocoders import Nominatim

# Sayfa Ayarları
st.set_page_config(page_title="Fay Mesafe Sorgu & Risk Analizi", layout="wide")

# --- ÖZEL CSS (Görsel İyileştirme) ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        height: auto !important;
        min-height: 50px !important;
    }
    div[data-testid="stMetricValue"] > div {
        font-size: 1.1rem !important; 
        white-space: normal !important; 
        line-height: 1.3 !important;
        overflow-wrap: break-word !important; 
        font-weight: 500 !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
        margin-bottom: 3px !important;
    }
    .leaflet-interactive {
        outline: none !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📍 Kapsamlı Fay Hattı & Deprem Sorgulama")
st.markdown("Haritadan bir nokta seçin veya GPS ile mevcut konumunuzu bulun.")

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

# GPS Butonu Paneli
st.write("**Mevcut konumunuzu kullanmak için butona tıklayın:**")
location_data = streamlit_geolocation()

if location_data and location_data.get('latitude') is not None:
    if st.session_state.last_gps_data != location_data:
        st.session_state.last_gps_data = location_data
        st.session_state.current_lat = location_data['latitude']
        st.session_state.current_lon = location_data['longitude']
        st.rerun()

@st.cache_data
def load_data():
    geojson_file = "TurkiyeFaults.geojson"
    if not os.path.exists(geojson_file):
        return None, None
    gdf = gpd.read_file(geojson_file)
    gdf_utm = gdf.to_crs(epsg=5259)
    return gdf, gdf_utm

def get_historical_quakes(lat, lon):
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={lat}&longitude={lon}&maxradiuskm=50&minmagnitude=5.0&starttime=1900-01-01"
    try:
        req = requests.get(url, timeout=5)
        if req.status_code == 200:
            return req.json().get('features', [])
    except:
        pass
    return []

# Adres Bulma Fonksiyonu (Reverse Geocoding)
def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="afet_kultur_uygulamasi")
        location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True, timeout=5)
        if location:
            return location.address
    except:
        pass
    return "Adres detayları sunucudan alınamadı."

def translate_slip_type(raw_type):
    if not isinstance(raw_type, str):
        return "Bilinmiyor"
    raw_lower = raw_type.lower()
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
    elif "transform" in raw_lower:
        return "Transform Fay"
    else:
        return raw_type.title()

try:
    faults_display, faults_utm = load_data()

    if faults_display is not None:
        
        if st.session_state.current_lat and st.session_state.current_lon:
            lat = st.session_state.current_lat
            lon = st.session_state.current_lon
            
            # Etkileşimli Yükleme Çubuğu (Spinner)
            with st.spinner("Hedef konum analiz ediliyor, lütfen bekleyin..."):
                
                # Adres Çekme İşlemi
                # (Sadece yeni bir konuma tıklandığında adresi baştan çekeriz, performansı artırır)
                if st.session_state.current_address == "Adres aranıyor..." or "current_address_coords" not in st.session_state or st.session_state.current_address_coords != (lat, lon):
                    st.session_state.current_address = get_address(lat, lon)
                    st.session_state.current_address_coords = (lat, lon)

                p_geom = Point(lon, lat)
                p_utm_series = gpd.GeoSeries([p_geom], crs="EPSG:4326").to_crs(epsg=5259)
                p_utm = p_utm_series.iloc[0] 

                distances = faults_utm.distance(p_utm)
                nearest_idx = distances.idxmin()
                distance_km = distances.min() / 1000

                nearest_fault_geom = faults_utm.geometry.iloc[nearest_idx]
                pts = nearest_points(p_utm, nearest_fault_geom) 
                
                line_geom = LineString([pts[0], pts[1]])
                line_gdf = gpd.GeoSeries([line_geom], crs="EPSG:5259").to_crs(epsg=4326)
                line_coords = [(p[1], p[0]) for p in line_gdf.iloc[0].coords]

                raw_slip = faults_display.iloc[nearest_idx].get("slip_type", "Bilinmiyor")
                fay_tipi = translate_slip_type(raw_slip)
                
                historical_quakes = get_historical_quakes(lat, lon)

            if distance_km <= 1.0:
                risk_level, risk_color = "Çok Yüksek", "🔴"
            elif distance_km <= 5.0:
                risk_level, risk_color = "Yüksek", "🟠"
            elif distance_km <= 15.0:
                risk_level, risk_color = "Orta", "🟡"
            else:
                risk_level, risk_color = "Düşük", "🟢"

            st.markdown(f"<h2 style='text-align: center; margin-top: 20px;'>{risk_color} Risk Derecesi: {risk_level}</h2>", unsafe_allow_html=True)
            
            # Adresi Arayüze Ekleme
            st.markdown(f"<p style='text-align: center; color: gray; font-size: 1.1rem;'>📍 <b>Konum:</b> {st.session_state.current_address}</p>", unsafe_allow_html=True)
            
            st.divider()
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"#### 📏 En Yakın Faya Mesafe")
                st.markdown(f"## **{distance_km:.2f} km**")
            with c2:
                st.markdown(f"#### ⚙️ Fay Tipi (Kinematiği)")
                st.markdown(f"## **{fay_tipi}**")
            
            st.write("") 
            
            # Rapor İçeriğine Adres ve Koordinat Eklendi
            rapor_icerik = f"""AFET BILINCI - RİSK ANALİZ RAPORU
Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}

--- SORGULANAN KONUM ---
Açık Adres: {st.session_state.current_address}
Koordinatlar: Enlem {lat:.5f}, Boylam {lon:.5f}

--- ANALIZ SONUCLARI ---
En Yakin Faya Mesafe : {distance_km:.2f} km
Fay Tipi (Kinematigi): {fay_tipi}
Risk Seviyesi        : {risk_level}

* Bu analiz USGS tarihsel deprem verileri ve aktif fay haritasi baz alinarak hesaplanmistir. Sadece farkindalik amaclidir.
"""
            st.download_button("📄 Detaylı Raporu İndir", data=rapor_icerik, file_name="Risk_Raporu.txt", mime="text/plain")
            st.divider()

            st.info("ℹ️ **Harita Bilgisi:** Renkli alanlar risk çemberleridir **(🔴 1 km | 🟠 5 km | 🟡 15 km)**. Mor daireler ise o bölgedeki 5.0 büyüklüğünden büyük geçmiş depremleri gösterir. Sağ üst köşeden harita görünümünü değiştirebilirsiniz.")

            start_loc = [lat, lon]
            start_zoom = 11
        else:
            start_loc = [39.75, 39.50]
            start_zoom = 8
            historical_quakes = []
            line_coords = []

        m = folium.Map(location=start_loc, zoom_start=start_zoom, control_scale=True, tiles=None)
        
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Uydu Görüntüsü',
            overlay=False
        ).add_to(m)
        folium.TileLayer(
            tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            attr='OpenTopoMap',
            name='Topografik Harita',
            overlay=False
        ).add_to(m)
        
        folium.TileLayer('OpenStreetMap', name='Sokak Haritası', overlay=False).add_to(m)

        folium.GeoJson(
            faults_display, 
            style_function=lambda x: {'color': 'black', 'weight': 1.5, 'opacity': 0.8},
            interactive=False,
            name='Aktif Fay Hatları'
        ).add_to(m)

        if st.session_state.current_lat and st.session_state.current_lon:
            folium.Circle(location=start_loc, radius=15000, color='yellow', fill=True, fill_opacity=0.1, weight=1, interactive=False).add_to(m)
            folium.Circle(location=start_loc, radius=5000, color='orange', fill=True, fill_opacity=0.15, weight=1, interactive=False).add_to(m)
            folium.Circle(location=start_loc, radius=1000, color='red', fill=True, fill_opacity=0.2, weight=1, interactive=False).add_to(m)
            
            if historical_quakes:
                for q in historical_quakes:
                    coords = q['geometry']['coordinates']
                    mag = q['properties']['mag']
                    yil = datetime.datetime.fromtimestamp(q['properties']['time'] / 1000.0).year if q['properties']['time'] else ""
                    folium.CircleMarker(
                        location=[coords[1], coords[0]], radius=float(mag) * 2.5,
                        color="purple", fill=True, tooltip=f"Yıl: {yil} | {mag} Mw",
                        interactive=True
                    ).add_to(m)

            folium.Marker(
                start_loc, 
                tooltip="Seçili Konum", 
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)
            
            folium.PolyLine(line_coords, color="red", weight=3, opacity=0.8, dash_array='5, 5', interactive=False).add_to(m)

        folium.LayerControl(position='topright').add_to(m)

        map_output = st_folium(
            m, 
            width="100%", 
            height=650, 
            key="main_map",
            returned_objects=["last_clicked"]
        )

        if map_output and map_output.get("last_clicked"):
            click_lat = map_output["last_clicked"]["lat"]
            click_lon = map_output["last_clicked"]["lng"]
            click_tuple = (click_lat, click_lon)
            
            if st.session_state.last_map_click != click_tuple:
                st.session_state.last_map_click = click_tuple
                st.session_state.current_lat = click_lat
                st.session_state.current_lon = click_lon
                st.rerun()

    else:
        st.error("GeoJSON dosyası yüklenemedi.")

except Exception as e:
    st.error(f"Sistemsel bir hata oluştu: {e}")