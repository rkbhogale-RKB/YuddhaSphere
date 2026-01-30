import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import time
from datetime import datetime
import random
import json
import threading
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="GPS RTS Sim - Live", layout="wide")

# Auto-refresh component
st_autorefresh(interval=2000, key="maprefresh")  # Refresh every 2 seconds

# ────────────────────────────────────────────────
# Improved Constants and Config
# ────────────────────────────────────────────────
MAX_BUILD_RADIUS_KM = 50
COSTS = {
    "Missile Silo": 400, 
    "SAM Site": 600, 
    "Airfield": 800,
    "Radar Station": 300,
    "Resource Depot": 500
}
STRUCTURE_HEALTH = {
    "Missile Silo": 150,
    "SAM Site": 100,
    "Airfield": 200,
    "Radar Station": 75,
    "Resource Depot": 120
}
TICK_INTERVAL = 1.0  # Update more frequently
BASE_INCOME = 25
RESOURCE_MULTIPLIER = 1.0

# ────────────────────────────────────────────────
# Initialize Session State
# ────────────────────────────────────────────────
if 'initialized' not in st.session_state:
    defaults = {
        'player_lat': 19.0760,
        'player_lon': 72.8777,
        'structures': [],
        'jets': [],
        'incoming_missiles': [],
        'enemy_aircraft': [],
        'resources': 2000,
        'last_tick': time.time(),
        'log': [],
        'build_mode': None,
        'build_preview': None,
        'selected_structure': None,
        'score': 0,
        'wave': 1,
        'resource_nodes': [],
        'last_wave_spawn': time.time(),
        'enemy_missiles_intercepted': 0,
        'structures_destroyed': 0,
        'game_speed': 1.0,
        'paused': False,
        'last_update': time.time(),
        'game_time': 0,
        'map_center': [19.0760, 72.8777],
        'map_zoom': 10,
        'initialized': True,
    }
    
    for key, value in defaults.items():
        st.session_state[key] = value
    
    # Generate initial resource nodes
    st.session_state.resource_nodes = []
    for i in range(5):
        angle = random.uniform(0, 2 * np.pi)
        distance = random.uniform(10, 40)
        lat = st.session_state.player_lat + (distance / 111) * np.cos(angle)
        lon = st.session_state.player_lon + (distance / (111 * np.cos(np.radians(st.session_state.player_lat)))) * np.sin(angle)
        st.session_state.resource_nodes.append({
            'lat': lat,
            'lon': lon,
            'resources': random.randint(200, 500),
            'id': i
        })

def add_log(msg, type="info"):
    colors = {
        "info": "📘",
        "warning": "⚠️",
        "danger": "🚨",
        "success": "✅",
        "resource": "💰"
    }
    icon = colors.get(type, "📝")
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.log.append(f"{icon} [{ts}] {msg}")
    if len(st.session_state.log) > 50:
        st.session_state.log.pop(0)

# ────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km"""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

# ────────────────────────────────────────────────
# Game Simulation Thread (Runs in Background)
# ────────────────────────────────────────────────
def game_tick():
    """Perform one game tick - updates positions, combat, etc."""
    if st.session_state.paused:
        return
    
    now = time.time()
    time_delta = min(now - st.session_state.last_update, 0.1) * st.session_state.game_speed
    st.session_state.last_update = now
    st.session_state.game_time += time_delta
    
    # Generate income
    income_multiplier = 1.0
    income_multiplier += len([s for s in st.session_state.structures if s['type'] == "Resource Depot"]) * 0.25
    st.session_state.resources += BASE_INCOME * income_multiplier * time_delta / 3.0
    
    # Spawn enemy waves
    if now - st.session_state.last_wave_spawn > 30:  # Every 30 seconds
        st.session_state.wave += 1
        st.session_state.last_wave_spawn = now
        
        # Spawn enemy missiles
        for _ in range(min(st.session_state.wave, 5)):
            offset = random.uniform(-1.5, 1.5)
            target_offset = random.uniform(-0.3, 0.3)
            st.session_state.incoming_missiles.append({
                'start_lat': st.session_state.player_lat + offset * 3,
                'start_lon': st.session_state.player_lon + offset * 3,
                'target_lat': st.session_state.player_lat + target_offset,
                'target_lon': st.session_state.player_lon + target_offset,
                'launched_at': now,
                'progress': 0.0,
                'speed': 0.05 + (st.session_state.wave * 0.005),
                'damage': 20 + (st.session_state.wave * 5),
                'id': len(st.session_state.incoming_missiles)
            })
        
        # Spawn enemy bombers at higher waves
        if st.session_state.wave >= 3:
            for _ in range(min(st.session_state.wave - 2, 3)):
                st.session_state.enemy_aircraft.append({
                    'lat': st.session_state.player_lat + random.uniform(-2, 2),
                    'lon': st.session_state.player_lon + random.uniform(-2, 2),
                    'target_type': random.choice(['Missile Silo', 'Airfield', 'Resource Depot']),
                    'health': 100,
                    'id': len(st.session_state.enemy_aircraft) + 1,
                    'speed_lat': random.uniform(-0.01, 0.01),
                    'speed_lon': random.uniform(-0.01, 0.01)
                })
        
        add_log(f"Wave {st.session_state.wave} incoming!", "danger")
    
    # Update missiles
    missiles_to_remove = []
    for inc in st.session_state.incoming_missiles[:]:
        inc['progress'] += inc['speed'] * time_delta
        
        # Check for SAM interception
        intercepted = False
        for s in st.session_state.structures:
            if s['type'] == "SAM Site":
                # Calculate current missile position
                cur_lat = inc['start_lat'] + inc['progress'] * (inc['target_lat'] - inc['start_lat'])
                cur_lon = inc['start_lon'] + inc['progress'] * (inc['target_lon'] - inc['start_lon'])
                dist = haversine(s['lat'], s['lon'], cur_lat, cur_lon)
                if dist < 20:  # 20km interception range
                    intercept_chance = 0.6 * time_delta
                    if random.random() < intercept_chance:
                        intercepted = True
                        missiles_to_remove.append(inc)
                        s['intercepts'] = s.get('intercepts', 0) + 1
                        st.session_state.enemy_missiles_intercepted += 1
                        st.session_state.score += 25
                        add_log(f"SAM Site intercepted enemy missile!", "success")
                        break
        
        # Check for impact
        if inc['progress'] >= 1.0 and inc not in missiles_to_remove:
            missiles_to_remove.append(inc)
            add_log("💥 Enemy missile impact!", "danger")
            
            # Damage nearby structures
            for s in st.session_state.structures:
                dist = haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon'])
                if dist < 8:  # 8km blast radius
                    damage = int(inc['damage'] * (1 - dist/8))
                    s['health'] = max(0, s['health'] - damage)
                    if s['health'] == 0:
                        st.session_state.structures_destroyed += 1
                        add_log(f"{s['type']} #{s['id']} destroyed!", "danger")
                        if st.session_state.selected_structure and s['id'] == st.session_state.selected_structure['id']:
                            st.session_state.selected_structure = None
    
    # Remove hit/missed missiles
    for inc in missiles_to_remove:
        if inc in st.session_state.incoming_missiles:
            st.session_state.incoming_missiles.remove(inc)
    
    # Update enemy aircraft movement
    for enemy in st.session_state.enemy_aircraft[:]:
        # Find target
        target_structures = [s for s in st.session_state.structures if s['type'] == enemy['target_type']]
        if target_structures:
            target = min(target_structures, 
                        key=lambda s: haversine(enemy['lat'], enemy['lon'], s['lat'], s['lon']))
            
            # Move toward target
            lat_diff = target['lat'] - enemy['lat']
            lon_diff = target['lon'] - enemy['lon']
            distance = max(0.001, haversine(enemy['lat'], enemy['lon'], target['lat'], target['lon']))
            
            enemy['lat'] += (lat_diff / distance) * 0.02 * time_delta
            enemy['lon'] += (lon_diff / distance) * 0.02 * time_delta
            
            # Attack if close enough
            if distance < 0.5:
                target['health'] = max(0, target['health'] - 30 * time_delta)
                if random.random() < 0.1:
                    add_log(f"Enemy bomber attacking {target['type']} #{target['id']}!", "warning")
                if target['health'] == 0:
                    st.session_state.structures_destroyed += 1
    
    # Update jets movement
    for jet in st.session_state.jets[:]:
        if jet['status'] == 'patrolling':
            # Move in a patrol pattern
            jet['lat'] += random.uniform(-0.01, 0.01) * time_delta
            jet['lon'] += random.uniform(-0.01, 0.01) * time_delta
            jet['fuel'] -= 0.5 * time_delta
            
            # Auto-engage enemies in range
            for enemy in st.session_state.enemy_aircraft[:]:
                if haversine(jet['lat'], jet['lon'], enemy['lat'], enemy['lon']) < 5:
                    if jet['missiles_left'] > 0 and random.random() < 0.3 * time_delta:
                        jet['missiles_left'] -= 1
                        st.session_state.enemy_aircraft.remove(enemy)
                        st.session_state.score += 100
                        add_log(f"Jet #{jet['id']} shot down enemy bomber!", "success")
                        break
            
            if jet['fuel'] <= 0:
                st.session_state.jets.remove(jet)
                add_log(f"Jet #{jet['id']} ran out of fuel", "warning")
    
    # Remove destroyed structures
    st.session_state.structures = [s for s in st.session_state.structures if s['health'] > 0]

# ────────────────────────────────────────────────
# Sidebar - Enhanced
# ────────────────────────────────────────────────
st.sidebar.title("🚀 GPS RTS - Live Command")

# Game Controls
st.sidebar.markdown("### 🎮 Game Controls")
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("⏸️ Pause" if not st.session_state.paused else "▶️ Resume"):
        st.session_state.paused = not st.session_state.paused
        st.rerun()
with col2:
    if st.button("🔄 Reset"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

st.session_state.game_speed = st.sidebar.slider("Game Speed", 0.1, 3.0, st.session_state.game_speed, 0.1)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Stats")

# Real-time metrics that update without rerun
metrics_placeholder = st.sidebar.empty()
log_placeholder = st.sidebar.empty()

st.sidebar.markdown("---")
st.sidebar.markdown("### 🏗️ Build Structures")

# Build buttons
structures = {
    "🎯 Missile Silo": {"cost": 400, "desc": "Launch defensive missiles"},
    "🛡️ SAM Site": {"cost": 600, "desc": "Anti-air defense (60% intercept)"},
    "✈️ Airfield": {"cost": 800, "desc": "Deploy fighter jets"},
    "📡 Radar Station": {"cost": 300, "desc": "+30% detection range"},
    "🏭 Resource Depot": {"cost": 500, "desc": "+25% income boost"}
}

for name, info in structures.items():
    colA, colB = st.sidebar.columns([3, 1])
    with colA:
        if st.button(f"{name}", key=f"build_{name}", use_container_width=True):
            build_type = name.split(" ")[1] + " " + name.split(" ")[2]
            st.session_state.build_mode = build_type if st.session_state.build_mode != build_type else None
            st.session_state.build_preview = None
            st.rerun()
    with colB:
        st.caption(f"${info['cost']}")

# ────────────────────────────────────────────────
# Main Layout - Using Columns for Better Organization
# ────────────────────────────────────────────────
col_left, col_right = st.columns([3, 1])

with col_left:
    # Update metrics in sidebar through the placeholder
    with metrics_placeholder.container():
        st.metric("💰 Resources", f"${int(st.session_state.resources):,}")
        st.metric("🏆 Score", f"{st.session_state.score}")
        st.metric("🌊 Wave", f"{st.session_state.wave}")
        st.metric("⏱️ Game Time", f"{int(st.session_state.game_time)}s")
    
    # Create map with current state
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles="cartodbpositron"
    )
    
    # Player base
    folium.Marker(
        [st.session_state.player_lat, st.session_state.player_lon],
        popup="🏠 Command Center",
        tooltip="Your HQ",
        icon=folium.Icon(color="darkblue", icon="flag", prefix="fa")
    ).add_to(m)
    
    # Build radius
    folium.Circle(
        radius=MAX_BUILD_RADIUS_KM * 1000,
        location=[st.session_state.player_lat, st.session_state.player_lon],
        color="green", fill=True, fill_opacity=0.08,
        popup=f"Construction Zone ({MAX_BUILD_RADIUS_KM}km radius)"
    ).add_to(m)
    
    # Resource nodes
    for node in st.session_state.resource_nodes:
        folium.CircleMarker(
            location=[node['lat'], node['lon']],
            radius=8,
            color="gold", fill=True, fill_color="yellow",
            fill_opacity=0.6,
            popup=f"💰 Resource Node\nResources: {node['resources']}"
        ).add_to(m)
    
    # Structures
    for s in st.session_state.structures:
        health_pct = s['health'] / STRUCTURE_HEALTH[s['type']]
        color = "green" if health_pct > 0.6 else "orange" if health_pct > 0.3 else "red"
        
        icons = {
            "Missile Silo": "crosshairs",
            "SAM Site": "shield-alt",
            "Airfield": "plane",
            "Radar Station": "satellite-dish",
            "Resource Depot": "industry"
        }
        
        folium.Marker(
            [s['lat'], s['lon']],
            popup=f"""
            <b>{s['type']} #{s['id']}</b><br>
            Health: {int(s['health'])}/{STRUCTURE_HEALTH[s['type']]}<br>
            {f"Missiles: {s.get('missiles', 0)}" if s['type'] == "Missile Silo" else ""}
            {f"Intercepts: {s.get('intercepts', 0)}" if s['type'] == "SAM Site" else ""}
            """,
            icon=folium.Icon(color=color, icon=icons[s['type']], prefix="fa")
        ).add_to(m)
    
    # Incoming missiles with smooth interpolation
    for inc in st.session_state.incoming_missiles:
        progress = min(1.0, inc['progress'])
        cur_lat = inc['start_lat'] + progress * (inc['target_lat'] - inc['start_lat'])
        cur_lon = inc['start_lon'] + progress * (inc['target_lon'] - inc['start_lon'])
        
        folium.CircleMarker(
            [cur_lat, cur_lon],
            radius=10,
            color="red", 
            fill=True, 
            fill_color="darkred",
            fill_opacity=0.8,
            popup=f"🚀 Enemy Missile\nProgress: {progress*100:.0f}%"
        ).add_to(m)
        
        # Draw missile trail
        folium.PolyLine(
            locations=[[inc['start_lat'], inc['start_lon']], [cur_lat, cur_lon]],
            color="red",
            weight=2,
            opacity=0.5
        ).add_to(m)
    
    # Enemy aircraft
    for enemy in st.session_state.enemy_aircraft:
        folium.Marker(
            [enemy['lat'], enemy['lon']],
            popup=f"Enemy Bomber\nTarget: {enemy['target_type']}",
            icon=folium.Icon(color="black", icon="plane", prefix="fa")
        ).add_to(m)
    
    # Jets
    for jet in st.session_state.jets:
        if jet['status'] == 'patrolling':
            folium.Marker(
                [jet['lat'], jet['lon']],
                popup=f"Fighter Jet #{jet['id']}\nMissiles: {jet['missiles_left']}\nFuel: {int(jet['fuel'])}%",
                icon=folium.Icon(color="orange", icon="fighter-jet", prefix="fa")
            ).add_to(m)
    
    # Build preview
    if st.session_state.build_preview:
        preview = st.session_state.build_preview
        folium.Marker(
            [preview['lat'], preview['lon']],
            popup="👆 Click CONFIRM to build",
            icon=folium.Icon(color="purple", icon="plus-circle", prefix="fa")
        ).add_to(m)
    
    # Render the map
    map_data = st_folium(
        m, 
        width=900, 
        height=600, 
        key="main_map",
        returned_objects=["last_clicked", "bounds", "zoom", "center"]
    )
    
    # Handle map interactions
    if map_data:
        if map_data.get("last_clicked"):
            clat = map_data["last_clicked"]["lat"]
            clon = map_data["last_clicked"]["lng"]
            
            # Build preview
            if st.session_state.build_mode:
                st.session_state.build_preview = {
                    'type': st.session_state.build_mode,
                    'lat': clat,
                    'lon': clon
                }
                st.rerun()
        
        # Update map view state
        if map_data.get("center"):
            st.session_state.map_center = [map_data["center"]["lat"], map_data["center"]["lng"]]
        if map_data.get("zoom"):
            st.session_state.map_zoom = map_data["zoom"]

with col_right:
    # Build confirmation panel
    if st.session_state.build_preview:
        preview = st.session_state.build_preview
        with st.container(border=True):
            st.subheader("Build Confirmation")
            st.write(f"Type: {preview['type']}")
            st.write(f"Location: {preview['lat']:.4f}, {preview['lon']:.4f}")
            st.write(f"Cost: ${COSTS[preview['type']]}")
            
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button("✅ Build", type="primary", use_container_width=True):
                    cost = COSTS[preview['type']]
                    if st.session_state.resources >= cost:
                        st.session_state.resources -= cost
                        sid = len(st.session_state.structures) + 1
                        new_struct = {
                            'id': sid,
                            'type': preview['type'],
                            'lat': preview['lat'],
                            'lon': preview['lon'],
                            'health': STRUCTURE_HEALTH[preview['type']],
                            'created_at': time.time()
                        }
                        if preview['type'] == "Missile Silo":
                            new_struct['missiles'] = 8
                        elif preview['type'] == "SAM Site":
                            new_struct['intercepts'] = 0
                        
                        st.session_state.structures.append(new_struct)
                        add_log(f"Built {preview['type']} #{sid}", "success")
                        st.session_state.build_mode = None
                        st.session_state.build_preview = None
                        st.rerun()
                    else:
                        st.error("Insufficient funds!")
            with col_cancel:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.build_preview = None
                    st.rerun()
    
    # Structure management panel
    if st.session_state.selected_structure:
        s = st.session_state.selected_structure
        with st.container(border=True):
            st.subheader(f"{s['type']} #{s['id']}")
            
            # Health bar
            health_pct = s['health'] / STRUCTURE_HEALTH[s['type']]
            st.progress(health_pct, text=f"Health: {int(s['health'])}/{STRUCTURE_HEALTH[s['type']]}")
            
            if s['type'] == "Missile Silo":
                st.metric("Missiles", s.get('missiles', 0))
                if st.button("Launch Missile", type="primary"):
                    if s.get('missiles', 0) > 0:
                        s['missiles'] -= 1
                        add_log(f"Missile launched from Silo #{s['id']}", "warning")
                        st.rerun()
            
            elif s['type'] == "Airfield":
                active_jets = len([j for j in st.session_state.jets if j.get('home_airfield') == s['id']])
                st.metric("Active Jets", active_jets)
                if st.button("Deploy Jet ($200)", type="secondary"):
                    if st.session_state.resources >= 200:
                        st.session_state.resources -= 200
                        st.session_state.jets.append({
                            'id': len(st.session_state.jets) + 1,
                            'lat': s['lat'],
                            'lon': s['lon'],
                            'missiles_left': 6,
                            'status': 'patrolling',
                            'home_airfield': s['id'],
                            'fuel': 100
                        })
                        add_log(f"Jet deployed from Airfield #{s['id']}", "success")
                        st.rerun()
            
            elif s['type'] == "SAM Site":
                st.metric("Intercepts", s.get('intercepts', 0))
                st.caption("Auto-defends against missiles")
            
            # Repair button
            if s['health'] < STRUCTURE_HEALTH[s['type']]:
                repair_cost = int((STRUCTURE_HEALTH[s['type']] - s['health']) * 2)
                if st.button(f"Repair (${repair_cost})", type="secondary"):
                    if st.session_state.resources >= repair_cost:
                        st.session_state.resources -= repair_cost
                        s['health'] = STRUCTURE_HEALTH[s['type']]
                        add_log(f"Repaired {s['type']} #{s['id']}", "success")
                        st.rerun()
            
            if st.button("Demolish (50% refund)", type="primary"):
                refund = int(COSTS[s['type']] * 0.5)
                st.session_state.resources += refund
                st.session_state.structures.remove(s)
                add_log(f"Demolished {s['type']} #{s['id']}", "warning")
                st.session_state.selected_structure = None
                st.rerun()
            
            if st.button("Close Panel"):
                st.session_state.selected_structure = None
                st.rerun()
    
    # Event log
    st.subheader("📋 Event Log")
    log_container = st.container(height=300, border=True)
    with log_container:
        for line in reversed(st.session_state.log[-15:]):
            st.markdown(line)

# ────────────────────────────────────────────────
# Run Game Tick (Only if not paused)
# ────────────────────────────────────────────────
if not st.session_state.paused:
    game_tick()

# ────────────────────────────────────────────────
# Status Display at Bottom
# ────────────────────────────────────────────────
st.divider()
col_status1, col_status2, col_status3, col_status4 = st.columns(4)
with col_status1:
    st.metric("Active Threats", 
              f"{len(st.session_state.incoming_missiles) + len(st.session_state.enemy_aircraft)}",
              help="Missiles + Enemy Aircraft")
with col_status2:
    st.metric("Defense Systems", 
              f"{len([s for s in st.session_state.structures if s['type'] in ['SAM Site', 'Missile Silo']])}",
              help="SAM Sites + Missile Silos")
with col_status3:
    st.metric("Resource Flow", 
              f"${int(BASE_INCOME * (1 + len([s for s in st.session_state.structures if s['type'] == 'Resource Depot']) * 0.25) / 3):,}/s",
              help="Income per second")
with col_status4:
    next_wave = max(0, 30 - (time.time() - st.session_state.last_wave_spawn))
    st.metric("Next Wave", 
              f"{int(next_wave)}s",
              help="Time until next enemy wave")

st.caption("GPS RTS Live • Real-time Strategy • v4.0 • Updates every 2 seconds")
