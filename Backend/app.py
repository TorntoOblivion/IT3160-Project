"""
app.py – Flask backend cho Bangkok MRT Route Finder.
Hỗ trợ API tìm đường và quản lý kịch bản sự cố (admin).
"""

import os
import json
import threading
import logging
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS
import networkx as nx
from flask import send_from_directory
import os
from Build_graph import build_graph, load_graph

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Flask app
# ----------------------------------------------------------------------
app = Flask(__name__)
@app.route("/")
def serve_index():
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "Frontend")
    return send_from_directory(frontend_dir, "index.html")
CORS(app)  # Cho phép frontend gọi API từ domain/port khác

# ----------------------------------------------------------------------
# Global state (thread-safe)
# ----------------------------------------------------------------------
global _graph
_graph = None
_graph_lock = threading.Lock()

# Trạng thái sự cố
_blocked_nodes = set()          # set các stop_id bị đóng
_blocked_edges = set()          # set các (u, v) với u, v là stop_id
_transfer_issues = {}           # dict {stop_id: severity}
_admin_lock = threading.Lock()


@app.route("/<path:filename>")
def serve_static(filename):
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "Frontend")
    return send_from_directory(frontend_dir, filename)
# ----------------------------------------------------------------------
# Helper – lấy đồ thị
# ----------------------------------------------------------------------
def get_graph():
    if _graph is None:
        raise RuntimeError("Đồ thị chưa được tải xong.")
    return _graph

# ----------------------------------------------------------------------
# Load đồ thị lúc khởi động (background nếu cần, nhưng ở đây làm đồng bộ)
# ----------------------------------------------------------------------
def init_graph():
    global _graph
    G = None
    if G is None:
        log.info("Chưa có cache, build đồ thị mới...")
        data_dir = Path(__file__).resolve().parent.parent / "DATA"
        if not data_dir.exists():
            raise FileNotFoundError(f"Thư mục DATA không tồn tại: {data_dir}")
        G = build_graph(str(data_dir))
    with _graph_lock:
        _graph = G
    log.info("Đồ thị đã sẵn sàng: %d nút, %d cạnh", G.number_of_nodes(), G.number_of_edges())

# Chạy init ngay khi import (có thể lâu, nhưng đảm bảo sẵn sàng)
try:
    init_graph()
except Exception as e:
    log.error("Không thể khởi tạo đồ thị: %s", e)

# ----------------------------------------------------------------------
# API – Lấy danh sách trạm MRT (cho frontend map)
# ----------------------------------------------------------------------
@app.route("/api/stations")
def api_stations():
    try:
        G = get_graph()
    except RuntimeError:
        return jsonify({"error": "Đồ thị chưa sẵn sàng"}), 503

    stations = []
    for node, data in G.nodes(data=True):
        if data.get("mode") == "rail":
            stop_id = node.replace("rail_", "")
            stations.append({
                "stop_id": stop_id,
                "stop_name": data.get("name", ""),
                "stop_lat": data.get("stop_lat") or data.get("y"),
                "stop_lon": data.get("stop_lon") or data.get("x"),
            })
    return jsonify(stations)

# ----------------------------------------------------------------------
# API – Tìm đường (dùng stop_id)
# ----------------------------------------------------------------------
@app.route("/api/find_route", methods=["POST"])
def find_route():
    try:
        G = get_graph()
    except RuntimeError:
        return jsonify({"error": "Đồ thị chưa sẵn sàng"}), 503

    data = request.get_json(force=True)
    start_id = str(data.get("start", "")).strip()
    end_id   = str(data.get("end", "")).strip()

    log.info(f"find_route request: start_id={start_id}, end_id={end_id}")

    if not start_id or not end_id:
        return jsonify({"error": "Thiếu start hoặc end"}), 400

    # Map sang node trong đồ thị
    start_node = f"rail_{start_id}"
    end_node   = f"rail_{end_id}"

    log.info(f"Checking nodes: start_node={start_node}, end_node={end_node}")
    log.info(f"Graph has {len(G)} nodes. Sample nodes: {list(G.nodes())[:5]}")

    if start_node not in G or end_node not in G:
        return jsonify({"error": "Không tìm thấy trạm yêu cầu"}), 404

    # Lấy trạng thái sự cố hiện tại
    with _admin_lock:
        blocked_nodes = set(_blocked_nodes)
        blocked_edges = set(_blocked_edges)
        # transfer_issues có thể dùng để tăng thời gian chuyển tuyến (tạm bỏ qua)

    # Tạo bản sao đồ thị để không làm hỏng đồ thị gốc
    H = G.copy()

    # Loại bỏ các node bị đóng (trạm đóng cửa hoàn toàn)
    nodes_to_remove = [f"rail_{nid}" for nid in blocked_nodes]
    H.remove_nodes_from(nodes_to_remove)

    # Loại bỏ các cạnh bị chặn
    edges_to_remove = []
    for u, v in blocked_edges:
        ru = f"rail_{u}"
        rv = f"rail_{v}"
        if H.has_edge(ru, rv):
            edges_to_remove.append((ru, rv))
        if H.has_edge(rv, ru):
            edges_to_remove.append((rv, ru))
    H.remove_edges_from(edges_to_remove)

    # Kiểm tra node start/end còn tồn tại không
    if start_node not in H or end_node not in H:
        return jsonify({"error": "Trạm đi hoặc đến đang bị đóng"}), 400

    # Tìm đường ngắn nhất (dùng travel_time làm trọng số)
    try:
        path = nx.shortest_path(H, source=start_node, target=end_node, weight="travel_time")
    except nx.NetworkXNoPath:
        return jsonify({"error": "Không tìm thấy đường đi"}), 404

    # Tính tổng khoảng cách và thời gian
    total_dist = 0.0
    total_time = 0.0
    for i in range(len(path)-1):
        u, v = path[i], path[i+1]
        edge_data = H[u][v]
        total_dist += edge_data.get("length", 0)
        total_time += edge_data.get("travel_time", 0)

    # Lấy tên trạm
    start_name = G.nodes[start_node].get("name", start_id)
    end_name   = G.nodes[end_node].get("name", end_id)

    # Chuyển path thành list stop_id (bỏ prefix rail_)
    path_ids = [node.replace("rail_", "") for node in path]

    log.info(f"Route found: {start_name} -> {end_name}, {len(path_ids)} stops")
    return jsonify({
        "start": start_name,
        "end": end_name,
        "path": path_ids,
        "distance": round(total_dist / 1000.0, 2),      # km
        "estimated_time": round(total_time / 60.0, 1)   # phút
    })

# ----------------------------------------------------------------------
# Admin – Đóng trạm (NODE_OUTAGE)
# ----------------------------------------------------------------------
@app.route("/api/admin/node_outage", methods=["POST"])
def admin_node_outage():
    data = request.get_json(force=True)
    nodes = data.get("affected_nodes", [])
    if not isinstance(nodes, list):
        return jsonify({"error": "affected_nodes phải là list"}), 400

    with _admin_lock:
        _blocked_nodes.update(nodes)
    log.info("Đã đóng %d trạm, tổng: %d", len(nodes), len(_blocked_nodes))
    return jsonify({"ok": True, "blocked_nodes_count": len(_blocked_nodes)})

# ----------------------------------------------------------------------
# Admin – Chặn đoạn ray (EDGE_OUTAGE)
# ----------------------------------------------------------------------
@app.route("/api/admin/edge_outage", methods=["POST"])
def admin_edge_outage():
    data = request.get_json(force=True)
    edges = data.get("affected_edges", [])
    if not isinstance(edges, list):
        return jsonify({"error": "affected_edges phải là list"}), 400

    parsed_edges = set()
    for edge_str in edges:
        # Edge format: "LineId_StationA_StationB" (từ admin.js)
        parts = edge_str.split("_")
        if len(parts) >= 3:
            # Phần đầu là LineId, hai phần cuối là StationA, StationB
            u = parts[-2]
            v = parts[-1]
            parsed_edges.add((u, v))
        else:
            log.warning("Không parse được edge: %s", edge_str)

    with _admin_lock:
        _blocked_edges.update(parsed_edges)
    log.info("Đã chặn %d đoạn ray, tổng: %d", len(parsed_edges), len(_blocked_edges))
    return jsonify({"ok": True, "blocked_edges_count": len(_blocked_edges)})

# ----------------------------------------------------------------------
# Admin – Lỗi chuyển tuyến (TRANSFER_ISSUE)
# ----------------------------------------------------------------------
@app.route("/api/admin/transfer_issue", methods=["POST"])
def admin_transfer_issue():
    data = request.get_json(force=True)
    affected = data.get("affected_nodes", {})
    if not isinstance(affected, dict):
        return jsonify({"error": "affected_nodes phải là object {stop_id: severity}"}), 400

    with _admin_lock:
        _transfer_issues.update(affected)
    log.info("Đã cập nhật lỗi chuyển tuyến cho %d trạm", len(affected))
    return jsonify({"ok": True, "transfer_issues_count": len(_transfer_issues)})

# ----------------------------------------------------------------------
# Admin – Xóa tất cả sự cố
# ----------------------------------------------------------------------
@app.route("/api/admin/clear", methods=["POST"])
def admin_clear():
    with _admin_lock:
        _blocked_nodes.clear()
        _blocked_edges.clear()
        _transfer_issues.clear()
    log.info("Đã xóa toàn bộ sự cố")
    return jsonify({"ok": True})

# ----------------------------------------------------------------------
# Admin – Xem trạng thái hiện tại
# ----------------------------------------------------------------------
@app.route("/api/admin/status", methods=["GET"])
def admin_status():
    with _admin_lock:
        status = {
            "blocked_nodes": list(_blocked_nodes),
            "blocked_edges": [f"{u}_{v}" for u, v in _blocked_edges],
            "transfer_issues": dict(_transfer_issues)
        }
    return jsonify(status)

# ----------------------------------------------------------------------
# Khởi động server
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)