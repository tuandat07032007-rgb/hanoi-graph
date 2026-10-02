"""Test offline (lưới giả) cho get_vehicle_graph / resolve_case_for_vehicle."""
import pytest

from hanoi_graph import (
    clear_vehicle_graph_cache, get_profile, get_vehicle_graph, resolve_case_for_vehicle,
    restriction_signature,
)
from synthetic import nid


def test_cung_kieu_han_che_dung_chung_do_thi(G):
    car, vf3, moto = (get_profile(x) for x in ("car_ice", "vf3", "motorbike_ice"))
    assert restriction_signature(car) == restriction_signature(vf3) != restriction_signature(moto)
    a, b, m = get_vehicle_graph(G, car), get_vehicle_graph(G, vf3), get_vehicle_graph(G, moto)
    assert a is b and a is not m
    assert set(a.graph["vehicle_ids"]) == {"car_ice", "vf3"}


def test_cache_theo_tung_do_thi_va_xoa_duoc(G):
    car = get_profile("car_ice")
    a = get_vehicle_graph(G, car)
    assert get_vehicle_graph(G, car) is a
    clear_vehicle_graph_cache(G)
    assert get_vehicle_graph(G, car) is not a


def test_cache_nhan_ra_do_thi_da_doi(G):
    car = get_profile("car_ice")
    a = get_vehicle_graph(G, car)
    G.remove_node(nid(0, 0))
    assert get_vehicle_graph(G, car) is not a        # số node đổi -> dựng lại


def test_ket_qua_loc_khong_sua_G(G):
    n = G.number_of_edges()
    H = get_vehicle_graph(G, get_profile("car_ice"))
    assert G.number_of_edges() == n and H is not G


def test_resolve_case_for_vehicle_snap_tren_do_thi_da_loc(G):
    # xe máy trên lưới giả: bẫy 200 và đảo bị bỏ do giữ SCC -> start/goal phải nằm trong H
    data = {"landmarks": {"a": {"lat": 21.0, "lng": 105.8}, "b": {"lat": 20.985, "lng": 105.815}}}
    case = {"id": "t", "start": "a", "goal": "b", "vehicles": ["motorbike_ice", "car_ice"], "flood": []}
    H, rc = resolve_case_for_vehicle(G, data, case)                       # mặc định xe đầu
    assert rc.start_node in H and rc.goal_node in H and H is not G
    assert rc.baseline_path and rc.baseline_path[0] == rc.start_node
    H2, rc2 = resolve_case_for_vehicle(G, data, case, "car_ice")
    assert rc2.start_node in H2
    with pytest.raises(ValueError):
        resolve_case_for_vehicle(G, data, case, "vf3")                    # vf3 không thuộc case


def test_resolve_case_bao_loi_khi_landmark_qua_xa(G):
    from hanoi_graph import resolve_case
    far = {"landmarks": {"a": {"lat": 21.0, "lng": 105.8}, "xa": {"lat": 21.5, "lng": 106.3}}}
    case = {"id": "t_far", "start": "a", "goal": "xa", "vehicles": ["car_ice"], "flood": []}
    with pytest.raises(ValueError, match=r"t_far.*goal 'xa'.*test_cases\.json"):
        resolve_case(G, far, case)
    with pytest.raises(ValueError):
        resolve_case_for_vehicle(G, far, case)
    rc = resolve_case(G, far, case, max_snap_m=None)               # chủ động tắt kiểm tra
    assert rc.goal_snap_m > 300 and rc.start_snap_m < 1


# ---------------------------------------------------------------- thẻ một chiều riêng của xe máy
def test_xe_may_di_nguoc_pho_mot_chieu_khi_oneway_motorcycle_no(G):
    from shapely.geometry import LineString
    import networkx as nx
    for a, b in ((nid(0, 0), nid(0, 1)), (nid(0, 1), nid(0, 2)), (nid(0, 2), nid(0, 3))):   # hàng 0: một chiều về Đông
        G[a][b][0]["oneway:motorcycle"] = "no"
    G[nid(0, 0)][nid(0, 1)][0]["geometry"] = LineString([(105.800, 21.0), (105.8025, 21.0001), (105.805, 21.0)])
    moto, car = get_profile("motorbike_ice"), get_profile("car_ice")
    Hm, Hc = get_vehicle_graph(G, moto), get_vehicle_graph(G, car)
    assert Hm.graph["oneway_overrides"] == {"contraflow_added": 3, "oneway_removed": 0}
    assert nx.shortest_path(Hm, nid(0, 3), nid(0, 0), weight="length") == [3, 2, 1, 0]      # xe máy đi ngược được
    assert nx.shortest_path(Hc, nid(0, 3), nid(0, 0), weight="length") == [3, 7, 6, 5, 4, 0]  # ô tô vẫn phải vòng
    back = next(iter(Hm[nid(0, 1)][nid(0, 0)].values()))
    assert back["contraflow"] is True and back["reversed"] is True
    assert list(back["geometry"].coords) == list(G[nid(0, 0)][nid(0, 1)][0]["geometry"].coords)[::-1]
    assert not G.has_edge(nid(0, 1), nid(0, 0))                                               # G gốc không đổi
    assert get_vehicle_graph(G, get_profile("motorbike_ev")) is Hm                            # xe máy điện dùng chung


def test_xe_may_chi_di_mot_chieu_khi_oneway_motorcycle_yes(G):
    a, b = nid(1, 0), nid(1, 1)                       # 4 <-> 5: hai chiều với ô tô
    G[a][b][0]["oneway:motorcycle"] = "yes"
    G[b][a][0]["oneway:motorcycle"] = "yes"           # cạnh ngược (reversed=True) cùng mang thẻ của way
    Hm, Hc = get_vehicle_graph(G, get_profile("motorbike_ice")), get_vehicle_graph(G, get_profile("car_ice"))
    assert Hm.has_edge(a, b) and not Hm.has_edge(b, a)
    assert Hc.has_edge(a, b) and Hc.has_edge(b, a)
    assert Hm.graph["oneway_overrides"]["oneway_removed"] == 1


def test_o_to_khong_ap_the_mot_chieu_cua_xe_may(G):
    G[nid(0, 0)][nid(0, 1)][0]["oneway:motorcycle"] = "no"
    Hc = get_vehicle_graph(G, get_profile("car_ice"))
    assert not Hc.has_edge(nid(0, 1), nid(0, 0))
    assert Hc.graph["oneway_overrides"] == {"contraflow_added": 0, "oneway_removed": 0}
