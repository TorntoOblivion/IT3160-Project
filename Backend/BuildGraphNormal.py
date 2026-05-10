import json
import networkx as nx
import os
import pickle
from pathlib import Path

# Khởi tạo đồ thị toàn cục
G = nx.DiGraph()

# Hằng số tốc độ mặc định
SPEED = {
    "walk": 1.4,
    "rail": 12
}

# ================= UTIL =================
def haversine(lon1, lat1, lon2, lat2):
    """Tính khoảng cách Haversine giữa hai điểm (mét)."""
    from math import radians, cos, sin, asin, sqrt

    R = 6371000
    dlon = radians(lon2 - lon1)
    dlat = radians(lat2 - lat1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))

# ================= LOAD GRAPH (DÙNG CHO APP.PY) =================
def load_graph():
    """Nạp đồ thị từ file cache/graph.pkl."""
    file_path = "cache/graph.pkl"
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"❌ Lỗi khi nạp đồ thị: {e}")
            return None
    return None

# ================= RAIL GRAPH =================
def build_rail_graph(data_dir):
    print("🚆 Building RAIL graph...")

    with open(os.path.join(data_dir, "stops_raw.json"), encoding="utf-8") as f:
        stops = json.load(f)

    with open(os.path.join(data_dir, "station_line_clean.json"), encoding="utf-8") as f:
        seq = json.load(f)

    with open(os.path.join(data_dir, "lines_clean.json"), encoding="utf-8") as f:
        lines = json.load(f)

    # Lọc các tuyến MRT hợp lệ
    valid_lines = {
        str(l.get("LINE_ID") or l.get("ID")).strip()
        for l in lines
        if str(l.get("TYPEE") or l.get("TYPE")).upper() == "MRT"
    }

    # Xây dựng thứ tự trạm cho mỗi tuyến
    mrt_seq = {}
    valid_stations = set()

    for item in seq:
        lid = str(item.get("LINE_ID") or item.get("LINE")).strip()
        if lid in valid_lines:
            sid = str(item.get("STATION_ID") or item.get("STATION")).strip()
            valid_stations.add(sid)
            mrt_seq.setdefault(lid, []).append(item)

    # Thêm các nút rail
    for s in stops:
        sid = str(s.get("stop_id")).strip()

        if sid in valid_stations:
            G.add_node(
                f"rail_{sid}",
                stop_lat=float(s.get("stop_lat")),
                stop_lon=float(s.get("stop_lon")),
                name=s.get("stop_name"),
                mode="rail"
            )

    # Thêm các cạnh rail (2 chiều)
    for lid, stations in mrt_seq.items():
        stations.sort(key=lambda x: int(x.get("STOP_SEQUENCE") or 0))

        for i in range(len(stations) - 1):
            u = f"rail_{stations[i]['STATION_ID']}"
            v = f"rail_{stations[i+1]['STATION_ID']}"

            if not (G.has_node(u) and G.has_node(v)):
                continue

            n1 = G.nodes[u]
            n2 = G.nodes[v]

            dist = haversine(
                n1["stop_lon"], n1["stop_lat"],
                n2["stop_lon"], n2["stop_lat"]
            )

            # Thời gian di chuyển = khoảng cách / tốc độ + 30 giây dừng ga
            time = dist / SPEED["rail"] + 30

            G.add_edge(u, v, length=dist, travel_time=time, mode="rail", line=lid)
            G.add_edge(v, u, length=dist, travel_time=time, mode="rail", line=lid)

# ================= WALK GRAPH =================
def build_walk_graph(data_dir):
    print("🚶 Building WALK graph from stops_raw...")

    rail_ids = {
        n.replace("rail_", "")
        for n, d in G.nodes(data=True)
        if d.get("mode") == "rail"
    }

    with open(os.path.join(data_dir, "stops_raw.json"), encoding="utf-8") as f:
        stops = json.load(f)

    walk_nodes = []

    for s in stops:
        sid = str(s.get("stop_id")).strip()

        if sid in rail_ids:
            continue

        node_id = f"walk_{sid}"
        lat = float(s.get("stop_lat"))
        lon = float(s.get("stop_lon"))

        G.add_node(
            node_id,
            stop_lat=lat,
            stop_lon=lon,
            name=s.get("stop_name"),
            mode="walk"
        )
        walk_nodes.append(node_id)

    print(f"✔ Walk nodes created: {len(walk_nodes)}")

# ================= RAIL ↔ WALK (CONNECTING) =================
def connect_rail_walk():
    print("🔗 Connecting RAIL ↔ WALK (ALL TO ALL)...")

    rail_nodes = [
        (n, d) for n, d in G.nodes(data=True)
        if d.get("mode") == "rail"
    ]

    walk_nodes = [
        (n, d) for n, d in G.nodes(data=True)
        if d.get("mode") == "walk"
    ]

    for r_id, r in rail_nodes:
        for w_id, w in walk_nodes:
            dist = haversine(
                r["stop_lon"], r["stop_lat"],
                w["stop_lon"], w["stop_lat"]
            )

            # Thời gian chuyển tiếp bằng đi bộ
            time = dist / SPEED["walk"]

            G.add_edge(r_id, w_id, length=dist, travel_time=time, mode="transfer")
            G.add_edge(w_id, r_id, length=dist, travel_time=time, mode="transfer")

# ================= SAVE =================
def save_graph():
    os.makedirs("cache", exist_ok=True)
    with open("cache/graph.pkl", "wb") as f:
        pickle.dump(G, f)
    print("💾 Saved graph.pkl to cache/")

# ================= MAIN =================
def build_graph_normal(data_dir):
    print("🚀 BUILD GRAPH NORMAL START")
    build_rail_graph(data_dir)
    build_walk_graph(data_dir)
    connect_rail_walk()
    save_graph()
    print(f"📊 Final Graph Status - Nodes: {G.number_of_nodes()} | Edges: {G.number_of_edges()}")

if __name__ == "__main__":
    # Xác định đường dẫn tương đối đến thư mục DATA
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_PATH = BASE_DIR / "DATA"
    
    if DATA_PATH.exists():
        build_graph_normal(data_dir=str(DATA_PATH))
    else:
        print(f"❌ Không tìm thấy thư mục DATA tại: {DATA_PATH}")
