"""Test offline (lưới giả): ngập theo geometry cạnh, view chỉ đọc, bundle nhiều xe + điểm ngập dùng chung,
check_case, nodes_in_bbox, đường dẫn tuyệt đối, chuẩn hoá sau khi nạp GraphML."""
import networkx as nx
import pytest

from hanoi_graph import (
    FloodSpot, apply_flood, check_case, flood_outcome, flooded_edges, get_profile, nodes_in_bbox, paths,
    resolve_case_bundle,
)
from synthetic import ISLAND_A, TRAP, nid

# lưới giả: hàng 1 nằm ở vĩ độ 20.995, cột cách nhau 0.005° kinh (~520 m)
MID_EDGE_SPOT = FloodSpot("mid", lat=20.995, lng=105.8010, radius_m=30, depth_cm=100)   # trên cạnh 4<->5, cách node 4 ~104 m


# ---------------------------------------------------------------- ngập theo geometry
def test_ngap_giua_canh_dai_khong_bi_bo_sot(G):
    # 2 đầu mút (node 4, 5) và trung điểm (105.8025) đều cách tâm > 30 m -> bản cũ bỏ sót; bản mới bắt được
    assert set(flooded_edges(G, [MID_EDGE_SPOT])) == {(nid(1, 0), nid(1, 1), 0), (nid(1, 1), nid(1, 0), 0)}


def test_apply_flood_view_chi_doc_va_khong_copy(G):
    moto = get_profile("motorbike_ice")
    V = apply_flood(G, [MID_EDGE_SPOT], moto, as_view=True)
    C = apply_flood(G, [MID_EDGE_SPOT], moto)
    assert V.number_of_edges() == C.number_of_edges() == G.number_of_edges() - 2
    assert not V.has_edge(nid(1, 0), nid(1, 1)) and G.has_edge(nid(1, 0), nid(1, 1))
    with pytest.raises(nx.NetworkXError):
        V.add_edge(0, 1)                                    # view: không sửa được
    assert nx.shortest_path(V, nid(1, 0), nid(1, 1), weight="length") != [nid(1, 0), nid(1, 1)]


def test_flooded_edges_bo_canh_da_xoa_khoi_G(G):
    flooded_edges(G, [MID_EDGE_SPOT])                       # dựng chỉ mục
    G.remove_edge(nid(1, 0), nid(1, 1))                     # số node không đổi -> chỉ mục cũ
    assert set(flooded_edges(G, [MID_EDGE_SPOT])) == {(nid(1, 1), nid(1, 0), 0)}
    apply_flood(G, [MID_EDGE_SPOT], get_profile("vf3"))     # không lỗi khi chỉ mục còn cạnh đã xoá


# ---------------------------------------------------------------- bundle nhiều xe
DATA = {
    "landmarks": {"a": {"lat": 21.0, "lng": 105.800}, "b": {"lat": 21.0, "lng": 105.815}},
    "cases": [],
}
CASE = {
    "id": "syn_flood", "start": "a", "goal": "b", "vehicles": ["motorbike_ice", "car_ice"],
    "flood": [{"mode": "on_route", "fraction": 0.5, "radius_m": 100, "depth_cm": 35}],
    "min_ratio": 1.0, "max_ratio": 2.0,           # chiều về phải vòng: ~1.71 lần chim bay
    "expect": {"reachable_for": {"car_ice": True}, "blocked_for": ["motorbike_ice"], "unchanged_for": ["car_ice"]},
    "also_reverse": True,
}


def test_bundle_moi_xe_mot_do_thi_va_diem_ngap_chung(G):
    b = resolve_case_bundle(G, DATA, CASE)
    assert set(b.runs) == {"motorbike_ice", "car_ice"}
    for r in b.runs.values():
        assert r.path == [0, 1, 2, 3] and r.start_node in r.graph and TRAP not in r.graph and ISLAND_A not in r.graph
    # điểm ngập ở node chung gần giữa đường: node 1 (đường nền 0-1-2-3, chỉ số 1.5 -> lấy 1)
    (spot,) = b.flood_spots
    assert (spot.lat, spot.lng) == (G.nodes[1]["y"], G.nodes[1]["x"])
    assert b.reverse_runs["car_ice"].path == [3, 7, 6, 5, 4, 0]      # chiều về phải vòng (hàng 0 một chiều)


def test_flood_outcome_va_check_case(G):
    b = resolve_case_bundle(G, DATA, CASE)
    assert flood_outcome(b, "car_ice").status == "unchanged"          # 35 cm <= 50
    o = flood_outcome(b, "motorbike_ice")                             # 35 cm > 20
    assert o.status == "rerouted" and 1 not in o.path and o.length_m > b.runs["motorbike_ice"].length_m
    results = check_case(b)
    assert results and all(ok for _, ok, _ in results), [r for r in results if not r[1]]


def test_check_case_bao_sai_khi_ky_vong_sai(G):
    wrong = dict(CASE, expect={"unchanged_for": ["motorbike_ice"]}, max_ratio=1.01)
    failed = {name for name, ok, _ in check_case(resolve_case_bundle(G, DATA, wrong)) if not ok}
    assert any("không đổi" in n for n in failed)                      # xe máy thực ra phải đổi đường
    assert any("về: tỉ lệ" in n for n in failed)                      # đường về dài ~1.71x chim bay > 1.01


def test_bundle_landmark_xa_bao_loi(G):
    far = {"landmarks": {"a": DATA["landmarks"]["a"], "x": {"lat": 21.5, "lng": 106.3}}}
    with pytest.raises(ValueError, match="test_cases.json"):
        resolve_case_bundle(G, far, dict(CASE, goal="x", flood=[]))


# ---------------------------------------------------------------- tiện ích khác
def test_nodes_in_bbox(G):
    keep = nodes_in_bbox(G, 0, 3, buffer_km=0.1)
    assert keep == {0, 1, 2, 3}
    assert nid(3, 3) in nodes_in_bbox(G, 0, 3, buffer_km=2.0)


def test_duong_dan_tuyet_doi():
    for p in (paths.GRAPH_PICKLE, paths.DISTRICTS_GEOJSON, paths.VEHICLE_PROFILES, paths.TEST_CASES):
        assert p.is_absolute() and paths.PROJECT_ROOT in p.parents
    assert paths.VEHICLE_PROFILES.exists() and paths.TEST_CASES.exists()


def test_chuan_hoa_sau_graphml():
    from hanoi_graph.loader import _normalize_after_graphml
    H = nx.MultiDiGraph()
    H.add_node(1, district="None")
    H.add_node(2, district="TayHo")
    _normalize_after_graphml(H)
    assert H.nodes[1]["district"] is None and H.nodes[2]["district"] == "TayHo"


def test_chi_mot_kieu_build_o_to_va_xe_may():
    """Build luôn tải đường của cả ô tô và xe máy (đồ thị từng xe lọc ra sau) — không còn bản chỉ-ô-tô."""
    import inspect
    import os
    import subprocess
    import sys

    from hanoi_graph.loader import ALL_VEHICLES_FILTER, VEHICLE_TAGS, download_hanoi_graph
    params = inspect.signature(download_hanoi_graph).parameters
    assert "network_type" not in params
    assert params["custom_filter"].default == ALL_VEHICLES_FILTER
    assert '"motor_vehicle"!~"no"' in ALL_VEHICLES_FILTER and "motorcar" not in ALL_VEHICLES_FILTER
    assert {"motorcycle", "motorcar", "oneway:motorcycle"} <= set(VEHICLE_TAGS)
    # PYTHONIOENCODING: trên Windows, stdout bị chuyển hướng (pipe) mặc định dùng cp1252 -> in chữ Việt
    # trong --help sẽ lỗi UnicodeEncodeError. Chạy script trực tiếp trong terminal thì không bị.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, str(paths.PROJECT_ROOT / "scripts" / "build_hanoi.py"), "--help"],
                         capture_output=True, text=True, encoding="utf-8", timeout=120, env=env)
    assert out.returncode == 0, out.stderr
    assert "--tile-km" in out.stdout
    assert "all-vehicles" not in out.stdout and "hanoi_drive" not in out.stdout

