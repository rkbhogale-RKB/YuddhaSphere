import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import time
from datetime import datetime, timedelta
import random

st.set_page_config(page_title="GPS RTS Sim - Rohit", layout="wide")

# ────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    """Distance in km"""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

def bearing(lat1, lon1, lat2, lon2):
    dlon = np.radians(lon2 - lon1)
    y = np.sin(dlon) * np.cos(np.radians(lat2))
    x = np.cos(np.radians(lat1)) * np.sin(np.radians(lat2)) - np.sin(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.cos(dlon)
    return (np.degrees(np.arctan2(y, x)) + 360) % 360

# ────────────────────────────────────────────────
# Session state init
# ────────────────────────────────────────────────
if 'structures' not in st.session_state:
    st.session_state.structures = []   # {'id', 'type', 'lat', 'lon', 'health', 'built_at', 'missiles':int, 'jets':list, ...}

if 'jets' not in st.session_state:
    st.session_state.jets = []         # {'id', 'from_airfield_id', 'lat', 'lon', 'target_lat', 'target_lon', 'launched_at', 'missiles_left':int, 'status': 'flying'/'landed'/'destroyed'}

if 'incoming' not in st.session_state:
    st.session_state.incoming = []     # enemy missiles {'lat_from', 'lon_from', 'target_lat', 'target_lon', 'launched_at', 'speed_km_s'}

if 'resources' not in st.session_state:
    st.session_state.resources = 1500

if 'last_tick' not in st.session_state:
    st.session_state.last_tick = time.time()

if 'log' not in st.session_state:
    st.session_state.log = []

def add_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.log.append(f"[{ts}] {msg}")
    if len(st.session_state.log) > 20:
        st.session_state.log.pop(0)

# ────────────────────────────────────────────────
# Costs & config
# ────────────────────────────────────────────────
COSTS = {
    "Missile Silo": 400,
    "SAM Site": 600,
    "Airfield": 800,
}
BUILD_TIME_SEC = 8   # fake build time

JET_MISSILES_DEFAULT = 4
JET_SPEED_KMH = 900
MISSILE_SPEED_KMH = 3000   # ballistic-ish
ENEMY_TICK_CHANCE = 0.15   # ~every 6-7 ticks new enemy missile

# ────────────────────────────────────────────────
# Sidebar - Build & Controls
# ────────────────────────────────────────────────
st.sidebar.title("GPS RTS Sim")

st.sidebar.subheader("Resources")
st.sidebar.metric("Cash", f"${st.session_state.resources:,}")

build_options = ["Missile Silo", "SAM Site", "Airfield"]
build_choice = st.sidebar.selectbox("Build Structure", build_options)

if st.sidebar.button("Launch Test Enemy Missile (debug)"):
    center_lat, center_lon = 19.0760, 72.8777
    st.session_state.incoming.append({
        'lat_from': center_lat + random.uniform(-3,3),
        'lon_from': center_lon + random.uniform(-3,3),
        'target_lat': center_lat + random.uniform(-0.5,0.5),
        'target_lon': center_lon + random.uniform(-0.5,0.5),
        'launched_at': time.time(),
        'speed_km_s': MISSILE_SPEED_KMH / 3600,
    })
    add_log("Debug: Enemy missile incoming!")

auto_tick = st.sidebar.checkbox("Auto simulation tick (~every 5s)", value=True)

# ────────────────────────────────────────────────
# Main Area - Map
# ────────────────────────────────────────────────
st.title("Single-Player GPS RTS Prototype")

m = folium.Map(location=[19.0760, 72.8777], zoom_start=10, tiles="cartodbpositron")

# Add structures
for i, s in enumerate(st.session_state.structures):
    color = {"Missile Silo":"red", "SAM Site":"blue", "Airfield":"green"}.get(s['type'], "gray")
    icon = folium.Icon(color=color, icon="star" if s['type']=="Missile Silo" else "shield" if s['type']=="SAM Site" else "plane")
    popup = f"<b>{s['type']}</b><br>ID: {s['id']}<br>Missiles: {s.get('missiles',0)}<br>Health: {s['health']}%"
    folium.Marker([s['lat'], s['lon']], popup=popup, tooltip=s['type'], icon=icon).add_to(m)

# Add player jets
for j in st.session_state.jets:
    if j['status'] == 'flying':
        color = "orange"
        popup = f"<b>Jet</b><br>Missiles left: {j['missiles_left']}<br>Status: Flying"
    elif j['status'] == 'landed':
        color = "darkgreen"
        popup = f"<b>Jet (Landed)</b><br>Missiles left: {j['missiles_left']}"
    else:
        continue
    folium.Marker([j['lat'], j['lon']], popup=popup, tooltip="Jet", icon=folium.Icon(color=color, icon="plane")).add_to(m)

# Add incoming enemy missiles (simple red dots)
for inc in st.session_state.incoming:
    folium.CircleMarker(
        [inc['target_lat'], inc['target_lon']],
        radius=6, color="darkred", fill=True, fill_color="red", fill_opacity=0.7,
        popup="Incoming enemy missile"
    ).add_to(m)

# Render map & capture clicks
clicked = st_folium(m, width=1000, height=600, returned_objects=["last_clicked", "last_object_clicked_tooltip"])

# Handle map click → place structure
if clicked and clicked.get("last_clicked"):
    lat = clicked["last_clicked"]["lat"]
    lon = clicked["last_clicked"]["lng"]

    st.info(f"Selected location: {lat:.4f}, {lon:.4f}")

    if st.button(f"Build {build_choice} here (Cost ${COSTS[build_choice]})"):
        if st.session_state.resources >= COSTS[build_choice]:
            st.session_state.resources -= COSTS[build_choice]
            sid = len(st.session_state.structures) + 1
            st.session_state.structures.append({
                'id': sid,
                'type': build_choice,
                'lat': lat,
                'lon': lon,
                'health': 100,
                'built_at': time.time(),
                'missiles': 6 if build_choice == "Missile Silo" else 0,
                'jets': [] if build_choice == "Airfield" else None
            })
            add_log(f"Built {build_choice} at {lat:.4f},{lon:.4f}")
            st.rerun()
        else:
            st.error("Not enough resources!")

# ────────────────────────────────────────────────
# Jets & Missile Launch UI
# ────────────────────────────────────────────────
st.subheader("Airforce & Missile Control")

col1, col2 = st.columns([3,2])

with col1:
    # List airfields & jets
    airfields = [s for s in st.session_state.structures if s['type'] == "Airfield"]
    if airfields:
        af_choice = st.selectbox("Select Airfield", [f"Airfield #{a['id']} ({a['lat']:.3f},{a['lon']:.3f})" for a in airfields])
        af_id = int(af_choice.split("#")[1].split()[0])
        af = next(a for a in airfields if a['id'] == af_id)

        # Build jet at airfield
        if st.button(f"Build Jet at Airfield #{af_id} (Cost $1200)"):
            if st.session_state.resources >= 1200:
                st.session_state.resources -= 1200
                jet_id = len(st.session_state.jets) + 1
                st.session_state.jets.append({
                    'id': jet_id,
                    'from_airfield_id': af_id,
                    'lat': af['lat'],
                    'lon': af['lon'],
                    'target_lat': None,
                    'target_lon': None,
                    'launched_at': None,
                    'missiles_left': JET_MISSILES_DEFAULT,
                    'status': 'landed'
                })
                add_log(f"Jet #{jet_id} built at Airfield #{af_id}")
                st.rerun()
            else:
                st.warning("Not enough cash for jet!")

    # Launch missile from silo or jet
    launch_from = st.radio("Launch missile from", ["Silo", "Jet"])

    if launch_from == "Silo":
        silos = [s for s in st.session_state.structures if s['type'] == "Missile Silo" and s.get('missiles',0) > 0]
        if silos:
            silo_choice = st.selectbox("Select Silo", [f"Silo #{s['id']} ({s['missiles']} left)" for s in silos])
            silo_id = int(silo_choice.split("#")[1].split()[0])
    else:
        flying_jets = [j for j in st.session_state.jets if j['status'] == 'flying' and j['missiles_left'] > 0]
        landed_jets = [j for j in st.session_state.jets if j['status'] == 'landed' and j['missiles_left'] > 0]
        jet_list = flying_jets + landed_jets
        if jet_list:
            jet_choice = st.selectbox("Select Jet", [f"Jet #{j['id']} ({j['missiles_left']} missiles left - {j['status']})" for j in jet_list])
            jet_id_sel = int(jet_choice.split("#")[1].split()[0])
            jet_sel = next(j for j in st.session_state.jets if j['id'] == jet_id_sel)

with col2:
    st.markdown("**Selected unit weapons**")
    if launch_from == "Jet" and 'jet_sel' in locals():
        st.info(f"Jet #{jet_sel['id']}\nMissiles: {jet_sel['missiles_left']}\nStatus: {jet_sel['status']}")
    elif launch_from == "Silo" and 'silo_id' in locals():
        silo = next(s for s in st.session_state.structures if s['id'] == silo_id)
        st.info(f"Silo #{silo['id']}\nMissiles: {silo['missiles']}")

# Target selection is done by clicking map while "target mode" active (simplified)
st.caption("Click map to set target → then press launch button below")

if 'pending_target' in st.session_state and st.session_state.pending_target:
    tlat, tlon = st.session_state.pending_target
    st.success(f"Target locked: {tlat:.4f}, {tlon:.4f}")

    if st.button("LAUNCH MISSILE AT TARGET"):
        if launch_from == "Silo" and 'silo_id' in locals():
            silo = next(s for s in st.session_state.structures if s['id'] == silo_id)
            if silo['missiles'] > 0:
                silo['missiles'] -= 1
                add_log(f"Missile launched from Silo #{silo_id} → {tlat:.4f},{tlon:.4f}")
                # For simplicity, instant launch simulation (later add flight)
                dist = haversine(silo['lat'], silo['lon'], tlat, tlon)
                travel_sec = (dist / MISSILE_SPEED_KMH) * 3600
                # ... could schedule hit later
                st.session_state.pending_target = None
                st.rerun()
        elif launch_from == "Jet" and 'jet_sel' in locals():
            if jet_sel['missiles_left'] > 0:
                jet_sel['missiles_left'] -= 1
                add_log(f"Jet #{jet_sel['id']} launched missile → {tlat:.4f},{tlon:.4f}")
                # Could update jet target too if wanted
                st.session_state.pending_target = None
                st.rerun()

# Click anywhere → potential target or build
if clicked and clicked.get("last_clicked") and not st.button:  # avoid conflict with build button
    st.session_state.pending_target = (clicked["last_clicked"]["lat"], clicked["last_clicked"]["lng"])

# ────────────────────────────────────────────────
# Simple simulation tick
# ────────────────────────────────────────────────
now = time.time()
if now - st.session_state.last_tick > 5 or st.button("Manual Tick"):
    st.session_state.last_tick = now

    # Grow resources slowly
    st.session_state.resources += 15

    # Random enemy attack
    if random.random() < ENEMY_TICK_CHANCE:
        center_lat, center_lon = 19.0760, 72.8777
        st.session_state.incoming.append({
            'lat_from': center_lat + random.uniform(-2,2),
            'lon_from': center_lon + random.uniform(-2,2),
            'target_lat': center_lat + random.uniform(-0.4,0.4),
            'target_lon': center_lon + random.uniform(-0.4,0.4),
            'launched_at': now,
            'speed_km_s': 3000 / 3600,
        })
        add_log("Enemy launched missile!")

    # Update flying jets (simple move toward target if set)
    for jet in st.session_state.jets:
        if jet['status'] == 'flying' and jet['target_lat'] is not None:
            dist = haversine(jet['lat'], jet['lon'], jet['target_lat'], jet['target_lon'])
            move_km = (JET_SPEED_KMH / 3600) * 5   # per tick
            if dist <= move_km:
                jet['lat'] = jet['target_lat']
                jet['lon'] = jet['target_lon']
                jet['status'] = 'landed'
            else:
                # move fraction toward target
                frac = move_km / dist
                jet['lat'] += frac * (jet['target_lat'] - jet['lat'])
                jet['lon'] += frac * (jet['target_lon'] - jet['lon'])

    # Very basic incoming missile resolution
    still_incoming = []
    for inc in st.session_state.incoming:
        dist_left = haversine(inc['lat_from'], inc['lon_from'], inc['target_lat'], inc['target_lon'])
        traveled = (now - inc['launched_at']) * inc['speed_km_s']
        if traveled >= dist_left:
            add_log("Enemy missile HIT target area!")
            # Could damage nearest structure here
        else:
            # Check interception by nearby SAM
            intercepted = False
            for s in st.session_state.structures:
                if s['type'] == "SAM Site":
                    d = haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon'])
                    if d < 15 and random.random() < 0.55:  # 55% chance if close
                        add_log("SAM intercepted enemy missile!")
                        intercepted = True
                        break
            if not intercepted:
                still_incoming.append(inc)
    st.session_state.incoming = still_incoming

    st.rerun()   # refresh UI

# ────────────────────────────────────────────────
# Log
# ────────────────────────────────────────────────
with st.expander("Event Log"):
    for line in reversed(st.session_state.log):
        st.caption(line)
