"""Kiểm tra liên thông — tránh báo sai "không tìm thấy đường" do node cô lập / đảo dữ liệu OSM.

Với đồ thị CÓ HƯỚNG, điều kiện đúng để mọi cặp (s, g) đều đi được là **liên thông mạnh**
(strongly connected), không phải liên thông yếu. Hai node cùng thành phần liên thông yếu
nhưng khác thành phần liên thông mạnh nghĩa là có đường một chiều đi được chiều này mà
không quay lại được (vd. khu vực chỉ có đường vào).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable

import networkx as nx

from .directed import require_directed


@dataclass
class ConnectivityReport:
    n_nodes: int
    n_edges: int
    n_weak_components: int
    n_strong_components: int
    largest_strong_size: int
    largest_strong_fraction: float
    isolated_nodes: list = field(default_factory=list)       # không có cạnh vào/ra nào
    small_strong_components: list = field(default_factory=list)  # [(size, sample_node)], sắp giảm dần

    @property
    def is_strongly_connected(self) -> bool:
        return self.n_strong_components == 1

    def summary(self) -> str:
        return (
            f"{self.n_nodes:,} node, {self.n_edges:,} cạnh | "
            f"{self.n_weak_components} TP liên thông yếu, {self.n_strong_components} TP liên thông mạnh | "
            f"TP mạnh lớn nhất = {self.largest_strong_size:,} node "
            f"({self.largest_strong_fraction:.2%}) | "
            f"{len(self.isolated_nodes)} node cô lập"
        )


def scc_labels(G) -> dict:
    """node -> id thành phần liên thông mạnh (0 = lớn nhất). Tính 1 lần, dùng lại nhiều lần."""
    require_directed(G)
    comps = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    labels = {}
    for i, comp in enumerate(comps):
        for n in comp:
            labels[n] = i
    return labels


def check_connectivity(G, max_small_listed: int = 20) -> ConnectivityReport:
    require_directed(G)
    strong = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    n = G.number_of_nodes()
    isolated = [v for v in G.nodes if G.in_degree(v) == 0 and G.out_degree(v) == 0]
    small = [(len(c), next(iter(c))) for c in strong[1:max_small_listed + 1]]
    return ConnectivityReport(
        n_nodes=n,
        n_edges=G.number_of_edges(),
        n_weak_components=nx.number_weakly_connected_components(G),
        n_strong_components=len(strong),
        largest_strong_size=len(strong[0]) if strong else 0,
        largest_strong_fraction=(len(strong[0]) / n) if n and strong else 0.0,
        isolated_nodes=isolated,
        small_strong_components=small,
    )


def keep_largest_scc(G):
    """Bản sao chỉ gồm thành phần liên thông mạnh lớn nhất (loại "đảo" và bẫy một chiều)."""
    require_directed(G)
    biggest = max(nx.strongly_connected_components(G), key=len)
    H = G.subgraph(biggest).copy()
    H.graph.pop("_node_arrays", None)
    return H


def diagnose_no_path(G, start: Hashable, goal: Hashable, island_max: int = 50) -> str:
    """Giải thích vì sao không có đường start->goal (hoặc 'OK' nếu có).

    Phân biệt các nguyên nhân để UI không báo chung chung "không tìm thấy đường":
      - node không thuộc đồ thị
      - node nằm trong "đảo" nhỏ (< island_max node, tách rời hẳn — thường là lỗi dữ liệu OSM)
      - 2 node thuộc 2 thành phần liên thông yếu lớn khác nhau
      - cùng liên thông yếu nhưng không có đường có hướng (bẫy đường một chiều)
    Chỉ chạy khi KHÔNG có đường nên chi phí duyệt thành phần không ảnh hưởng đường đi bình thường.
    """
    require_directed(G)
    for name, n in (("start", start), ("goal", goal)):
        if n not in G:
            return f"{name} ({n!r}) không có trong đồ thị"
    if nx.has_path(G, start, goal):
        return "OK"
    U = G.to_undirected(as_view=True)
    comp_s = nx.node_connected_component(U, start)
    if goal in comp_s:
        return "cùng thành phần liên thông yếu nhưng không có đường có hướng start->goal (bẫy đường một chiều)"
    comp_g = nx.node_connected_component(U, goal)
    if len(comp_s) < island_max:
        return f"start nằm trong đảo cô lập ({len(comp_s)} node) — nhiều khả năng lỗi dữ liệu OSM, nên snap sang node khác"
    if len(comp_g) < island_max:
        return f"goal nằm trong đảo cô lập ({len(comp_g)} node) — nhiều khả năng lỗi dữ liệu OSM, nên snap sang node khác"
    return "start và goal thuộc 2 thành phần liên thông yếu lớn khác nhau (không nối với nhau kể cả bỏ qua chiều)"
