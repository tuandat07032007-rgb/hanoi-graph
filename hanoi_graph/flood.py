"""Mô hình ngập tối thiểu: điểm ngập (lat, lng, bán kính, độ sâu) -> các cạnh bị ngập -> cạnh bị chặn theo xe.

Quy tắc: một cạnh bị NGẬP nếu có ÍT NHẤT MỘT điểm trên hình dạng thật của cạnh (geometry) nằm trong bán kính
của điểm ngập. Nếu nhiều điểm ngập phủ cùng một cạnh thì lấy độ sâu LỚN NHẤT. Xe bị CHẶN ở cạnh ngập khi
độ sâu > ngưỡng lội nước của xe (VehicleProfile.can_pass, so sánh <=).

Bản cũ chỉ xét 2 đầu mút + trung điểm cạnh. Đồ thị Hà Nội có ~4.500 cạnh dài > 600 m (dài nhất ~11 km),
nên điểm ngập bán kính 60 m nằm giữa một cạnh dài (không trùng trung điểm) bị bỏ sót. Bản này tra theo
chỉ mục không gian của cạnh (spatial.py): đúng hơn, và nhanh hơn nhiều so với duyệt 600k cạnh bằng Python.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .spatial import get_edge_index
from .vehicles import VehicleProfile


@dataclass(frozen=True)
class FloodSpot:
    id: str
    lat: float
    lng: float
    radius_m: float
    depth_cm: float


def flooded_edges(G, spots) -> dict:
    """{(u, v, key): depth_cm} cho mọi cạnh bị ngập (key = 0 nếu G không phải multigraph)."""
    idx = get_edge_index(G)
    multi = G.is_multigraph()
    out: dict = {}
    for s in spots:
        for e in idx.within(s.lat, s.lng, s.radius_m):
            u, v, k = e
            # chỉ mục có thể cũ nếu G vừa bị xoá cạnh mà số node không đổi -> bỏ cạnh không còn tồn tại
            if not (G.has_edge(u, v, k) if multi else G.has_edge(u, v)):
                continue
            out[e] = max(out.get(e, 0.0), s.depth_cm)
    return out


def blocked_edges(G, spots, profile: VehicleProfile) -> set:
    """Tập cạnh mà `profile` KHÔNG đi qua được (độ sâu ngập > ngưỡng lội nước)."""
    return {e for e, depth in flooded_edges(G, spots).items() if not profile.can_pass(depth)}


def apply_flood(G, spots, profile: VehicleProfile, as_view: bool = False):
    """Đồ thị G đã bỏ các cạnh bị chặn với phương tiện này (giữ nguyên hướng).

    as_view=False (mặc định): trả về BẢN SAO sửa được — với đồ thị Hà Nội tốn vài giây và nhiều RAM.
    as_view=True: trả về view CHỈ ĐỌC (nx.restricted_view) — tức thời, không tốn RAM; đủ cho tìm đường.
    """
    blocked = blocked_edges(G, spots, profile)
    multi = G.is_multigraph()
    if as_view:
        edges = list(blocked) if multi else [(u, v) for u, v, _ in blocked]
        return nx.restricted_view(G, [], edges)
    H = G.copy()
    H.graph.pop("_node_arrays", None)
    for u, v, key in blocked:
        if multi:
            H.remove_edge(u, v, key)
        else:
            H.remove_edge(u, v)
    return H
