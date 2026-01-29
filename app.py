import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import time
from datetime import datetime
import random
import json

st.set_page_config(page_title="GPS RTS Sim - Rohit", layout="wide")

# ────────────────────────────────────────────────
# Geolocation component (JS → get real user location)
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
        } else {
            window.parent.postMessage({
                type: "streamlit:componentValue",
                value: {error: "Geolocation not supported"}
            }, "*");
        }
    };
    getLocation();
    </script>
    """
    html = f"""
    <div id="geoloc"></div>
    {js_code}
    """
    return st.components.v1.html(html, height=0)

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
    st.session_state.player_lat = 19.0760   # Mumbai fallback
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

if 'location_granted' not in st.session_state:
    st.session_state.location_granted = False

def add_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.log.append(f"[{ts}] {msg}")
    if len(st.session_state.log) > 30:
        st.session_state.log.pop(0)

# Try to get real location (runs once)
if not st.session_state.location_granted:
    with st.spinner("Getting your location... (please allow in browser)"):
        get_user_location_component()
        # Wait a tiny bit for JS callback – hacky but works in most cases
        time.sleep(1.5)
        # In real app we'd use st.experimental_get_query_params or component callback
        # For simplicity here we assume user pastes or defaults – improve later with better component

# For now: manual override button if location didn't come through
if st.sidebar.button("Use my current location (allow GPS)"):
    # In production: parse from component value
    # Here: placeholder – user can manually set or we use IP fallback
    st.session_state.player_lat = 19.0760   # Replace with real from JS in full impl
    st.session_state.player_lon = 72.8777
    st.session_state.location_granted = True
    st.rerun()

# ────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────
MAX_BUILD_RADIUS_KM = 30
COSTS = {"Missile Silo": 400, "SAM Site": 600, "Airfield": 800}
TICK_INTERVAL = 5  # seconds

# ────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────
st.sidebar.title("GPS RTS - Player @ {:.4f}, {:.4f}".format(
    st.session_state.player_lat, st.session_state.player_lon))

st.sidebar.metric("Resources", f"${st.session_state.resources}")

build_choice = st.sidebar.selectbox("Build", ["Missile Silo", "SAM Site", "Airfield"])

auto_tick = st.sidebar.checkbox("Auto tick every ~5s", True)

if st.sidebar.button("Manual Tick"):
    st.rerun()

# ────────────────────────────────────────────────
# Map
# ────────────────────────────────────────────────
m = folium.Map(location=[st.session_state.player_lat, st.session_state.player_lon], zoom_start=11, tiles="cartodbpositron")

# Player marker
folium.Marker(
    [st.session_state.player_lat, st.session_state.player_lon],
    popup="You (Player Base)",
    tooltip="Your Position",
    icon=folium.Icon(color="blue", icon="user", prefix="fa")
).add_to(m)

# 30 km build radius
folium.Circle(
    radius=MAX_BUILD_RADIUS_KM * 1000,  # meters
    location=[st.session_state.player_lat, st.session_state.player_lon],
    color="green", fill=True, fill_opacity=0.1, popup="Build area (30 km)"
).add_to(m)

# Structures
for s in st.session_state.structures:
    color = {"Missile Silo":"red", "SAM Site":"blue", "Airfield":"green"}[s['type']]
    folium.Marker(
        [s['lat'], s['lon']],
        popup=f"{s['type']} #{s['id']} | Health: {s['health']}% | Missiles: {s.get('missiles',0)}",
        icon=folium.Icon(color=color)
    ).add_to(m)

# Jets (simple static for now)
for j in st.session_state.jets:
    if j['status'] in ['flying', 'landed']:
        folium.Marker(
            [j['lat'], j['lon']],
            popup=f"Jet #{j['id']} | Missiles: {j['missiles_left']} | {j['status']}",
            icon=folium.Icon(color="orange", icon="plane")
        ).add_to(m)

# Incoming missiles – show current position
for inc in st.session_state.incoming_missiles:
    progress = min(1.0, inc['progress'])
    cur_lat = inc['start_lat'] + progress * (inc['target_lat'] - inc['start_lat'])
    cur_lon = inc['start_lon'] + progress * (inc['target_lon'] - inc['start_lon'])
    folium.CircleMarker(
        [cur_lat, cur_lon],
        radius=8, color="red", fill=True, fill_color="darkred",
        popup=f"Enemy missile → approaching"
    ).add_to(m)

clicked = st_folium(m, width=1100, height=650)

# Place building on click
if clicked and clicked.get("last_clicked"):
    clat = clicked["last_clicked"]["lat"]
    clon = clicked["last_clicked"]["lng"]
    dist_from_player = haversine(st.session_state.player_lat, st.session_state.player_lon, clat, clon)

    if dist_from_player > MAX_BUILD_RADIUS_KM:
        st.warning(f"Too far! You can only build within {MAX_BUILD_RADIUS_KM} km of your position.")
    elif st.button(f"Place {build_choice} here (${COSTS[build_choice]})"):
        if st.session_state.resources >= COSTS[build_choice]:
            st.session_state.resources -= COSTS[build_choice]
            sid = len(st.session_state.structures) + 1
            st.session_state.structures.append({
                'id': sid,
                'type': build_choice,
                'lat': clat,
                'lon': clon,
                'health': 100,
                'missiles': 6 if build_choice == "Missile Silo" else 0
            })
            add_log(f"Built {build_choice} #{sid} at {clat:.4f}, {clon:.4f}")
            st.rerun()
        else:
            st.error("Not enough resources!")

# ────────────────────────────────────────────────
# Simulation tick
# ────────────────────────────────────────────────
now = time.time()
if auto_tick and now - st.session_state.last_tick >= TICK_INTERVAL or st.button("Force Tick"):
    st.session_state.last_tick = now

    st.session_state.resources += 20  # passive income

    # Spawn enemy missile ~every 15–40s randomly
    if random.random() < 0.25:
        offset = random.uniform(-0.8, 0.8)
        st.session_state.incoming_missiles.append({
            'start_lat': st.session_state.player_lat + offset * 2,
            'start_lon': st.session_state.player_lon + offset * 2,
            'target_lat': st.session_state.player_lat + random.uniform(-0.15, 0.15),
            'target_lon': st.session_state.player_lon + random.uniform(-0.15, 0.15),
            'launched_at': now,
            'progress': 0.0,
            'speed': random.uniform(0.08, 0.15)   # fraction per tick
        })
        add_log("Incoming enemy missile detected!")

    # Move missiles
    still_alive = []
    for inc in st.session_state.incoming_missiles:
        inc['progress'] += inc['speed']
        if inc['progress'] >= 1.0:
            # Hit!
            add_log("Enemy missile IMPACT!")
            # Damage random nearby structure
            nearby = [s for s in st.session_state.structures if haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon']) < 5]
            if nearby:
                victim = random.choice(nearby)
                victim['health'] = max(0, victim['health'] - random.randint(25, 60))
                add_log(f"Structure #{victim['id']} damaged! Health now {victim['health']}%")
        else:
            # Check SAM interception
            intercepted = False
            for s in st.session_state.structures:
                if s['type'] == "SAM Site" and haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon']) < 18:
                    if random.random() < 0.6:
                        add_log("SAM site intercepted enemy missile!")
                        intercepted = True
                        break
            if not intercepted:
                still_alive.append(inc)
    st.session_state.incoming_missiles = still_alive

    st.rerun()

# Log
with st.expander("Event Log", expanded=True):
    for line in reversed(st.session_state.log[-12:]):
        st.markdown(line)
