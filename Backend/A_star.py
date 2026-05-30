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

def _k_nearest_nodes(G, lat, lng, skipped, k=3):
    """Tìm Top K node gần nhất xung quanh 1 tọa độ"""
    nodes = []
    for n, d in G.nodes(data=True):
        if n in skipped: continue
        nlat, nlng = _get_node_coords(G, n)
        if nlat is None or nlng is None: continue
        dist = _haversine(lat, lng, nlat, nlng)
        nodes.append((n, dist, nlat, nlng))
    nodes.sort(key=lambda x: x[1])
    return nodes[:k]

def astar_route(
    G: nx.DiGraph,
    start_lat: float, start_lng: float, end_lat: float, end_lng: float,
    mode: str = "multimodal",
    blocked: Optional[Set[Tuple[Any, Any]]] = None,
    skipped_stations: Optional[Set[Any]] = None,
    transfer_issues: Optional[Dict[str, str]] = None,
    departure_time_s: Optional[float] = None,
    start_node: Optional[Any] = None, end_node: Optional[Any] = None,
) -> Dict:
    
    blocked = blocked or set()
    skipped = skipped_stations or set()

    if departure_time_s is None:
        from datetime import datetime
        now = datetime.now()
        departure_time_s = now.hour * 3600 + now.minute * 60 + now.second
    departure_time_s = float(departure_time_s)
    allowed_modes = {"walk", "rail", "transfer"} if mode == "multimodal" else {mode}

    # ĐỊNH NGHĨA VIRTUAL NODES
    start_node = "VIRTUAL_START"
    end_node = "VIRTUAL_END"

    # Lấy 3 lựa chọn trạm gần nhất cho cả điểm đầu và điểm cuối
    start_stations = _k_nearest_nodes(G, start_lat, start_lng, skipped, k=3)
    end_stations = _k_nearest_nodes(G, end_lat, end_lng, skipped, k=3)
    end_station_names = {n for n, _, _, _ in end_stations}

    open_heap = []
    came_from = {start_node: (None, "walk", 0.0)}
    g_score = {start_node: 0.0}
    visited = set()

    # TRƯỜNG HỢP 1: Đi bộ trực tiếp từ điểm xuất phát tới đích (Nếu khoảng cách rất gần)
    dist_direct = _haversine(start_lat, start_lng, end_lat, end_lng)
    tt_direct = dist_direct / _WALK_SPEED
    g_score[end_node] = tt_direct
    heapq.heappush(open_heap, (tt_direct, tt_direct, end_node))
    came_from[end_node] = (start_node, "walk", tt_direct)

    # TRƯỜNG HỢP 2: Khởi tạo các nhánh đi bộ từ Tọa độ thực tế ra 3 Trạm MRT gần nhất
    for st, dist, st_lat, st_lng in start_stations:
        tt = dist / _WALK_SPEED
        g_score[st] = tt
        h = _haversine(st_lat, st_lng, end_lat, end_lng) / _RAIL_SPEED
        heapq.heappush(open_heap, (tt + h, tt, st))
        came_from[st] = (start_node, "walk", tt)

    # --- A* search ---
    while open_heap:
        f, g, current = heapq.heappop(open_heap)
        if current in visited: continue
        visited.add(current)

        if current == end_node:
            break

        # Nếu đang đứng ở 1 trong 3 trạm đích tiềm năng, AI tự tạo đường đi bộ về Vị trí đích thực tế
        if current in end_station_names:
            clat, clng = _get_node_coords(G, current)
            dist_to_end = _haversine(clat, clng, end_lat, end_lng)
            tt_to_end = dist_to_end / _WALK_SPEED
            tentative_g = g + tt_to_end
            
            if tentative_g < g_score.get(end_node, float("inf")):
                g_score[end_node] = tentative_g
                heapq.heappush(open_heap, (tentative_g, tentative_g, end_node))
                came_from[end_node] = (current, "walk", tt_to_end)

        # Bỏ qua vì các Node Ảo không nằm trong Đồ thị thực G
        if current not in G: 
            continue 

        for neighbor, edata in G[current].items():
            if neighbor in visited: continue
            edge_mode = edata.get("mode", "walk")
            if edge_mode not in allowed_modes: continue
            if (current, neighbor) in blocked: continue
            
            # Cấm đi vào vùng ga hỏng
            if neighbor in skipped: continue

            travel_time = edata["travel_time"]
            raw_node_id = str(neighbor).replace("rail_", "").replace("walk_", "")
            
            # Nếu ga này đang bị ùn tắc, cộng thêm thời gian phạt (giây)
            if raw_node_id in transfer_issues:
                severity = transfer_issues[raw_node_id]
                if severity == 'light':
                    travel_time += 300 # 5 phút
                elif severity == 'heavy':
                    travel_time += 900 # 15 phút
                elif severity == 'extreme':
                    travel_time += 1800 # 30 phút
            tentative_g = g + travel_time
            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                
                # Heuristic hướng về tọa độ đích
                nlat, nlng = _get_node_coords(G, neighbor)
                h = _haversine(nlat, nlng, end_lat, end_lng) / _RAIL_SPEED
                
                heapq.heappush(open_heap, (tentative_g + h, tentative_g, neighbor))
                came_from[neighbor] = (current, edge_mode, travel_time)
    
    if end_node not in came_from:
        raise ValueError("Không tìm thấy đường đi.")
        
    # --- Khôi phục đường đi ---
    path_nodes = []
    cur = end_node
    while cur != start_node:
        path_nodes.append(cur)
        parent, _, _ = came_from[cur]
        if parent is None: break
        cur = parent
    path_nodes.append(start_node)
    path_nodes.reverse()

    # --- Trích xuất dữ liệu mượt mà từ Virtual Nodes ---
    coords_all, segments = [], []
    total_dist = total_time = walk_time = rail_time = transfer_time = 0.0
    cur_mode = cur_name = cur_line = None
    cur_coords = []
    cur_dist = cur_time = 0.0
    cur_dep_s = departure_time_s
    cur_from_lat = cur_from_lng = None

    def flush_segment():
        nonlocal cur_mode, cur_coords, cur_dist, cur_time, cur_name, cur_line, cur_from_lat, cur_from_lng, cur_dep_s
        if not cur_coords: return
        seg_start_time = cur_dep_s - cur_time
        seg = {
            "mode": cur_mode, "from_lat": cur_from_lat, "from_lng": cur_from_lng,
            "to_lat": cur_coords[-1][0], "to_lng": cur_coords[-1][1],
            "distance_m": round(cur_dist, 1), "time_s": round(cur_time, 1),
            "name": cur_name, "coords": list(cur_coords),
            "dep_time_s": round(seg_start_time, 0), "arr_time_s": round(cur_dep_s, 0),
        }
        if cur_line: seg["line"] = cur_line
        segments.append(seg)

    for i in range(len(path_nodes)-1):
        u = path_nodes[i]; v = path_nodes[i+1]
        
        # Bắt chính xác tọa độ ảo
        if u == "VIRTUAL_START":
            if v == "VIRTUAL_END":
                coords = [[start_lat, start_lng], [end_lat, end_lng]]
            else:
                v_lat, v_lng = _get_node_coords(G, v)
                coords = [[start_lat, start_lng], [v_lat, v_lng]]
            mode_e = "walk"; tt = came_from[v][2]; dist = tt * _WALK_SPEED
            name = "Đi bộ ra ga"; line = ""
        elif v == "VIRTUAL_END":
            u_lat, u_lng = _get_node_coords(G, u)
            coords = [[u_lat, u_lng], [end_lat, end_lng]]
            mode_e = "walk"; tt = came_from[v][2]; dist = tt * _WALK_SPEED
            name = "Đi bộ tới đích"; line = ""
        else:
            if not G.has_edge(u, v): continue
            edata = G[u][v]
            mode_e = edata["mode"]; dist = edata["length"]; tt = came_from[v][2]
            coords = _edge_coords(G, u, v)
            name = edata.get("name", ""); line = edata.get("line", "")

        if cur_mode != mode_e:
            flush_segment()
            cur_mode = mode_e; cur_coords = list(coords); cur_dist = dist; cur_time = tt
            cur_name = name; cur_line = line
            cur_from_lat = coords[0][0]; cur_from_lng = coords[0][1]
        else:
            if cur_coords and cur_coords[-1] == coords[0]:
                cur_coords.extend(coords[1:])
            else: cur_coords.extend(coords)
            cur_dist += dist; cur_time += tt
            if not cur_name and name: cur_name = name
            if not cur_line and line: cur_line = line

        if cur_mode == "walk": walk_time += tt
        elif cur_mode == "rail": rail_time += tt
        elif cur_mode == "transfer": transfer_time += tt
            
        total_dist += dist; total_time += tt; cur_dep_s += tt
        if coords_all and coords_all[-1] == coords[0]:
            coords_all.extend(coords[1:])
        else: coords_all.extend(coords)

    flush_segment()

    return {
        "coords": coords_all, "segments": segments,
        "distance_m": round(total_dist, 1), "time_s": round(total_time, 1),
        "walk_time_s": round(walk_time, 1), "rail_time_s": round(rail_time, 1), "transfer_time_s": round(transfer_time, 1),
        "departure_time_s": round(departure_time_s, 0), "arrival_time_s": round(departure_time_s + total_time, 0),
        "start_node": str(start_node), "end_node": str(end_node), "path_nodes": path_nodes,
    }