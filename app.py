import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point
import os

# Sayfa Ayarları
st.set_page_config(page_title="En Yakın Fay Sorgu", layout="wide")

st.title("📍 Türkiye Aktif Fay Sorgulama Sistemi")
st.info("Harita üzerinde bir noktaya tıklayarak en yakın aktif fay hattını ve mesafesini görebilirsiniz.")

# Veri Yükleme Fonksiyonu
@st.cache_data
def load_data():
    # GitHub'daki dosya adıyla birebir aynı olmalı
    geojson_file = "TurkiyeFaults.geojson"
    if not os.path.exists(geojson_file):
        return None, None
    
    gdf = gpd.read_file(geojson_file)
    # Mesafe hesabı için Türkiye UTM projeksiyonu
    gdf_utm = gdf.to_crs(epsg=5259) 
    return gdf, gdf_utm

try:
    faults_display, faults_utm = load_data()

    if faults_display is not None:
        # Harita (Erzincan Odaklı Başlangıç)
        m = folium.Map(location=[39.75, 39.50], zoom_start=8)

        # Fay hatlarını siyah ve ince çiziyoruz
        folium.GeoJson(
            faults_display,
            style_function=lambda x: {'color': 'black', 'weight': 1.0, 'opacity': 0.6},
            tooltip=folium.GeoJsonTooltip(fields=[faults_display.columns[0]], aliases=['Fay Adı:'])
        ).add_to(m)

        # Haritayı Göster
        map_output = st_folium(m, width="100%", height=600)

        # Tıklama Yakalama
        if map_output["last_clicked"]:
            clicked_lat = map_output["last_clicked"]["lat"]
            clicked_lon = map_output["last_clicked"]["lng"]
            
            # Tıklanan noktayı koordinat sistemine çevir
            p_utm = gpd.GeoSeries([Point(clicked_lon, clicked_lat)], crs="EPSG:4326").to_crs(epsg=5259).iloc[0]

            # Mesafeleri hesapla
            distances = faults_utm.distance(p_utm)
            nearest_idx = distances.idxmin()
            distance_km = distances.min() / 1000

            # Fay adını belirle (Hangi sütun doluysa onu almaya çalışır)
            # Eğer dosyanızda özel bir sütun adı varsa burayı 'NAME' yapabiliriz.
            fay_adi = faults_display.iloc[nearest_idx][0] 

            # Görsel Sonuç Paneli
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.metric("En Yakın Fay Hattı", str(fay_adi))
            with col2:
                st.metric("Kuş Uçuşu Mesafe", f"{distance_km:.2f} km")
            
            if distance_km < 1:
                st.error("⚠️ Seçtiğiniz nokta bir fay hattının çok yakınında (1 km altı)!")
    else:
        st.error("GeoJSON dosyası yüklenemedi. Lütfen dosya adını kontrol edin.")

except Exception as e:
    st.error(f"Sistemsel bir hata oluştu: {e}")