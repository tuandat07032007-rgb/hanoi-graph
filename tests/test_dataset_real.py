"""Bộ data test cố định trên ĐỒ THỊ THẬT: mọi kỳ vọng trong test_cases.json + so với đáp án đã chốt (golden.json).

    python -m pytest tests/test_dataset_real.py -v -rs        (~1,5–3 phút: dựng đồ thị lọc theo xe + chỉ mục cạnh)

Nếu test golden FAIL vì "đồ thị đã đổi" -> vừa tải lại OSM: chạy `python scripts/freeze_golden.py` để chốt lại.
"""
import json

import networkx as nx
import pytest

from hanoi_graph import check_case, flood_outcome, load_cases, make_heuristic, path_length_m, resolve_case_bundle
from hanoi_graph.paths import GOLDEN

pytestmark = pytest.mark.hanoi

DATA = load_cases()
CASE_IDS = [c["id"] for c in DATA["cases"]]


@pytest.fixture(scope="module")
def bundles(hanoi_graph):
    """{case_id: (bundle, outcomes)} — tính một lần cho cả module."""
    out = {}
    for case in DATA["cases"]:
        b = resolve_case_bundle(hanoi_graph, DATA, case)
        outcomes = {vid: flood_outcome(b, vid) for vid in b.runs} if b.flood_spots else {}
        out[case["id"]] = (b, outcomes)
    return out


@pytest.fixture(scope="module")
def golden():
    if not GOLDEN.exists():
        pytest.skip("Chưa có tests/fixtures/golden.json — chạy: python scripts/freeze_golden.py")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- kỳ vọng ghi trong test_cases.json
@pytest.mark.parametrize("case_id", CASE_IDS)
def test_ky_vong_cua_case(bundles, case_id):
    b, outcomes = bundles[case_id]
    failed = [f"{name} [{detail}]" for name, ok, detail in check_case(b, outcomes) if not ok]
    assert not failed, f"{case_id}:\n  " + "\n  ".join(failed)


def test_landmark_dung_quan_khai_bao(hanoi_districts):
    sai = {k: (p["district"], hanoi_districts.get(p["lat"], p["lng"]))
           for k, p in DATA["landmarks"].items() if hanoi_districts.get(p["lat"], p["lng"]) != p["district"]}
    assert not sai, f"landmark khác quận khai báo (khai báo, thực tế): {sai}"


def test_diem_ngap_dung_chung_cho_moi_xe(bundles):
    b, outcomes = bundles["case_4_flood_on_route"]
    spot = b.flood_spots[0]
    for vid, r in b.runs.items():   # điểm ngập nằm đúng trên đường nền của TỪNG xe
        assert any(abs(r.graph.nodes[n]["y"] - spot.lat) < 1e-9 and abs(r.graph.nodes[n]["x"] - spot.lng) < 1e-9
                   for n in r.path), vid
    spot_nodes = {n for n in b.runs["car_ice"].path
                  if abs(b.base_graph.nodes[n]["y"] - spot.lat) < 1e-9 and abs(b.base_graph.nodes[n]["x"] - spot.lng) < 1e-9}
    for vid, o in outcomes.items():
        if o.path:
            path_length_m(b.runs[vid].graph, o.path)          # đường khi ngập vẫn hợp lệ theo chiều
        if o.status == "rerouted":                            # xe bị chặn: đường mới phải tránh tâm điểm ngập
            assert not (spot_nodes & set(o.path)), vid


# ---------------------------------------------------------------- so với đáp án đã chốt
def test_golden_cung_do_thi(hanoi_graph, golden):
    meta = golden["_meta"]["graph"]
    if hanoi_graph.number_of_nodes() != meta["n_nodes"] or hanoi_graph.number_of_edges() != meta["n_edges"]:
        pytest.fail(f"Đồ thị đã đổi so với lúc chốt golden ({meta}) — chạy: python scripts/freeze_golden.py")


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_khop_golden(bundles, golden, case_id):
    tol = golden["_meta"]["tolerance_m"]
    assert case_id in golden["cases"], f"{case_id} chưa có trong golden.json — chạy lại freeze_golden.py"
    exp = golden["cases"][case_id]["vehicles"]
    b, outcomes = bundles[case_id]
    for vid, r in b.runs.items():
        g = exp[vid]
        assert (r.start_node, r.goal_node) == (g["start_node"], g["goal_node"]), f"{vid}: snap khác golden"
        assert r.length_m == pytest.approx(g["length_m"], abs=tol), f"{vid}: độ dài khác golden"
        if "reverse" in g:
            assert b.reverse_runs[vid].length_m == pytest.approx(g["reverse"]["length_m"], abs=tol)
        if "flood" in g:
            o = outcomes[vid]
            assert o.status == g["flood"]["status"], f"{vid}: kết quả ngập khác golden"
            if g["flood"]["length_m"] is not None:
                assert o.length_m == pytest.approx(g["flood"]["length_m"], abs=tol)


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_astar_bang_dijkstra_golden(bundles, golden, case_id):
    """Bất biến: A* với heuristic haversine (admissible) phải cho đúng độ dài tối ưu đã chốt."""
    b, _ = bundles[case_id]
    for vid, r in b.runs.items():
        h = make_heuristic(r.graph, r.goal_node)
        path = nx.astar_path(r.graph, r.start_node, r.goal_node, heuristic=lambda n, _g: h(n), weight="length")
        assert path_length_m(r.graph, path) == pytest.approx(golden["cases"][case_id]["vehicles"][vid]["length_m"],
                                                            abs=golden["_meta"]["tolerance_m"])
