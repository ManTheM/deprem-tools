import streamlit as st
import geopandas as gpd
from shapely.ops import nearest_points
import folium
from streamlit_folium import st_folium

# Sayfa Yapılandırması
st.set_page_config(page_title="En Yakın Fay Sorgulama", layout="wide")

st.title("📍 En Yakın Fay Hattı Sorgulama")
st.write("Harita üzerinde bir noktaya tıklayarak en yakın aktif fayı ve mesafesini görebilirsiniz.")

# 1. Veriyi Yükle (Dosya adın: TurkiyeFaults.geojson)
@st.cache_data
def load_data():
    # Dosyanın script ile aynı klasörde olduğunu varsayıyoruz
    gdf = gpd.read_file("TurkiyeFaults.geojson")
    # Mesafe hesaplaması için metrik sisteme (UTM) geçiş yapıyoruz
    gdf_utm = gdf.to_crs(epsg=5259) # Türkiye için uygun UTM zonu
    return gdf, gdf_utm

try:
    faults_display, faults_utm = load_data()

    # 2. Haritayı Oluştur
    m = folium.Map(location=[39.75, 39.50], zoom_start=8) # Erzincan merkezli açılış

    # Fay hatlarını siyah ve ince olarak ekle (Senin istediğin gibi)
    folium.GeoJson(
        faults_display,
        style_function=lambda x: {'color': 'black', 'weight': 1.5, 'opacity': 0.7},
        name="Aktif Faylar"
    ).add_to(m)

    # 3. Harita Etkileşimi
    map_data = st_folium(m, width=1100, height=600)

    if map_data["last_clicked"]:
        clicked_lat = map_data["last_clicked"]["lat"]
        clicked_lon = map_data["last_clicked"]["lng"]
        
        # Tıklanan noktayı tanımla ve UTM'e dönüştür
        from shapely.geometry import Point
        point = Point(clicked_lon, clicked_lat)
        point_gdf = gpd.GeoSeries([point], crs="EPSG:4326").to_crs(epsg=5259)
        clicked_point_utm = point_gdf.iloc[0]

        # En yakın fayı bul
        # faults_utm içindeki tüm geometrilerle mesafe hesapla
        distances = faults_utm.distance(clicked_point_utm)
        min_dist_idx = distances.idxmin()
        min_dist_km = distances.min() / 1000 # Metreden Kilometreye

        # Fay bilgilerini al
        fay_adi = faults_display.iloc[min_dist_idx].get("NAME", "İsimsiz Fay") # 'NAME' sütun adını kontrol etmelisin

        # Sonucu Göster
        st.success(f"🔍 **Sonuç:** Seçilen noktaya en yakın fay: **{fay_adi}**")
        st.info(f"📏 **Mesafe:** Yaklaşık **{min_dist_km:.2f} km**")
        
        # Görsel geri bildirim için küçük bir not
        if min_dist_km < 1:
            st.warning("⚠️ Dikkat: Fay hattına çok yakın bir konum seçtiniz.")

except Exception as e:
    st.error(f"Veri yüklenirken bir hata oluştu: {e}")
    st.info("Lütfen 'TurkiyeFaults.geojson' dosyasının uygulama klasöründe olduğundan emin olun.")