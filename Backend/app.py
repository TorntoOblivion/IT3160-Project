"""
main_app.py – Flask backend cho Bangkok MRT Route Finder.
Sử dụng A* (astar.py) để tìm đường.
Chỉ tải đồ thị từ cache (graph.pkl). Nếu chưa có cache, hãy chạy BuildGraphNormal.py trước.
"""

import os
import json
import threading
import logging
from pathlib import Path
from math import radians, cos, sin, asin, sqrt

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import networkx as nx

from BuildGraphNormal import load_graph  # chỉ import load, không import build
from A_star import astar_route        # đảm bảo astar.py nằm cùng thư mục

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
CORS(app)

# ----------------------------------------------------------------------
# Global state (thread-safe)
# ----------------------------------------------------------------------
global _graph
_graph = None
_graph_lock = threading.Lock()

# Trạng thái sự cố (admin)
_blocked_nodes = set()          # set các stop_id bị đóng
_blocked_edges = set()          # set các (u, v) với u, v là stop_id
_transfer_issues = {}           # dict {stop_id: severity}
_admin_lock = threading.Lock()

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_graph():
    """Trả về đồ thị nếu đã sẵn sàng."""
    with _graph_lock:
        if _graph is None:
            raise RuntimeError("Đồ thị chưa được tải. Hãy chạy BuildGraphNormal.py trước.")
        return _graph

def _get_node_coords(G, node):
    """Lấy tọa độ (lat, lng) từ node."""
    data = G.nodes[node]
    lat = data.get('stop_lat') or data.get('y')
    lng = data.get('stop_lon') or data.get('x')
    return lat, lng

def _haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng/2)**2
    return 2 * R * asin(sqrt(a))

def _find_nearest_node(G, lat, lng):
    """Tìm node (walk hoặc rail) gần nhất với tọa độ, dùng Haversine."""
    best_node = None
    best_dist = float('inf')
    for node, data in G.nodes(data=True):
        nlat, nlng = _get_node_coords(G, node)
        if nlat is None or nlng is None:
            continue
        d = _haversine(lat, lng, nlat, nlng)
        if d < best_dist:
            best_dist = d
            best_node = node
    return best_node

# ----------------------------------------------------------------------
# Tải đồ thị từ cache (chỉ một lần khi khởi động)
# ----------------------------------------------------------------------
def init_graph():
    global _graph
    G = load_graph()
    if G is None:
        raise FileNotFoundError(
            "Không tìm thấy file cache/graph.pkl. "
            "Hãy chạy BuildGraphNormal.py để tạo đồ thị trước khi khởi động server."
        )
    with _graph_lock:
        _graph = G
    log.info("Đồ thị đã tải từ cache: %d nút, %d cạnh", G.number_of_nodes(), G.number_of_edges())

try:
    init_graph()
except Exception as e:
    log.error("Không thể tải đồ thị: %s", e)
    # Server vẫn chạy, các API sẽ báo lỗi 503

# ----------------------------------------------------------------------
# API – Trang chủ
# ----------------------------------------------------------------------
@app.route("/")
def root():
    """Khi truy cập địa chỉ gốc, hiển thị trang Đăng nhập trước."""
    root_dir = Path(__file__).resolve().parent.parent
    return send_from_directory(str(root_dir / "Frontend" / "HTML"), "login.html")

@app.route("/home")
@app.route("/index.html")
def home_page():
    """Trang bản đồ chính (sau khi đăng nhập xong)."""
    root_dir = Path(__file__).resolve().parent.parent
    return send_from_directory(str(root_dir / "Frontend" / "HTML"), "index.html")

@app.route("/admin")
@app.route("/admin.html")
def admin_page():
    """Trang quản trị sự cố."""
    root_dir = Path(__file__).resolve().parent.parent
    return send_from_directory(str(root_dir / "Frontend" / "HTML"), "admin.html")

@app.route("/login")
@app.route("/login.html")
def login_page():
    """Trang đăng nhập (dùng cho các liên kết trực tiếp)."""
    root_dir = Path(__file__).resolve().parent.parent
    return send_from_directory(str(root_dir / "Frontend" / "HTML"), "login.html")

@app.route("/<path:filename>")
def static_files(filename):
    """Phục vụ CSS, JS và các tệp trong thư mục Frontend."""
    root_dir = Path(__file__).resolve().parent.parent
    frontend_dir = root_dir / "Frontend"
    
    # Tìm file trong thư mục Frontend/ (cho CSS/JS) hoặc Frontend/HTML/
    if (frontend_dir / filename).exists():
        return send_from_directory(str(frontend_dir), filename)
    elif (frontend_dir / "HTML" / filename).exists():
        return send_from_directory(str(frontend_dir / "HTML"), filename)
        
    return jsonify({"error": "File not found"}), 404

# ----------------------------------------------------------------------
# API – Lấy danh sách trạm MRT
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
    return jsonify({"stations": stations})

# ----------------------------------------------------------------------
# API – Tìm node gần nhất từ tọa độ (dùng khi click trên map)
# ----------------------------------------------------------------------
@app.route("/api/nearest_node", methods=["POST"])
def nearest_node():
    try:
        G = get_graph()
    except RuntimeError:
        return jsonify({"error": "Đồ thị chưa sẵn sàng"}), 503

    data = request.get_json(force=True)
    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return jsonify({"error": "Thiếu lat hoặc lng"}), 400

    node = _find_nearest_node(G, float(lat), float(lng))
    if node is None:
        return jsonify({"error": "Không tìm thấy node"}), 404

    node_data = G.nodes[node]
    return jsonify({
        "node_id": node,
        "name": node_data.get("name", ""),
        "lat": _get_node_coords(G, node)[0],
        "lng": _get_node_coords(G, node)[1],
        "mode": node_data.get("mode", "walk")
    })

# ----------------------------------------------------------------------
# API – Tìm đường (sử dụng A*)
# ----------------------------------------------------------------------
@app.route("/api/find_route", methods=["POST"])
def find_route():
    try:
        G = get_graph()
    except RuntimeError:
        return jsonify({"error": "Đồ thị chưa sẵn sàng"}), 503

    data = request.get_json(force=True)
    # Có thể truyền start_node/end_node trực tiếp, hoặc start/end (stop_id)
    start_id = str(data.get("start", "")).strip()
    end_id   = str(data.get("end", "")).strip()
    start_node = data.get("start_node")
    end_node   = data.get("end_node")

    # Nếu không có node trực tiếp thì tìm theo stop_id
    if not start_node:
        if start_id:
            start_node = f"rail_{start_id}"
        else:
            return jsonify({"error": "Thiếu start_node hoặc start"}), 400
    if not end_node:
        if end_id:
            end_node = f"rail_{end_id}"
        else:
            return jsonify({"error": "Thiếu end_node hoặc end"}), 400

    if start_node not in G or end_node not in G:
        return jsonify({"error": f"Node không tồn tại: {start_node} hoặc {end_node}"}), 404

    # Lấy tọa độ
    start_lat, start_lng = _get_node_coords(G, start_node)
    end_lat, end_lng     = _get_node_coords(G, end_node)

    if None in (start_lat, start_lng, end_lat, end_lng):
        return jsonify({"error": "Node thiếu tọa độ"}), 500

    # Lấy trạng thái sự cố hiện tại
    with _admin_lock:
        blocked_nodes = set(_blocked_nodes)
        blocked_edges = set(_blocked_edges)

    # Chuyển đổi sang định dạng A* cần
    skipped_stations = {f"rail_{nid}" for nid in blocked_nodes}
    blocked_edges_set = set()
    for u, v in blocked_edges:
        ru = f"rail_{u}"
        rv = f"rail_{v}"
        blocked_edges_set.add((ru, rv))
        blocked_edges_set.add((rv, ru))

    try:
        result = astar_route(
            G,
            start_lat, start_lng,
             end_lat, end_lng,
            mode="multimodal",
            blocked=blocked_edges_set,
            skipped_stations=skipped_stations,
            start_node=start_node,    # <-- thêm
            end_node=end_node         # <-- thêm
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log.exception("Lỗi khi chạy A*")
        return jsonify({"error": "Lỗi máy chủ nội bộ"}), 500

    # Lấy danh sách path nodes (đã được astar.py trả về)
    path_nodes = result.get("path_nodes", [])
    # Lọc rail node để hiển thị danh sách trạm
    rail_path = [n for n in path_nodes if n.startswith("rail_")]

    # Tên điểm
    start_name = G.nodes[start_node].get("name") if start_node in G else start_node
    end_name   = G.nodes[end_node].get("name") if end_node in G else end_node

    return jsonify({
        "start": start_name,
        "end": end_name,
        "path": [n.replace("rail_", "") for n in rail_path],
        "distance": round(result.get("distance_m", 0) / 1000.0, 2),
        "estimated_time": round(result.get("time_s", 0) / 60.0, 1)
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
        _blocked_nodes.clear()
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
            u = parts[-2]
            v = parts[-1]
            parsed_edges.add((u, v))
        else:
            log.warning("Không parse được edge: %s", edge_str)

    with _admin_lock:
        _blocked_edges.clear()
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
        _transfer_issues.clear()
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
