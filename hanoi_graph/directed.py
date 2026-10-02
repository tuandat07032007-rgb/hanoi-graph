"""Đường một chiều: giữ đồ thị CÓ HƯỚNG đúng như OSM.

OSMnx (graph_from_*) luôn trả về `MultiDiGraph`:
  * đường hai chiều  -> 2 cạnh ngược nhau (u->v và v->u, cạnh ngược có reversed=True)
  * đường một chiều  -> chỉ 1 cạnh theo chiều OSM way (oneway=True)
Nên KHÔNG được chuyển sang `nx.Graph`/`to_undirected()` — làm vậy sẽ mất chiều đi thật.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


def require_directed(G) -> None:
    """Báo lỗi nếu G không có hướng (tránh vô tình dùng đồ thị vô hướng)."""
    if not G.is_directed():
        raise TypeError(
            "Đồ thị phải là DiGraph/MultiDiGraph. Đồ thị vô hướng làm mất chiều đường một chiều."
        )


@dataclass
class OnewayReport:
    n_edges: int
    n_edges_with_reverse: int      # cạnh có cạnh ngược (đường hai chiều)
    n_edges_oneway: int            # cạnh KHÔNG có cạnh ngược (một chiều thực sự trong đồ thị)
    n_tagged_oneway: int           # cạnh có thuộc tính oneway=True
    n_tagged_oneway_but_has_reverse: int  # nghi vấn: gắn oneway nhưng vẫn có cạnh ngược

    @property
    def oneway_fraction(self) -> float:
        return self.n_edges_oneway / self.n_edges if self.n_edges else 0.0


def _truthy(v) -> bool:
    if isinstance(v, (list, tuple, set)):
        return any(_truthy(x) for x in v)
    return str(v).strip().lower() in {"true", "yes", "1", "-1"}


def oneway_report(G) -> OnewayReport:
    """Thống kê đường một chiều để kiểm tra nhanh dữ liệu đã nạp."""
    require_directed(G)
    n = with_rev = tagged = suspicious = 0
    for u, v, data in G.edges(data=True):
        n += 1
        has_rev = G.has_edge(v, u) and u != v
        with_rev += has_rev
        if _truthy(data.get("oneway", False)):
            tagged += 1
            # cạnh oneway có cạnh ngược có thể là 2 way song song khác nhau -> chỉ là cảnh báo
            suspicious += has_rev
    return OnewayReport(n, with_rev, n - with_rev, tagged, suspicious)


def to_digraph(G: nx.MultiDiGraph, weight: str = "length") -> nx.DiGraph:
    """Gộp cạnh song song của MultiDiGraph thành DiGraph (giữ cạnh có `weight` nhỏ nhất).

    Dùng cho thuật toán cần DiGraph đơn giản. Giữ nguyên HƯỚNG. Mỗi cạnh lưu thêm
    'key' (khoá cạnh gốc trong MultiDiGraph) để truy ngược khi cần.
    """
    require_directed(G)
    D = nx.DiGraph()
    D.graph.update({k: v for k, v in G.graph.items() if not k.startswith("_")})
    D.add_nodes_from(G.nodes(data=True))
    for u, v, key, data in G.edges(keys=True, data=True):
        w = data.get(weight, float("inf"))
        if not D.has_edge(u, v) or w < D[u][v].get(weight, float("inf")):
            D.add_edge(u, v, key=key, **data)
    return D
