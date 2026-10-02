"""Cắt đồ thị nhỏ quanh 2 điểm (bounding-box + buffer) để tăng tốc tìm đường."""
from __future__ import annotations

import math
from typing import Hashable, Union

import networkx as nx

from .geo import haversine_m, node_arrays, nearest_node

Point = Union[Hashable, tuple]  # node id HOẶC (lat, lng)

_KM_PER_DEG_LAT = 111.195  # 2*pi*R/360 với R = 6371.009 km


def _resolve(G, p: Point) -> tuple[Hashable, float, float]:
    """Chuyển node id hoặc (lat, lng) thành (node, lat, lng) của node gần nhất."""
    if isinstance(p, tuple) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p):
        n = nearest_node(G, p[0], p[1])
    else:
        n = p
        if n not in G:
            raise KeyError(f"Node {n!r} không có trong đồ thị")
    return n, float(G.nodes[n]["y"]), float(G.nodes[n]["x"])


def bbox_with_buffer(lat1, lng1, lat2, lng2, buffer_km: float):
    """(south, west, north, east) bao 2 điểm, nới mỗi phía `buffer_km` (quy đổi km -> độ)."""
    south, north = min(lat1, lat2), max(lat1, lat2)
    west, east = min(lng1, lng2), max(lng1, lng2)
    dlat = buffer_km / _KM_PER_DEG_LAT
    mid_lat = math.radians((south + north) / 2.0)
    dlng = buffer_km / (_KM_PER_DEG_LAT * max(math.cos(mid_lat), 1e-6))
    return south - dlat, west - dlng, north + dlat, east + dlng


def nodes_in_bbox(G, start: Point, goal: Point, buffer_km: float = 2.0) -> set:
    """Tập node trong hộp bao (start, goal) nới `buffer_km` — KHÔNG copy đồ thị (vector hoá numpy, 1–5 ms với đồ thị Hà Nội).

    Dùng khi muốn giới hạn vùng tìm kiếm ngay trong thuật toán (bỏ qua hàng xóm không thuộc tập) thay vì
    cắt một đồ thị con bằng get_subgraph_near (copy tốn hàng trăm ms – vài giây với tuyến dài, xem benchmark).
    Lưu ý: không tự nới hộp khi mất đường — tự kiểm tra kết quả và nới buffer nếu cần.
    """
    s, slat, slng = _resolve(G, start)
    g, glat, glng = _resolve(G, goal)
    ids, lats, lngs = node_arrays(G)
    south, west, north, east = bbox_with_buffer(slat, slng, glat, glng, buffer_km)
    mask = (lats >= south) & (lats <= north) & (lngs >= west) & (lngs <= east)
    keep = set(ids[mask].tolist())
    keep.update((s, g))
    return keep


def get_subgraph_near(
    G: nx.MultiDiGraph,
    start: Point,
    goal: Point,
    buffer_km: float = 2.0,
    ensure_connected: bool = True,
    max_buffer_km: float = 50.0,
    growth: float = 2.0,
) -> nx.MultiDiGraph:
    """Đồ thị con gồm các node nằm trong hộp bao (start, goal) nới `buffer_km` mỗi phía.

    * start/goal: node id hoặc (lat, lng) — tọa độ được snap về node gần nhất (haversine).
    * Trả về BẢN SAO (có hướng, giữ nguyên thuộc tính) nên sửa được mà không ảnh hưởng G.
    * ensure_connected=True: nếu trong hộp không có đường có hướng start->goal (do hộp cắt
      mất đường vòng / đường một chiều) thì nhân buffer lên `growth` lần tới khi có đường
      hoặc chạm `max_buffer_km`; khi đó trả về đồ thị lớn nhất thử được. Nếu G gốc cũng
      không có đường thì cứ trả hộp cuối — dùng connectivity.diagnose_no_path để biết lý do.
    * Node start/goal đã snap được lưu ở sub.graph['start_node'] / ['goal_node'].
    """
    s, slat, slng = _resolve(G, start)
    g, glat, glng = _resolve(G, goal)
    ids, lats, lngs = node_arrays(G)

    buffer = float(buffer_km)
    while True:
        south, west, north, east = bbox_with_buffer(slat, slng, glat, glng, buffer)
        mask = (lats >= south) & (lats <= north) & (lngs >= west) & (lngs <= east)
        keep = set(ids[mask].tolist())
        keep.update((s, g))
        sub = G.subgraph(keep).copy()
        sub.graph.pop("_node_arrays", None)  # cache numpy của G gốc không hợp lệ cho sub
        if not ensure_connected or s == g or nx.has_path(sub, s, g):
            break
        if buffer >= max_buffer_km or len(keep) >= G.number_of_nodes():
            break
        buffer = min(buffer * growth, max_buffer_km)

    sub.graph.update(
        start_node=s, goal_node=g, buffer_km_used=buffer,
        bbox=(south, west, north, east),
        straight_line_km=haversine_m(slat, slng, glat, glng) / 1000.0,
    )
    return sub


def subgraph_stats(G, sub) -> dict:
    """Tỉ lệ thu nhỏ — để log xem việc cắt có đáng không."""
    return {
        "nodes": sub.number_of_nodes(),
        "edges": sub.number_of_edges(),
        "node_fraction": sub.number_of_nodes() / max(G.number_of_nodes(), 1),
        "edge_fraction": sub.number_of_edges() / max(G.number_of_edges(), 1),
        "buffer_km_used": sub.graph.get("buffer_km_used"),
    }
