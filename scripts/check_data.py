"""Kiểm tra nhanh "sức khoẻ" dữ liệu sau khi build/copy về máy: đồ thị, một chiều, liên thông, quận, xe, bộ test.

    python scripts/check_data.py          (~30 s; không cần mạng)

In ra từng mục kèm [OK] / [!!]. Mục [!!] nghĩa là cần xem lại (vd. đồ thị bị vô hướng, thiếu file, landmark xa đường).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hanoi_graph import (  # noqa: E402
    DistrictIndex, check_connectivity, get_district, load_cases, load_graph, load_profiles, nearest_node,
    oneway_report,
)
from hanoi_graph.paths import DISTRICTS_GEOJSON, GOLDEN, GRAPH_GRAPHML, GRAPH_PICKLE  # noqa: E402
from hanoi_graph.testcases import MAX_SNAP_M  # noqa: E402


def mark(ok: bool) -> str:
    return "[OK]" if ok else "[!!]"


def main() -> None:
    print("1) FILE DỮ LIỆU")
    for p in (GRAPH_PICKLE, GRAPH_GRAPHML, DISTRICTS_GEOJSON, GOLDEN):
        print(f"   {mark(p.exists())} {p.name:28s} {p.stat().st_size / 1e6:8.1f} MB" if p.exists()
              else f"   {mark(False)} {p.name:28s} chưa có")

    print("\n2) ĐỒ THỊ")
    t0 = time.perf_counter()
    G = load_graph()
    print(f"   Nạp trong {time.perf_counter() - t0:.1f} s: {type(G).__name__}, "
          f"{G.number_of_nodes():,} node, {G.number_of_edges():,} cạnh")
    print(f"   {mark(G.is_directed())} có hướng (DiGraph/MultiDiGraph)")

    r = oneway_report(G)
    print(f"   {mark(0.01 < r.oneway_fraction < 0.15)} cạnh một chiều (không có cạnh ngược): "
          f"{r.n_edges_oneway:,} ({r.oneway_fraction:.2%}); gắn oneway=True: {r.n_tagged_oneway:,}; "
          f"oneway nhưng có cạnh ngược (đường đôi): {r.n_tagged_oneway_but_has_reverse:,}")

    c = check_connectivity(G)
    print(f"   {mark(c.is_strongly_connected)} liên thông: {c.summary()}")

    print("\n3) QUẬN / HUYỆN")
    idx = DistrictIndex.load()
    km2 = idx.gdf.to_crs(32648).area.sum() / 1e6
    print(f"   {mark(len(idx.gdf) == 30)} {len(idx.gdf)} đơn vị, tổng {km2:,.0f} km² (thật ~3.360 km²)")
    for name, (lat, lng), expected in [("Hồ Gươm", (21.0287, 105.8524), "HoanKiem"),
                                       ("Cầu Giấy", (21.0330, 105.7990), "CauGiay"),
                                       ("Sơn Tây", (21.1380, 105.5050), "SonTay"),
                                       ("Hạ Long (ngoài HN)", (20.9599, 107.0425), None)]:
        got = get_district(lat, lng, index=idx)
        print(f"   {mark(got == expected)} get_district{(lat, lng)} -> {got!r:12s} ({name})")
    no_district = sum(1 for _, d in G.nodes(data=True) if d.get("district") in (None, "None"))
    print(f"   {mark(no_district < 0.001 * G.number_of_nodes())} node không thuộc quận nào: {no_district}")

    print("\n4) PHƯƠNG TIỆN (config/vehicle_profiles.json)")
    for vid, p in load_profiles().items():
        print(f"   {vid:14s} {p.name_vi:24s} lội nước {p.max_wading_depth_cm:4.0f} cm  trần {p.speed_cap_kph:3.0f} km/h  "
              f"cấm {list(p.forbidden_highway_types) or '-'} {dict(p.forbidden_tags) or ''}"
              + (f"  một chiều riêng: {p.oneway_tag}" if p.oneway_tag else ""))

    print("\n5) BỘ DATA TEST (tests/fixtures/test_cases.json)")
    data = load_cases()
    print(f"   {len(data['cases'])} case, {len(data['landmarks'])} landmark")
    for key, lm in data["landmarks"].items():
        _, d = nearest_node(G, lm["lat"], lm["lng"], return_dist=True)
        used = any(key in (c["start"], c["goal"]) for c in data["cases"])
        ok = d <= MAX_SNAP_M or not used
        print(f"   {mark(ok)} {key:18s} cách node gần nhất {d:6.0f} m{'' if used else '  (chưa case nào dùng)'}")
    if GOLDEN.exists():
        meta = json.loads(GOLDEN.read_text(encoding="utf-8"))["_meta"]
        same = meta["graph"]["n_nodes"] == G.number_of_nodes()
        print(f"   {mark(same)} golden.json chốt lúc {meta['generated_at']} trên đồ thị {meta['graph']['n_nodes']:,} node"
              + ("" if same else "  -> đồ thị đã đổi: chạy python scripts/freeze_golden.py"))
    else:
        print(f"   {mark(False)} chưa có golden.json -> chạy python scripts/freeze_golden.py")


if __name__ == "__main__":
    main()
