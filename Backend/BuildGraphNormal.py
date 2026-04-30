import json
import networkx as nx
import os

G = nx.DiGraph()

SPEED = {
    "walk": 1.4,
    "rail": 12
}


# ================= UTIL =================
def haversine(lon1, lat1, lon2, lat2):
    from math import radians, cos, sin, asin, sqrt

    R = 6371000
    dlon = radians(lon2 - lon1)
    dlat = radians(lat2 - lat1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


# ================= RAIL GRAPH (GIỮ NGUYÊN LOGIC) =================
def build_rail_graph(data_dir):
    print("🚆 Building RAIL graph...")

    with open(os.path.join(data_dir, "stops_raw.json"), encoding="utf-8") as f:
        stops = json.load(f)

    with open(os.path.join(data_dir, "station_line_clean.json"), encoding="utf-8") as f:
        seq = json.load(f)

    with open(os.path.join(data_dir, "lines_clean.json"), encoding="utf-8") as f:
        lines = json.load(f)

    # valid MRT lines
    valid_lines = {
        str(l.get("LINE_ID") or l.get("ID")).strip()
        for l in lines
        if str(l.get("TYPEE") or l.get("TYPE")).upper() == "MRT"
    }

    # build sequence per line
    mrt_seq = {}
    valid_stations = set()

    for item in seq:
        lid = str(item.get("LINE_ID") or item.get("LINE")).strip()
        if lid in valid_lines:
            sid = str(item.get("STATION_ID") or item.get("STATION")).strip()
            valid_stations.add(sid)
            mrt_seq.setdefault(lid, []).append(item)

    # add rail nodes
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

    # add rail edges (2 chiều)
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

            time = dist / SPEED["rail"] + 30

            G.add_edge(u, v, length=dist, travel_time=time, mode="rail", line=lid)
            G.add_edge(v, u, length=dist, travel_time=time, mode="rail", line=lid)


# ================= WALK GRAPH (MỚI THEO YÊU CẦU) =================
def build_walk_graph(data_dir):
    print("🚶 Building WALK graph from stops_raw...")

    # load rail nodes để loại trùng
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

        # bỏ nếu là rail node
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

    # add walk edges (optional - nối gần kề nếu muốn)
    # (ở đây giữ đơn giản: không cần connect walk-to-walk)

    print(f"✔ Walk nodes: {len(walk_nodes)}")


# ================= RAIL ↔ WALK (ALL-TO-ALL 2 CHIỀU) =================
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

            time = dist / SPEED["walk"]

            # 2 chiều
            G.add_edge(r_id, w_id, length=dist, travel_time=time, mode="transfer")
            G.add_edge(w_id, r_id, length=dist, travel_time=time, mode="transfer")


# ================= SAVE =================
def save_graph():
    os.makedirs("cache", exist_ok=True)

    import pickle

    with open("cache/graph.pkl", "wb") as f:
        pickle.dump(G, f)

    print("💾 Saved graph.pkl")


# ================= MAIN =================
def build_graph_normal(data_dir):
    print("🚀 BUILD GRAPH NORMAL START")

    build_rail_graph(data_dir)
    build_walk_graph(data_dir)
    connect_rail_walk()
    save_graph()

    print(f"📊 Nodes: {G.number_of_nodes()} | Edges: {G.number_of_edges()}")


if __name__ == "__main__":
    build_graph_normal(
        data_dir=r"C:\project_intro_AI\Project-Intro-to-AI\Frontend\Data"
    )