"""Test trên ĐỒ THỊ HÀ NỘI THẬT (data/hanoi_all.*) — tính chất của chính file dữ liệu: có hướng, một chiều,
liên thông, đồ thị lọc theo xe, snap theo cạnh, trần tốc độ. (Các case của bộ data test: test_dataset_real.py)

Khác test_core_offline.py (lưới giả), file này kiểm tra chính file dữ liệu: nếu ai đó build/lưu nhầm
đồ thị vô hướng, hoặc mất thuộc tính oneway/reversed, các test dưới đây sẽ báo.

Chạy:  python -m pytest tests/test_hanoi_real.py -v -rs
Tự skip nếu chưa có data (fixture hanoi_graph trong conftest.py).
"""
import random

import networkx as nx
import pytest

from hanoi_graph import (
    add_vehicle_travel_times, check_connectivity, get_profile, get_vehicle_graph, load_cases,
    make_heuristic, oneway_report, path_length_m, require_directed, snap_pair,
    snap_point,
)
from hanoi_graph.directed import _truthy

pytestmark = pytest.mark.hanoi


# ---------------------------------------------------------------- kiểu & thống kê
def test_hanoi_la_multidigraph(hanoi_graph):
    G = hanoi_graph
    assert isinstance(G, nx.MultiDiGraph) and G.is_directed() and G.is_multigraph()
    require_directed(G)
    assert G.number_of_nodes() > 100_000 and G.number_of_edges() > 300_000   # cả thành phố, không phải 1 quận


def test_ty_le_duong_mot_chieu_hop_ly(hanoi_graph):
    r = oneway_report(hanoi_graph)
    # Đồ thị vô hướng "hai chiều hoá" sẽ cho ~0% ; dữ liệu Hà Nội thật hiện ~3%.
    assert 0.01 < r.oneway_fraction < 0.15, f"tỉ lệ cạnh một chiều bất thường: {r.oneway_fraction:.2%}"
    assert r.n_tagged_oneway > 1000
    # số cạnh gắn oneway=True phải xấp xỉ số cạnh thật sự không có cạnh ngược
    assert abs(r.n_tagged_oneway - r.n_edges_oneway) / r.n_edges_oneway < 0.10


def test_canh_oneway_hau_het_khong_co_canh_nguoc(hanoi_graph):
    r = oneway_report(hanoi_graph)
    # Hiện ~1,5% cạnh oneway vẫn có cạnh ngược (đường đôi ngược chiều); nếu vọt lên là sai dữ liệu.
    assert r.n_tagged_oneway_but_has_reverse / r.n_tagged_oneway < 0.05


def test_con_thuoc_tinh_reversed(hanoi_graph):
    # OSMnx đánh dấu cạnh ngược của đường hai chiều bằng reversed=True; mất cờ này = lưu/nạp sai.
    n_rev = sum(1 for _, _, d in hanoi_graph.edges(data=True) if _truthy(d.get("reversed", False)))
    assert n_rev > 0.2 * hanoi_graph.number_of_edges()


def test_lien_thong_manh(hanoi_graph):
    # finalize_graph giữ SCC lớn nhất => không còn bẫy một chiều / đảo
    r = check_connectivity(hanoi_graph)
    assert r.is_strongly_connected, r.summary()


# ---------------------------------------------------------------- hành vi theo chiều
def _oneway_edges_without_reverse(G, k, seed=7):
    edges = [(u, v) for u, v, d in G.edges(data=True)
             if _truthy(d.get("oneway", False)) and u != v and not G.has_edge(v, u)]
    assert len(edges) > k
    return random.Random(seed).sample(edges, k)


def test_canh_mot_chieu_khong_di_nguoc_duoc(hanoi_graph):
    G = hanoi_graph
    for u, v in _oneway_edges_without_reverse(G, 25):
        assert G.has_edge(u, v) and not G.has_edge(v, u)
        with pytest.raises(ValueError):                    # path_length_m bắt lỗi sai chiều
            path_length_m(G, [v, u])
        back = nx.shortest_path(G, v, u, weight="length")  # muốn quay lại phải vòng
        assert back != [v, u] and len(back) > 2
        assert path_length_m(G, back) >= path_length_m(G, [u, v]) - 1e-6   # không ngắn hơn đi thẳng


def test_duong_di_va_ve_bat_doi_xung(hanoi_graph):
    G = hanoi_graph
    rnd = random.Random(11)
    nodes = list(G.nodes)
    asym, n = 0, 12
    for _ in range(n):
        a, b = rnd.sample(nodes, 2)
        fwd = nx.shortest_path_length(G, a, b, weight="length")
        bwd = nx.shortest_path_length(G, b, a, weight="length")
        asym += abs(fwd - bwd) > 1.0
    # đồ thị vô hướng => dist(a,b)==dist(b,a) với MỌI cặp; có hướng thật => hầu hết cặp lệch
    assert asym >= n // 2, f"chỉ {asym}/{n} cặp bất đối xứng — nghi đồ thị đã bị vô hướng hoá"


# ---------------------------------------------------------------- đồ thị lọc theo xe
def test_do_thi_loc_dung_chung_theo_kieu_han_che(hanoi_graph):
    car, vf3, moto = (get_profile(x) for x in ("car_ice", "vf3", "motorbike_ice"))
    Hc, Hv, Hm = (get_vehicle_graph(hanoi_graph, p) for p in (car, vf3, moto))
    assert Hc is Hv and Hc is not Hm                       # chỉ dựng 2 đồ thị cho 3 xe
    assert check_connectivity(Hc).is_strongly_connected and check_connectivity(Hm).is_strongly_connected
    assert Hc.is_directed() and Hm.is_directed()


# ---------------------------------------------------------------- snap theo cạnh & trần tốc độ
def test_snap_landmark_theo_canh(hanoi_graph):
    lm = load_cases()["landmarks"]
    far = set()                    # mọi landmark đều đã nằm sát đường xe đi được
    for key, p in lm.items():
        r = snap_point(hanoi_graph, p["lat"], p["lng"], role="start")
        assert r.node in hanoi_graph
        assert r.offroad_m <= r.node_dist_m + 1.0              # cách đường không xa hơn cách node
        assert (r.warning is not None) == (key in far), (key, r.offroad_m)


def test_snap_tren_do_thi_xe_va_tim_duong_theo_thoi_gian(hanoi_graph):
    import networkx as nx
    moto = get_profile("motorbike_ice")
    H = get_vehicle_graph(hanoi_graph, moto)
    s, g = snap_pair(H, (21.0288, 105.8523), (21.0050, 105.8430))   # Hồ Gươm -> Bách khoa
    assert s.ok and g.ok and s.node in H and g.node in H
    w = add_vehicle_travel_times(H, moto)
    h = make_heuristic(H, g.node, mode="time", max_speed_kph=moto.speed_cap_kph)
    path = nx.astar_path(H, s.node, g.node, heuristic=lambda n, _g: h(n), weight=w)
    t, length = nx.path_weight(H, path, w), nx.path_weight(H, path, "length")
    assert t >= length / (moto.speed_cap_kph / 3.6) - 1e-6        # không nhanh hơn trần 50 km/h
    assert path_length_m(H, path) > 0                              # hợp lệ theo chiều


def test_xe_may_di_hai_chieu_tren_pho_mot_chieu_oneway_motorcycle_no(hanoi_graph):
    """Thẻ oneway:motorcycle=no (phố một chiều với ô tô, xe máy đi hai chiều): đồ thị xe máy có cạnh ngược,
    đồ thị ô tô thì không."""
    G = hanoi_graph
    Hm = get_vehicle_graph(G, get_profile("motorbike_ice"))
    Hc = get_vehicle_graph(G, get_profile("car_ice"))
    assert Hm.graph["oneway_overrides"]["contraflow_added"] > 1000
    assert sum(1 for _, _, d in Hc.edges(data=True) if d.get("contraflow")) == 0
    tagged = [(u, v) for u, v, d in G.edges(data=True)
              if d.get("oneway:motorcycle") == "no" and _truthy(d.get("oneway", False)) and not G.has_edge(v, u)]
    sample = random.Random(3).sample(tagged, 25)
    for u, v in sample:
        if u in Hm and v in Hm:
            assert Hm.has_edge(v, u), (u, v)                    # xe máy đi ngược được
        if u in Hc and v in Hc:
            assert not Hc.has_edge(v, u), (u, v)                # ô tô thì không
