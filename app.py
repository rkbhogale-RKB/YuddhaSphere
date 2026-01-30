import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import time
from datetime import datetime
import random

st.set_page_config(page_title="GPS RTS Sim - Rohit FIXED", layout="wide")

# ────────────────────────────────────────────────
# Geolocation component (attempts to get real location)
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
defaults = {
    'player_lat': 19.0760,           # Mumbai
    'player_lon': 72.8777,
    'structures': [],
    'jets': [],
    'incoming_missiles': [],
    'resources': 1500,
    'last_tick': time.time(),
    'log': [],
    'build_mode': None,
    'build_preview': None,
    'selected_structure': None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

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
TICK_INTERVAL = 5  # seconds

# ────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────
st.sidebar.title("🚀 GPS RTS - Player @ {:.4f}, {:.4f}".format(
    st.session_state.player_lat, st.session_state.player_lon))
st.sidebar.metric("Resources", f"${st.session_state.resources:,}")

# Build mode toggle buttons
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

# Show current build mode status
if st.session_state.build_mode:
    st.sidebar.success(f"🟢 BUILD MODE: {st.session_state.build_mode}")
    st.sidebar.info(f"Cost: ${COSTS[st.session_state.build_mode]} | Click map in green circle")
else:
    st.sidebar.info("❌ No build mode active")

st.sidebar.divider()   # ← this is the corrected line

auto_tick = st.sidebar.checkbox("⚡ Auto tick every ~5s", value=True)
if st.sidebar.button("🔄 Manual Tick"):
    tick_simulation()
    st.rerun()

# ────────────────────────────────────────────────
# Map
# ────────────────────────────────────────────────
m = folium.Map(location=[st.session_state.player_lat, st.session_state.player_lon],
               zoom_start=11, tiles="cartodbpositron")

# Player base marker
folium.Marker(
    [st.session_state.player_lat, st.session_state.player_lon],
    popup="🏠 You (Player Base)",
    tooltip="Your Position",
    icon=folium.Icon(color="blue", icon="user", prefix="fa")
).add_to(m)

# Build radius circle
folium.Circle(
    radius=MAX_BUILD_RADIUS_KM * 1000,
    location=[st.session_state.player_lat, st.session_state.player_lon],
    color="green", fill=True, fill_opacity=0.1,
    popup=f"Build area ({MAX_BUILD_RADIUS_KM} km)"
).add_to(m)

# Build preview (floating marker before confirm)
if st.session_state.build_preview:
    preview = st.session_state.build_preview
    dist = haversine(st.session_state.player_lat, st.session_state.player_lon,
                     preview['lat'], preview['lon'])
    if dist <= MAX_BUILD_RADIUS_KM:
        color = {"Missile Silo":"red", "SAM Site":"blue", "Airfield":"green"}[preview['type']]
        folium.Marker(
            [preview['lat'], preview['lon']],
            popup=f"👆 Click CONFIRM to build {preview['type']} (${COSTS[preview['type']]})",
            icon=folium.Icon(color=color, icon="plus", prefix="fa")
        ).add_to(m)
        folium.Circle(
            radius=150, location=[preview['lat'], preview['lon']],
            color=color, fill=True, fill_opacity=0.25
        ).add_to(m)

# Structures
for s in st.session_state.structures:
    color = {"Missile Silo":"red", "SAM Site":"blue", "Airfield":"green"}[s['type']]
    icon_name = "crosshairs" if s['type'] == "Missile Silo" else "shield-alt" if s['type'] == "SAM Site" else "plane"
    folium.Marker(
        [s['lat'], s['lon']],
        popup=f"""
        <b>{s['type']} #{s['id']}</b><br>
        Health: {s['health']}%<br>
        {"Missiles: " + str(s.get('missiles', 0)) if s['type'] == "Missile Silo" else ""}
        {"Jets: " + str(len([j for j in st.session_state.jets if j.get('home_airfield') == s['id']])) if s['type'] == "Airfield" else ""}
        <hr>
        <small>Click marker → manage</small>
        """,
        icon=folium.Icon(color=color, icon=icon_name, prefix="fa")
    ).add_to(m)

# Jets
for j in st.session_state.jets:
    if j['status'] in ['flying', 'landed']:
        folium.Marker(
            [j['lat'], j['lon']],
            popup=f"Jet #{j['id']} | Missiles left: {j['missiles_left']} | {j['status']}",
            icon=folium.Icon(color="orange", icon="fighter-jet", prefix="fa")
        ).add_to(m)

# Incoming missiles
for inc in st.session_state.incoming_missiles:
    progress = min(1.0, inc['progress'])
    cur_lat = inc['start_lat'] + progress * (inc['target_lat'] - inc['start_lat'])
    cur_lon = inc['start_lon'] + progress * (inc['target_lon'] - inc['start_lon'])
    folium.CircleMarker(
        [cur_lat, cur_lon],
        radius=10,
        color="red", fill=True, fill_color="darkred",
        popup=f"🚀 Enemy missile ({progress*100:.0f}%)"
    ).add_to(m)

clicked = st_folium(m, width=1100, height=650, key="main_map")

# ────────────────────────────────────────────────
# Map click handling
# ────────────────────────────────────────────────
if clicked and clicked.get("last_clicked"):
    clat = clicked["last_clicked"]["lat"]
    clon = clicked["last_clicked"]["lng"]
    dist_from_player = haversine(st.session_state.player_lat, st.session_state.player_lon, clat, clon)

    # 1. Build preview
    if st.session_state.build_mode and dist_from_player <= MAX_BUILD_RADIUS_KM:
        st.session_state.build_preview = {
            'type': st.session_state.build_mode,
            'lat': clat,
            'lon': clon
        }
        st.rerun()

    # 2. Select structure (approximate click detection)
    for s in st.session_state.structures:
        if haversine(s['lat'], s['lon'], clat, clon) < 0.015:  # ~1.5 km tolerance
            st.session_state.selected_structure = s
            st.rerun()
            break

# ────────────────────────────────────────────────
# Build confirmation bar
# ────────────────────────────────────────────────
if st.session_state.build_preview:
    preview = st.session_state.build_preview
    colA, colB, colC = st.columns([3, 1.5, 1.5])
    with colA:
        st.success(f"📍 Proposed: {preview['type']} @ {preview['lat']:.4f}, {preview['lon']:.4f}")
    with colB:
        if st.button("✅ CONFIRM BUILD", type="primary", use_container_width=True):
            cost = COSTS[preview['type']]
            if st.session_state.resources >= cost:
                st.session_state.resources -= cost
                sid = len(st.session_state.structures) + 1
                new_struct = {
                    'id': sid,
                    'type': preview['type'],
                    'lat': preview['lat'],
                    'lon': preview['lon'],
                    'health': 100,
                }
                if preview['type'] == "Missile Silo":
                    new_struct['missiles'] = 6
                st.session_state.structures.append(new_struct)
                add_log(f"Built {preview['type']} #{sid}")
                st.session_state.build_mode = None
                st.session_state.build_preview = None
                st.rerun()
            else:
                st.error("Not enough resources!")
                st.session_state.build_preview = None
                st.rerun()
    with colC:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.build_preview = None
            st.rerun()

# ────────────────────────────────────────────────
# Structure management panel
# ────────────────────────────────────────────────
if st.session_state.selected_structure:
    s = st.session_state.selected_structure
    with st.expander(f"⚙️ Managing {s['type']} #{s['id']}", expanded=True):
        colL, colR = st.columns(2)
        with colL:
            st.metric("Health", f"{s['health']}%")
            if s['type'] == "Missile Silo":
                st.metric("Missiles", s.get('missiles', 0))
            elif s['type'] == "Airfield":
                jet_count = len([j for j in st.session_state.jets if j.get('home_airfield') == s['id']])
                st.metric("Jets", jet_count)

        with colR:
            if s['type'] == "Missile Silo" and s.get('missiles', 0) > 0:
                if st.button("🚀 Launch Missile"):
                    s['missiles'] -= 1
                    add_log(f"Missile launched from silo #{s['id']}")
                    st.rerun()
            elif s['type'] == "Airfield":
                if st.button("✈️ Launch Jet"):
                    st.session_state.jets.append({
                        'id': len(st.session_state.jets) + 1,
                        'lat': s['lat'],
                        'lon': s['lon'],
                        'missiles_left': 4,
                        'status': 'flying',
                        'home_airfield': s['id']
                    })
                    add_log(f"Jet launched from airfield #{s['id']}")
                    st.rerun()

        if st.button("✕ Close panel"):
            st.session_state.selected_structure = None
            st.rerun()

# ────────────────────────────────────────────────
# Simulation tick logic
# ────────────────────────────────────────────────
def tick_simulation():
    now = time.time()
    st.session_state.last_tick = now
    st.session_state.resources += 20

    # Random enemy missile spawn (~every 15–40s on average)
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
        add_log("Incoming enemy missile detected!")

    # Update missiles
    still_alive = []
    for inc in st.session_state.incoming_missiles:
        inc['progress'] += inc['speed']
        if inc['progress'] >= 1.0:
            add_log("💥 Missile IMPACT!")
            nearby = [s for s in st.session_state.structures
                      if haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon']) < 5]
            if nearby:
                victim = random.choice(nearby)
                dmg = random.randint(25, 60)
                victim['health'] = max(0, victim['health'] - dmg)
                add_log(f"Structure #{victim['id']} hit! Health now {victim['health']}%")
        else:
            intercepted = False
            for s in st.session_state.structures:
                if s['type'] == "SAM Site" and haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon']) < 18:
                    if random.random() < 0.60:
                        add_log("🛡️ SAM interception successful!")
                        intercepted = True
                        break
            if not intercepted:
                still_alive.append(inc)

    st.session_state.incoming_missiles = still_alive

# Auto-tick
now = time.time()
if auto_tick and now - st.session_state.last_tick >= TICK_INTERVAL:
    tick_simulation()
    st.rerun()

# ────────────────────────────────────────────────
# Event Log
# ────────────────────────────────────────────────
with st.expander("📋 Event Log", expanded=False):
    for line in reversed(st.session_state.log[-15:]):
        st.markdown(line)

st.caption("GPS RTS • Mumbai-based • v2 • fixed syntax + UX improvements")
