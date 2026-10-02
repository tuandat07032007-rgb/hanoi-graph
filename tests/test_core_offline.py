"""Test offline cho geo, directed, connectivity, subgraph, districts, vehicles, flood (đồ thị giả lập)."""
import math

import networkx as nx
import numpy as np
import osmnx as ox
import pytest

from hanoi_graph import (
    FloodSpot, apply_flood, blocked_edges, check_connectivity, diagnose_no_path, get_profile,
    get_subgraph_near, haversine_km, haversine_m, keep_largest_scc, load_profiles, make_heuristic,
    nearest_node, oneway_report, path_length_m, recompute_edge_lengths, require_directed, slugify,
    to_digraph,
)
from hanoi_graph.districts import HANOI_UNITS
from synthetic import ISLAND_A, TRAP, nid


# ---------------------------------------------------------------- geo
def test_haversine_khop_osmnx():
    for args in [(21.03, 105.85, 21.22, 105.80), (20.96, 105.77, 21.14, 105.50), (0, 0, 0, 1)]:
        assert haversine_m(*args) == pytest.approx(ox.distance.great_circle(*args), rel=1e-9)


def test_haversine_gia_tri_biet_truoc():
    assert haversine_km(0, 0, 1, 0) == pytest.approx(111.195, abs=0.01)           # 1° vĩ
    assert haversine_km(21, 105, 21, 106) == pytest.approx(111.195 * math.cos(math.radians(21)), rel=2e-3)


def test_euclid_phang_sai_o_vi_do_ha_noi():
    # 1° kinh ở 21°B: Euclid phẳng (theo độ) sẽ coi = 1° vĩ -> lệch ~7%
    hv = haversine_km(21, 105, 21, 106)
    euclid = 1.0 * 111.195
    assert abs(euclid - hv) / hv > 0.05


def test_haversine_doi_xung_va_vector():
    a = haversine_m(21.0, 105.8, 21.1, 105.9)
    assert a == pytest.approx(haversine_m(21.1, 105.9, 21.0, 105.8))
    v = haversine_m(21.0, 105.8, np.array([21.1, 21.2]), np.array([105.9, 106.0]))
    assert v.shape == (2,) and v[0] == pytest.approx(a)
    assert haversine_m(21, 105, 21, 105) == 0.0


def test_recompute_length_khop_haversine(G):
    for u, v, d in G.edges(data=True):
        assert d["length"] == pytest.approx(
            haversine_m(G.nodes[u]["y"], G.nodes[u]["x"], G.nodes[v]["y"], G.nodes[v]["x"])
        )
    assert recompute_edge_lengths(G) == G.number_of_edges()


def test_heuristic_admissible_va_consistent(G):
    goal = nid(3, 3)
    h = make_heuristic(G, goal)
    true = nx.single_source_dijkstra_path_length(G.reverse(copy=False), goal, weight="length")
    for n, dist in true.items():
        assert h(n) <= dist + 1e-6                       # admissible
    for u, v, d in G.edges(data=True):
        assert h(u) <= d["length"] + h(v) + 1e-6          # consistent
    assert h(goal) == 0.0


def test_heuristic_time_admissible(G):
    goal = nid(3, 3)
    speed = 50.0
    h = make_heuristic(G, goal, mode="time", max_speed_kph=speed)
    for u, v, d in G.edges(data=True):
        t = d["length"] / (speed / 3.6)
        assert h(u) <= t + h(v) + 1e-6


def test_path_length_bao_loi_sai_chieu(G):
    assert path_length_m(G, [0, 1, 2, 3]) > 0
    with pytest.raises(ValueError):
        path_length_m(G, [3, 2, 1, 0])                   # hàng 0 một chiều về Đông


def test_nearest_node(G):
    assert nearest_node(G, 21.0001, 105.8001) == 0
    n, d = nearest_node(G, 21.0, 105.8, return_dist=True)
    assert n == 0 and d == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------- một chiều
def test_chi_nhan_do_thi_co_huong():
    with pytest.raises(TypeError):
        require_directed(nx.Graph())
    require_directed(nx.MultiDiGraph())


def test_duong_mot_chieu_dung_dap_an(G):
    assert nx.shortest_path(G, 0, 3, weight="length") == [0, 1, 2, 3]
    assert nx.shortest_path(G, 3, 0, weight="length") == [3, 7, 6, 5, 4, 0]
    assert path_length_m(G, [3, 7, 6, 5, 4, 0]) > path_length_m(G, [0, 1, 2, 3])


def test_oneway_report(G):
    r = oneway_report(G)
    assert r.n_edges_oneway == 4            # 3 cạnh hàng 0 + cạnh vào bẫy 15->200
    assert r.n_tagged_oneway == 4
    assert r.n_tagged_oneway_but_has_reverse == 0


def test_to_digraph_giu_huong_va_canh_ngan_nhat(G):
    G.add_edge(0, 1, key=5, length=1.0, highway="service", oneway=True)   # cạnh song song ngắn hơn
    D = to_digraph(G)
    assert isinstance(D, nx.DiGraph) and not D.is_multigraph()
    assert D[0][1]["length"] == 1.0
    assert not D.has_edge(1, 0)


# ---------------------------------------------------------------- liên thông
def test_check_connectivity(G):
    r = check_connectivity(G)
    assert r.n_weak_components == 2                   # lưới(+bẫy) và đảo
    assert r.n_strong_components == 3                 # lưới 16 node, bẫy, đảo
    assert r.largest_strong_size == 16
    assert not r.is_strongly_connected
    assert r.isolated_nodes == []
    assert "TP liên thông mạnh" in r.summary()


def test_keep_largest_scc_loai_dao_va_bay(G):
    H = keep_largest_scc(G)
    assert set(H.nodes) == set(range(16))
    assert ISLAND_A not in H and TRAP not in H
    assert check_connectivity(H).is_strongly_connected
    assert H.number_of_nodes() < G.number_of_nodes()   # bản sao, G gốc không đổi


def test_diagnose_no_path(G):
    assert diagnose_no_path(G, 0, 3) == "OK"
    assert "đảo cô lập" in diagnose_no_path(G, ISLAND_A, 0)
    assert "đảo cô lập" in diagnose_no_path(G, 0, ISLAND_A)
    assert "bẫy đường một chiều" in diagnose_no_path(G, TRAP, 0)
    assert "không có trong đồ thị" in diagnose_no_path(G, 999, 0)


def test_node_co_lap_hoan_toan_duoc_phat_hien(G):
    G.add_node(777, y=21.0, x=105.9)
    assert 777 in check_connectivity(G).isolated_nodes


# ---------------------------------------------------------------- subgraph
def test_subgraph_hop_nho_khong_ensure(G):
    sub = get_subgraph_near(G, 0, 3, buffer_km=0.1, ensure_connected=False)
    assert sub.is_directed() and set(sub.nodes) == {0, 1, 2, 3}
    assert nx.has_path(sub, 0, 3) and not nx.has_path(sub, 3, 0)   # hộp cắt mất đường vòng


def test_subgraph_tu_nong_buffer_de_giu_lien_thong(G):
    sub = get_subgraph_near(G, 3, 0, buffer_km=0.1)
    assert nx.has_path(sub, 3, 0)
    assert sub.graph["buffer_km_used"] > 0.1
    assert sub.graph["start_node"] == 3 and sub.graph["goal_node"] == 0
    assert sub.number_of_nodes() < G.number_of_nodes()


def test_subgraph_nhan_toa_do_va_la_ban_sao(G):
    sub = get_subgraph_near(G, (21.0, 105.8), (21.0, 105.815), buffer_km=0.1, ensure_connected=False)
    assert sub.graph["start_node"] == 0 and sub.graph["goal_node"] == 3
    sub.remove_node(1)
    assert 1 in G


def test_subgraph_khong_co_duong_thi_khong_lap_vo_han(G):
    sub = get_subgraph_near(G, 0, ISLAND_A, buffer_km=1.0, max_buffer_km=8.0)
    assert not nx.has_path(sub, 0, ISLAND_A)


# ---------------------------------------------------------------- quận
def test_slugify_ten_that():
    cases = {"Tây Hồ": "TayHo", "Đống Đa": "DongDa", "Bắc Từ Liêm": "BacTuLiem",
             "Ứng Hòa": "UngHoa", "Hà Đông": "HaDong", "Mê Linh": "MeLinh", "Sơn Tây": "SonTay"}
    for name, slug in cases.items():
        assert slugify(name) == slug


def test_danh_sach_30_don_vi_khong_trung():
    assert len(HANOI_UNITS) == 30
    assert sum(k == "Quận" for k, _ in HANOI_UNITS) == 12
    assert sum(k == "Huyện" for k, _ in HANOI_UNITS) == 17
    assert sum(k == "Thị xã" for k, _ in HANOI_UNITS) == 1
    slugs = [slugify(n) for _, n in HANOI_UNITS]
    assert len(set(slugs)) == 30


def test_get_district(district_index):
    assert district_index.get(21.0, 105.800) == "KhuTay"
    assert district_index.get(21.0, 105.815) == "KhuDong"
    assert district_index.get(22.5, 106.5) is None            # xa ngoài Hà Nội
    assert district_index.get(21.0 + 0.0015, 105.800) == "KhuTay"   # lệch nhỏ ra ngoài biên: trong dung sai/polygon


def test_tag_graph_nodes(G, district_index):
    counts = district_index.tag_graph_nodes(G)
    assert G.nodes[nid(0, 0)]["district"] == "KhuTay"
    assert G.nodes[nid(2, 3)]["district"] == "KhuDong"
    assert G.nodes[ISLAND_A]["district"] is None
    assert counts["KhuTay"] == 8 and counts["KhuDong"] >= 8   # +node 200 có thể rơi vào Đông


# ---------------------------------------------------------------- phương tiện
def test_vehicle_profiles_gia_tri_nhom_chot():
    p = load_profiles()
    assert p["motorbike_ice"].max_wading_depth_cm == 20
    assert p["car_ice"].max_wading_depth_cm == 50
    assert p["vf3"].max_wading_depth_cm == 30
    assert p["vf3"].max_wading_depth_mm == 300
    assert {"motorbike_ice", "motorbike_ev", "car_ice", "car_ev", "vf3"} <= set(p)
    assert {v.powertrain for v in p.values()} == {"ice", "ev"}
    assert {v.category for v in p.values()} == {"motorbike", "car"}


def test_can_pass_bien_va_safety_factor():
    vf3 = get_profile("vf3")
    assert vf3.can_pass(30) and not vf3.can_pass(30.1)        # <= nên đúng ngưỡng vẫn đi được
    assert not get_profile("vf3", safety_factor=0.8).can_pass(30)   # 30*0.8 = 24 cm
    assert get_profile("motorbike_ice").can_pass(20)
    assert not get_profile("motorbike_ice").can_pass(21)


def test_xe_may_cam_cao_toc():
    m, c = get_profile("motorbike_ice"), get_profile("car_ice")
    assert not m.allows_highway("motorway") and not m.allows_highway(["primary", "motorway_link"])
    assert c.allows_highway("motorway") and m.allows_highway("residential")


def test_profile_khong_ton_tai():
    with pytest.raises(KeyError):
        get_profile("xe_bus")


# ---------------------------------------------------------------- ngập
SPOT = FloodSpot("F1", lat=21.0, lng=105.805, radius_m=100, depth_cm=35)   # tại node 1


def test_ngap_chan_dung_xe(G):
    moto, car, vf3 = (get_profile(x) for x in ("motorbike_ice", "car_ice", "vf3"))
    assert blocked_edges(G, [SPOT], car) == set()               # 35 <= 50
    assert blocked_edges(G, [SPOT], moto) and blocked_edges(G, [SPOT], vf3)  # 35 > 20, 35 > 30
    deeper = FloodSpot("F2", 21.0, 105.805, 100, 60)
    assert blocked_edges(G, [deeper], car)


def test_apply_flood_doi_huong_di(G):
    moto = get_profile("motorbike_ice")
    H = apply_flood(G, [SPOT], moto)
    assert H.number_of_edges() < G.number_of_edges() and G.number_of_edges() > 0
    path = nx.shortest_path(H, 0, 3, weight="length")
    assert 1 not in path and path[0] == 0 and path[-1] == 3
    assert path_length_m(H, path) > path_length_m(G, [0, 1, 2, 3])
    assert nx.shortest_path(apply_flood(G, [SPOT], get_profile("car_ice")), 0, 3, weight="length") == [0, 1, 2, 3]


def test_ngap_do_sau_lon_nhat_khi_chong_nhau(G):
    from hanoi_graph import flooded_edges
    f = flooded_edges(G, [FloodSpot("a", 21.0, 105.805, 100, 10), FloodSpot("b", 21.0, 105.805, 100, 40)])
    assert set(f.values()) == {40}


def test_ngap_dat_tren_dao_khong_anh_huong_luoi(G):
    far = FloodSpot("x", 21.05, 105.85, 50, 100)   # đúng chỗ đảo
    assert blocked_edges(G, [far], get_profile("vf3")) != set()
    H = apply_flood(G, [far], get_profile("vf3"))
    assert nx.shortest_path(H, 0, 3, weight="length") == [0, 1, 2, 3]
