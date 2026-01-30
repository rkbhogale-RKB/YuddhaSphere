import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import time
from datetime import datetime
import random

st.set_page_config(page_title="GPS RTS Sim - Enhanced", layout="wide")

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
TICK_INTERVAL = 3  # seconds
BASE_INCOME = 25
RESOURCE_MULTIPLIER = 1.0

# ────────────────────────────────────────────────
# Initialize Session State
# ────────────────────────────────────────────────
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
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

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

def generate_resource_nodes(base_lat, base_lon):
    """Generate random resource nodes around base"""
    nodes = []
    for _ in range(5):
        angle = random.uniform(0, 2 * np.pi)
        distance = random.uniform(10, 40)
        lat = base_lat + (distance / 111) * np.cos(angle)
        lon = base_lon + (distance / (111 * np.cos(np.radians(base_lat)))) * np.sin(angle)
        nodes.append({
            'lat': lat,
            'lon': lon,
            'resources': random.randint(200, 500),
            'id': len(nodes)
        })
    return nodes

# Initialize resource nodes if empty
if not st.session_state.resource_nodes:
    st.session_state.resource_nodes = generate_resource_nodes(
        st.session_state.player_lat, st.session_state.player_lon
    )

# ────────────────────────────────────────────────
# Sidebar - Enhanced
# ────────────────────────────────────────────────
st.sidebar.title("🚀 GPS RTS - Command Center")
st.sidebar.markdown("---")

# Player stats
col1, col2 = st.sidebar.columns(2)
with col1:
    st.metric("💰 Resources", f"${st.session_state.resources:,}")
with col2:
    st.metric("🏆 Score", st.session_state.score)

st.sidebar.markdown(f"**Wave:** {st.session_state.wave}")
st.sidebar.progress(min(st.session_state.wave * 0.1, 1.0), 
                    text=f"Difficulty: {min(st.session_state.wave * 10, 100)}%")

st.sidebar.markdown("---")
st.sidebar.subheader("Build Structures")

# Build buttons with icons and descriptions
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
        if st.button(f"{name} (${info['cost']})", key=f"build_{name}", use_container_width=True):
            build_type = name.split(" ")[1] + " " + name.split(" ")[2]
            st.session_state.build_mode = build_type if st.session_state.build_mode != build_type else None
            st.session_state.build_preview = None
            st.rerun()
    with colB:
        st.caption(f"{info['desc']}")

st.sidebar.markdown("---")

# Game Controls
st.sidebar.subheader("Game Controls")
col3, col4 = st.sidebar.columns(2)
with col3:
    auto_tick = st.checkbox("Auto-tick", value=True, help="Automatically progress game")
with col4:
    if st.button("⏱️ Manual Tick", use_container_width=True):
        st.rerun()

if st.sidebar.button("🔄 Reset Game", type="secondary"):
    for key in defaults:
        st.session_state[key] = defaults[key]
    st.session_state.resource_nodes = generate_resource_nodes(
        st.session_state.player_lat, st.session_state.player_lon
    )
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Stats")
st.sidebar.markdown(f"""
- 🛡️ Intercepted: {st.session_state.enemy_missiles_intercepted}
- 💥 Destroyed: {st.session_state.structures_destroyed}
- ✈️ Active Jets: {len([j for j in st.session_state.jets if j['status'] == 'flying'])}
- 🏗️ Structures: {len(st.session_state.structures)}
""")

# ────────────────────────────────────────────────
# Map - Enhanced with better visuals
# ────────────────────────────────────────────────
m = folium.Map(location=[st.session_state.player_lat, st.session_state.player_lon],
               zoom_start=10, tiles="cartodbpositron", control_scale=True)

# Player base with custom icon
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
        popup=f"💰 Resource Node\nResources: {node['resources']}\nDistance: {haversine(st.session_state.player_lat, st.session_state.player_lon, node['lat'], node['lon']):.1f}km"
    ).add_to(m)

# Structures with health-based colors
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
        Health: {s['health']}/{STRUCTURE_HEALTH[s['type']]}<br>
        {f"Missiles: {s.get('missiles', 0)}" if s['type'] == "Missile Silo" else ""}
        {f"Intercepts: {s.get('intercepts', 0)}" if s['type'] == "SAM Site" else ""}
        {f"Bonus: +25% income" if s['type'] == "Resource Depot" else ""}
        <hr><small>Click to manage</small>
        """,
        icon=folium.Icon(color=color, icon=icons[s['type']], prefix="fa")
    ).add_to(m)
    
    # Add range circles for defensive structures
    if s['type'] in ["SAM Site", "Radar Station"]:
        folium.Circle(
            location=[s['lat'], s['lon']],
            radius=15000 if s['type'] == "Radar Station" else 18000,
            color="blue" if s['type'] == "SAM Site" else "gray",
            fill=True,
            fill_opacity=0.05,
            popup=f"{s['type']} Coverage"
        ).add_to(m)

# Build preview
if st.session_state.build_preview:
    preview = st.session_state.build_preview
    dist = haversine(st.session_state.player_lat, st.session_state.player_lon,
                     preview['lat'], preview['lon'])
    if dist <= MAX_BUILD_RADIUS_KM:
        color = {"Missile Silo":"red", "SAM Site":"blue", "Airfield":"green",
                "Radar Station":"purple", "Resource Depot":"orange"}[preview['type']]
        folium.Marker(
            [preview['lat'], preview['lon']],
            popup=f"👆 Click CONFIRM to build {preview['type']}",
            icon=folium.Icon(color=color, icon="plus-circle", prefix="fa")
        ).add_to(m)

# Jets
for j in st.session_state.jets:
    if j['status'] in ['flying', 'patrolling']:
        folium.Marker(
            [j['lat'], j['lon']],
            popup=f"Fighter Jet #{j['id']}\nMissiles: {j['missiles_left']}\nStatus: {j['status'].title()}",
            icon=folium.Icon(color="orange", icon="fighter-jet", prefix="fa")
        ).add_to(m)

# Incoming threats
for inc in st.session_state.incoming_missiles:
    progress = min(1.0, inc['progress'])
    cur_lat = inc['start_lat'] + progress * (inc['target_lat'] - inc['start_lat'])
    cur_lon = inc['start_lon'] + progress * (inc['target_lon'] - inc['start_lon'])
    
    folium.CircleMarker(
        [cur_lat, cur_lon],
        radius=12,
        color="red", 
        fill=True, 
        fill_color="darkred",
        fill_opacity=0.8,
        popup=f"🚀 Enemy Missile\nETA: {(1-progress)/inc['speed']:.1f} ticks"
    ).add_to(m)

# Enemy aircraft
for enemy in st.session_state.enemy_aircraft:
    folium.Marker(
        [enemy['lat'], enemy['lon']],
        popup=f"Enemy Bomber\nTargeting: {enemy['target_type']}",
        icon=folium.Icon(color="black", icon="plane", prefix="fa")
    ).add_to(m)

# Render map
map_data = st_folium(m, width=1200, height=700, key="main_map")

# ────────────────────────────────────────────────
# Map Interaction
# ────────────────────────────────────────────────
if map_data and map_data.get("last_clicked"):
    clat = map_data["last_clicked"]["lat"]
    clon = map_data["last_clicked"]["lng"]
    dist_from_player = haversine(st.session_state.player_lat, st.session_state.player_lon, clat, clon)
    
    # Build preview
    if st.session_state.build_mode and dist_from_player <= MAX_BUILD_RADIUS_KM:
        # Check if too close to existing structures
        too_close = any(haversine(s['lat'], s['lon'], clat, clon) < 2 for s in st.session_state.structures)
        if not too_close:
            st.session_state.build_preview = {
                'type': st.session_state.build_mode,
                'lat': clat,
                'lon': clon
            }
            st.rerun()
        else:
            add_log("Too close to existing structure!", "warning")
    
    # Select structure
    for s in st.session_state.structures:
        if haversine(s['lat'], s['lon'], clat, clon) < 1.0:  # 1km click radius
            st.session_state.selected_structure = s
            st.rerun()
            break
    
    # Collect resources
    for node in st.session_state.resource_nodes:
        if haversine(node['lat'], node['lon'], clat, clon) < 1.0:
            if node['resources'] > 0:
                amount = min(node['resources'], 100)
                st.session_state.resources += amount
                node['resources'] -= amount
                add_log(f"Collected ${amount} from resource node", "resource")
                if node['resources'] <= 0:
                    st.session_state.resource_nodes.remove(node)
                st.rerun()
            break

# ────────────────────────────────────────────────
# Build Confirmation Bar
# ────────────────────────────────────────────────
if st.session_state.build_preview:
    preview = st.session_state.build_preview
    dist = haversine(st.session_state.player_lat, st.session_state.player_lon,
                     preview['lat'], preview['lon'])
    
    with st.container(border=True):
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.success(f"📍 **Build Preview:** {preview['type']} at {preview['lat']:.4f}, {preview['lon']:.4f}")
            st.caption(f"Distance from HQ: {dist:.1f}km | Cost: ${COSTS[preview['type']]}")
        
        with col2:
            if st.button("✅ Confirm Build", type="primary", use_container_width=True):
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
                    
                    # Add type-specific attributes
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
                    st.session_state.build_preview = None
                    st.rerun()
        
        with col3:
            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.build_preview = None
                st.rerun()

# ────────────────────────────────────────────────
# Structure Management Panel
# ────────────────────────────────────────────────
if st.session_state.selected_structure:
    s = st.session_state.selected_structure
    with st.expander(f"⚙️ Managing {s['type']} #{s['id']}", expanded=True):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Health bar
            health_pct = s['health'] / STRUCTURE_HEALTH[s['type']]
            st.progress(health_pct, text=f"Health: {s['health']}/{STRUCTURE_HEALTH[s['type']]}")
            
            # Structure-specific actions
            if s['type'] == "Missile Silo":
                st.metric("🚀 Missiles", s.get('missiles', 0))
                if s.get('missiles', 0) > 0:
                    if st.button("Launch Missile at Target", type="primary"):
                        # Find enemy target
                        enemies = st.session_state.enemy_aircraft + [
                            m for m in st.session_state.incoming_missiles 
                            if haversine(s['lat'], s['lon'], m['target_lat'], m['target_lon']) < 50
                        ]
                        if enemies:
                            s['missiles'] -= 1
                            target = random.choice(enemies)
                            add_log(f"Missile launched at enemy target", "warning")
                            # Simulate hit
                            if random.random() < 0.8:
                                if 'target_type' in target:
                                    st.session_state.enemy_aircraft.remove(target)
                                else:
                                    st.session_state.incoming_missiles.remove(target)
                                st.session_state.score += 50
                                add_log("Target destroyed!", "success")
                        else:
                            add_log("No targets in range", "warning")
                        st.rerun()
            
            elif s['type'] == "Airfield":
                active_jets = [j for j in st.session_state.jets if j.get('home_airfield') == s['id']]
                st.metric("✈️ Jets", len(active_jets))
                if len(active_jets) < 3:  # Max 3 jets per airfield
                    if st.button("Deploy Fighter Jet ($200)", type="secondary"):
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
                        else:
                            st.error("Need $200 for jet deployment")
            
            elif s['type'] == "SAM Site":
                st.metric("🛡️ Intercepts", s.get('intercepts', 0))
                st.caption("Auto-defends against missiles in range")
            
            elif s['type'] == "Resource Depot":
                st.success("+25% income boost active")
                st.caption("Passively increases resource generation")
        
        with col2:
            # Repair option
            repair_cost = (STRUCTURE_HEALTH[s['type']] - s['health']) * 2
            if s['health'] < STRUCTURE_HEALTH[s['type']]:
                if st.button(f"Repair (${repair_cost})", type="secondary"):
                    if st.session_state.resources >= repair_cost:
                        st.session_state.resources -= repair_cost
                        s['health'] = STRUCTURE_HEALTH[s['type']]
                        add_log(f"Repaired {s['type']} #{s['id']}", "success")
                        st.rerun()
                    else:
                        st.error("Insufficient funds for repair")
            
            # Sell structure
            if st.button("💣 Demolish", type="primary"):
                refund = COSTS[s['type']] * 0.5
                st.session_state.resources += int(refund)
                st.session_state.structures.remove(s)
                add_log(f"Demolished {s['type']} #{s['id']} (Refund: ${int(refund)})", "warning")
                st.session_state.selected_structure = None
                st.rerun()
        
        st.divider()
        if st.button("Close Panel"):
            st.session_state.selected_structure = None
            st.rerun()

# ────────────────────────────────────────────────
# Enhanced Simulation Tick
# ────────────────────────────────────────────────
def tick_simulation():
    now = time.time()
    st.session_state.last_tick = now
    
    # Calculate income with bonuses
    income_multiplier = 1.0
    income_multiplier += len([s for s in st.session_state.structures if s['type'] == "Resource Depot"]) * 0.25
    base_income = int(BASE_INCOME * income_multiplier)
    st.session_state.resources += base_income
    
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
                'damage': 20 + (st.session_state.wave * 5)
            })
        
        # Spawn enemy bombers at higher waves
        if st.session_state.wave >= 3:
            for _ in range(min(st.session_state.wave - 2, 3)):
                st.session_state.enemy_aircraft.append({
                    'lat': st.session_state.player_lat + random.uniform(-2, 2),
                    'lon': st.session_state.player_lon + random.uniform(-2, 2),
                    'target_type': random.choice(['Missile Silo', 'Airfield', 'Resource Depot']),
                    'health': 100,
                    'id': len(st.session_state.enemy_aircraft) + 1
                })
        
        add_log(f"Wave {st.session_state.wave} incoming!", "danger")
    
    # Update missiles
    missiles_to_remove = []
    for inc in st.session_state.incoming_missiles:
        inc['progress'] += inc['speed']
        
        # Check for SAM interception
        intercepted = False
        for s in st.session_state.structures:
            if s['type'] == "SAM Site":
                dist = haversine(s['lat'], s['lon'], inc['target_lat'], inc['target_lon'])
                if dist < 20:  # 20km interception range
                    intercept_chance = 0.6
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
                        if s == st.session_state.selected_structure:
                            st.session_state.selected_structure = None
    
    # Remove hit/missed missiles
    for inc in missiles_to_remove:
        if inc in st.session_state.incoming_missiles:
            st.session_state.incoming_missiles.remove(inc)
    
    # Update enemy aircraft
    for enemy in st.session_state.enemy_aircraft[:]:
        # Move toward target
        target_structures = [s for s in st.session_state.structures if s['type'] == enemy['target_type']]
        if target_structures:
            target = random.choice(target_structures)
            # Move toward target
            if haversine(enemy['lat'], enemy['lon'], target['lat'], target['lon']) > 1:
                enemy['lat'] += (target['lat'] - enemy['lat']) * 0.1
                enemy['lon'] += (target['lon'] - enemy['lon']) * 0.1
            else:
                # Attack structure
                target['health'] = max(0, target['health'] - 30)
                add_log(f"Enemy bomber attacking {target['type']} #{target['id']}!", "warning")
                if target['health'] == 0:
                    st.session_state.structures_destroyed += 1
    
    # Update jets
    for jet in st.session_state.jets[:]:
        if jet['status'] == 'patrolling':
            # Move randomly
            jet['lat'] += random.uniform(-0.05, 0.05)
            jet['lon'] += random.uniform(-0.05, 0.05)
            jet['fuel'] -= 1
            
            # Auto-engage enemies in range
            for enemy in st.session_state.enemy_aircraft:
                if haversine(jet['lat'], jet['lon'], enemy['lat'], enemy['lon']) < 5:
                    if jet['missiles_left'] > 0:
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

# Auto-tick logic
if auto_tick:
    now = time.time()
    if now - st.session_state.last_tick >= TICK_INTERVAL:
        tick_simulation()
        st.rerun()

# ────────────────────────────────────────────────
# Event Log with Filters
# ────────────────────────────────────────────────
with st.expander("📋 Event Log", expanded=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Game Events")
    with col2:
        log_filter = st.selectbox("Filter:", ["All", "Attacks", "Resources", "Buildings", "Defenses"])
    
    log_container = st.container(height=200, border=True)
    
    filtered_logs = st.session_state.log
    if log_filter == "Attacks":
        filtered_logs = [l for l in st.session_state.log if "🚨" in l or "💥" in l or "⚠️" in l]
    elif log_filter == "Resources":
        filtered_logs = [l for l in st.session_state.log if "💰" in l or "✅" in l]
    elif log_filter == "Buildings":
        filtered_logs = [l for l in st.session_state.log if "Built" in l or "demolished" in l]
    elif log_filter == "Defenses":
        filtered_logs = [l for l in st.session_state.log if "intercepted" in l or "SAM" in l]
    
    with log_container:
        for line in reversed(filtered_logs[-20:]):
            st.markdown(line)

# ────────────────────────────────────────────────
# Status Bar
# ────────────────────────────────────────────────
st.divider()
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Active Threats", 
              f"{len(st.session_state.incoming_missiles) + len(st.session_state.enemy_aircraft)}",
              delta=None)
with col2:
    st.metric("Defenses", 
              f"{len([s for s in st.session_state.structures if s['type'] in ['SAM Site', 'Missile Silo']])}",
              delta=None)
with col3:
    st.metric("Resource Nodes", 
              f"{len(st.session_state.resource_nodes)}",
              delta=None)
with col4:
    next_tick = max(0, TICK_INTERVAL - (time.time() - st.session_state.last_tick))
    st.metric("Next Tick", 
              f"{next_tick:.1f}s",
              delta=None)

st.caption("GPS RTS Enhanced • Strategy Defense Game • v3.0")
