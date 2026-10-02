"""Nạp & "giải" bộ data test cố định (tests/fixtures/test_cases.json) thành node / phương tiện / điểm ngập.

Cách dùng khuyến nghị (mỗi xe một đồ thị đã lọc, điểm ngập DÙNG CHUNG cho mọi xe trong case):

    from hanoi_graph import load_graph, load_cases, resolve_case_bundle, flood_outcome
    G = load_graph(); data = load_cases()
    for case in data["cases"]:
        b = resolve_case_bundle(G, data, case)
        for vid, run in b.runs.items():        # run.graph, run.start_node, run.goal_node, run.path, run.length_m
            ...                                # chạy thuật toán của bạn trên run.graph, so với run.length_m
        if b.flood_spots:
            out = flood_outcome(b, vid)        # "unchanged" | "rerouted" | "unreachable"

Đáp án đã chốt (độ dài tối ưu từng case/xe) nằm ở tests/fixtures/golden.json — tạo bằng scripts/freeze_golden.py.
Hàm cũ resolve_case / resolve_case_for_vehicle vẫn giữ để tương thích.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import networkx as nx

from .flood import FloodSpot, blocked_edges
from .geo import haversine_m, nearest_node, path_length_m
from .paths import TEST_CASES
from .vehicles import VehicleProfile, get_profile, get_vehicle_graph

DEFAULT_CASES = TEST_CASES
MAX_SNAP_M = 300.0   # mốc (landmark) cách node gần nhất quá ngưỡng này => tọa độ sai hoặc nằm ngoài đồ thị


def load_cases(path: Path | str = DEFAULT_CASES) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class ResolvedCase:
    id: str
    raw: dict
    start_node: object
    goal_node: object
    start_snap_m: float
    goal_snap_m: float
    straight_line_m: float
    vehicles: list[VehicleProfile]
    flood_spots: list[FloodSpot] = field(default_factory=list)
    baseline_path: Optional[list] = None


def _baseline_path(G, s, g, weight="length"):
    try:
        return nx.shortest_path(G, s, g, weight=weight)
    except nx.NetworkXNoPath:
        return None


def resolve_case(G, data: dict, case: dict, max_snap_m: Optional[float] = MAX_SNAP_M) -> ResolvedCase:
    """Snap landmark -> node TRÊN `G` được truyền vào, rồi dùng node đó trên chính G.

    Với xe cần lọc đường (xe máy, ô tô) KHÔNG truyền đồ thị gốc rồi mới lọc: bước lọc có thể loại node
    vừa snap. Dùng `resolve_case_for_vehicle` (lọc trước, snap sau).

    Nếu landmark cách node gần nhất quá `max_snap_m` (mặc định MAX_SNAP_M = 300 m) thì ném ValueError:
    toạ độ landmark sai hoặc nằm ngoài vùng đường của đồ thị — sửa toạ độ trong test_cases.json.
    Truyền max_snap_m=None để tắt kiểm tra (chỉ khi chủ động chấp nhận snap xa).
    """
    lm = data["landmarks"]
    a, b = lm[case["start"]], lm[case["goal"]]
    s, ds = nearest_node(G, a["lat"], a["lng"], return_dist=True)
    g, dg = nearest_node(G, b["lat"], b["lng"], return_dist=True)
    _check_snap(case, "start", case["start"], ds, max_snap_m)
    _check_snap(case, "goal", case["goal"], dg, max_snap_m)
    vehicles = [get_profile(v) for v in case["vehicles"]]
    base = _baseline_path(G, s, g) if s != g else [s]

    spots: list[FloodSpot] = []
    for i, f in enumerate(case.get("flood", [])):
        if f["mode"] == "fixed":
            lat, lng = f["lat"], f["lng"]
        elif f["mode"] == "on_route":
            if not base:
                raise ValueError(f"{case['id']}: không có đường nền để đặt điểm ngập on_route")
            n = base[int(round(f["fraction"] * (len(base) - 1)))]
            lat, lng = float(G.nodes[n]["y"]), float(G.nodes[n]["x"])
        else:
            raise ValueError(f"mode ngập không hỗ trợ: {f['mode']}")
        spots.append(FloodSpot(f"{case['id']}_F{i + 1}", lat, lng, f["radius_m"], f["depth_cm"]))

    return ResolvedCase(
        id=case["id"], raw=case, start_node=s, goal_node=g, start_snap_m=ds, goal_snap_m=dg,
        straight_line_m=haversine_m(a["lat"], a["lng"], b["lat"], b["lng"]),
        vehicles=vehicles, flood_spots=spots, baseline_path=base,
    )


def resolve_case_for_vehicle(G, data: dict, case: dict, vehicle_id: Optional[str] = None,
                             max_snap_m: Optional[float] = MAX_SNAP_M):
    """Làm đúng thứ tự: lọc đồ thị theo xe (có cache) RỒI mới snap start/goal trên đồ thị đã lọc.

    Trả về (H, ResolvedCase). Dùng H để tìm đường; start_node/goal_node luôn nằm trong H.
    vehicle_id mặc định là xe đầu tiên của case. Case nhiều xe: gọi lần lượt cho từng xe — mỗi xe có
    start/goal riêng nếu đồ thị lọc của chúng khác nhau. Lưu ý: H dùng chung giữa các xe cùng kiểu
    hạn chế; không sửa trực tiếp (cần thì H.copy()).
    """
    vehicle_id = vehicle_id or case["vehicles"][0]
    if vehicle_id not in case["vehicles"]:
        raise ValueError(f"{case['id']}: xe {vehicle_id!r} không thuộc case (có: {case['vehicles']})")
    H = get_vehicle_graph(G, get_profile(vehicle_id))
    return H, resolve_case(H, data, case, max_snap_m=max_snap_m)


# ======================================================================== bundle: mọi xe của một case
@dataclass
class VehicleRun:
    """Một xe trong một case: đồ thị đã lọc cho xe đó + start/goal đã snap TRÊN đồ thị đó + đáp án tối ưu."""
    vehicle: VehicleProfile
    graph: object                  # đồ thị lọc theo xe (dùng chung giữa các xe cùng kiểu hạn chế — KHÔNG sửa)
    start_node: object
    goal_node: object
    start_snap_m: float
    goal_snap_m: float
    path: Optional[list]           # đường ngắn nhất theo độ dài (Dijkstra) — None nếu không có đường
    length_m: Optional[float]


@dataclass
class CaseBundle:
    id: str
    raw: dict
    base_graph: object             # đồ thị gốc G (để tra cạnh ngập một lần cho mọi xe)
    straight_line_m: float         # đường chim bay giữa 2 landmark
    runs: dict                     # vehicle_id -> VehicleRun (chiều start -> goal)
    reverse_runs: dict = field(default_factory=dict)   # vehicle_id -> VehicleRun (goal -> start), nếu also_reverse
    flood_spots: list = field(default_factory=list)


@dataclass
class FloodOutcome:
    status: str                    # "unchanged" | "rerouted" | "unreachable"
    path: Optional[list]
    length_m: Optional[float]
    n_blocked_edges: int


def _dijkstra(H, s, g):
    if s == g:
        return [s], 0.0
    try:
        length, path = nx.single_source_dijkstra(H, s, g, weight="length")
        return path, float(length)
    except nx.NetworkXNoPath:
        return None, None


def _check_snap(case, role, key, dist, max_snap_m):
    if max_snap_m is not None and dist > max_snap_m:
        raise ValueError(
            f"{case['id']}: landmark {role} {key!r} cách node gần nhất {dist:.0f} m "
            f"(> {max_snap_m:.0f} m) — toạ độ sai hoặc ngoài vùng đường của đồ thị; "
            f"sửa lat/lng trong test_cases.json (hoặc truyền max_snap_m khác)"
        )


def _make_run(G, data, case, profile, reverse: bool, max_snap_m) -> VehicleRun:
    lm = data["landmarks"]
    a_key, b_key = (case["goal"], case["start"]) if reverse else (case["start"], case["goal"])
    a, b = lm[a_key], lm[b_key]
    H = get_vehicle_graph(G, profile)                      # lọc theo xe TRƯỚC ...
    s, ds = nearest_node(H, a["lat"], a["lng"], return_dist=True)   # ... rồi mới snap trên đồ thị đã lọc
    g, dg = nearest_node(H, b["lat"], b["lng"], return_dist=True)
    _check_snap(case, "start", a_key, ds, max_snap_m)
    _check_snap(case, "goal", b_key, dg, max_snap_m)
    path, length = _dijkstra(H, s, g)
    return VehicleRun(profile, H, s, g, ds, dg, path, length)


def _common_route_node(case, runs: dict, fraction: float):
    """Node nằm trên đường nền của MỌI xe, gần vị trí `fraction` nhất dọc theo đường của xe đầu tiên.

    Nhờ vậy điểm ngập on_route nằm trên tuyến của tất cả các xe -> so sánh "xe máy bị chặn, ô tô vẫn qua"
    mới công bằng (bản cũ đặt theo đường nền của từng đồ thị nên mỗi xe có thể gặp một điểm ngập khác).
    """
    paths = [r.path for r in runs.values()]
    if any(p is None for p in paths):
        raise ValueError(f"{case['id']}: có xe không có đường nền -> không đặt được điểm ngập on_route")
    first = paths[0]
    common = set(first[1:-1])
    for p in paths[1:]:
        common &= set(p[1:-1])
    if not common:
        raise ValueError(f"{case['id']}: các xe không có node chung trên đường nền -> đổi fraction/landmark "
                         f"hoặc dùng mode 'fixed'")
    target = fraction * (len(first) - 1)
    return min((i for i, n in enumerate(first) if n in common), key=lambda i: (abs(i - target), i))


def resolve_case_bundle(G, data: dict, case: dict, max_snap_m: Optional[float] = MAX_SNAP_M) -> CaseBundle:
    """Giải một case cho MỌI xe: lọc đồ thị theo xe -> snap -> Dijkstra (đáp án tối ưu) -> điểm ngập chung."""
    lm = data["landmarks"]
    a, b = lm[case["start"]], lm[case["goal"]]
    runs = {vid: _make_run(G, data, case, get_profile(vid), False, max_snap_m) for vid in case["vehicles"]}
    reverse_runs = {}
    if case.get("also_reverse"):
        reverse_runs = {vid: _make_run(G, data, case, get_profile(vid), True, max_snap_m)
                        for vid in case["vehicles"]}

    spots: list = []
    first_run = next(iter(runs.values()))
    for i, f in enumerate(case.get("flood", [])):
        if f["mode"] == "fixed":
            lat, lng = f["lat"], f["lng"]
        elif f["mode"] == "on_route":
            idx = _common_route_node(case, runs, f["fraction"])
            n = first_run.path[idx]
            lat, lng = float(G.nodes[n]["y"]), float(G.nodes[n]["x"])
        else:
            raise ValueError(f"mode ngập không hỗ trợ: {f['mode']}")
        spots.append(FloodSpot(f"{case['id']}_F{i + 1}", lat, lng, f["radius_m"], f["depth_cm"]))

    return CaseBundle(
        id=case["id"], raw=case, base_graph=G,
        straight_line_m=haversine_m(a["lat"], a["lng"], b["lat"], b["lng"]),
        runs=runs, reverse_runs=reverse_runs, flood_spots=spots,
    )


def flood_outcome(bundle: CaseBundle, vehicle_id: str, tol_m: float = 0.01) -> FloodOutcome:
    """Tìm lại đường ngắn nhất của xe khi có ngập (view chỉ đọc, không copy đồ thị) và phân loại kết quả."""
    run = bundle.runs[vehicle_id]
    H = run.graph
    multi = H.is_multigraph()
    blocked = [e for e in blocked_edges(bundle.base_graph, bundle.flood_spots, run.vehicle)
               if (H.has_edge(*e) if multi else H.has_edge(e[0], e[1]))]
    view = nx.restricted_view(H, [], blocked if multi else [(u, v) for u, v, _ in blocked])
    path, length = _dijkstra(view, run.start_node, run.goal_node)
    if path is None:
        status = "unreachable"
    elif run.length_m is not None and abs(length - run.length_m) <= tol_m:
        status = "unchanged"
    else:
        status = "rerouted"
    return FloodOutcome(status, path, length, len(blocked))


def node_district(G, n):
    d = G.nodes[n].get("district")
    return None if d in (None, "None") else d


def check_case(bundle: CaseBundle, outcomes: Optional[dict] = None) -> list:
    """Kiểm tra mọi kỳ vọng ghi trong case. Trả về [(tên kiểm tra, đạt?, chi tiết)].

    outcomes: {vehicle_id: FloodOutcome} (tự tính nếu case có ngập mà không truyền vào).
    """
    case, res = bundle.raw, []
    exp = case.get("expect", {})
    lo, hi = case.get("min_ratio", 1.0), case.get("max_ratio", float("inf"))

    def add(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    for direction, runs in (("đi", bundle.runs), ("về", bundle.reverse_runs)):
        for vid, r in runs.items():
            tag = f"{vid}/{direction}"
            add(f"{tag}: có đường", r.path is not None)
            if r.path is None:
                continue
            path_length_m(r.graph, r.path)                       # ném lỗi nếu có bước sai chiều
            ratio = r.length_m / bundle.straight_line_m if bundle.straight_line_m else float("nan")
            add(f"{tag}: tỉ lệ đường/chim bay trong [{lo}, {hi}]", lo <= ratio <= hi, f"{ratio:.3f}")
            add(f"{tag}: >= đường chim bay giữa 2 node",
                r.length_m + 1e-6 >= haversine_m(r.graph.nodes[r.start_node]["y"], r.graph.nodes[r.start_node]["x"],
                                                 r.graph.nodes[r.goal_node]["y"], r.graph.nodes[r.goal_node]["x"]))
            if "same_district" in exp:
                ds, dg = node_district(r.graph, r.start_node), node_district(r.graph, r.goal_node)
                add(f"{tag}: cùng quận = {exp['same_district']}", (ds == dg) == exp["same_district"], f"{ds} -> {dg}")

    if case.get("also_reverse"):
        for vid in bundle.runs:
            f, b = bundle.runs[vid], bundle.reverse_runs[vid]
            if f.path and b.path:
                differ = list(reversed(b.path)) != f.path or abs(f.length_m - b.length_m) > 1.0
                add(f"{vid}: đi và về khác nhau (đường một chiều)", differ,
                    f"đi {f.length_m:.0f} m, về {b.length_m:.0f} m")

    if bundle.flood_spots:
        outcomes = outcomes or {vid: flood_outcome(bundle, vid) for vid in bundle.runs}
        for vid, ok in exp.get("reachable_for", {}).items():
            add(f"{vid}: còn đường khi ngập = {ok}", (outcomes[vid].status != "unreachable") == ok,
                outcomes[vid].status)
        for vid in exp.get("blocked_for", []):
            add(f"{vid}: bị ngập chặn (phải đổi đường/không đi được)",
                outcomes[vid].status in ("rerouted", "unreachable"), outcomes[vid].status)
        for vid in exp.get("unchanged_for", []):
            add(f"{vid}: đường không đổi khi ngập", outcomes[vid].status == "unchanged", outcomes[vid].status)

    if "subgraph" in case:
        from .subgraph import get_subgraph_near
        cfg = case["subgraph"]
        for vid, r in bundle.runs.items():
            sub = get_subgraph_near(r.graph, r.start_node, r.goal_node, buffer_km=cfg["buffer_km"])
            path, length = _dijkstra(sub, r.start_node, r.goal_node)
            limit = r.length_m * (1 + cfg.get("max_length_overhead", 0.0))
            add(f"{vid}: subgraph {cfg['buffer_km']} km giữ được đường (dài thêm <= {cfg.get('max_length_overhead', 0):.0%})",
                path is not None and length <= limit + 1e-6,
                "không có đường" if path is None else f"{length:.0f} m / tối ưu {r.length_m:.0f} m")
    return res

