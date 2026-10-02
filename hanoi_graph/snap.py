"""Snap toạ độ bất kỳ (lat, lng) vào đồ thị — theo CẠNH gần nhất, đúng chiều đường một chiều.

Vì sao không dùng nearest_node? Sau simplify, node chỉ còn ở nút giao: đồ thị Hà Nội có hàng nghìn cạnh
dài > 600 m (dài nhất ~11 km). Một điểm nằm sát đường dài ở ngoại thành vẫn có thể cách node gần nhất
hàng trăm mét, và node gần nhất có thể thuộc con đường KHÁC. Snap theo cạnh đo đúng "điểm cách đường bao xa".

Chọn node theo vai trò (role):
  * "start": từ điểm trên cạnh u->v chỉ đi tiếp được về v  => ứng viên là đầu CUỐI các cạnh gần nhất
  * "goal":  muốn tới điểm trên cạnh u->v phải đi từ u      => ứng viên là đầu ĐẦU các cạnh gần nhất
  * "any":   cả hai đầu
Đường hai chiều có 2 cạnh ngược nhau nên ứng viên gồm cả u và v -> chọn đầu gần hơn dọc theo đường.
Đường một chiều thì bị ép theo chiều: điểm xuất phát giữa phố một chiều phải đi xuôi chiều ra đầu kia.

Kết quả KHÔNG báo lỗi khi điểm xa đường (người dùng bấm giữa hồ vẫn cần có đường đi): xem `warning`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Optional

from .geo import haversine_m
from .spatial import clear_edge_index_cache, get_edge_index

DEFAULT_WARN_M = 300.0
_TIE_TOL_M = 0.5            # các cạnh cách điểm trong khoảng d_min + 0.5 m coi như cùng gần nhất (cạnh xuôi/ngược)


@dataclass(frozen=True)
class SnapResult:
    node: Hashable              # node dùng làm start/goal cho thuật toán
    offroad_m: float            # khoảng cách từ điểm tới con đường gần nhất (vuông góc)
    along_m: float              # quãng đường dọc theo cạnh từ chỗ chiếu tới `node` (chưa tính trong đường đi)
    node_dist_m: float          # khoảng cách thẳng (haversine) từ điểm tới `node`
    edge: tuple                 # (u, v, key) cạnh được snap vào
    warning: Optional[str]      # khác None nếu offroad_m > warn_m

    @property
    def ok(self) -> bool:
        return self.warning is None


def clear_snap_index_cache(G=None) -> None:
    """Giữ tên cũ cho tương thích — chỉ mục cạnh nay dùng chung với flood.py (spatial.py)."""
    clear_edge_index_cache(G)


def snap_point(G, lat: float, lng: float, role: str = "any", warn_m: float = DEFAULT_WARN_M) -> SnapResult:
    """Snap (lat, lng) vào cạnh gần nhất của G rồi chọn node theo `role` ("start" | "goal" | "any").

    Lần gọi đầu trên một đồ thị dựng chỉ mục không gian (đồ thị Hà Nội: ~15 giây), các lần sau
    dùng lại (cache theo đối tượng G, tự dựng lại nếu số node đổi; nếu chỉ sửa CẠNH của G thì gọi
    clear_snap_index_cache(G)). Snap trên đồ thị sẽ chạy
    thuật toán (vd. đồ thị đã lọc theo xe), không snap trên G gốc rồi dùng cho đồ thị khác.
    """
    if role not in ("start", "goal", "any"):
        raise ValueError("role phải là 'start', 'goal' hoặc 'any'")
    idx = get_edge_index(G)
    pt = idx.point(lat, lng)
    _, dist = idx.tree.query_nearest(pt, return_distance=True)
    d_min = float(dist[0])
    cand_edges = idx.tree.query(pt, predicate="dwithin", distance=d_min + _TIE_TOL_M)

    best = None   # (along_m, node, edge_tuple)
    for ei in cand_edges:
        line = idx.lines[ei]
        u, v, k = idx.edges[ei]
        t = line.project(pt)                     # mét tính từ đầu u dọc theo cạnh
        options = []
        if role in ("start", "any"):
            options.append((line.length - t, v))
        if role in ("goal", "any"):
            options.append((t, u))
        for along, node in options:
            if best is None or along < best[0]:
                best = (along, node, (u, v, k))

    along, node, edge = best
    nd = G.nodes[node]
    node_dist = haversine_m(lat, lng, nd["y"], nd["x"])
    warning = None
    if d_min > warn_m:
        warning = f"điểm ({lat:.5f}, {lng:.5f}) cách đường gần nhất {d_min:.0f} m (> {warn_m:.0f} m)"
    return SnapResult(node=node, offroad_m=d_min, along_m=float(along), node_dist_m=node_dist,
                      edge=edge, warning=warning)


def snap_pair(G, start: tuple, goal: tuple, warn_m: float = DEFAULT_WARN_M):
    """Tiện ích: snap cặp (lat, lng) đi/đến với đúng vai trò. Trả về (SnapResult start, SnapResult goal)."""
    return (snap_point(G, start[0], start[1], role="start", warn_m=warn_m),
            snap_point(G, goal[0], goal[1], role="goal", warn_m=warn_m))
