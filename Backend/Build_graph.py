import os
import json
import pickle
import networkx as nx
import osmnx as ox

G = nx.DiGraph()

SPEED = {
    "walk": 1.4,   # m/s
    "rail": 12     # m/s (ví dụ)
}

# ================= UTIL =================
def haversine(lon1, lat1, lon2, lat2):
    from math import radians, cos, sin, asin, sqrt
    R = 6371000
    dlon = radians(lon2 - lon1)
    dlat = radians(lat2 - lat1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))


# ================= MRT GRAPH =================
def build_subway_graph(data_dir):
    print("🚧 Building MRT graph...")

    # 1. Load danh sách tuyến MRT
    with open(os.path.join(data_dir, 'lines_clean.json'), encoding='utf-8') as f:
        lines = json.load(f)
        lines = lines if isinstance(lines, list) else list(lines.values())[0]

    valid_lines = {
        str(l.get('LINE_ID') or l.get('ID')).strip()
        for l in lines
        if str(l.get('TYPEE') or l.get('TYPE')).upper() == 'MRT'
    }

    # 2. Load sequence trạm
    with open(os.path.join(data_dir, 'station_line_clean.json'), encoding='utf-8') as f:
        seq = json.load(f)
        seq = seq if isinstance(seq, list) else list(seq.values())[0]

    mrt_seq = {}
    valid_stations = set()

    for item in seq:
        lid = str(item.get('LINE_ID') or item.get('LINE')).strip()
        if lid in valid_lines:
            sid = str(item.get('STATION_ID') or item.get('STATION')).strip()
            valid_stations.add(sid)
            mrt_seq.setdefault(lid, []).append(item)

    # 3. Load thông tin trạm
    with open(os.path.join(data_dir, 'stops_raw.json'), encoding='utf-8') as f:
        stops = json.load(f)
        stops = stops if isinstance(stops, list) else list(stops.values())[0]

    for s in stops:
        sid = str(s.get('stop_id') or s.get('ID')).strip()
        if sid in valid_stations:
            G.add_node(
                f"rail_{sid}",
                stop_lat=float(s.get('stop_lat') or s.get('LAT')),
                stop_lon=float(s.get('stop_lon') or s.get('LON')),
                name=s.get('stop_name') or s.get('NAME'),
                mode="rail"
            )

    # 4. Add edges (2 chiều)
    for lid, stations in mrt_seq.items():
        stations.sort(key=lambda x: int(x.get('STOP_SEQUENCE') or 0))

        for i in range(len(stations) - 1):
            u = f"rail_{stations[i].get('STATION_ID')}"
            v = f"rail_{stations[i+1].get('STATION_ID')}"

            if not (G.has_node(u) and G.has_node(v)):
                continue

            n1, n2 = G.nodes[u], G.nodes[v]
            dist = haversine(n1['stop_lon'], n1['stop_lat'],
                             n2['stop_lon'], n2['stop_lat'])

            time = dist / SPEED["rail"] + 30  # +30s wait

            # 2 chiều
            G.add_edge(u, v, length=dist, travel_time=time, mode="rail", line=lid)
            G.add_edge(v, u, length=dist, travel_time=time, mode="rail", line=lid)


# ================= WALK GRAPH =================
def build_walk_graph():
    print("🚧 Download WALK graph from OSM...")

    G_walk = ox.graph_from_place("Bangkok, Thailand", network_type="walk")

    # convert → loại multi-edge + đảm bảo đơn giản
    G_walk = nx.Graph(G_walk)

    # add node
    for node, data in G_walk.nodes(data=True):
        G.add_node(
            f"walk_{node}",
            stop_lat=data['y'],
            stop_lon=data['x'],
            mode="walk"
        )

    # add edge (2 chiều)
    for u, v, data in G_walk.edges(data=True):
        dist = data.get("length", 1)
        time = dist / SPEED["walk"]

        G.add_edge(f"walk_{u}", f"walk_{v}", length=dist, travel_time=time, mode="walk")
        G.add_edge(f"walk_{v}", f"walk_{u}", length=dist, travel_time=time, mode="walk")


# ================= TRANSFER =================
def connect_transfer(radius=300, max_neighbors=3):
    print("🚧 Connecting WALK ↔ RAIL...")

    rail_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("mode") == "rail"]
    walk_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("mode") == "walk"]

    for r_id, r_data in rail_nodes:
        candidates = []

        for w_id, w_data in walk_nodes:
            dist = haversine(
                r_data['stop_lon'], r_data['stop_lat'],
                w_data['stop_lon'], w_data['stop_lat']
            )

            if dist <= radius:
                candidates.append((dist, w_id))

        candidates.sort(key=lambda x: x[0])

        for dist, w_id in candidates[:max_neighbors]:
            time = dist / SPEED["walk"]

            G.add_edge(r_id, w_id, length=dist, travel_time=time, mode="transfer")
            G.add_edge(w_id, r_id, length=dist, travel_time=time, mode="transfer")


# ================= OPTIONAL: REDUCE GRAPH =================
def reduce_graph_random(max_nodes=50000):
    """
    ⚠️ OPTION (không bật mặc định)
    Giảm số node bằng cách:
    - chỉ giữ node nằm gần MRT
    - hoặc random sampling
    - CÁCH DƯỚI ĐÂY LÀ RANDOM
    """

    print(f"⚠️ Reducing graph to ~{max_nodes} nodes...")

    import random
    nodes = list(G.nodes())

    if len(nodes) <= max_nodes:
        return

    keep = set(random.sample(nodes, max_nodes))
    remove = [n for n in nodes if n not in keep]

    G.remove_nodes_from(remove)



def reduce_graph_near_mrt(radius=3000):
    """
    Giữ lại:
    - toàn bộ rail nodes
    - walk nodes gần MRT trong bán kính radius (m)

    Xoá:
    - walk nodes quá xa → giảm size graph mạnh nhưng vẫn giữ routing hợp lý
    """

    print(f"⚠️ Reducing graph (keep nodes within {radius}m from MRT)...")

    rail_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("mode") == "rail"]
    walk_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("mode") == "walk"]

    keep_nodes = set()

    # luôn giữ rail
    for r_id, _ in rail_nodes:
        keep_nodes.add(r_id)

    # với mỗi walk node → kiểm tra có gần MRT không
    for w_id, w_data in walk_nodes:
        w_lat = w_data['stop_lat']
        w_lon = w_data['stop_lon']

        for r_id, r_data in rail_nodes:
            dist = haversine(
                w_lon, w_lat,
                r_data['stop_lon'], r_data['stop_lat']
            )

            if dist <= radius:
                keep_nodes.add(w_id)
                break  # đủ rồi, không cần check thêm MRT khác

    # remove node không cần
    remove_nodes = [n for n in G.nodes() if n not in keep_nodes]
    G.remove_nodes_from(remove_nodes)

    print(f"✅ Reduced graph → {G.number_of_nodes()} nodes")

# ================= SAVE / LOAD =================
def save_graph():
    os.makedirs("cache", exist_ok=True)

    # GraphML (debug)
    nx.write_graphml(G, "cache/multi_modal.graphml")

    # Pickle (load nhanh)
    with open("cache/graph.pkl", "wb") as f:
        pickle.dump(G, f)

    # Export node JSON (frontend)
    nodes = []
    for n, d in G.nodes(data=True):
        nodes.append({
            "stop_id": n,
            "stop_name": d.get("name", ""),
            "stop_lat": str(d["stop_lat"]),
            "stop_lon": str(d["stop_lon"]),
            "zone_id": "1",
            "wheelchair_boarding": "1"
        })

    with open("cache/nodes.json", "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)

    print("✅ Saved graph + pickle + nodes.json")


def load_graph():
    if os.path.exists("cache/graph.pkl"):
        print("⚡ Loading graph from pickle...")
        with open("cache/graph.pkl", "rb") as f:
            return pickle.load(f)
    return None


# ================= MAIN =================
def build_graph(data_dir):
    global G

    G_loaded = load_graph()
    if G_loaded:
        G = G_loaded
    else:
        print("🚧 Building graph from scratch...")

        build_subway_graph(data_dir)
        build_walk_graph()
        connect_transfer()

        # # ⚠️ OPTION:
        # # reduce_graph_random(50000)

        # reduce_graph_near_mrt(radius=3000)

        save_graph()

    print(f"📊 Nodes: {G.number_of_nodes()} | Edges: {G.number_of_edges()}")
    return G


if __name__ == "__main__":
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent 
    data_folder = str(base_dir / "DATA")
    build_graph(data_folder)