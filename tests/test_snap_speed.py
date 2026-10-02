"""Test offline: snap_point theo cạnh (đúng chiều một chiều) và thời gian đi theo trần tốc độ xe."""
import networkx as nx
import pytest

from hanoi_graph import (
    add_vehicle_travel_times, clear_snap_index_cache, get_profile, make_heuristic, snap_pair,
    snap_point, time_weight, travel_time_attr, vehicle_speed_kph,
)
from synthetic import nid

# điểm sát phía Bắc cạnh 0->1 (hàng 0, MỘT CHIỀU về Đông), gần node 0 hơn node 1
P_ONEWAY = (21.0004, 105.8012)
# điểm sát cạnh 4<->5 (hàng 1, hai chiều), gần node 4 hơn
P_TWOWAY = (20.9952, 105.8012)


# ---------------------------------------------------------------- snap
def test_snap_mot_chieu_ep_theo_chieu(G):
    s = snap_point(G, *P_ONEWAY, role="start")
    g = snap_point(G, *P_ONEWAY, role="goal")
    assert s.node == nid(0, 1)          # đứng giữa phố một chiều về Đông: chỉ đi tiếp ra node 1
    assert g.node == nid(0, 0)          # muốn tới điểm đó phải vào từ node 0
    assert s.edge[:2] == (nid(0, 0), nid(0, 1))
    assert snap_point(G, *P_ONEWAY, role="any").node == nid(0, 0)   # không xét chiều: đầu gần hơn
    assert s.offroad_m == pytest.approx(44.5, abs=1.0) and s.ok


def test_snap_hai_chieu_chon_dau_gan_hon(G):
    for role in ("start", "goal", "any"):
        assert snap_point(G, *P_TWOWAY, role=role).node == nid(1, 0)


def test_snap_along_va_node_dist(G):
    r = snap_point(G, *P_ONEWAY, role="start")
    # chiếu tại ~0.0012° kinh từ node 0 trên cạnh dài 0.005° -> còn ~0.0038° (~395 m) tới node 1
    assert r.along_m == pytest.approx(0.0038 * 111195 * 0.9336, rel=0.02)
    assert r.node_dist_m > r.offroad_m


def test_snap_xa_duong_canh_bao_khong_bao_loi(G):
    r = snap_point(G, 21.010, 105.800, role="start")
    assert not r.ok and r.warning is not None and "cách đường gần nhất" in r.warning and r.offroad_m > 1000
    assert snap_point(G, 21.010, 105.800, warn_m=5000).ok


def test_snap_pair_va_cache(G):
    s, g = snap_pair(G, P_ONEWAY, P_TWOWAY)
    assert (s.node, g.node) == (nid(0, 1), nid(1, 0))
    G.add_node(999, y=21.02, x=105.83)                                     # đổi số node
    G.add_edge(999, nid(0, 0), highway="residential", oneway=True, length=1.0)
    assert snap_point(G, 21.02, 105.83, role="start").node == nid(0, 0)    # index tự dựng lại, thấy cạnh mới
    G.remove_edge(999, nid(0, 0))
    clear_snap_index_cache(G)                                              # chỉ sửa cạnh -> xoá cache bằng tay
    assert 999 not in snap_point(G, 21.02, 105.83, role="start").edge[:2]     # cạnh đã xoá không còn trong index


def test_snap_sai_role(G):
    with pytest.raises(ValueError):
        snap_point(G, *P_ONEWAY, role="xyz")


# ---------------------------------------------------------------- trần tốc độ
def test_toc_do_bi_chan_boi_tran_xe():
    moto, car, vf3 = (get_profile(x) for x in ("motorbike_ice", "car_ice", "vf3"))
    # trần đọc từ config/vehicle_profiles.json -> nhóm chỉnh trần thì test vẫn đúng
    assert vehicle_speed_kph(moto, {"speed_kph": 200}) == moto.speed_cap_kph   # đường nhanh hơn trần -> theo trần
    assert vehicle_speed_kph(car, {"speed_kph": 200}) == car.speed_cap_kph
    assert vehicle_speed_kph(vf3, {"speed_kph": 10}) == 10           # đường chậm hơn trần -> theo đường
    assert vehicle_speed_kph(car, {}) == car.speed_cap_kph           # thiếu speed_kph -> trần xe
    assert vehicle_speed_kph(car, {"speed_kph": [10, 200]}) == 10    # list sau simplify -> lấy chậm nhất


def test_add_vehicle_travel_times_khong_ghi_de_va_tach_theo_xe(G):
    for _, _, d in G.edges(data=True):
        d["speed_kph"] = 100.0
        d["travel_time"] = d["length"] / (100 / 3.6)
    car, vf3 = get_profile("car_ice"), get_profile("vf3")
    a_car, a_vf3 = add_vehicle_travel_times(G, car), add_vehicle_travel_times(G, vf3)
    assert (a_car, a_vf3) == (travel_time_attr(car), travel_time_attr(vf3)) == ("travel_time_car_ice", "travel_time_vf3")
    _, _, d = next(iter(G.edges(data=True)))
    # đường 100 km/h > trần của cả hai xe -> mỗi xe chạy đúng trần của nó (đọc từ config, không ghi cứng số)
    assert d[a_car] == pytest.approx(d["length"] / (car.speed_cap_kph / 3.6))
    assert d[a_vf3] == pytest.approx(d["length"] / (vf3.speed_cap_kph / 3.6))
    assert d["travel_time"] == pytest.approx(d["length"] / (100 / 3.6))   # gốc giữ nguyên


def test_time_weight_va_heuristic_admissible(G):
    for _, _, d in G.edges(data=True):
        d["speed_kph"] = 100.0
    moto = get_profile("motorbike_ice")
    attr = add_vehicle_travel_times(G, moto)
    goal = nid(3, 3)
    h = make_heuristic(G, goal, mode="time", max_speed_kph=moto.speed_cap_kph)
    true = nx.single_source_dijkstra_path_length(G.reverse(copy=False), goal, weight=attr)
    assert all(h(n) <= t + 1e-6 for n, t in true.items())
    p1 = nx.astar_path(G, 0, goal, heuristic=lambda n, _g: h(n), weight=attr)
    p2 = nx.dijkstra_path(G, 0, goal, weight=time_weight(moto))
    assert nx.path_weight(G, p1, attr) == pytest.approx(nx.path_weight(G, p2, attr))
