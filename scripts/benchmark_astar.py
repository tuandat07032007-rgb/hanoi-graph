"""Benchmark A* trên ĐỒ THỊ HÀ NỘI THẬT — để nhóm quyết định có cần bounding-box / Weighted A* sớm không.

Ba lần đo của nhóm (mỗi lệnh ~1 phút; mỗi lần ghi vào thư mục riêng để không ghi đè nhau):
    python scripts/benchmark_astar.py --repeat 3                     # ô tô, ngắn nhất theo mét -> outputs/benchmark/
    python scripts/benchmark_astar.py --weight time --repeat 3 --out outputs/benchmark_car_time
    python scripts/benchmark_astar.py --vehicle motorbike_ice --weight time --repeat 3 --out outputs/benchmark_moto_time
Khác:
    python scripts/benchmark_astar.py --quick            # nhanh: 2 cặp ngẫu nhiên mỗi nhóm, bỏ đo cắt subgraph

Kết quả: in bảng ra màn hình + ghi outputs/benchmark/ (hoặc thư mục --out)
    benchmark_summary.md   báo cáo gửi nhóm (cấu hình máy, chi phí một lần, bảng theo khoảng cách, từng case)
    benchmark_raw.csv      từng truy vấn × từng thuật toán (thời gian, số node duyệt, độ dài, % dài hơn tối ưu)

Thuật toán so sánh (cùng MỘT cài đặt A* đơn giản bằng heapq để đếm được số node duyệt và so sánh công bằng):
    Dijkstra            A* với h = 0 (mốc tối ưu)
    A*                  h = haversine tới đích (admissible, consistent) -> độ dài phải BẰNG Dijkstra
    WA* w=...           f = g + w·h (Weighted A*): nhanh hơn, độ dài <= w × tối ưu
    A* + bbox lọc       chỉ duyệt node trong hộp bao (start, goal) nới --buffer-km (nodes_in_bbox, không copy);
                        tự nới gấp đôi nếu hộp làm mất đường
    cắt subgraph (copy) thời gian get_subgraph_near(...) — chi phí nếu cắt đồ thị con bằng hàm có sẵn
    nx.astar_path       A* của thư viện networkx (tham chiếu, không đếm node)
Thời gian là thời gian TÌM ĐƯỜNG (không gồm nạp đồ thị); chi phí một lần (nạp, lọc theo xe, dựng danh sách kề)
được báo riêng. Kết quả phụ thuộc máy — chạy trên máy của bạn rồi gửi file .md cho nhóm.
"""
import argparse
import csv
import heapq
import math
import platform
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import networkx as nx  # noqa: E402

from hanoi_graph import (  # noqa: E402
    get_profile, get_subgraph_near, get_vehicle_graph, haversine_m, load_cases, load_graph, nearest_node,
    nodes_in_bbox, vehicle_speed_kph,
)
from hanoi_graph.geo import EARTH_RADIUS_M  # noqa: E402
from hanoi_graph.paths import OUTPUT_DIR  # noqa: E402

BUCKETS = [(0, 5), (5, 15), (15, 30), (30, 80)]      # km đường chim bay


# ============================================================ cài đặt A* dùng chung cho mọi biến thể
def build_adjacency(H, cost_fn):
    """{u: [(v, cost)]} — cạnh song song lấy cost nhỏ nhất. Dựng 1 lần, mọi thuật toán dùng chung."""
    adj = {}
    for u, nbrs in H.adj.items():
        adj[u] = [(v, min(cost_fn(d) for d in keyed.values())) for v, keyed in nbrs.items()]
    return adj


def build_coords(H):
    return {n: (math.radians(d["y"]), math.radians(d["x"]), math.cos(math.radians(d["y"])))
            for n, d in H.nodes(data=True)}


def make_h(coords, goal, scale=1.0):
    """haversine(n, goal) × scale — cùng công thức/bán kính với hanoi_graph.geo.haversine_m."""
    phi2, lmb2, cos2 = coords[goal]
    two_r = 2.0 * EARTH_RADIUS_M * scale
    sin, asin, sqrt = math.sin, math.asin, math.sqrt

    def h(n):
        phi1, lmb1, cos1 = coords[n]
        a = sin((phi2 - phi1) * 0.5) ** 2 + cos1 * cos2 * sin((lmb2 - lmb1) * 0.5) ** 2
        return two_r * asin(sqrt(a if a < 1.0 else 1.0))
    return h


def astar(adj, s, g, h=None, w=1.0, allowed=None):
    """Trả về (path, cost, số node đã duyệt). h=None -> Dijkstra. allowed: tập node được phép đi (bbox)."""
    INF = math.inf
    gscore, parent, closed, hcache = {s: 0.0}, {s: None}, set(), {}

    def hv(n):
        v = hcache.get(n)
        if v is None:
            v = hcache[n] = h(n) if h is not None else 0.0
        return v

    heap, counter, expanded, found = [(w * hv(s), 0, s)], 0, 0, False
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        _, _, u = pop(heap)
        if u in closed:
            continue
        if u == g:
            found = True
            break
        closed.add(u)
        expanded += 1
        gu = gscore[u]
        for v, c in adj[u]:
            if allowed is not None and v not in allowed:
                continue
            ng = gu + c
            if ng < gscore.get(v, INF):
                gscore[v] = ng
                parent[v] = u
                counter += 1
                push(heap, (ng + w * hv(v), counter, v))
    if not found:
        return None, INF, expanded
    path, n = [], g
    while n is not None:
        path.append(n)
        n = parent[n]
    return path[::-1], gscore[g], expanded


def timed(fn, repeat):
    best, out = math.inf, None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t0)
    return out, best * 1000.0


# ============================================================ truy vấn
def dataset_queries(H, vehicle_id):
    data = load_cases()
    out = []
    for c in data["cases"]:
        a, b = data["landmarks"][c["start"]], data["landmarks"][c["goal"]]
        s, g = nearest_node(H, a["lat"], a["lng"]), nearest_node(H, b["lat"], b["lng"])
        out.append((f"{c['id']}", s, g))
    return out


def random_queries(H, per_bucket, seed, max_tries=200_000):
    rnd = random.Random(seed)
    nodes = list(H.nodes)
    need = {bk: per_bucket for bk in BUCKETS}
    out = []
    tries = 0
    while any(need.values()) and tries < max_tries:
        tries += 1
        s, g = rnd.choice(nodes), rnd.choice(nodes)
        if s == g:
            continue
        d = haversine_m(H.nodes[s]["y"], H.nodes[s]["x"], H.nodes[g]["y"], H.nodes[g]["x"]) / 1000
        for lo, hi in BUCKETS:
            if lo <= d < hi and need[(lo, hi)]:
                need[(lo, hi)] -= 1
                out.append((f"rand_{lo}-{hi}km_{per_bucket - need[(lo, hi)]}", s, g))
                break
    return out


def bucket_of(km):
    for lo, hi in BUCKETS:
        if lo <= km < hi:
            return f"{lo}–{hi} km"
    return f">= {BUCKETS[-1][1]} km"


# ============================================================ bảng
def fmt_table(headers, rows):
    cols = list(zip(*([headers] + [[str(x) for x in r] for r in rows]))) if rows else [[h] for h in headers]
    widths = [max(len(x) for x in col) for col in cols]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep = "  ".join("-" * w for w in widths)
    body = ["  ".join(str(x).rjust(w) if i else str(x).ljust(w) for i, (x, w) in enumerate(zip(r, widths)))
            for r in rows]
    return "\n".join([line, sep] + body)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def cpu_name():
    if platform.system() == "Windows":          # platform.processor() trên Windows chỉ ra "Intel64 Family 6 ..."
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    name = platform.processor()
    if not name or name in ("x86_64", "i386", "AMD64"):
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return name or platform.machine()


def med(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return statistics.median(xs) if xs else float("nan")


# ============================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vehicle", default="car_ice")
    ap.add_argument("--weight", choices=["length", "time"], default="length",
                    help="length: ngắn nhất theo mét; time: nhanh nhất theo giây (trần tốc độ xe)")
    ap.add_argument("--pairs", type=int, default=5, help="số cặp ngẫu nhiên mỗi nhóm khoảng cách (4 nhóm)")
    ap.add_argument("--weights", type=float, nargs="+", default=[1.2, 1.5, 2.0], help="các hệ số w của WA*")
    ap.add_argument("--buffer-km", type=float, default=2.0, help="buffer của bbox")
    ap.add_argument("--repeat", type=int, default=1, help="chạy lặp mỗi phép đo, lấy lần nhanh nhất")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quick", action="store_true", help="2 cặp ngẫu nhiên mỗi nhóm, bỏ đo cắt subgraph")
    ap.add_argument("--no-subgraph-copy", action="store_true", help="bỏ đo get_subgraph_near (chậm với tuyến dài)")
    ap.add_argument("--no-networkx", action="store_true", help="bỏ đo nx.astar_path")
    ap.add_argument("--out", default=str(OUTPUT_DIR / "benchmark"))
    args = ap.parse_args()
    if args.quick:
        args.pairs, args.no_subgraph_copy = 2, True

    print("=" * 78)
    print(f"Benchmark A* — xe {args.vehicle}, tối ưu theo {args.weight}")
    print("=" * 78)
    one_time = {}
    t0 = time.perf_counter()
    G = load_graph()
    one_time["Nạp đồ thị (pickle)"] = time.perf_counter() - t0
    profile = get_profile(args.vehicle)
    t0 = time.perf_counter()
    H = get_vehicle_graph(G, profile)
    one_time[f"Lọc đồ thị theo xe {args.vehicle}"] = time.perf_counter() - t0
    if args.weight == "length":
        cost_fn, h_scale, unit = (lambda d: d["length"]), 1.0, "m"
    else:
        cost_fn = lambda d: d["length"] / (vehicle_speed_kph(profile, d) / 3.6)  # noqa: E731
        h_scale, unit = 1.0 / (profile.speed_cap_kph / 3.6), "s"
    t0 = time.perf_counter()
    adj = build_adjacency(H, cost_fn)
    coords = build_coords(H)
    one_time["Dựng danh sách kề + toạ độ (cho A*)"] = time.perf_counter() - t0
    worse = "dài hơn" if unit == "m" else "chậm hơn"     # chi phí cao hơn tối ưu: theo mét hay theo giây
    n_nodes, n_edges = H.number_of_nodes(), sum(len(v) for v in adj.values())
    print(f"Đồ thị {args.vehicle}: {n_nodes:,} node, {n_edges:,} cạnh (đã gộp cạnh song song)")
    for k, v in one_time.items():
        print(f"  {k:42s} {v:6.1f} s")

    fixed = dataset_queries(H, args.vehicle)
    queries = fixed + random_queries(H, args.pairs, args.seed)
    n_fixed = len(fixed)
    print(f"\n{len(queries)} truy vấn ({n_fixed} case cố định + {len(queries) - n_fixed} cặp ngẫu nhiên, "
          f"seed={args.seed}). Đang chạy...\n")

    algos = ["Dijkstra", "A*"] + [f"WA* w={w:g}" for w in args.weights] + [f"A* + bbox {args.buffer_km:g} km"]
    rows = []        # dict mỗi (truy vấn, thuật toán)
    t_all = time.perf_counter()
    for qi, (qid, s, g) in enumerate(queries, 1):
        km = haversine_m(H.nodes[s]["y"], H.nodes[s]["x"], H.nodes[g]["y"], H.nodes[g]["x"]) / 1000
        h = make_h(coords, g, h_scale)
        base = None
        results = {}
        (p, c, e), ms = timed(lambda: astar(adj, s, g), args.repeat)
        results["Dijkstra"] = (p, c, e, ms, 0.0, None)
        base = c
        (p, c, e), ms = timed(lambda: astar(adj, s, g, h), args.repeat)
        results["A*"] = (p, c, e, ms, 0.0, None)
        for w in args.weights:
            (p, c, e), ms = timed(lambda: astar(adj, s, g, h, w=w), args.repeat)
            results[f"WA* w={w:g}"] = (p, c, e, ms, 0.0, None)
        # bbox lọc trực tiếp (không copy), tự nới nếu mất đường
        buf, prep_total, ms_total, e_total = args.buffer_km, 0.0, 0.0, 0
        while True:
            allowed, prep = timed(lambda: nodes_in_bbox(H, s, g, buffer_km=buf), 1)
            (p, c, e), ms = timed(lambda: astar(adj, s, g, h, allowed=allowed), args.repeat)
            prep_total, ms_total, e_total = prep_total + prep, ms_total + ms, e_total + e
            if p is not None or buf >= 64:
                break
            buf *= 2
        results[f"A* + bbox {args.buffer_km:g} km"] = (p, c, e_total, ms_total, prep_total, buf)
        if not args.no_subgraph_copy:
            _, ms = timed(lambda: get_subgraph_near(H, s, g, buffer_km=args.buffer_km), 1)
            results["cắt subgraph (copy)"] = (None, math.nan, None, math.nan, ms, None)
        if not args.no_networkx:
            weight = "length" if args.weight == "length" else (lambda u, v, d: min(cost_fn(x) for x in d.values()))
            p, ms = timed(lambda: nx.astar_path(H, s, g, heuristic=lambda n, _t: h(n), weight=weight), args.repeat)
            c = sum(min(cost_fn(x) for x in H[u][v].values()) for u, v in zip(p[:-1], p[1:]))
            results["nx.astar_path"] = (p, c, None, ms, 0.0, None)

        for name, (p, c, e, ms, prep, buf_used) in results.items():
            subopt = (c / base - 1) * 100 if (base and c == c and c != math.inf) else math.nan
            if subopt == subopt and abs(subopt) < 1e-6:      # sai số dấu phẩy động (vd. -0.0000001 %) -> 0
                subopt = 0.0
            rows.append({
                "query": qid, "group": "case" if not qid.startswith("rand_") else "random", "bucket": bucket_of(km),
                "straight_km": round(km, 2), "algorithm": name, "time_ms": round(ms, 2) if ms == ms else "",
                "prep_ms": round(prep, 2), "expanded": "" if e is None else e,
                "cost": "" if c != c or c == math.inf else round(c, 2), "unit": unit,
                "subopt_pct": "" if subopt != subopt else round(subopt, 3),
                "path_nodes": "" if p is None else len(p), "bbox_buffer_km": "" if buf_used is None else buf_used,
            })
        a_c, d_c = results["A*"][1], results["Dijkstra"][1]
        flag = "" if abs(a_c - d_c) <= 1e-6 * max(1.0, d_c) else "  <-- A* KHÁC Dijkstra!"
        print(f"[{qi:2d}/{len(queries)}] {qid:34s} {km:6.1f} km | Dijkstra {results['Dijkstra'][3]:8.1f} ms "
              f"| A* {results['A*'][3]:7.1f} ms{flag}")
    total_s = time.perf_counter() - t_all

    # -------------------------------------------------------- tổng hợp
    names = algos + (["cắt subgraph (copy)"] if not args.no_subgraph_copy else []) + \
        ([] if args.no_networkx else ["nx.astar_path"])
    bucket_names = [f"{lo}–{hi} km" for lo, hi in BUCKETS]
    summary_rows = []
    for bname in bucket_names:
        qs = {r["query"] for r in rows if r["bucket"] == bname}
        if not qs:
            continue
        for name in names:
            rs = [r for r in rows if r["bucket"] == bname and r["algorithm"] == name]
            if name == "cắt subgraph (copy)":
                tms = [r["prep_ms"] for r in rs]
                summary_rows.append([bname, len(qs), name, f"{med(tms):.1f}", f"{max(tms):.1f}", "", "", "(chỉ thời gian cắt)"])
                continue
            tms = [r["time_ms"] + r["prep_ms"] for r in rs]
            exp_ = [r["expanded"] for r in rs if r["expanded"] != ""]
            sub = [r["subopt_pct"] for r in rs if r["subopt_pct"] != ""]
            summary_rows.append([bname, len(qs), name, f"{med(tms):.1f}", f"{max(tms):.1f}",
                                 f"{med(exp_):,.0f}" if exp_ else "", f"{max(sub):.2f}" if sub else "", ""])
    headers = ["Khoảng cách", "Số truy vấn", "Thuật toán", "Trung vị ms", "Tối đa ms", "Node duyệt (TV)",
               f"{worse.capitalize()} tối ưu tối đa %", "Ghi chú"]

    case_rows = []
    for qid, s, g in fixed:
        rs = {r["algorithm"]: r for r in rows if r["query"] == qid}
        d = rs["Dijkstra"]
        wa = rs.get("WA* w=1.5") or rs[f"WA* w={args.weights[0]:g}"]
        bb = rs[f"A* + bbox {args.buffer_km:g} km"]
        case_rows.append([qid, d["straight_km"], d["cost"], d["time_ms"], rs["A*"]["time_ms"], rs["A*"]["expanded"],
                          d["expanded"], wa["time_ms"], wa["subopt_pct"], round(bb["time_ms"] + bb["prep_ms"], 1)])
    case_headers = ["Case", "Chim bay km", f"Tối ưu ({unit})", "Dijkstra ms", "A* ms", "A* node", "Dijkstra node",
                    f"{'WA* w=1.5' if 'WA* w=1.5' in names else 'WA*'} ms", f"WA* {worse} %", "bbox ms"]

    # các con số chính (chỉ là số liệu, quyết định để nhóm)
    def ratio_med(a, b, key):
        vals = []
        for q in {r["query"] for r in rows}:
            ra = next(r for r in rows if r["query"] == q and r["algorithm"] == a)
            rb = next(r for r in rows if r["query"] == q and r["algorithm"] == b)
            if ra[key] not in ("", 0) and rb[key] not in ("", 0):
                vals.append(rb[key] / ra[key])
        return med(vals)

    a_rows = [r for r in rows if r["algorithm"] == "A*"]
    long_a = [r["time_ms"] for r in a_rows if r["straight_km"] >= 30]
    mismatches = [r["query"] for r in a_rows if r["subopt_pct"] != "" and abs(r["subopt_pct"]) > 1e-4]
    facts = [
        f"A* cho {'độ dài' if unit == 'm' else 'thời gian đi'} BẰNG Dijkstra ở "
        f"{len(a_rows) - len(mismatches)}/{len(a_rows)} truy vấn"
        + (f" (KHÁC ở: {', '.join(mismatches)})" if mismatches else "") + ".",
        f"A* duyệt ít node hơn Dijkstra trung vị {ratio_med('A*', 'Dijkstra', 'expanded'):.1f} lần, "
        f"nhanh hơn trung vị {ratio_med('A*', 'Dijkstra', 'time_ms'):.1f} lần.",
        f"Thời gian A* trên toàn đồ thị: trung vị {med([r['time_ms'] for r in a_rows]):.0f} ms, "
        f"tối đa {max(r['time_ms'] for r in a_rows):.0f} ms"
        + (f"; tuyến >= 30 km: trung vị {med(long_a):.0f} ms." if long_a else "."),
    ]
    for w in args.weights:
        n = f"WA* w={w:g}"
        subs = [r["subopt_pct"] for r in rows if r["algorithm"] == n and r["subopt_pct"] != ""]
        facts.append(f"{n}: nhanh hơn A* trung vị {ratio_med(n, 'A*', 'time_ms'):.1f} lần, "
                     f"{worse} tối ưu tối đa {max(subs):.2f}% (trung vị {med(subs):.2f}%).")
    bbn = f"A* + bbox {args.buffer_km:g} km"
    bb_rows = [r for r in rows if r["algorithm"] == bbn]
    bb_sub = [r["subopt_pct"] for r in bb_rows if r["subopt_pct"] != ""]
    grown = sum(1 for r in bb_rows if r["bbox_buffer_km"] not in ("", args.buffer_km))
    facts.append(f"{bbn} (gồm thời gian lọc node): nhanh hơn A* toàn đồ thị trung vị "
                 f"{med([(a['time_ms']) / max(b['time_ms'] + b['prep_ms'], 1e-9) for a, b in zip(a_rows, bb_rows)]):.1f} lần; "
                 f"{worse} tối ưu tối đa {max(bb_sub) if bb_sub else 0:.2f}%; phải tự nới hộp ở {grown} truy vấn.")
    if not args.no_subgraph_copy:
        cut = [r["prep_ms"] for r in rows if r["algorithm"] == "cắt subgraph (copy)"]
        facts.append(f"get_subgraph_near (copy đồ thị con): riêng bước cắt mất trung vị {med(cut):.0f} ms, tối đa "
                     f"{max(cut):.0f} ms — so với A* toàn đồ thị trung vị {med([r['time_ms'] for r in a_rows]):.0f} ms.")
    if not args.no_networkx:
        facts.append(f"nx.astar_path (thư viện): chậm hơn A* tự viết trung vị "
                     f"{ratio_med('A*', 'nx.astar_path', 'time_ms'):.1f} lần (cùng heuristic).")

    # -------------------------------------------------------- in + ghi file
    print("\n" + "=" * 78)
    print("CÁC CON SỐ CHÍNH")
    print("=" * 78)
    for f in facts:
        print(" -", f)
    print("\nTHEO KHOẢNG CÁCH (thời gian = tìm đường + lọc bbox nếu có)")
    print(fmt_table(headers, summary_rows))
    print("\nTỪNG CASE CỐ ĐỊNH")
    print(fmt_table(case_headers, case_rows))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "benchmark_raw.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    import networkx
    env = [
        ["Thời điểm", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Máy", f"{cpu_name()} — {platform.system()} {platform.release()}"],
        ["Python / networkx", f"{platform.python_version()} / {networkx.__version__}"],
        ["Phương tiện / tối ưu theo", f"{args.vehicle} / {args.weight} ({unit})"],
        ["Đồ thị đã lọc", f"{n_nodes:,} node, {n_edges:,} cạnh"],
        ["Truy vấn", f"{len(queries)} ({n_fixed} case cố định + {len(queries) - n_fixed} ngẫu nhiên, seed {args.seed}), "
                     f"lặp {args.repeat}"],
        ["Tổng thời gian chạy", f"{total_s:.0f} s"],
    ]
    md = [
        f"# Benchmark A* trên đồ thị Hà Nội — {args.vehicle}",
        "",
        md_table(["Mục", "Giá trị"], env),
        "",
        "## Các con số chính",
        "",
        *[f"- {f}" for f in facts],
        "",
        "## Chi phí một lần (trước khi tìm đường)",
        "",
        md_table(["Bước", "Thời gian (s)"], [[k, f"{v:.1f}"] for k, v in one_time.items()]),
        "",
        "## Theo khoảng cách đường chim bay",
        "",
        "Thời gian = tìm đường (+ lọc node cho bbox). TV = trung vị.",
        "",
        md_table(headers, summary_rows),
        "",
        "## Từng case cố định",
        "",
        md_table(case_headers, case_rows),
        "",
        "## Cách đọc",
        "",
        "- **Node duyệt**: số node được lấy ra khỏi hàng đợi ưu tiên — không phụ thuộc máy, dùng để so sánh "
        "thuật toán công bằng hơn thời gian.",
        f"- **{worse.capitalize()} tối ưu %**: so với Dijkstra (mốc tối ưu). A* phải là 0; Weighted A* được phép > 0 "
        "nhưng không quá (w−1)·100%.",
        "- Thời gian phụ thuộc máy và việc đang chạy gì khác; chạy với `--repeat 3` để ổn định hơn.",
        "- Lệnh tái tạo: `python scripts/benchmark_astar.py " + " ".join(sys.argv[1:]) + "`",
        "",
    ]
    (out_dir / "benchmark_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nĐã ghi: {out_dir / 'benchmark_summary.md'}\n       {out_dir / 'benchmark_raw.csv'}")


if __name__ == "__main__":
    main()
