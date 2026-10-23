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

    if res.node == edge_key[1]:
        dist_to_v = along_m
        dist_to_u = max(0.0, edge_len - dist_to_v)
    else:
        dist_to_u = along_m
        dist_to_v = max(0.0, edge_len - dist_to_u)

    return edge_key, dist_to_u, dist_to_v


def snap_coord_to_edge(G: nx.Graph, lat: float, lng: float) -> EdgeKey:
    """Trả về khóa của cạnh gần tọa độ (lat, lng) nhất."""
    edge_key, _, _ = snap_coord_to_edge_with_offset(G, lat, lng)
    return edge_key


@dataclass(init=False)
class FloodSource:
    """Đối tượng nguồn ngập động theo thời gian."""
    lat: float
    lng: float
    f0: float
    k: float
    id: str
    lon: float | None = field(default=None, repr=False)

    radius: float = field(default=0.0, init=False)
    edge_0: EdgeKey | None = field(default=None, init=False)
    dist_to_u0: float = field(default=0.0, init=False)
    dist_to_v0: float = field(default=0.0, init=False)
    district: str = field(default="Default", init=False)
    drain_rate: float = field(default=DRAINAGE_RATES["Default"], init=False)
    _custom_drain_rate: bool = field(default=False, init=False, repr=False)
    _auto_drain_rate: float = field(default=DRAINAGE_RATES["Default"], init=False, repr=False)

    def __init__(
        self,
        lat: float,
        lng: float = 0.0,
        f0: float = 0.0,
        k: float = RADIUS_K,
        id: str = "",
        *,
        lon: float | None = None,
        depth_cm: float | None = None,
        radius: float | None = None,
        radius_m: float | None = None,
        district: str = "Default",
        drain_rate: float | None = None,
    ) -> None:
        self.lat = float(lat)
        if lon is not None and lng == 0.0:
            self.lng = float(lon)
        else:
            self.lng = float(lng)
        self.lon = self.lng

        actual_f0 = float(depth_cm) if depth_cm is not None else float(f0)
        self.f0 = actual_f0

        explicit_radius = radius if radius is not None else radius_m
        if explicit_radius is not None:
            r_val = max(0.0, float(explicit_radius))
            self.k = (r_val / math.sqrt(actual_f0)) if actual_f0 > 0.0 else float(k)
            self.radius = r_val
        else:
            self.k = float(k)
            self.radius = self.radius_at_depth(self.f0)

        self.id = id if id else f"flood_{self.lat:.5f}_{self.lng:.5f}"
        self.edge_0 = None
        self.dist_to_u0 = 0.0
        self.dist_to_v0 = 0.0
        self.district = district if district else "Default"

        if drain_rate is not None:
            self.drain_rate = float(drain_rate)
            self._custom_drain_rate = True
            self._auto_drain_rate = self.drain_rate
        else:
            self.drain_rate = get_drain_rate_for_district(self.district)
            self._custom_drain_rate = False
            self._auto_drain_rate = self.drain_rate

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
        """
        Gắn tọa độ vào cạnh e_0 bằng `snap_point` và lấy tốc độ rút nước từ `get_district`.
        Bảo toàn `drain_rate` nếu người dùng đã chủ động thiết lập giá trị tùy chỉnh trước đó.
        """
        user_modified_rate = self._custom_drain_rate or (self.drain_rate != self._auto_drain_rate)

        self.edge_0, self.dist_to_u0, self.dist_to_v0 = snap_coord_to_edge_with_offset(
            G, self.lat, self.lng
        )
        district_name = get_district_fn(self.lat, self.lng)
        if district_name and (district_name != "Default" or self.district == "Default"):
            self.district = district_name
        elif not self.district:
            self.district = "Default"

        if not user_modified_rate:
            self.drain_rate = get_drain_rate_for_district(self.district)
            self._auto_drain_rate = self.drain_rate

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