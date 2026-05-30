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
    
    # 1. Thay đổi cốt lõi: Lấy thẳng tọa độ click do Frontend gửi lên chứ không lấy ID trạm nữa
    start_lat = data.get("start_lat")
    start_lng = data.get("start_lng")
    end_lat = data.get("end_lat")
    end_lng = data.get("end_lng")

    if None in (start_lat, start_lng, end_lat, end_lng):
        return jsonify({"error": "Thiếu dữ liệu tọa độ điểm đi hoặc điểm đến"}), 400

    # Lấy trạng thái sự cố hiện tại
    with _admin_lock:
        blocked_nodes = set(_blocked_nodes)
        blocked_edges = set(_blocked_edges)
        transfer_issues = dict(_transfer_issues)

    # Chuyển đổi danh sách trạm bảo trì sang định dạng A* cần
    skipped_stations = set()
    for nid in blocked_nodes:
        skipped_stations.add(f"rail_{nid}")
        skipped_stations.add(f"walk_{nid}")

    # Chuyển đổi danh sách ray hỏng sang định dạng A* cần
    blocked_edges_set = set()
    for u, v in blocked_edges:
        ru = f"rail_{u}"
        rv = f"rail_{v}"
        blocked_edges_set.add((ru, rv))
        blocked_edges_set.add((rv, ru))
        
        wu = f"walk_{u}"
        wv = f"walk_{v}"
        blocked_edges_set.add((wu, wv))
        blocked_edges_set.add((wv, wu))

    try:
        # Gọi thuật toán A* bằng 4 tham số tọa độ thực tế
        result = astar_route(
            G,
            float(start_lat), float(start_lng),
            float(end_lat), float(end_lng),
            mode="multimodal",
            blocked=blocked_edges_set,
            skipped_stations=skipped_stations,
            transfer_issues=transfer_issues
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log.exception("Lỗi khi chạy A*")
        return jsonify({"error": "Lỗi máy chủ nội bộ"}), 500

    path_nodes = result.get("path_nodes", [])
    rail_path = [n for n in path_nodes if n.startswith("rail_")]

    # 2. Lấy danh sách TÊN các trạm tàu điện đi qua để hiển thị danh sách lịch trình
    path_names = []
    for n in rail_path:
        path_names.append(G.nodes[n].get("name", n.replace("rail_", "")))

    # 3. Chuyển đổi cấu trúc mảng Segment thành định dạng path_details để Frontend vẽ Polyline
    path_details = []
    for seg in result.get("segments", []):
        coords = seg.get("coords", [])
        mode = seg.get("mode", "walk")
        for i in range(len(coords) - 1):
            path_details.append({
                "latA": coords[i][0],
                "lonA": coords[i][1],
                "latB": coords[i+1][0],
                "lonB": coords[i+1][1],
                "type": mode
            })

    # Trả toàn bộ dữ liệu sạch về cho client
    return jsonify({
        "start": "Vị trí của bạn",
        "end": "Vị trí đích",
        "path": [n.replace("rail_", "") for n in rail_path],
        "path_names": path_names,
        "path_details": path_details,
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
