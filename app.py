import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points
import os

# Sayfa Ayarları
st.set_page_config(page_title="Fay Mesafe Sorgu", layout="wide")

st.title("📍 En Yakın Fay Hattı Sorgulama")
st.info("Harita üzerinde herhangi bir noktaya tıklayın. En yakın fay hattı ile aranızda bir bağlantı çizgisi oluşacaktır.")

@st.cache_data
def load_data():
    geojson_file = "TurkiyeFaults.geojson"
    if not os.path.exists(geojson_file):
        return None, None
    
    gdf = gpd.read_file(geojson_file)
    # Mesafe hesabı için Türkiye UTM (Metrik)
    gdf_utm = gdf.to_crs(epsg=5259) 
    return gdf, gdf_utm

try:
    faults_display, faults_utm = load_data()

    if faults_display is not None:
        # Harita (Erzincan Odaklı)
        m = folium.Map(location=[39.75, 39.50], zoom_start=8)

        # Ana Fay Hatları (Siyah ve İnce)
        folium.GeoJson(
            faults_display,
            style_function=lambda x: {'color': 'black', 'weight': 1.0, 'opacity': 0.5}
        ).add_to(m)

        # Haritayı Göster ve Tıklamayı Dinle
        map_output = st_folium(m, width="100%", height=600, key="initial_map")

        if map_output["last_clicked"]:
            clicked_lat = map_output["last_clicked"]["lat"]
            clicked_lon = map_output["last_clicked"]["lng"]
            
            # 1. Tıklanan noktayı UTM'e çevir
            p_geom = Point(clicked_lon, clicked_lat)
            p_utm_series = gpd.GeoSeries([p_geom], crs="EPSG:4326").to_crs(epsg=5259)
            p_utm = p_utm_series.iloc[0] # Bu bir Point objesidir

            # 2. En yakın fayı ve mesafeyi bul
            distances = faults_utm.distance(p_utm)
            nearest_idx = distances.idxmin()
            distance_km = distances.min() / 1000

            # 3. Geometriyi doğru formatta al
            nearest_fault_geom = faults_utm.geometry.iloc[nearest_idx]
            
            # nearest_points fonksiyonuna iki saf 'Geometry' objesi gönderiyoruz
            pts = nearest_points(p_utm, nearest_fault_geom) 
            pt1 = pts[0] # Tıklanan yer (UTM)
            pt2 = pts[1] # Fay üzerindeki en yakın nokta (UTM)
            
            # Noktaları geri WGS84'e (Lat/Lon) çevir
            line_geom = LineString([pt1, pt2])
            line_gdf = gpd.GeoSeries([line_geom], crs="EPSG:5259").to_crs(epsg=4326)
            line_coords = [(p[1], p[0]) for p in line_gdf.iloc[0].coords]

            # 4. Sonuç Haritası
            st.divider()
            st.subheader(f"📏 En Yakın Fay Hattına Mesafe: {distance_km:.2f} km")
            
            m2 = folium.Map(location=[clicked_lat, clicked_lon], zoom_start=12)
            
            # Faylar (Yazım hatası düzeltildi)
            folium.GeoJson(
                faults_display, 
                style_function=lambda x: {'color': 'black', 'weight': 1.0, 'opacity': 0.4}
            ).add_to(m2)
            
            # Tıklanan Nokta
            folium.Marker([clicked_lat, clicked_lon], tooltip="Sizin Noktanız").add_to(m2)
            
            # Bağlantı Çizgisi (Kırmızı ve Kesikli)
            folium.PolyLine(line_coords, color="red", weight=3, opacity=0.8, dash_array='5, 10').add_to(m2)

            # Haritayı tekrar render et
            st_folium(m2, width="100%", height=600, key="result_map")

            if distance_km < 1.0:
                st.warning("⚠️ Seçtiğiniz nokta fay hattına çok yakın!")

    else:
        st.error("GeoJSON dosyası bulunamadı. Lütfen GitHub deponuzu kontrol edin.")

except Exception as e:
    st.error(f"Hata oluştu: {e}")