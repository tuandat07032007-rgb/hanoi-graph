"""Hàm khoảng cách trên mặt cầu (haversine) — NGUỒN DUY NHẤT cho khoảng cách trong dự án.

Dùng chung cho:
  * độ dài cạnh (`recompute_edge_lengths`)
  * heuristic h(n) của A*/GBFS/BALA* (`make_heuristic`)
  * tìm node gần nhất, cắt subgraph theo buffer_km

Không dùng Euclid trên (lat, lng): ở vĩ độ Hà Nội (~21°B) 1° kinh ≈ 103.9 km
nhưng 1° vĩ ≈ 111.2 km, nên Euclid phẳng sai lệch ~7% theo phương Đông–Tây.
"""
from __future__ import annotations

import math
from typing import Callable, Hashable, Iterable, Optional

import numpy as np

# Cùng bán kính với osmnx.distance.great_circle (6_371_009 m) để độ dài cạnh
# do ta tính lại khớp với độ dài OSMnx tính sẵn (sai số ~0 m).
EARTH_RADIUS_M = 6_371_009.0

# Tốc độ tối đa dùng cho heuristic theo THỜI GIAN (km/h). Phải >= tốc độ nhanh nhất
# mà cost thực tế có thể dùng, nếu không h(n) sẽ không admissible.
DEFAULT_H_MAX_SPEED_KPH = 120.0


def haversine_m(lat1, lng1, lat2, lng2):
    """Khoảng cách great-circle (mét). Nhận scalar hoặc numpy array (broadcast)."""
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = phi2 - phi1
    dlmb = np.radians(lng2) - np.radians(lng1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlmb / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    d = 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
    return float(d) if np.ndim(d) == 0 else d


def haversine_km(lat1, lng1, lat2, lng2):
    return haversine_m(lat1, lng1, lat2, lng2) / 1000.0


def node_latlng(G, n: Hashable) -> tuple[float, float]:
    """(lat, lng) của node OSMnx (thuộc tính 'y' = lat, 'x' = lng)."""
    d = G.nodes[n]
    return float(d["y"]), float(d["x"])


def node_distance_m(G, a: Hashable, b: Hashable) -> float:
    la, lo = node_latlng(G, a)
    lb, lp = node_latlng(G, b)
    return haversine_m(la, lo, lb, lp)


def recompute_edge_lengths(G, attr: str = "length") -> int:
    """Tính lại `length` (mét) của MỌI cạnh bằng haversine giữa 2 đầu mút.

    Lưu ý: cạnh cong (đã simplify) có geometry dài hơn đoạn thẳng đầu–cuối. Vì vậy
    nếu cạnh có 'geometry' (LineString) ta cộng haversine dọc theo các đỉnh của nó;
    nếu không thì dùng đoạn thẳng đầu–cuối. Trả về số cạnh đã cập nhật.
    """
    count = 0
    for u, v, data in G.edges(data=True):
        geom = data.get("geometry")
        if geom is not None:
            xs, ys = geom.xy  # x = lng, y = lat
            xs = np.asarray(xs)
            ys = np.asarray(ys)
            data[attr] = float(np.sum(haversine_m(ys[:-1], xs[:-1], ys[1:], xs[1:])))
        else:
            lu, ou = node_latlng(G, u)
            lv, ov = node_latlng(G, v)
            data[attr] = haversine_m(lu, ou, lv, ov)
        count += 1
    return count


def path_length_m(G, path: Iterable[Hashable], weight: str = "length") -> float:
    """Tổng độ dài (m) của một đường đi; với cạnh song song lấy cạnh ngắn nhất."""
    path = list(path)
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        if not G.has_edge(u, v):
            raise ValueError(f"Không có cạnh có hướng {u} -> {v} (sai chiều đường một chiều?)")
        edge = G[u][v]
        if G.is_multigraph():
            total += min(d.get(weight, math.inf) for d in edge.values())
        else:
            total += edge.get(weight, math.inf)
    return total


def make_heuristic(
    G,
    goal: Hashable,
    mode: str = "distance",
    max_speed_kph: Optional[float] = None,
) -> Callable[[Hashable], float]:
    """Trả về h(n) = khoảng cách haversine từ n tới `goal`.

    mode="distance": đơn vị mét — admissible & consistent khi cost = độ dài cạnh (m).
    mode="time":     đơn vị giây = dist / v_max — admissible khi cost = thời gian đi (s)
                     và không cạnh nào nhanh hơn `max_speed_kph`.
    """
    glat, glng = node_latlng(G, goal)
    if mode == "distance":
        def h(n: Hashable) -> float:
            lat, lng = node_latlng(G, n)
            return haversine_m(lat, lng, glat, glng)
    elif mode == "time":
        v_ms = (max_speed_kph or DEFAULT_H_MAX_SPEED_KPH) * 1000.0 / 3600.0

        def h(n: Hashable) -> float:
            lat, lng = node_latlng(G, n)
            return haversine_m(lat, lng, glat, glng) / v_ms
    else:
        raise ValueError("mode phải là 'distance' hoặc 'time'")
    return h


def nearest_node(G, lat: float, lng: float, return_dist: bool = False):
    """Node gần (lat, lng) nhất theo haversine (vector hoá bằng numpy)."""
    ids, lats, lngs = node_arrays(G)
    d = haversine_m(lat, lng, lats, lngs)
    i = int(np.argmin(d))
    return (ids[i], float(d[i])) if return_dist else ids[i]


def node_arrays(G):
    """(ids, lats, lngs) dạng numpy; cache theo (số node) trong G.graph để tái dùng."""
    cache = G.graph.get("_node_arrays")
    if cache is not None and cache[0] == G.number_of_nodes():
        return cache[1], cache[2], cache[3]
    ids = np.fromiter(G.nodes, dtype=object, count=G.number_of_nodes())
    lats = np.fromiter((d["y"] for _, d in G.nodes(data=True)), dtype=float, count=len(ids))
    lngs = np.fromiter((d["x"] for _, d in G.nodes(data=True)), dtype=float, count=len(ids))
    G.graph["_node_arrays"] = (G.number_of_nodes(), ids, lats, lngs)
    return ids, lats, lngs
