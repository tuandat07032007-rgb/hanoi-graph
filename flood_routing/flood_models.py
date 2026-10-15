from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import math
import networkx as nx

from hanoi_graph.districts import get_district as default_get_district
from hanoi_graph.geo import node_distance_m
from hanoi_graph.snap import snap_point

from .flood_config import (
    DRAINAGE_RATES,
    RADIUS_K,
    EdgeKey,
    get_drain_rate_for_district,
)


def _edge_length_m(G: nx.Graph, edge_key: EdgeKey) -> float:
    """
    Lấy độ dài cạnh (mét) từ thuộc tính 'length' hoặc tính bằng `node_distance_m`.
    Xử lý an toàn cả khóa 2 phần tử `(u, v)` và 3 phần tử `(u, v, k)` trên MultiDiGraph.
    """
    if G.is_multigraph():
        if len(edge_key) == 3:
            u, v, k = edge_key
            data = G.edges[u, v, k]
        else:
            u, v = edge_key[0], edge_key[1]
            data = min(
                G[u][v].values(),
                key=lambda d: float(d.get("length", float("inf"))),
            )
    else:
        u, v = edge_key[0], edge_key[1]
        data = G.edges[u, v]

    if "length" in data:
        return float(data["length"])
    return node_distance_m(G, u, v)


def snap_coord_to_edge_with_offset(
    G: nx.Graph,
    lat: float,
    lng: float,
) -> tuple[EdgeKey, float, float]:
    """
    Ánh xạ tọa độ (lat, lng) vào cạnh gần nhất bằng `hanoi_graph.snap.snap_point`.
    Trả về: (edge_key, dist_to_u_meters, dist_to_v_meters) chính xác theo `res.node` và `res.along_m`.
    """
    if G.number_of_edges() == 0:
        raise ValueError("Đồ thị G không có cạnh nào để ánh xạ điểm ngập!")

    is_multi = G.is_multigraph()
    res = snap_point(G, lat, lng, role="any")
    raw_edge = res.edge

    if is_multi:
        edge_key: EdgeKey = (
            raw_edge if len(raw_edge) == 3 else (raw_edge[0], raw_edge[1], 0)
        )
    else:
        edge_key = (raw_edge[0], raw_edge[1])

    edge_len = _edge_length_m(G, edge_key)
    along_m = max(0.0, min(edge_len, float(res.along_m)))

    # `res.along_m` là khoảng cách dọc cạnh tính tới `res.node` (đầu mút gần hơn)
    if res.node == edge_key[1]:  # Điểm ngập nằm gần đầu v hơn đầu u
        dist_to_v = along_m
        dist_to_u = max(0.0, edge_len - dist_to_v)
    else:  # Điểm ngập nằm gần đầu u hơn đầu v
        dist_to_u = along_m
        dist_to_v = max(0.0, edge_len - dist_to_u)

    return edge_key, dist_to_u, dist_to_v


def snap_coord_to_edge(G: nx.Graph, lat: float, lng: float) -> EdgeKey:
    """Trả về khóa của cạnh gần tọa độ (lat, lng) nhất."""
    edge_key, _, _ = snap_coord_to_edge_with_offset(G, lat, lng)
    return edge_key


@dataclass
class FloodSource:
    """Đối tượng nguồn ngập động theo thời gian."""
    lat: float
    lng: float = 0.0
    f0: float = 0.0  # Độ sâu ngập ban đầu tại tâm (cm)
    k: float = RADIUS_K
    id: str = ""
    lon: float | None = field(default=None, repr=False)

    radius: float = field(default=0.0, init=False)
    edge_0: EdgeKey | None = field(default=None, init=False)
    dist_to_u0: float = field(default=0.0, init=False)
    dist_to_v0: float = field(default=0.0, init=False)
    district: str = field(default="Default", init=False)
    drain_rate: float = field(default=DRAINAGE_RATES["Default"], init=False)

    def __post_init__(self) -> None:
        if self.lon is not None and self.lng == 0.0:
            self.lng = float(self.lon)
        self.lon = self.lng

        if not self.id:
            self.id = f"flood_{self.lat:.5f}_{self.lng:.5f}"

        self.radius = self.radius_at_depth(self.f0)
        if self.drain_rate == DRAINAGE_RATES["Default"]:
            self.drain_rate = get_drain_rate_for_district(self.district)

    @property
    def radius_m(self) -> float:
        return self.radius

    @property
    def depth_cm(self) -> float:
        return self.f0

    def radius_at_depth(self, depth_cm: float) -> float:
        """Công thức bán kính động: R = k * sqrt(F_0)."""
        if depth_cm <= 0.0 or self.k <= 0.0:
            return 0.0
        return self.k * math.sqrt(depth_cm)

    def bind_to_graph(
        self,
        G: nx.Graph,
        get_district_fn: Callable[[float, float], str] = default_get_district,
    ) -> None:
        """Gắn tọa độ vào cạnh e_0 bằng `snap_point` và lấy tốc độ rút nước từ `get_district`."""
        self.edge_0, self.dist_to_u0, self.dist_to_v0 = snap_coord_to_edge_with_offset(
            G, self.lat, self.lng
        )
        district_name = get_district_fn(self.lat, self.lng)
        self.district = district_name if district_name else "Default"
        self.drain_rate = get_drain_rate_for_district(self.district)

    def f0_at_time(self, t: float) -> float:
        """Công thức rút nước theo thời gian: F_0(e_0, t) = max(0, F_0 - r(area) * t)."""
        if t <= 0.0:
            return max(0.0, self.f0)
        return max(0.0, self.f0 - self.drain_rate * t)

    def radius_at_time(
        self, t: float, override_r: float | None = None, shrink: bool = False
    ) -> float:
        """Tính bán kính vùng ngập tại thời điểm t."""
        f_now = self.f0_at_time(t)
        if f_now <= 0.0:
            return 0.0
        base_r = override_r if override_r is not None else self.radius
        if not shrink or self.f0 <= 0.0:
            return base_r
        return base_r * math.sqrt(f_now / self.f0)