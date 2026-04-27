"""
astar.py – A* route planner for Bangkok MRT + walking (DiGraph).
Trả về lộ trình chi tiết kèm danh sách node (path_nodes).
"""

import heapq
import math
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

# Hằng số
_WALK_SPEED = 1.4       # m/s
_RAIL_SPEED = 12.0      # m/s (max, dùng cho heuristic)
_DWELL      = 30.0      # giây dừng tại mỗi ga (fixed)

def _haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))

def _get_node_coords(G, node):
    data = G.nodes[node]
    lat = data.get('stop_lat') or data.get('y')
    lng = data.get('stop_lon') or data.get('x')
    return lat, lng

def _nearest_node(G, lat, lng, skip_nodes=None):
    """Tìm node gần nhất, tránh các node bị skip (nếu có)."""
    skip_nodes = skip_nodes or set()
    best_node, best_dist = None, float('inf')
    for n, d in G.nodes(data=True):
        if n in skip_nodes:
            continue
        nlat, nlng = _get_node_coords(G, n)
        if nlat is None or nlng is None:
            continue
        dist = _haversine(lat, lng, nlat, nlng)
        if dist < best_dist:
            best_dist = dist
            best_node = n
    # fallback nếu tất cả đều bị skip
    if best_node is None and skip_nodes:
        return _nearest_node(G, lat, lng, set())
    return best_node

def _heuristic(G, a, b):
    """Heuristic admissible: khoảng cách chim bay / tốc độ tối đa."""
    lat_a, lng_a = _get_node_coords(G, a)
    lat_b, lng_b = _get_node_coords(G, b)
    if None in (lat_a, lng_a, lat_b, lng_b):
        return 0.0
    return _haversine(lat_a, lng_a, lat_b, lng_b) / _RAIL_SPEED

def _edge_coords(G, u, v):
    """Trả về danh sách [lat, lng] của cạnh (dùng geometry nếu có)."""
    data = G[u][v]
    u_lat, u_lng = _get_node_coords(G, u)
    v_lat, v_lng = _get_node_coords(G, v)
    if 'geometry' in data:
        try:
            coords = [[lat, lng] for lng, lat in data['geometry'].coords]
            if coords:
                d_start = (coords[0][0] - u_lat)**2 + (coords[0][1] - u_lng)**2
                d_end   = (coords[-1][0] - u_lat)**2 + (coords[-1][1] - u_lng)**2
                if d_start > d_end:
                    coords.reverse()
            return coords
        except:
            pass
    if u_lat is not None and v_lat is not None:
        return [[u_lat, u_lng], [v_lat, v_lng]]
    return []

def astar_route(
    G: nx.DiGraph,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    mode: str = "multimodal",
    blocked: Optional[Set[Tuple[Any, Any]]] = None,
    skipped_stations: Optional[Set[Any]] = None,
    departure_time_s: Optional[float] = None,
    start_node: Optional[Any] = None,
    end_node: Optional[Any] = None,
) -> Dict:
    """
    Tìm đường đi tối ưu bằng A*.

    Tham số:
        start_node, end_node: nếu biết trước node (từ nearest_node API), truyền vào sẽ chính xác.
    Trả về dict có 'path_nodes' – danh sách node theo thứ tự từ start đến end.
    """
    blocked = blocked or set()
    skipped = skipped_stations or set()

    if departure_time_s is None:
        from datetime import datetime
        now = datetime.now()
        departure_time_s = now.hour * 3600 + now.minute * 60 + now.second
    departure_time_s = float(departure_time_s)

    allowed_modes = {"walk", "rail", "transfer"} if mode == "multimodal" else {mode}

    # --- Xác định node xuất phát/đích ---
    if start_node is None:
        start_node = _nearest_node(G, start_lat, start_lng, skipped)
    if end_node is None:
        end_node = _nearest_node(G, end_lat, end_lng, skipped)

    if start_node is None or end_node is None:
        raise ValueError("Không tìm thấy node phù hợp.")

    # Trường hợp xuất phát và đích trùng node
    if start_node == end_node:
        d = _haversine(start_lat, start_lng, end_lat, end_lng)
        t = d / _WALK_SPEED
        return {
            "coords": [[start_lat, start_lng], [end_lat, end_lng]],
            "segments": [{
                "mode": "walk",
                "from_lat": start_lat, "from_lng": start_lng,
                "to_lat":   end_lat,   "to_lng":   end_lng,
                "distance_m": round(d, 1),
                "time_s": round(t, 1),
                "name": "Đi bộ thẳng",
            }],
            "distance_m": round(d, 1),
            "time_s": round(t, 1),
            "walk_time_s": round(t, 1),
            "rail_time_s": 0.0,
            "transfer_time_s": 0.0,
            "departure_time_s": round(departure_time_s, 0),
            "arrival_time_s": round(departure_time_s + t, 0),
            "start_node": str(start_node),
            "end_node": str(end_node),
            "path_nodes": [start_node, end_node],
        }

    # --- A* search ---
    open_heap = [(0.0, 0.0, start_node)]
    came_from = {start_node: (None, "walk", 0.0)}  # (parent, mode, travel_time_from_parent)
    g_score = {start_node: 0.0}
    visited = set()

    while open_heap:
        f, g, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)

        if current == end_node:
            break

        for neighbor, edata in G[current].items():
            if neighbor in visited:
                continue
            
            edge_mode = edata.get("mode", "walk")
            if edge_mode not in allowed_modes:
                continue
            if (current, neighbor) in blocked:
                continue

            travel_time = edata["travel_time"]

            # 1. Ràng buộc tại ga đang đứng: Cấm đi bộ/transfer ra nếu đang ở ga đóng cửa
            if current in skipped and current != start_node and current != end_node:
                if edge_mode != "rail":
                    continue
            
            # 2. Ràng buộc tại ga sắp tới
            if neighbor in skipped:
                if edge_mode != "rail":
                    continue # Không thể đi bộ/transfer vào ga đang đóng cửa
                else:
                    travel_time -= _DWELL # Tàu chạy xuyên qua ga skip, không dừng lại

            # Tính toán cost và push vào open list
            tentative_g = g + travel_time
            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                h = _heuristic(G, neighbor, end_node)
                heapq.heappush(open_heap, (tentative_g + h, tentative_g, neighbor))
                came_from[neighbor] = (current, edge_mode, travel_time)

    if end_node not in came_from:
        raise ValueError("Không tìm thấy đường đi.")

    # --- Khôi phục đường đi (danh sách node) ---
    path_nodes = []
    cur = end_node
    while cur != start_node:
        path_nodes.append(cur)
        parent, _, _ = came_from[cur]
        if parent is None:
            break
        cur = parent
    path_nodes.append(start_node)
    path_nodes.reverse()

    # --- Xây dựng segments và tọa độ (dựa trên path_nodes) ---
    coords_all = []
    segments = []
    total_dist = 0.0
    total_time = 0.0
    walk_time = 0.0
    rail_time = 0.0
    transfer_time = 0.0

    cur_mode = None
    cur_coords = []
    cur_dist = 0.0
    cur_time = 0.0
    cur_name = ""
    cur_line = ""
    cur_from_lat = None
    cur_from_lng = None
    cur_dep_s = departure_time_s

    def flush_segment():
        nonlocal cur_mode, cur_coords, cur_dist, cur_time, cur_name, cur_line, cur_from_lat, cur_from_lng, cur_dep_s
        if not cur_coords:
            return
            
        # Tính thời điểm bắt đầu của segment hiện tại
        seg_start_time = cur_dep_s - cur_time
        
        seg = {
            "mode": cur_mode,
            "from_lat": cur_from_lat,
            "from_lng": cur_from_lng,
            "to_lat": cur_coords[-1][0],
            "to_lng": cur_coords[-1][1],
            "distance_m": round(cur_dist, 1),
            "time_s": round(cur_time, 1),
            "name": cur_name,
            "coords": list(cur_coords),
            "dep_time_s": round(seg_start_time, 0),
            "arr_time_s": round(cur_dep_s, 0),
        }
        if cur_line:
            seg["line"] = cur_line
        segments.append(seg)

    for i in range(len(path_nodes)-1):
        u = path_nodes[i]
        v = path_nodes[i+1]

        # Đảm bảo có cạnh (với thuật toán mới, 100% sẽ luôn có cạnh trực tiếp)
        if not G.has_edge(u, v):
            continue
            
        edata = G[u][v]
        mode_e = edata["mode"]
        dist = edata["length"]
        tt = came_from[v][2]   # Lấy travel_time chính xác đã lưu lúc chạy A* (đã trừ DWELL nếu skip)
        coords = _edge_coords(G, u, v)
        name = edata.get("name", "")
        line = edata.get("line", "")

        # Gom vào segment hiện tại
        if cur_mode != mode_e:
            flush_segment()
            cur_mode = mode_e
            cur_coords = list(coords)
            cur_dist = dist
            cur_time = tt
            cur_name = name
            cur_line = line
            cur_from_lat = coords[0][0]
            cur_from_lng = coords[0][1]
        else:
            if cur_coords and cur_coords[-1] == coords[0]:
                cur_coords.extend(coords[1:])
            else:
                cur_coords.extend(coords)
            cur_dist += dist
            cur_time += tt
            if not cur_name and name:
                cur_name = name
            if not cur_line and line:
                cur_line = line

        # Cập nhật tổng
        if cur_mode == "walk":
            walk_time += tt
        elif cur_mode == "rail":
            rail_time += tt
        elif cur_mode == "transfer":
            transfer_time += tt
            
        total_dist += dist
        total_time += tt
        cur_dep_s += tt  # Tích lũy timeline liên tục

        # Toàn bộ tọa độ vẽ
        if coords_all and coords_all[-1] == coords[0]:
            coords_all.extend(coords[1:])
        else:
            coords_all.extend(coords)

    # Đẩy segment cuối cùng vào mảng
    flush_segment()

    arrival_time_s = departure_time_s + total_time

    return {
        "coords":           coords_all,
        "segments":         segments,
        "distance_m":       round(total_dist, 1),
        "time_s":           round(total_time, 1),
        "walk_time_s":      round(walk_time, 1),
        "rail_time_s":      round(rail_time, 1),
        "transfer_time_s":  round(transfer_time, 1),
        "departure_time_s": round(departure_time_s, 0),
        "arrival_time_s":   round(arrival_time_s, 0),
        "start_node":       str(start_node),
        "end_node":         str(end_node),
        "path_nodes":       path_nodes,
    }