"""Chốt "đáp án đúng" (golden) cho bộ data test cố định -> tests/fixtures/golden.json.

Với mỗi case và mỗi xe: node start/goal sau khi snap, độ dài đường ngắn nhất (Dijkstra — tối ưu chắc chắn),
danh sách node của đường, chiều về (nếu also_reverse), kết quả khi có ngập, độ dài khi cắt subgraph.
Đồng thời kiểm tra mọi kỳ vọng ghi trong test_cases.json (check_case) — case nào sai thì KHÔNG ghi file.

    python scripts/freeze_golden.py            # tính, in bảng, ghi golden.json (hỏi lại nếu file đã có)
    python scripts/freeze_golden.py --force    # ghi đè không hỏi
    python scripts/freeze_golden.py --dry-run  # chỉ tính và in, không ghi

Chạy lại khi: tải lại OSM (build_hanoi.py), sửa toạ độ landmark/thêm case, đổi vehicle_profiles.json.
tests/test_dataset_real.py so kết quả hiện tại với file này (sai lệch > 1 m là FAIL).
"""
import argparse
import json
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hanoi_graph import check_case, flood_outcome, load_cases, load_graph, resolve_case_bundle  # noqa: E402
from hanoi_graph.paths import GOLDEN, GRAPH_PICKLE, TEST_CASES  # noqa: E402
from hanoi_graph.subgraph import get_subgraph_near  # noqa: E402
from hanoi_graph.testcases import _dijkstra  # noqa: E402


def _compact_int_lists(text: str) -> str:
    """json.dumps(indent=...) in mỗi phần tử list một dòng; gom các list số nguyên (đường đi) về một dòng."""
    return re.sub(r"\[\s*(-?\d+(?:,\s*-?\d+)*)\s*\]",
                  lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", text)


def graph_fingerprint(G) -> dict:
    return {"n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges()}


def run_record(r) -> dict:
    return {
        "start_node": r.start_node, "goal_node": r.goal_node,
        "start_snap_m": round(r.start_snap_m, 1), "goal_snap_m": round(r.goal_snap_m, 1),
        "length_m": None if r.length_m is None else round(r.length_m, 2),
        "n_path_nodes": None if r.path is None else len(r.path),
        "path": r.path,
    }


def freeze(G, data) -> tuple[dict, list]:
    cases_out, failures = {}, []
    for case in data["cases"]:
        t0 = time.perf_counter()
        b = resolve_case_bundle(G, data, case)
        outcomes = {vid: flood_outcome(b, vid) for vid in b.runs} if b.flood_spots else {}
        checks = check_case(b, outcomes)
        bad = [c for c in checks if not c[1]]
        failures += [(case["id"], *c) for c in bad]

        per_vehicle = {}
        for vid, r in b.runs.items():
            rec = run_record(r)
            if vid in b.reverse_runs:
                rec["reverse"] = run_record(b.reverse_runs[vid])
            if vid in outcomes:
                o = outcomes[vid]
                rec["flood"] = {"status": o.status, "n_blocked_edges": o.n_blocked_edges,
                                "length_m": None if o.length_m is None else round(o.length_m, 2)}
            if "subgraph" in case:
                sub = get_subgraph_near(r.graph, r.start_node, r.goal_node, buffer_km=case["subgraph"]["buffer_km"])
                _, length = _dijkstra(sub, r.start_node, r.goal_node)
                rec["subgraph_length_m"] = None if length is None else round(length, 2)
            per_vehicle[vid] = rec
        cases_out[case["id"]] = {
            "straight_line_m": round(b.straight_line_m, 1),
            "flood_spots": [asdict(s) for s in b.flood_spots],
            "vehicles": per_vehicle,
        }
        print(f"{case['id']:32s} {len(checks) - len(bad):2d}/{len(checks)} kiểm tra đạt   "
              f"({time.perf_counter() - t0:5.1f}s)")
        for vid, rec in per_vehicle.items():
            extra = ""
            if "reverse" in rec:
                extra += f" | về {rec['reverse']['length_m'] / 1000:.2f} km"
            if "flood" in rec:
                extra += f" | ngập: {rec['flood']['status']}"
            if "subgraph_length_m" in rec:
                extra += f" | subgraph {rec['subgraph_length_m'] / 1000:.2f} km"
            print(f"    {vid:14s} {rec['length_m'] / 1000:7.2f} km  {rec['n_path_nodes']:4d} node{extra}")
    return cases_out, failures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ghi đè golden.json không hỏi")
    ap.add_argument("--dry-run", action="store_true", help="chỉ tính và in, không ghi file")
    args = ap.parse_args()

    t0 = time.perf_counter()
    G = load_graph()
    print(f"Nạp đồ thị: {G.number_of_nodes():,} node ({time.perf_counter() - t0:.1f}s)\n")
    data = load_cases()
    cases_out, failures = freeze(G, data)

    if failures:
        print("\nKHÔNG ghi golden.json vì có kỳ vọng sai:")
        for cid, name, _, detail in failures:
            print(f"  - {cid}: {name}  [{detail}]")
        sys.exit(1)

    out = {
        "_meta": {
            "generated_by": "scripts/freeze_golden.py",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "graph_file": GRAPH_PICKLE.name,
            "graph": graph_fingerprint(G),
            "test_cases_version": data.get("_meta", {}).get("version"),
            "tolerance_m": 1.0,
            "note": "Độ dài = đường ngắn nhất theo 'length' (Dijkstra). Thuật toán khác (A*, Weighted A*...) so "
                    "với length_m: A* đúng phải bằng (sai số <= tolerance_m), Weighted A* được phép dài hơn.",
        },
        "cases": cases_out,
    }
    if args.dry_run:
        print("\n--dry-run: không ghi file.")
        return
    if GOLDEN.exists() and not args.force:
        if input(f"\n{GOLDEN.relative_to(ROOT)} đã có. Ghi đè? [y/N] ").strip().lower() != "y":
            print("Bỏ qua, không ghi.")
            return
    GOLDEN.write_text(_compact_int_lists(json.dumps(out, ensure_ascii=False, indent=2)), encoding="utf-8")
    print(f"\nĐã ghi {GOLDEN.relative_to(ROOT)}  (tất cả kỳ vọng trong {TEST_CASES.name} đều đạt)")


if __name__ == "__main__":
    main()
