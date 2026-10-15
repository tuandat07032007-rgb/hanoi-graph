from __future__ import annotations

from collections.abc import Callable, Hashable
import heapq
from typing import Any
import networkx as nx

from hanoi_graph.geo import node_distance_m
from hanoi_graph.spatial import get_edge_index
from hanoi_graph.vehicles import VehicleProfile, get_profile

from .flood_config import DEFAULT_WEIGHT_ATTR, EdgeKey
from .flood_models import FloodSource, default_get_district


class SpreadEntry:
    """Lưu kết quả tiền xử lý của một nguồn ngập trên một cạnh."""
    __slots__ = ("source", "dist_e", "base_r", "alpha_0")

    def __init__(self, source: FloodSource, dist_e: float, base_r: float) -> None:
        self.source = source
        self.dist_e = dist_e
        self.base_r = base_r
        self.alpha_0 = max(0.0, 1.0 - (dist_e / base_r)) if base_r > 0.0 else 0.0

    def __iter__(self):
        """Hỗ trợ tuple-unpacking `for src, alpha in influences:`."""
        yield self.source
        yield self.alpha_0


SpreadCache = dict[EdgeKey, list[SpreadEntry]]


def _resolve_profile(profile: VehicleProfile | str | float) -> Any:
    """Chuẩn hóa tham số profile: nhận tên xe (str), đối tượng VehicleProfile, hoặc ngưỡng cm (float)."""
    if isinstance(profile, str):
        return get_profile(profile)
    return profile


def _can_vehicle_pass(profile_obj: Any, depth_cm: float) -> bool:
    """Kiểm tra phương tiện có vượt qua được mức ngập depth_cm hay không."""
    if hasattr(profile_obj, "can_pass"):
        return bool(profile_obj.can_pass(depth_cm))
    if hasattr(profile_obj, "effective_wading_cm"):
        return depth_cm <= float(profile_obj.effective_wading_cm)
    if hasattr(profile_obj, "max_wading_depth_cm"):
        return depth_cm <= float(profile_obj.max_wading_depth_cm)
    return depth_cm <= float(profile_obj)


def _dijkstra_with_initial_offsets(
    G_undir: nx.Graph,
    init_boundary: list[tuple[Hashable, float]],
    cutoff: float,
    weight: str,
) -> dict[Hashable, float]:
    """
    Multi-source Dijkstra với khoảng cách khởi tạo tại 2 đầu mút u0, v0 từ `SnapResult.along_m`.
    """
    dists: dict[Hashable, float] = {}
    pq: list[tuple[float, int, Hashable]] = []
    counter = 0

    for node, init_d in init_boundary:
        if init_d <= cutoff and (node not in dists or init_d < dists[node]):
            dists[node] = init_d
            counter += 1
            heapq.heappush(pq, (init_d, counter, node))

    is_multi = G_undir.is_multigraph()

    while pq:
        d_u, _, u = heapq.heappop(pq)
        if d_u > dists.get(u, float("inf")):
            continue

        for v, edge_atlas in G_undir[u].items():
            if is_multi:
                w = min(float(edata.get(weight, 1.0)) for edata in edge_atlas.values())
            else:
                w = float(edge_atlas.get(weight, 1.0))

            new_d = d_u + w
            if new_d <= cutoff and new_d < dists.get(v, float("inf")):
                dists[v] = new_d
                counter += 1
                heapq.heappush(pq, (new_d, counter, v))

    return dists


def compute_flood_spread(
    G: nx.Graph,
    sources: list[FloodSource],
    R: float | None = None,
    get_district_fn: Callable[[float, float], str] = default_get_district,
    weight: str = DEFAULT_WEIGHT_ATTR,
    use_endpoint_offset: bool = True,
) -> SpreadCache:
    """
    Chạy 1 lần khi user chốt điểm nguồn ngập.
    Kết hợp Multi-source Dijkstra trên mạng lưới và kiểm tra hình học `idx.within(lat, lng, radius_m)`.
    """
    spread_cache: SpreadCache = {}
    if not sources:
        return spread_cache

    is_multi = G.is_multigraph()
    G_undir = G.to_undirected(as_view=True)
    idx = get_edge_index(G)

    for src in sources:
        source_r = R if R is not None else src.radius
        if source_r <= 0.0:
            continue

        src.bind_to_graph(G, get_district_fn=get_district_fn)
        assert src.edge_0 is not None

        u0, v0 = src.edge_0[0], src.edge_0[1]
        init_u0 = src.dist_to_u0 if use_endpoint_offset else 0.0
        init_v0 = src.dist_to_v0 if use_endpoint_offset else 0.0

        node_dists = _dijkstra_with_initial_offsets(
            G_undir,
            init_boundary=[(u0, init_u0), (v0, init_v0)],
            cutoff=source_r,
            weight=weight,
        )

        spatial_edges: set[EdgeKey] | None = None
        if idx is not None and hasattr(idx, "within"):
            within_edges = idx.within(src.lat, src.lng, source_r)
            spatial_edges = (
                set(within_edges)
                if is_multi
                else {(e[0], e[1]) for e in within_edges}
            )

        visited_edges: set[EdgeKey] = set()
        candidate_nodes = set(node_dists.keys()) | {u0, v0}

        for u in candidate_nodes:
            if is_multi:
                inc_edges = list(G.out_edges(u, keys=True)) + list(G.in_edges(u, keys=True))  # type: ignore[attr-defined]
            else:
                inc_edges = list(G.out_edges(u)) + list(G.in_edges(u))  # type: ignore[attr-defined]

            for item in inc_edges:
                edge_key: EdgeKey = item if is_multi else (item[0], item[1])
                if edge_key in visited_edges:
                    continue
                visited_edges.add(edge_key)

                u_e, v_e = edge_key[0], edge_key[1]

                if (u_e == u0 and v_e == v0) or (u_e == v0 and v_e == u0):
                    dist_e = 0.0
                else:
                    if spatial_edges is not None and edge_key not in spatial_edges:
                        continue
                    dist_e = min(
                        node_dists.get(u_e, float("inf")),
                        node_dists.get(v_e, float("inf")),
                    )

                if dist_e < source_r:
                    entry = SpreadEntry(source=src, dist_e=dist_e, base_r=source_r)
                    if entry.alpha_0 > 0.0:
                        spread_cache.setdefault(edge_key, []).append(entry)

    return spread_cache


def flood_at_time(
    spread_cache: SpreadCache,
    t: float,
    shrink_radius: bool = False,
) -> dict[EdgeKey, float]:
    """
    Tính mức ngập F(e, t) tại thời điểm t với chi phí O(1) trên mỗi cạnh ngập.
    Dùng max() giữa các nguồn chồng lấn, không cộng dồn.
    """
    flood_map: dict[EdgeKey, float] = {}
    if not spread_cache:
        return flood_map

    f0_now: dict[str, float] = {}

    for edge_key, influences in spread_cache.items():
        max_f = 0.0
        for item in influences:
            if isinstance(item, SpreadEntry):
                src = item.source
                if src.id not in f0_now:
                    f0_now[src.id] = src.f0_at_time(t)
                f_center = f0_now[src.id]
                if f_center <= 0.0:
                    continue

                if shrink_radius:
                    r_now = src.radius_at_time(t, override_r=item.base_r, shrink=True)
                    alpha = max(0.0, 1.0 - (item.dist_e / r_now)) if r_now > 0.0 else 0.0
                else:
                    alpha = item.alpha_0

                f_val = f_center * alpha
            else:
                src, alpha = item
                if src.id not in f0_now:
                    f0_now[src.id] = src.f0_at_time(t)
                f_val = f0_now[src.id] * alpha

            if f_val > max_f:
                max_f = f_val

        if max_f > 0.0:
            flood_map[edge_key] = max_f

    return flood_map


def blocked_edges_at_time(
    H: nx.Graph,
    spread_cache: SpreadCache,
    t: float,
    profile: VehicleProfile | str | float,
    shrink_radius: bool = False,
) -> set[EdgeKey]:
    """Xác định các cạnh trên đồ thị phương tiện H bị chặn tại thời điểm t theo ngưỡng ngập của `profile`."""
    prof_obj = _resolve_profile(profile)
    flood_map = flood_at_time(spread_cache, t=t, shrink_radius=shrink_radius)
    is_h_multi = H.is_multigraph()
    blocked: set[EdgeKey] = set()

    for edge_key, depth_cm in flood_map.items():
        if not _can_vehicle_pass(prof_obj, depth_cm):
            u, v = edge_key[0], edge_key[1]
            if is_h_multi:
                if len(edge_key) == 3 and H.has_edge(u, v, edge_key[2]):  # type: ignore[misc]
                    blocked.add((u, v, edge_key[2]))
                elif H.has_edge(u, v):
                    for k in H[u][v]:
                        blocked.add((u, v, k))
            else:
                if H.has_edge(u, v):
                    blocked.add((u, v))

    return blocked


def apply_dynamic_flood(
    H: nx.Graph,
    spread_cache_or_sources: SpreadCache | list[FloodSource],
    t: float,
    profile: VehicleProfile | str | float,
    shrink_radius: bool = False,
    as_view: bool = True,
) -> nx.Graph:
    """
    Trả về đồ thị (mặc định là `nx.restricted_view` chỉ đọc) đã loại bỏ các cạnh ngập quá ngưỡng xe tại thời điểm t.
    Nếu nhận vào `list[FloodSource]`, hàm tự động gọi `compute_flood_spread` để đảm bảo nhất quán 100%
    mô hình suy giảm tuyến tính theo mạng lưới đường bộ.
    """
    prof_obj = _resolve_profile(profile)

    if isinstance(spread_cache_or_sources, list):
        spread_cache = compute_flood_spread(H, spread_cache_or_sources)
    else:
        spread_cache = spread_cache_or_sources

    blocked = blocked_edges_at_time(
        H, spread_cache, t=t, profile=prof_obj, shrink_radius=shrink_radius
    )
    if not blocked:
        return H if as_view else H.copy()

    multi = H.is_multigraph()
    edges: list[Any] = list(blocked) if multi else [(e[0], e[1]) for e in blocked]
    view = nx.restricted_view(H, [], edges)
    return view if as_view else view.copy()
