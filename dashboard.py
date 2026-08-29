import streamlit as st
import pandas as pd, sqlite3, json
import plotly.graph_objects as go
import plotly.express as px
import paho.mqtt.publish as publish
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="PowerStep - Live Dashboard", layout="wide")
st_autorefresh(interval=5000, key="refresh")

DB_PATH = "energy_system.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

# --- ╪ز╪ص┘é┘é ┘à┘ ╪د┘╪ز┘╪ذ┘è┘ç╪د╪ز ╪║┘è╪▒ ╪د┘┘à╪ص┘┘ê┘╪ر ---
alerts = pd.read_sql("SELECT * FROM alerts WHERE resolved=0 ORDER BY ts DESC LIMIT 5", conn)
if not alerts.empty and (alerts["severity"] == "high").any():
    st.error(f"≡اأذ ╪ز┘╪ذ┘è┘ç ╪╣╪د╪ش┘: {alerts.iloc[0]['message']}")

st.title("ظأة PowerStep Grid ظ¤ Live Dashboard")

energy = pd.read_sql("SELECT * FROM readings_energy ORDER BY id DESC LIMIT 500", conn, parse_dates=["ts"])
latest_gen = energy["power_mw"].head(20).mean() if not energy.empty else 0
consumption_est = latest_gen * 0.9  # ┘à╪س╪د┘ - ╪د╪▒╪ذ╪╖┘ç╪د ╪ذ┘é╪▒╪د╪ة╪ر ACS712 ╪د┘┘╪╣┘┘è╪ر

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.plotly_chart(go.Figure(go.Indicator(mode="gauge+number", value=latest_gen,
        title={"text": "╪د┘╪ز┘ê┘┘è╪» ╪د┘┘╪ص╪╕┘è (mW)"}, gauge={"axis": {"range": [0, 3000]}})),
        use_container_width=True)
with col2:
    st.plotly_chart(go.Figure(go.Indicator(mode="gauge+number", value=consumption_est,
        title={"text": "╪د┘╪د╪│╪ز┘ç┘╪د┘â ╪د┘┘╪ص╪╕┘è (mW)"}, gauge={"axis": {"range": [0, 3000]}})),
        use_container_width=True)
with col3:
    self_suff = min(100, (latest_gen / consumption_est * 100) if consumption_est else 0)
    st.plotly_chart(go.Figure(go.Indicator(mode="gauge+number", value=self_suff,
        title={"text": "┘╪│╪ذ╪ر ╪د┘╪د┘â╪ز┘╪د╪ة ╪د┘╪░╪د╪ز┘è %"})), use_container_width=True)
with col4:
    st.metric("╪ص╪د┘╪ر ╪┤╪ص┘ ╪د┘╪ز╪«╪▓┘è┘ (SoC)", "68%")  # ╪د╪▒╪ذ╪╖┘ç╪د ╪ذ┘à╪ز╪║┘è╪▒ storage_soc ╪د┘┘╪╣┘┘è

st.subheader("≡اôê ╪د┘╪ز┘ê┘┘è╪» ┘à┘é╪د╪ذ┘ ╪د┘╪د╪│╪ز┘ç┘╪د┘â ╪د┘╪ز╪▒╪د┘â┘à┘è")
if not energy.empty:
    fig = px.line(energy.sort_values("ts"), x="ts", y="power_mw", color="tile_id")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("≡ا¤ح ╪«╪▒┘è╪╖╪ر ┘â╪س╪د┘╪ر ╪د┘╪ص╪▒┘â╪ر (RSSI Heat Strip)")
rssi = pd.read_sql("SELECT * FROM readings_rssi ORDER BY id DESC LIMIT 200", conn, parse_dates=["ts"])
if not rssi.empty:
    st.plotly_chart(px.imshow([rssi["rssi"].values], aspect="auto",
        color_continuous_scale="Greens"), use_container_width=True)

st.subheader("≡اؤي╕ ┘┘ê╪ص╪ر ╪د┘╪ز╪ص┘â┘à ╪د┘┘è╪»┘ê┘è ╪ذ╪د┘╪ث╪ص┘à╪د┘")
c1, c2 = st.columns(2)
if c1.button("╪ز╪┤╪║┘è┘ ╪ح╪╢╪د╪ة╪ر ╪د┘┘à┘à╪▒"):
    publish.single("actuators/relay/corridor_light/cmd", "ON", hostname="broker.emqx.io")
if c2.button("╪ح┘è┘é╪د┘ ╪ح╪╢╪د╪ة╪ر ╪د┘┘à┘à╪▒"):
    publish.single("actuators/relay/corridor_light/cmd", "OFF", hostname="broker.emqx.io")

st.subheader("≡اْ░ ╪ص╪د╪│╪ذ╪ر ╪د┘╪ز┘ê┘┘è╪▒ ╪د┘┘à╪د┘┘è ┘ê╪د┘╪ذ┘è╪خ┘è")
tariff = st.number_input("╪│╪╣╪▒ ╪د┘┘â┘è┘┘ê┘ê╪د╪╖/╪│╪د╪╣╪ر ╪ذ╪د┘╪ش┘┘è┘ç (╪ص╪»┘ّ╪س┘ç ┘à┘ ┘╪د╪ز┘ê╪▒╪ز┘â┘à ╪د┘┘╪╣┘┘è╪ر)", value=1.5)
co2_factor = st.number_input("┘à╪╣╪د┘à┘ ╪د┘╪د┘╪ذ╪╣╪د╪س╪د╪ز kgCO2/kWh (╪▒╪د╪ش╪╣┘ç ┘à┘ ┘à╪╡╪»╪▒ ╪▒╪│┘à┘è ┘à╪ص╪»┘ّ╪س)", value=0.45)
total_wh = energy["power_mw"].sum() / 1000 / 3600 if not energy.empty else 0
st.write(f"╪د┘╪╖╪د┘é╪ر ╪د┘┘à╪ص╪╡┘ê╪»╪ر ╪د┘╪ز╪▒╪د┘â┘à┘è╪ر: **{total_wh:.3f} Wh** | "
         f"╪د┘╪ز┘ê┘┘è╪▒ ╪د┘┘à┘é╪»╪▒: **{total_wh/1000*tariff:.4f} ╪ش┘┘è┘ç** | "
         f"CO2 ╪د┘┘à┘ê┘╪▒: **{total_wh/1000*co2_factor*1000:.2f} ╪ش╪▒╪د┘à**")

st.subheader("≡اôï ╪│╪ش┘ ╪د┘╪ز┘╪ذ┘è┘ç╪د╪ز")
all_alerts = pd.read_sql("SELECT * FROM alerts ORDER BY id DESC LIMIT 20", conn)
st.dataframe(all_alerts, use_container_width=True)
