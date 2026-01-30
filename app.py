import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import time
from datetime import datetime
import random
import json

st.set_page_config(page_title="GPS RTS Sim - Rohit FIXED", layout="wide")

# ────────────────────────────────────────────────
# Geolocation component
# ────────────────────────────────────────────────
def get_user_location_component():
    js_code = """
    <script>
    const getLocation = () => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude;
                    const lon = position.coords.longitude;
                    const acc = position.coords.accuracy;
                    window.parent.postMessage({
                        type: "streamlit:componentValue",
                        value: {lat: lat, lon: lon, accuracy: acc}
                    }, "*");
                },
                (error) => {
                    window.parent.postMessage({
                        type: "streamlit:componentValue",
                        value: {error: error.message}
                    }, "*");
                },
                {enableHighAccuracy: true, timeout: 5000, maximumAge: 0}
            );
        }
    };
    getLocation();
    </script>
    """
    return st.components.v1.html(js_code, height=0)

# ────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

# ────────────────────────────────────────────────
# Init session state
# ────────────────────────────────────────────────
if 'player_lat' not in st.session_state:
    st.session_state.player_lat = 19.0760
    st.session_state.player_lon = 72.8777
if 'structures' not in st.session_state:
    st.session_state.structures = []
if 'jets' not in st.session_state:
    st.session_state.jets = []
if 'incoming_missiles' not in st.session_state:
    st.session_state.incoming_missiles = []
if 'resources' not in st.session_state:
    st.session_state.resources = 1500
if 'last_tick' not in st.session_state:
    st.session_state.last_tick = time.time()
if 'log' not in st.session_state:
    st.session_state.log = []
if 'build_mode' not in st.session_state:
    st.session_state.build_mode = None  # "Missile Silo", "SAM Site", "Airfield"
if 'build_preview' not in st.session_state:
    st.session_state.build_preview = None
if 'selected_structure' not in st.session_state:
    st.session_state.selected_structure = None

def add_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.log.append(f"[{ts}] {msg}")
    if len(st.session_state.log) > 30:
        st.session_state.log.pop(0)

# ────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────
MAX_BUILD_RADIUS_KM = 30
COSTS = {"Missile Silo": 400, "SAM Site": 600, "Airfield": 800}
TICK_INTERVAL = 5

# ────────────────────────────────────────────────
# Sidebar - BUILD MODE SELECTOR
# ────────────────────────────────────────────────
st.sidebar.title("🚀 GPS RTS - Player @ {:.4f}, {:.4f}".format(
    st.session_state.player_lat, st.session_state.player_lon))
st.sidebar.metric("Resources", f"${st.session_state.resources:,}")

# Build mode buttons (toggle)
col1, col2, col3 = st.sidebar.columns(3)
if col1.button("🎯 Missile Silo ($400)", use_container_width=True):
    st.session_state.build_mode = "Missile Silo" if st.session_state.build_mode != "Missile Silo" else None
    st.session_state.build_preview = None
    st.rerun()

if col2.button("🛡️ SAM Site ($600)", use_container_width=True):
    st.session_state.build_mode = "SAM Site" if st.session_state.build_mode != "SAM Site" else None
    st.session_state.build_preview = None
    st.rerun()

if col3.button("✈️ Airfield ($800)", use_container_width=True):
    st.session_state.build_mode = "Airfield" if st.session_state.build_mode != "Airfield" else None
    st.session_state.build_preview = None
    st.rerun()

# Show current build mode
if st.session_state.build_mode:
    st.sidebar.success(f"🟢 BUILD MODE: {st.session_state.build_mode}")
    st.sidebar.info(f"Cost: ${COSTS[st.session_state.build_mode]} | Click anywhere in green circle!")
else:
    st.sidebar.info("❌ No build mode active")

st.sidebar divider = st.sidebar.divider()

auto_tick = st.sidebar.checkbox("⚡ Auto tick every 5s", True)
if st.sidebar.button("🔄 Manual Tick"):
    tick_simulation()
    st.rerun()

# ────────────────────────────────────────────────
# Main Map
# ────────────────────────────────────────────────
m = folium.Map(location=[st.session_state.player_lat, st.session_state.player_lon], zoom_start=11, tiles="cartodbpositron")

# Player base
folium.Marker(
    [st.session_state.player_lat, st.session_state.player_lon],
    popup="🏠 You (Player Base)",
    tooltip="Your Position",
    icon=folium.Icon(color="blue", icon="user", prefix="fa")
).add_to(m)

# Build radius
folium.Circle(
    radius=MAX_BUILD_RADIUS_KM * 1000,
    location=[st.session_state.player_lat, st.session_state.player_lon],
    color="green", fill=True, fill_opacity=0.1,
    popup=f"Build area ({MAX_BUILD_RADIUS_KM} km)"
).add_to(m)

# BUILD PREVIEW (when in build mode and clicked)
if st.session_state.build_preview:
    preview = st.session_state.build_preview
    dist = haversine(st.session_state.player_lat, st.session_state.player_lon, preview['lat'], preview['lon'])
    if dist <= MAX_BUILD_RADIUS_KM:
        color = {"Missile Silo":"red", "SAM Site":"blue", "Airfield":"green"}[preview['type']]
        folium.Marker(
            [preview['lat'], preview['lon']],
            popup=f"👆 CLICK CONFIRM to build {preview['type']} (${COSTS[preview['type']]})",
            icon=folium.Icon(color=color, icon="plus", prefix="fa")
        ).add_to(m)
        # Confirmation circle
        folium.Circle(
            radius=100, location=[preview['lat'], preview['lon']],
            color=color, fill=True, fillOpacity=0.3,
            popup="Click CONFIRM to build!"
        ).add_to(m)

# Structures with CLICKABLE MENUS
for s in st.session_state.structures:
    color = {"Missile Silo":"red", "SAM Site":"blue", "Airfield":"green"}[s['type']]
    popup_html = f"""
    <b>{s['type']} #{s['id']}</b><br>
    Health: {s['health']}%<br>
    { 'Missiles: ' + str(s.get('missiles',0)) if s['type'] == 'Missile Silo' else ''}<br>
    { 'Jets: ' + str(len([j for j in st.session_state.jets if j.get('home_airfield') == s['id']])) if s['type'] == 'Airfield' else ''}<br>
    <hr>
    <button onclick="selectStructure({s['id']})">⚙️ Manage</button>
    """
    folium.Marker(
        [s['lat'], s['lon']],
        popup=popup_html,
        icon=folium.Icon(color=color, icon="building" if s['type']=="Airfield" else "crosshairs" if s['type']=="Missile Silo" else "shield-alt")
    ).add_to(m)

# Jets
for j in st.session_state.jets:
    if j['status'] in ['flying', 'landed']:
        folium.Marker(
            [j['lat'], j['lon']],
            popup=f"Jet #{j['id']} | Missiles: {j['missiles_left']} | {j['status']}",
            icon=folium.Icon(color="orange", icon="fighter-jet", prefix="fa")
        ).add_to(m)

# Incoming missiles
for inc in st.session_state.incoming_missiles:
    progress = min(1.0, inc['progress'])
    cur_lat = inc['start_lat'] + progress * (inc['target_lat'] - inc['start_lat'])
    cur_lon = inc['start_lon'] + progress * (inc['target_lon'] - inc['start_lon'])
    folium.CircleMarker(
        [cur_lat, cur_lon], radius=10, color="red", fill=True, fill_color="darkred",
        popup=f"🚀 Enemy missile ({progress*100:.0f}%)"
    ).add_to(m)

# ────────────────────────────────────────────────
# HANDLE MAP CLICKS & STRUCTURE SELECTION
# ────────────────────────────────────────────────
clicked = st_folium(m, width=1100, height=650, key="main_map")

if clicked and clicked.get("last_clicked"):
    clat, clon = clicked["last_clicked"]["lat"], clicked["last_clicked"]["lng"]
    dist_from_player = haversine(st.session_state.player_lat, st.session_state.player_lon, clat, clon)
    
    # BUILD MODE CLICK
    if st.session_state.build_mode and dist_from_player <= MAX_BUILD_RADIUS_KM:
        st.session_state.build_preview = {
            'type': st.session_state.build_mode,
            'lat': clat,
            'lon': clon
        }
        st.rerun()
    
    # Structure selection (click on structure)
    for s in st.session_state.structures:
        if haversine(s['lat'], s['lon'], clat, clon) < 0.01:  # 100m radius
            st.session_state.selected_structure = s
            st.rerun()
            break

# ────────────────────────────────────────────────
# BUILD CONFIRMATION
# ────────────────────────────────────────────────
if st.session_state.build_preview:
    preview = st.session_state.build_preview
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.success(f"📍 Build {preview['type']} at {preview['lat']:.4f}, {preview['lon']:.4f}")
    with col2:
        if st.button("✅ CONFIRM BUILD", type="primary", use_container_width=True):
            cost = COSTS[preview['type']]
            if st.session_state.resources >= cost:
                st.session_state.resources -= cost
                sid = len(st.session_state.structures) + 1
                st.session_state.structures.append({
                    'id': sid,
                    'type': preview['type'],
                    'lat': preview['lat'],
                    'lon': preview['lon'],
                    'health': 100,
                    'missiles': 6 if preview['type'] == "Missile Silo" else 0
                })
                add_log(f"✅ Built {preview['type']} #{sid}")
                st.session_state.build_mode = None
                st.session_state.build_preview = None
                st.rerun()
            else:
                st.error("❌ Not enough resources!")
                st.session_state.build_preview = None
                st.rerun()
    with col3:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.build_preview = None
            st.rerun()

# ────────────────────────────────────────────────
# STRUCTURE MANAGEMENT PANEL
# ────────────────────────────────────────────────
if st.session_state.selected_structure:
    s = st.session_state.selected_structure
    st.header(f"⚙️ Manage {s['type']} #{s['id']}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Health", f"{s['health']}%")
        if s['type'] == "Missile Silo":
            st.metric("Missiles", s.get('missiles', 0))
        elif s['type'] == "Airfield":
            jet_count = len([j for j in st.session_state.jets if j.get('home_airfield') == s['id']])
            st.metric("Jets", jet_count)
    
    with col2:
        if st.button("🚀 Launch Missile" if s['type'] == "Missile Silo" and s.get('missiles',0) > 0 else "⏳ No missiles", key="launch"):
            if s['type'] == "Missile Silo" and s.get('missiles',0) > 0:
                s['missiles'] -= 1
                add_log(f"🚀 Missile #{s['id']} launched!")
        if st.button("✈️ Launch Jet" if s['type'] == "Airfield" else "N/A", key="launch_jet"):
            if s['type'] == "Airfield":
                st.session_state.jets.append({
                    'id': len(st.session_state.jets) + 1,
                    'lat': s['lat'],
                    'lon': s['lon'],
                    'missiles_left': 4,
                    'status': 'flying',
                    'home_airfield': s['id']
                })
                add_log(f"✈️ Jet #{len(st.session_state.jets)} launched from Airfield #{s['id']}")
    
    if st.button("✕ Close", key="close_panel"):
        st.session_state.selected_structure = None
        st.rerun()

# ────────────────────────────────────────────────
# SIMULATION TICK
# ────────────────────────────────────────────────
def tick_simulation():
    now = time.time()
    st.session_state.last_tick = now
    st.session_state.resources += 20
    
    # Spawn enemy missile
    if random.random() < 0.25:
        offset = random.uniform(-0.8, 0.8)
        st.session_state.incoming_missiles.append({
            'start_lat': st.session_state.player_lat + offset * 2,
            'start_lon': st.session_state.player_lon + offset * 2,
            'target_lat': st.session_state.player_lat + random.uniform(-0.15, 0.15),
            'target_lon': st.session_state.player_lon + random.uniform(-0.15, 0.15),
            'launched_at': now,
            'progress': 0.0,
            'speed': random.uniform(0.08, 0.15)
        })
        add_log("🚀 Incoming enemy missile!")
    
    # Update missiles
    still_alive = []
    for inc in st.session_state.incoming_missiles:
        inc['progress'] += inc['speed']
        if inc['progress'] >= 1.0:
            add_log("💥 Enemy missile IMPACT!")
            nearby = [s for s in st.session_state.structures if haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon']) < 5]
            if nearby:
                victim = random.choice(nearby)
                victim['health'] = max(0, victim['health'] - random.randint(25, 60))
                add_log(f"💥 Structure #{victim['id']} damaged! {victim['health']}%")
        else:
            # SAM intercept
            intercepted = False
            for s in st.session_state.structures:
                if s['type'] == "SAM Site" and haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon']) < 18:
                    if random.random() < 0.6:
                        add_log("🛡️ SAM intercepted missile!")
                        intercepted = True
                        break
            if not intercepted:
                still_alive.append(inc)
    st.session_state.incoming_missiles = still_alive

# Auto tick
now = time.time()
if auto_tick and now - st.session_state.last_tick >= TICK_INTERVAL:
    tick_simulation()
    st.rerun()

# ────────────────────────────────────────────────
# Event Log
# ────────────────────────────────────────────────
with st.expander("📋 Event Log", expanded=False):
    for line in reversed(st.session_state.log[-15:]):
        st.code(line, language=None)

# Footer
st.markdown("---")
st.caption("🎮 Fixed by Grok - Build mode, structure menus, no more reload spam!")
