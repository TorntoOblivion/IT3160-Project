"""
astar.py – A* route planner for Bangkok MRT + walking (DiGraph).
Supports:
- Normal routing
- Blocked edges (u, v)
- Skipped stations (trains pass through without stopping)
"""

import heapq
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx

# Constants
_WALK_SPEED = 1.4       # m/s
_RAIL_SPEED = 12.0      # m/s (max MRT speed, used for heuristic)
_DWELL = 30.0           # seconds dwell at each station (fixed by graph builder)

def _dist_m(lat1, lng1, lat2, lng2):
    """Haversine distance in meters."""
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _get_node_coords(G, node):
    """Return (lat, lng) for a node, regardless of attribute naming."""
    data = G.nodes[node]
    lat = data.get('stop_lat') or data.get('y')
    lng = data.get('stop_lon') or data.get('x')
    return lat, lng


def _nearest_node(G, lat, lng, skip_nodes=None):
    """
    Find nearest graph node to (lat, lng) excluding nodes in skip_nodes.
    If all nodes are skipped, fallback to nearest anyway.
    """
    skip_nodes = skip_nodes or set()
    best_node, best_dist = None, float('inf')

    for node, data in G.nodes(data=True):
        if node in skip_nodes:
            continue
        nlat, nlng = _get_node_coords(G, node)
        if nlat is None or nlng is None:
            continue
        d = _dist_m(lat, lng, nlat, nlng)
        if d < best_dist:
            best_dist = d
            best_node = node

    if best_node is None and skip_nodes:
        return _nearest_node(G, lat, lng, set())
    return best_node


def _heuristic(G, a, b):
    """Admissible A* heuristic: straight-line distance / max speed."""
    lat_a, lng_a = _get_node_coords(G, a)
    lat_b, lng_b = _get_node_coords(G, b)
    if None in (lat_a, lng_a, lat_b, lng_b):
        return 0.0
    return _dist_m(lat_a, lng_a, lat_b, lng_b) / _RAIL_SPEED


def _edge_coords(G, u, v):
    """
    Return list of [lat, lng] waypoints for edge u->v.
    For walk edges with stored geometry, use that; otherwise straight line.
    """
    data = G[u][v]
    u_lat, u_lng = _get_node_coords(G, u)
    v_lat, v_lng = _get_node_coords(G, v)

    if 'geometry' in data:
        geom = data['geometry']
        try:
            coords = [[lat, lng] for lng, lat in geom.coords]  # shapely gives (x,y) = (lng,lat)
            # Ensure direction: if first point is closer to v than u, reverse
            if coords:
                d_first = (coords[0][0] - u_lat)**2 + (coords[0][1] - u_lng)**2
                d_last  = (coords[-1][0] - u_lat)**2 + (coords[-1][1] - u_lng)**2
                if d_first > d_last:
                    coords.reverse()
            return coords
        except Exception:
            pass

    # Straight line fallback
    if u_lat is not None and v_lat is not None:
        return [[u_lat, u_lng], [v_lat, v_lng]]
    return []


# ============================================================
#  Main A* router
# ============================================================
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
) -> Dict:
    """
    Find optimal route using time-dependent A* (simple version).

    Parameters
    ----------
    G : nx.DiGraph
    blocked : set of (u, v) tuples – edges to avoid
    skipped_stations : set of node ids – stations where trains don't stop
    departure_time_s : seconds since midnight (unused here but kept for API compatibility)
    """
    blocked = blocked or set()
    skipped = skipped_stations or set()

    # Default departure time (not really used, just for output)
    if departure_time_s is None:
        from datetime import datetime
        now = datetime.now()
        departure_time_s = now.hour * 3600 + now.minute * 60 + now.second
    departure_time_s = float(departure_time_s)

    allowed_modes = {
        "walk":       {"walk"},
        "multimodal": {"walk", "rail", "transfer"},
    }.get(mode, {"walk", "rail", "transfer"})

    # 1. Snap to graph (avoid skipped stations for start/end)
    start_node = _nearest_node(G, start_lat, start_lng, skipped)
    end_node   = _nearest_node(G, end_lat,   end_lng,   skipped)
    if start_node is None or end_node is None:
        raise ValueError("Could not find any valid node near given coordinates.")

    # Trivial case
    if start_node == end_node:
        d = _dist_m(start_lat, start_lng, end_lat, end_lng)
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
            "distance_m": round(d, 1), "time_s": round(t, 1),
            "walk_time_s": round(t, 1), "rail_time_s": 0.0, "transfer_time_s": 0.0,
            "departure_time_s": round(departure_time_s, 0),
            "arrival_time_s": round(departure_time_s + t, 0),
            "start_node": str(start_node), "end_node": str(end_node),
        }

    # 2. A* search
    open_set = [(0.0, 0.0, start_node)]  # (f, g, node)
    came_from = {start_node: (None, "walk", 0.0)}  # (parent, mode, travel_time_from_parent)
    g_score = {start_node: 0.0}
    visited = set()

    found = False
    while open_set:
        f, g, current = heapq.heappop(open_set)
        if current in visited:
            continue
        visited.add(current)

        if current == end_node:
            found = True
            break

        # Determine previous mode (for skip logic)
        if current == start_node:
            prev_mode = "walk"
        else:
            prev_mode = came_from[current][1]

        for neighbor, edata in G[current].items():
            if neighbor in visited:
                continue

            edge_mode = edata.get("mode", "walk")
            if edge_mode not in allowed_modes:
                continue

            # --- Blocked edge ---
            if (current, neighbor) in blocked:
                continue

            # === SKIPPED STATION LOGIC ===
            if neighbor in skipped:
                if edge_mode == "rail":
                    # Train passes through → look ahead to next rail stop
                    for next_node, next_data in G[neighbor].items():
                        if next_node == current:
                            continue
                        if next_data.get("mode") != "rail":
                            continue

                        # Cost = time to skipped station (minus dwell) + time from there to next
                        time_to_skip = edata["travel_time"] - _DWELL
                        time_from_skip = next_data["travel_time"]
                        combined_time = time_to_skip + time_from_skip

                        tentative_g = g + combined_time
                        if tentative_g < g_score.get(next_node, float("inf")):
                            g_score[next_node] = tentative_g
                            h = _heuristic(G, next_node, end_node)
                            heapq.heappush(open_set, (tentative_g + h, tentative_g, next_node))
                            came_from[next_node] = (current, "rail", combined_time)
                    # Do NOT add this skipped node itself
                    continue
                elif edge_mode == "transfer":
                    # Cannot enter/exit a closed station
                    continue
                else:  # walk to closed station (unlikely)
                    continue

            # --- Normal edge processing ---
            travel_time = edata["travel_time"]
            tentative_g = g + travel_time
            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                h = _heuristic(G, neighbor, end_node)
                heapq.heappush(open_set, (tentative_g + h, tentative_g, neighbor))
                came_from[neighbor] = (current, edge_mode, travel_time)

    if not found:
        raise ValueError(
            f"Không tìm thấy đường. Skipped={len(skipped)}, Blocked={len(blocked)}"
        )

    # 3. Reconstruct path node list + segments
    # First build ordered list of nodes (including virtual skipped ones for geometry)
    path = []
    node = end_node
    while node != start_node:
        parent, mode_, _ = came_from[node]
        if parent is None:
            break
        # If parent->node skipped some station, we insert it for visual continuity
        if parent != came_from[node][0]:
            # This means a skip occurred: parent directly connected to node, bypassing a station.
            # We need to find which station was skipped. Unfortunately we don't store it explicitly.
            # As a heuristic: if there's a rail node between parent and node that is in skipped set,
            # we'll insert it. But to keep it simple, we can detect by checking if parent and node
            # are not adjacent in original graph rail edges. We'll just insert the skipped station
            # from the graph structure.
            # For now, we'll handle geometry differently during segment building.
            pass
        path.append(node)
        node = parent
    path.append(start_node)
    path.reverse()

    # 4. Build segments and full coords
    all_coords = []
    segments = []
    total_dist = 0.0
    total_time = 0.0
    walk_time = 0.0
    rail_time = 0.0
    transfer_time = 0.0

    # Helper to flush current segment
    cur_seg = None   # dict with keys: mode, coords, dist, time, name, line, from_lat, from_lng, dep_s

    def flush():
        nonlocal cur_seg
        if cur_seg is None or not cur_seg["coords"]:
            return
        seg = {
            "mode": cur_seg["mode"],
            "from_lat": cur_seg["from_lat"],
            "from_lng": cur_seg["from_lng"],
            "to_lat": cur_seg["coords"][-1][0],
            "to_lng": cur_seg["coords"][-1][1],
            "distance_m": round(cur_seg["dist"], 1),
            "time_s": round(cur_seg["time"], 1),
            "name": cur_seg.get("name", ""),
            "coords": list(cur_seg["coords"]),
            "dep_time_s": round(cur_seg["dep_s"], 0),
            "arr_time_s": round(cur_seg["dep_s"] + cur_seg["time"], 0),
        }
        if cur_seg.get("line"):
            seg["line"] = cur_seg["line"]
        segments.append(seg)
        cur_seg = None

    # Connector: user click → start node
    start_lat_node, start_lng_node = _get_node_coords(G, start_node)
    dist_start = _dist_m(start_lat, start_lng, start_lat_node, start_lng_node)
    cur_time = departure_time_s
    if dist_start > 2.0:
        t = dist_start / _WALK_SPEED
        cur_seg = {
            "mode": "walk",
            "coords": [[start_lat, start_lng], [start_lat_node, start_lng_node]],
            "dist": dist_start,
            "time": t,
            "name": "Đi bộ ra ga",
            "line": "",
            "from_lat": start_lat, "from_lng": start_lng,
            "dep_s": cur_time,
        }
        all_coords.extend(cur_seg["coords"])
        total_dist += dist_start
        total_time += t
        walk_time += t
        cur_time += t
        flush()

    # Traverse edges along path, handling skipped stations
    idx = 0
    while idx < len(path) - 1:
        u = path[idx]
        v = path[idx + 1]

        # Check if we have a direct edge (normal case)
        if G.has_edge(u, v):
            edata = G[u][v]
            coords = _edge_coords(G, u, v)
            dist = edata.get("length", 0)
            tt = came_from[v][2]  # travel time stored in came_from
            mode_e = edata["mode"]
            line = edata.get("line", "")
            name = edata.get("name", "")
            idx += 1
        else:
            # Skipped station: u → (skipped) → v
            # Find the skipped node between u and v. It must be the next node in original path?
            # Actually path already contains the skipped node, but we removed it because we didn't insert.
            # Let's lookup from graph: find a rail node x such that u->x and x->v are rail edges.
            skipped_node = None
            for x in G[u]:
                if G.has_edge(x, v) and G[x][v].get("mode") == "rail" and x in skipped:
                    skipped_node = x
                    break
            if skipped_node is None:
                # Fallback: use straight line from u to v
                coords = [[_get_node_coords(G, u)[0], _get_node_coords(G, u)[1]],
                          [_get_node_coords(G, v)[0], _get_node_coords(G, v)[1]]]
                dist = _dist_m(coords[0][1], coords[0][0], coords[1][1], coords[1][0])
                tt = dist / _RAIL_SPEED  # approximation
                mode_e = "rail"
                line = ""
                name = ""
                idx += 1
            else:
                # Build coords: u -> skipped -> v
                coords = [_get_node_coords(G, u),
                          _get_node_coords(G, skipped_node),
                          _get_node_coords(G, v)]
                dist1 = G[u][skipped_node]["length"]
                dist2 = G[skipped_node][v]["length"]
                dist = dist1 + dist2
                tt = came_from[v][2]  # already combined
                mode_e = "rail"
                line = G[u][skipped_node].get("line", "")
                name = f"{G.nodes[u].get('name','')} → {G.nodes[v].get('name','')}"
                idx += 2  # because we consumed two edges

        # Merge into current segment or start new one
        if cur_seg is None or cur_seg["mode"] != mode_e:
            flush()
            u_lat, u_lng = coords[0]
            cur_seg = {
                "mode": mode_e,
                "coords": list(coords),
                "dist": dist,
                "time": tt,
                "name": name,
                "line": line,
                "from_lat": u_lat, "from_lng": u_lng,
                "dep_s": cur_time,
            }
        else:
            # Same mode: extend coords, avoiding duplicate point
            if cur_seg["coords"] and coords and cur_seg["coords"][-1] == coords[0]:
                cur_seg["coords"].extend(coords[1:])
            else:
                cur_seg["coords"].extend(coords)
            cur_seg["dist"] += dist
            cur_seg["time"] += tt
            if not cur_seg["name"] and name:
                cur_seg["name"] = name
            if not cur_seg["line"] and line:
                cur_seg["line"] = line

        # Update global coords & stats
        if all_coords and coords and all_coords[-1] == coords[0]:
            all_coords.extend(coords[1:])
        else:
            all_coords.extend(coords)
        total_dist += dist
        total_time += tt
        cur_time += tt
        if mode_e == "walk":
            walk_time += tt
        elif mode_e == "rail":
            rail_time += tt
        elif mode_e == "transfer":
            transfer_time += tt

    # Connector: end node → user destination
    end_lat_node, end_lng_node = _get_node_coords(G, end_node)
    dist_end = _dist_m(end_lat_node, end_lng_node, end_lat, end_lng)
    if dist_end > 2.0:
        t = dist_end / _WALK_SPEED
        flush()
        cur_seg = {
            "mode": "walk",
            "coords": [[end_lat_node, end_lng_node], [end_lat, end_lng]],
            "dist": dist_end,
            "time": t,
            "name": "Đi bộ tới đích",
            "line": "",
            "from_lat": end_lat_node, "from_lng": end_lng_node,
            "dep_s": cur_time,
        }
        if all_coords and all_coords[-1] == cur_seg["coords"][0]:
            all_coords.append(cur_seg["coords"][1])
        else:
            all_coords.extend(cur_seg["coords"])
        total_dist += dist_end
        total_time += t
        walk_time += t
        cur_time += t
        flush()
    else:
        flush()

    arrival_time_s = departure_time_s + total_time

    return {
        "coords":           all_coords,
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
    }