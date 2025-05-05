import streamlit as st
import json
import os
from PIL import Image

# Load data
DATA_FILE = "data.json"
if not os.path.exists(DATA_FILE):
    st.error("No data found. Run the base_analyzer.py first.")
    st.stop()

with open(DATA_FILE, "r") as f:
    data = json.load(f)

st.set_page_config(layout="wide")
st.title("Military Base Analysis Dashboard")

# Sidebar for selection
locations = list(data.keys())
selected_location = st.sidebar.selectbox("Select a location to review:", locations)
record = data[selected_location]

# Show location
st.subheader(f"Analysis for {record['country']} @ {record['latitude']:.4f}, {record['longitude']:.4f}")

# Show screenshots first
st.markdown("### 📸 Screenshots")
screenshots = record.get("screenshot_paths", [])
if screenshots:
    cols = st.columns(3)  # 3 columns grid
    for idx, path in enumerate(screenshots):
        if os.path.exists(path):
            with cols[idx % 3]:
                st.image(Image.open(path), use_column_width=True)
else:
    st.write("No screenshots found.")

# Commander summary underneath
st.markdown("### 🧠 Commander Summary")
commander_summary = record.get("commander_summary", {})
if isinstance(commander_summary, dict):
    st.json(commander_summary)
else:
    st.write(commander_summary)

# Analyst reports
st.markdown("---")
st.markdown("### 📋 Analyst Reports")
steps = record.get("steps", [])
for idx, analysis in enumerate(steps):
    st.markdown(f"#### Step {idx + 1}")
    st.json(analysis)
