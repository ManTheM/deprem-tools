import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point, LineString
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
        map_output = st_folium(m, width="100%", height=600)

        if map_output["last_clicked"]:
            clicked_lat = map_output["last_clicked"]["lat"]
            clicked_lon = map_output["last_clicked"]["lng"]
            
            # 1. Tıklanan noktayı UTM'e çevir
            p_geom = Point(clicked_lon, clicked_lat)
            p_utm = gpd.GeoSeries([p_geom], crs="EPSG:4326").to_crs(epsg=5259).iloc[0]

            # 2. En yakın fayı ve mesafeyi bul
            distances = faults_utm.distance(p_utm)
            nearest_idx = distances.idxmin()
            distance_km = distances.min() / 1000

            # 3. En yakın fayı (geometriyi) bul ve o fay üzerindeki en yakın noktayı hesapla
            nearest_fault_geom = faults_utm.iloc[nearest_idx]
            # Fay üzerindeki en yakın nokta (UTM)
            from shapely.ops import nearest_points
            pt1, pt2 = nearest_points(p_utm, nearest_fault_geom) # pt1 tıklanan yer, pt2 faydaki yer
            
            # Noktaları geri WGS84'e (Lat/Lon) çevir ki haritada çizilsin
            line_gdf = gpd.GeoSeries([LineString([pt1, pt2])], crs="EPSG:5259").to_crs(epsg=4326)
            line_coords = [(p[1], p[0]) for p in line_gdf.iloc[0].coords]

            # 4. Haritayı Yeniden Oluştur (Çizgi ile birlikte)
            # Not: Streamlit-folium'da dinamik çizgi eklemek için haritayı tekrar render ediyoruz
            m2 = folium.Map(location=[clicked_lat, clicked_lon], zoom_start=11)
            
            # Faylar
            folium.GeoJson(faults_display, style_function=lambda x: {'color': 'black', 'weight': 1.0, 'opacity': 0.4}).add_to(m2)
            
            # Tıklanan Nokta
            folium.Marker([clicked_lat, clicked_lon], icon=folium.Icon(color='blue', icon='info-sign')).add_to(m2)
            
            # Bağlantı Çizgisi (Kırmızı ve Kesikli)
            folium.PolyLine(line_coords, color="red", weight=3, opacity=0.8, dash_array='5, 5').add_to(m2)

            # Sonuç Ekranı
            st.divider()
            st.metric(label="En Yakın Fay Hattına Mesafe", value=f"{distance_km:.2f} km")
            
            if distance_km < 0.5:
                st.error("⚠️ Çok kritik konum: Fay hattının hemen üzerindesiniz veya çok yakınındasınız!")
            
            # Haritayı çizgi eklenmiş haliyle tekrar göster
            st_folium(m2, width="100%", height=600, key="result_map")

    else:
        st.error("GeoJSON dosyası bulunamadı.")

except Exception as e:
    st.error(f"Hata: {e}")