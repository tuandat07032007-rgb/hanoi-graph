"""Chỉ mục không gian của CẠNH (STRtree) — dùng chung cho snap toạ độ (snap.py) và mô hình ngập (flood.py).

Mỗi cạnh được biểu diễn bằng đúng hình dạng thật của nó (thuộc tính `geometry` nếu đường cong, nếu không
thì đoạn thẳng nối 2 đầu mút), chiếu sang mét bằng phép chiếu equirectangular quanh vĩ độ giữa của đồ thị.
Với phạm vi Hà Nội (~20.5–21.4°B) sai số khoảng cách < 0.5% — đủ cho snap/ngập (đơn vị vài chục mét).
Độ dài cạnh và heuristic vẫn tính bằng haversine (geo.py); chỉ mục này chỉ dùng để TÌM cạnh gần.

Dựng chỉ mục cho đồ thị Hà Nội mất ~15 s, sau đó mỗi truy vấn ~0.1 ms. Chỉ mục được cache theo đối tượng
đồ thị (tự giải phóng khi đồ thị bị thu hồi) và tự dựng lại khi SỐ NODE đổi. Nếu chỉ thêm/xoá CẠNH mà
không đổi số node, gọi clear_edge_index_cache(G).
"""
from __future__ import annotations

import math
import weakref

import numpy as np
import shapely
from shapely import STRtree

from .geo import EARTH_RADIUS_M

_CACHE: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_M_PER_DEG = math.radians(1.0) * EARTH_RADIUS_M


class EdgeIndex:
    """lines[i] (LineString, mét) <-> edges[i] = (u, v, key). key = 0 nếu G không phải multigraph."""

    def __init__(self, G):
        lats = [d["y"] for _, d in G.nodes(data=True)]
        self.lat0 = (min(lats) + max(lats)) / 2.0 if lats else 0.0
        self._kx = _M_PER_DEG * math.cos(math.radians(self.lat0))
        self.edges = []
        coords, parts = [], []
        multi = G.is_multigraph()
        it = G.edges(keys=True, data=True) if multi else ((u, v, 0, d) for u, v, d in G.edges(data=True))
        for i, (u, v, k, d) in enumerate(it):
            geom = d.get("geometry")
            if geom is not None:
                xy = np.asarray(geom.coords)[:, :2]
            else:
                xy = np.array([[G.nodes[u]["x"], G.nodes[u]["y"]], [G.nodes[v]["x"], G.nodes[v]["y"]]])
            if len(xy) < 2 or (len(xy) == 2 and np.allclose(xy[0], xy[1])):   # self-loop / cạnh 0 m
                xy = np.vstack([xy[:1], xy[:1] + 1e-9])
            coords.append(xy)
            parts.append(np.full(len(xy), i))
            self.edges.append((u, v, k))
        if coords:
            allxy = np.vstack(coords)
            px, py = self.project(allxy[:, 0], allxy[:, 1])
            self.lines = shapely.linestrings(np.column_stack([px, py]), indices=np.concatenate(parts))
        else:
            self.lines = np.array([], dtype=object)
        self.tree = STRtree(self.lines)
        self.n_nodes = G.number_of_nodes()

    def project(self, lng, lat):
        """lng/lat (độ) -> x/y (mét)."""
        return np.asarray(lng) * self._kx, np.asarray(lat) * _M_PER_DEG

    def point(self, lat: float, lng: float):
        x, y = self.project(lng, lat)
        return shapely.Point(float(x), float(y))

    def within(self, lat: float, lng: float, radius_m: float) -> list:
        """Danh sách (u, v, key) của mọi cạnh có ÍT NHẤT MỘT điểm cách (lat, lng) <= radius_m."""
        hits = self.tree.query(self.point(lat, lng), predicate="dwithin", distance=float(radius_m))
        return [self.edges[i] for i in hits]


def get_edge_index(G) -> EdgeIndex:
    idx = _CACHE.get(G)
    # chỉ so số node (O(1)); number_of_edges() của MultiDiGraph phải duyệt cả đồ thị (~1 s với Hà Nội)
    if idx is None or idx.n_nodes != G.number_of_nodes():
        idx = EdgeIndex(G)
        _CACHE[G] = idx
    return idx


def clear_edge_index_cache(G=None) -> None:
    """Xoá chỉ mục của G (hoặc của mọi đồ thị nếu G=None)."""
    if G is None:
        _CACHE.clear()
    else:
        _CACHE.pop(G, None)
