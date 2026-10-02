"""Đồ thị giả lập nhỏ (đặt quanh Hà Nội) với đáp án biết trước — chạy offline, không cần OSM.

Lưới 4x4, id = hàng*4 + cột (0..15). Hàng 0 ở phía Bắc. Khoảng cách ~0.005° mỗi bước.

    0 → 1 → 2 → 3        hàng 0: MỘT CHIỀU đi về phía Đông
    ↕   ↕   ↕   ↕
    4 ↔ 5 ↔ 6 ↔ 7        hàng 1..3 và mọi cạnh dọc: hai chiều
    ↕   ↕   ↕   ↕
    8 ↔ 9 ↔10 ↔11
    ↕   ↕   ↕   ↕
   12 ↔13 ↔14 ↔15 → 200  node 200: CHỈ có cạnh vào (15→200) = bẫy một chiều (liên thông yếu, không liên thông mạnh)

   100 ↔ 101             "đảo" cô lập hoàn toàn khỏi lưới (mô phỏng lỗi dữ liệu OSM)

Đáp án biết trước: 0→3 = [0,1,2,3]; 3→0 bắt buộc vòng [3,7,6,5,4,0].
"""
from __future__ import annotations

import geopandas as gpd
import networkx as nx
from shapely.geometry import box

from hanoi_graph.geo import recompute_edge_lengths

LAT0, LNG0, STEP = 21.000, 105.800, 0.005
ROWS = COLS = 4
TRAP, ISLAND_A, ISLAND_B = 200, 100, 101


def nid(r: int, c: int) -> int:
    return r * COLS + c


def build_synthetic_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph(crs="EPSG:4326")
    for r in range(ROWS):
        for c in range(COLS):
            G.add_node(nid(r, c), y=LAT0 - r * STEP, x=LNG0 + c * STEP)

    def two_way(a, b, **attrs):
        G.add_edge(a, b, highway=attrs.pop("highway", "residential"), oneway=False, **attrs)
        G.add_edge(b, a, highway="residential", oneway=False, reversed=True)

    for r in range(ROWS):
        for c in range(COLS):
            if c + 1 < COLS:
                a, b = nid(r, c), nid(r, c + 1)
                if r == 0:  # hàng 0 một chiều về phía Đông
                    G.add_edge(a, b, highway="residential", oneway=True)
                else:
                    two_way(a, b)
            if r + 1 < ROWS:
                two_way(nid(r, c), nid(r + 1, c))

    # bẫy một chiều: 15 -> 200 (không có đường ra)
    G.add_node(TRAP, y=LAT0 - 3 * STEP - STEP, x=LNG0 + 3 * STEP)
    G.add_edge(nid(3, 3), TRAP, highway="residential", oneway=True)

    # đảo cô lập 100 <-> 101, nằm xa lưới
    G.add_node(ISLAND_A, y=LAT0 + 0.05, x=LNG0 + 0.05)
    G.add_node(ISLAND_B, y=LAT0 + 0.05, x=LNG0 + 0.055)
    G.add_edge(ISLAND_A, ISLAND_B, highway="residential", oneway=False)
    G.add_edge(ISLAND_B, ISLAND_A, highway="residential", oneway=False, reversed=True)

    recompute_edge_lengths(G)
    return G


def synthetic_districts() -> gpd.GeoDataFrame:
    """2 "quận" giả: nửa Tây (cột 0-1) và nửa Đông (cột 2-3) của lưới; đảo 100/101 nằm ngoài cả hai."""
    west = box(LNG0 - 0.002, LAT0 - 4 * STEP, LNG0 + 1.5 * STEP, LAT0 + 0.002)
    east = box(LNG0 + 1.5 * STEP, LAT0 - 4 * STEP, LNG0 + 3 * STEP + 0.002, LAT0 + 0.002)
    return gpd.GeoDataFrame(
        {"name": ["Khu Tây", "Khu Đông"], "kind": ["Quận", "Quận"], "slug": ["KhuTay", "KhuDong"]},
        geometry=[west, east], crs="EPSG:4326",
    )
