"""Test chức năng & hiệu năng của gói `flood_routing` trên ĐỒ THỊ HÀ NỘI THẬT (data/hanoi_all.*).

Sử dụng trực tiếp fixture `hanoi_graph` từ `conftest.py` và bộ dữ liệu `load_cases()` từ `hanoi_graph`.
Không kiểm tra hiệu năng của 2 hàm tìm đường; tập trung vào các hàm mô phỏng điểm ngập, lan tỏa,
rút nước theo thời gian, chồng lấn nguồn ngập và lọc cạnh theo phương tiện.

Chạy (hiển thị bảng kết quả chi tiết ra màn hình):
    python -m pytest tests/test_flood_routing_real.py -v -s -rs
Tự skip nếu chưa có data (fixture hanoi_graph trong conftest.py).
"""
from __future__ import annotations

import math
import sys
import time

import networkx as nx
import pytest

from flood_routing import (
    FloodSource,
    apply_dynamic_flood,
    blocked_edges_at_time,
    compute_flood_spread,
    flood_at_time,
    get_drain_rate_for_district,
)
from hanoi_graph import (
    get_profile,
    get_vehicle_graph,
    load_cases,
    require_directed,
)
from hanoi_graph.districts import get_district, slugify

pytestmark = pytest.mark.hanoi


def _print_banner(title: str) -> None:
    print("\n" + "=" * 95)
    print(f"  {title}")
    print("=" * 95)


# ---------------------------------------------------------------- 1. Landmarks, Quận & Bán kính động
def test_1_landmarks_district_and_dynamic_radius(hanoi_graph):
    """Kiểm tra snap điểm ngập, tra cứu quận tự động và bán kính động R = k*sqrt(F_0) trên 10 landmarks."""
    G = hanoi_graph
    require_directed(G)
    landmarks = load_cases()["landmarks"]

    _print_banner(
        f"TEST 1: TRA CỨU QUẬN, TỐC ĐỘ RÚT r(area) & BÁN KÍNH ĐỘNG TRÊN ĐỒ THỊ THẬT "
        f"({G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges)"
    )
    print(
        f"  {'Landmark':<18} | {'Quận kỳ vọng':<12} | {'Quận thực tế':<12} | "
        f"{'r(area) cm/p':<12} | {'R(36cm, k=50)':<15} | {'Cạnh snap e_0':<26} | {'Thời gian'}"
    )
    print("-" * 95)

    for key, p in landmarks.items():
        lat, lng = float(p["lat"]), float(p["lng"])
        expected_district = p["district"]

        t0 = time.perf_counter()
        src = FloodSource(lat=lat, lng=lng, f0=36.0, k=50.0, id=f"src_{key}")
        src.bind_to_graph(G, get_district_fn=get_district)
        bind_ms = (time.perf_counter() - t0) * 1000.0

        expected_r = 50.0 * math.sqrt(36.0)  # 300.0 m
        expected_rate = get_drain_rate_for_district(expected_district)

        print(
            f"  {key:<18} | {expected_district:<12} | {src.district:<12} | "
            f"{src.drain_rate:>10.2f}   | {src.radius_m:>11.1f} m  | "
            f"{str(src.edge_0):<26} | {bind_ms:>6.2f} ms"
        )

        assert src.edge_0 is not None
        assert G.has_edge(*src.edge_0)
        assert slugify(src.district) == slugify(expected_district)
        assert math.isclose(src.drain_rate, expected_rate, rel_tol=1e-6)
        assert math.isclose(src.radius_m, expected_r, rel_tol=1e-6)


# ---------------------------------------------------------------- 2. Lan tỏa tuyến tính từ 1 điểm ngập
def test_2_single_source_spatial_spread(hanoi_graph):
    """Test 1 điểm ngập (Tháp Rùa) -> lan ra các cạnh lân cận giảm dần tuyến tính theo khoảng cách."""
    G = hanoi_graph
    lm = load_cases()["landmarks"]["thap_rua"]

    src = FloodSource(lat=lm["lat"], lng=lm["lng"], f0=40.0, k=50.0, id="thap_rua_spot")
    # Với F_0 = 40cm, k = 50 -> R = 50 * sqrt(40) ≈ 316.23 m
    t0 = time.perf_counter()
    spread_cache = compute_flood_spread(G, [src], get_district_fn=get_district)
    spread_ms = (time.perf_counter() - t0) * 1000.0

    flood_t0 = flood_at_time(spread_cache, t=0.0)
    assert len(flood_t0) > 10, "Điểm ngập tại Tháp Rùa phải lan ra nhiều cạnh xung quanh trên bản đồ thật"
    assert src.edge_0 in flood_t0
    assert math.isclose(flood_t0[src.edge_0], src.f0, abs_tol=1e-5)

    # Kiểm tra công thức F(e) = F_0 * max(0, 1 - dist/R) trên mọi cạnh bị ảnh hưởng
    samples = []
    for edge_key, entries in spread_cache.items():
        entry = entries[0]
        actual_f = flood_t0[edge_key]
        expected_f = src.f0 * max(0.0, 1.0 - entry.dist_e / src.radius_m)
        assert math.isclose(actual_f, expected_f, abs_tol=1e-5)
        samples.append((entry.dist_e, edge_key, entry.alpha_0, actual_f, expected_f))

    samples.sort(key=lambda x: x[0])

    _print_banner("TEST 2: 1 ĐIỂM NGẬP (THÁP RÙA) LAN TỎA TUYẾN TÍNH TRÊN ĐỒ THỊ HÀ NỘI THẬT")
    print(f"  [+] Tâm ngập: {lm['name']} ({lm['lat']}, {lm['lng']}) | Cạnh nguồn e_0 = {src.edge_0}")
    print(f"  [+] Độ sâu F_0 = {src.f0:.1f} cm | Bán kính động R = {src.radius_m:.2f} m | Số cạnh ngập: {len(flood_t0)}")
    print(f"  [+] Thời gian chạy compute_flood_spread (1 lần): {spread_ms:.2f} ms")
    print("-" * 95)
    print(f"  {'Cạnh (u, v, key)':<32} | {'Khoảng cách dist':<18} | {'Hệ số alpha':<14} | {'F(e) thực tế':<14} | {'F(e) kỳ vọng'}")
    print("-" * 95)

    # In 8 mẫu đại diện trải đều từ tâm (dist = 0) ra rìa vùng ngập (dist -> R)
    step = max(1, len(samples) // 8)
    for dist_e, edge_key, alpha, actual_f, expected_f in samples[::step][:8]:
        print(
            f"  {str(edge_key):<32} | {dist_e:>14.2f} m  | {alpha:>14.4f} | "
            f"{actual_f:>10.2f} cm  | {expected_f:>10.2f} cm"
        )

    assert samples[0][3] > samples[-1][3] > 0.0


# ---------------------------------------------------------------- 3. Nước rút theo thời gian t
def test_3_water_recession_over_time(hanoi_graph):
    """Test nước rút theo thời gian t: F_0(e_0, t) = max(0, F_0 - r(area)*t) ở 2 quận khác nhau."""
    G = hanoi_graph
    lms = load_cases()["landmarks"]
    lm_hk = lms["thap_rua"]         # Hoàn Kiếm: r = 0.50 cm/phút
    lm_ntl = lms["ben_xe_my_dinh"]  # Nam Từ Liêm: r = 0.90 cm/phút

    src_hk = FloodSource(lat=lm_hk["lat"], lng=lm_hk["lng"], f0=36.0, k=40.0, id="hk_spot")
    src_ntl = FloodSource(lat=lm_ntl["lat"], lng=lm_ntl["lng"], f0=36.0, k=40.0, id="ntl_spot")

    cache = compute_flood_spread(G, [src_hk, src_ntl], get_district_fn=get_district)

    t_clear_hk = src_hk.f0 / src_hk.drain_rate    # 36 / 0.50 = 72 phút
    t_clear_ntl = src_ntl.f0 / src_ntl.drain_rate  # 36 / 0.90 = 40 phút

    _print_banner("TEST 3: MÔ PHỎNG NƯỚC RÚT THEO THỜI GIAN t GIỮA CÁC QUẬN TRÊN BẢN ĐỒ THẬT")
    print(f"  [+] Hoàn Kiếm   (Tháp Rùa)       : F_0 = 36.0 cm, r = {src_hk.drain_rate:.2f} cm/phút -> Rút hết lúc t = {t_clear_hk:.1f} phút")
    print(f"  [+] Nam Từ Liêm (Bến xe Mỹ Đình) : F_0 = 36.0 cm, r = {src_ntl.drain_rate:.2f} cm/phút -> Rút hết lúc t = {t_clear_ntl:.1f} phút")
    print("-" * 95)
    print(
        f"  {'Thời điểm t (phút)':<20} | {'Tâm Hoàn Kiếm (Thực / Kỳ vọng)':<34} | "
        f"{'Tâm Nam Từ Liêm (Thực / Kỳ vọng)':<34}"
    )
    print("-" * 95)

    assert src_hk.edge_0 is not None and src_ntl.edge_0 is not None

    for t in (0.0, 10.0, 20.0, 40.0, 55.0, 72.0, 85.0):
        fmap = flood_at_time(cache, t=t)
        act_hk = fmap.get(src_hk.edge_0, 0.0)
        act_ntl = fmap.get(src_ntl.edge_0, 0.0)

        exp_hk = max(0.0, 36.0 - src_hk.drain_rate * t)
        exp_ntl = max(0.0, 36.0 - src_ntl.drain_rate * t)

        print(
            f"  t = {t:<16.1f} | {act_hk:>10.2f} cm / {exp_hk:>10.2f} cm      | "
            f"{act_ntl:>10.2f} cm / {exp_ntl:>10.2f} cm"
        )
        assert math.isclose(act_hk, exp_hk, abs_tol=1e-5)
        assert math.isclose(act_ntl, exp_ntl, abs_tol=1e-5)

    # Tại t = 40 phút: Mỹ Đình đã rút cạn về 0, Hoàn Kiếm vẫn còn ngập 16 cm
    f_40 = flood_at_time(cache, t=40.0)
    assert f_40.get(src_ntl.edge_0, 0.0) == 0.0
    assert math.isclose(f_40.get(src_hk.edge_0, 0.0), 16.0, abs_tol=1e-5)

    # Tại t = 72 phút: Cả 2 quận đều đã rút hết hoàn toàn
    assert flood_at_time(cache, t=72.0) == {}


# ---------------------------------------------------------------- 4. Chồng lấn nguồn ngập & Ngưỡng xe (case_4, case_4b)
def test_4_overlapping_sources_and_vehicle_thresholds(hanoi_graph):
    """Test chồng lấn nhiều nguồn ngập dùng max() và kiểm tra chặn cạnh theo xe từ test_cases.json."""
    G = hanoi_graph
    data = load_cases()
    lm1 = data["landmarks"]["thap_rua"]
    lm2 = data["landmarks"]["nha_hat_lon"]

    # Phần A: Đặt 2 nguồn tại Tháp Rùa và Nhà hát Lớn (cách nhau ~750m chim bay) với R = 1200m để giao thoa
    s1 = FloodSource(lat=lm1["lat"], lng=lm1["lng"], f0=35.0, id="overlap_thap_rua")
    s2 = FloodSource(lat=lm2["lat"], lng=lm2["lng"], f0=48.0, id="overlap_nha_hat_lon")

    cache_overlap = compute_flood_spread(G, [s1, s2], R=1200.0, get_district_fn=get_district)
    fmap_overlap = flood_at_time(cache_overlap, t=0.0)

    overlap_edges = [
        (ekey, entries) for ekey, entries in cache_overlap.items() if len(entries) >= 2
    ]
    assert len(overlap_edges) > 0, "Với R=1200m, vùng ngập Tháp Rùa và Nhà hát Lớn phải giao thoa!"

    _print_banner("TEST 4: XỬ LÝ CHỒNG LẤN DÙNG MAX() & KIỂM CHỨNG NGƯỠNG XE (CASE_4 & CASE_4B)")
    print(f"  [Phần A] Số cạnh đường phố thực tế bị ảnh hưởng bởi cả 2 nguồn ngập: {len(overlap_edges)} cạnh")
    print("-" * 95)
    print(f"  {'Cạnh giao thoa (u, v, key)':<32} | {'Do Nguồn 1':<14} | {'Do Nguồn 2':<14} | {'Thực tế max()':<14} | {'Nếu cộng dồn (Sai)'}")
    print("-" * 95)

    for ekey, entries in overlap_edges[:6]:
        vals = [e.source.f0_at_time(0.0) * e.alpha_0 for e in entries]
        expected_max = max(vals)
        wrong_sum = sum(vals)
        actual_f = fmap_overlap[ekey]
        print(
            f"  {str(ekey):<32} | {vals[0]:>10.2f} cm | {vals[1]:>10.2f} cm | "
            f"{actual_f:>10.2f} cm | {wrong_sum:>10.2f} cm"
        )
        assert math.isclose(actual_f, expected_max, abs_tol=1e-5)
        assert actual_f < wrong_sum - 1e-4

    # Phần B: Kiểm tra lọc cạnh ngập trên đồ thị phương tiện (Hm, Hv, Hc) ứng với case_4 (35cm) và case_4b (30cm)
    print("-" * 95)
    print("  [Phần B] Kiểm tra chặn cạnh trên đồ thị lọc theo xe (get_vehicle_graph):")
    print(f"  {'Kịch bản (test_cases.json)':<28} | {'Mức ngập':<10} | {'motorbike_ice (20cm)':<22} | {'vf3 (30cm)':<18} | {'car_ice (50cm)'}")
    print("-" * 95)

    vehicles = {vid: get_profile(vid) for vid in ("motorbike_ice", "vf3", "car_ice")}
    veh_graphs = {vid: get_vehicle_graph(G, prof) for vid, prof in vehicles.items()}

    for case_id, depth_cm, radius_m, exp_blocked in [
        ("case_4_flood_on_route", 35.0, 60.0, {"motorbike_ice", "vf3"}),
        ("case_4b_flood_boundary_30cm", 30.0, 60.0, {"motorbike_ice"}),
    ]:
        # Đặt điểm ngập tại đường ô tô/xe máy đều đi qua (Lăng Bác)
        lm_test = data["landmarks"]["lang_bac"]
        k_val = radius_m / math.sqrt(depth_cm)
        spot = FloodSource(lat=lm_test["lat"], lng=lm_test["lng"], f0=depth_cm, k=k_val, id=case_id)
        c_case = compute_flood_spread(G, [spot], get_district_fn=get_district)

        row_str = {}
        for vid, prof in vehicles.items():
            H_veh = veh_graphs[vid]
            blocked = blocked_edges_at_time(H_veh, c_case, t=0.0, profile=prof)
            view = apply_dynamic_flood(H_veh, c_case, t=0.0, profile=prof, as_view=True)

            if vid in exp_blocked:
                assert len(blocked) > 0
                assert view.number_of_edges() == H_veh.number_of_edges() - len(blocked)
                row_str[vid] = f"BỊ CHẶN ({len(blocked)} cạnh)"
            else:
                assert len(blocked) == 0
                assert view.number_of_edges() == H_veh.number_of_edges()
                row_str[vid] = "ĐI QUA (0 cạnh)"

        print(
            f"  {case_id:<28} | {depth_cm:>6.1f} cm  | "
            f"{row_str['motorbike_ice']:<22} | {row_str['vf3']:<18} | {row_str['car_ice']}"
        )


# ---------------------------------------------------------------- 5. Benchmark hiệu năng trên bản đồ thật
def test_5_flood_routing_performance_on_real_map(hanoi_graph):
    """Đo hiệu năng thực tế của các hàm flood_routing trên đồ thị Hà Nội (không gồm hàm tìm đường)."""
    G = hanoi_graph
    landmarks = load_cases()["landmarks"]

    # Tạo đồng thời 10 nguồn ngập tại 10 landmarks trên toàn thành phố
    sources = [
        FloodSource(
            lat=float(p["lat"]),
            lng=float(p["lng"]),
            f0=40.0,
            k=50.0,  # R ≈ 316.2 m
            id=f"bench_{key}",
        )
        for key, p in landmarks.items()
    ]

    # 1. Thời gian tiền xử lý compute_flood_spread (chạy 1 lần khi user chốt 10 điểm ngập)
    t0 = time.perf_counter()
    spread_cache = compute_flood_spread(G, sources, get_district_fn=get_district)
    spread_ms = (time.perf_counter() - t0) * 1000.0
    n_affected_edges = len(spread_cache)

    # 2. Thời gian gọi flood_at_time lặp lại 1,000 lần liên tiếp khi re-plan (bán kính cố định)
    n_queries = 1000
    t0 = time.perf_counter()
    for i in range(n_queries):
        _ = flood_at_time(spread_cache, t=float(i % 60), shrink_radius=False)
    total_fixed_ms = (time.perf_counter() - t0) * 1000.0
    avg_fixed_us = (total_fixed_ms * 1000.0) / n_queries
    qps = n_queries / (total_fixed_ms / 1000.0) if total_fixed_ms > 0 else float("inf")

    # 3. Thời gian gọi flood_at_time lặp lại 1,000 lần có co bán kính động R(t)
    t0 = time.perf_counter()
    for i in range(n_queries):
        _ = flood_at_time(spread_cache, t=float(i % 60), shrink_radius=True)
    total_shrink_ms = (time.perf_counter() - t0) * 1000.0
    avg_shrink_us = (total_shrink_ms * 1000.0) / n_queries

    # 4. Thời gian tạo restricted_view (apply_dynamic_flood) trên đồ thị xe thật (Hm, Hv, Hc)
    veh_profiles = [get_profile(x) for x in ("motorbike_ice", "vf3", "car_ice")]
    veh_graphs = [get_vehicle_graph(G, p) for p in veh_profiles]

    n_view_loops = 100
    t0 = time.perf_counter()
    for _ in range(n_view_loops):
        for H_v, prof in zip(veh_graphs, veh_profiles):
            _ = apply_dynamic_flood(H_v, spread_cache, t=10.0, profile=prof, as_view=True)
    total_view_ms = (time.perf_counter() - t0) * 1000.0
    avg_view_us = (total_view_ms * 1000.0) / (n_view_loops * len(veh_profiles))

    _print_banner("TEST 5: BENCHMARK HIỆU NĂNG FLOOD_ROUTING TRÊN ĐỒ THỊ HÀ NỘI THẬT")
    print(f"  [+] Quy mô đồ thị Hà Nội    : {G.number_of_nodes():,} nodes | {G.number_of_edges():,} edges")
    print(f"  [+] Số nguồn ngập đồng thời : {len(sources)} nguồn (10 landmarks khắp Hà Nội)")
    print(f"  [+] Số cạnh trong vùng ngập : {n_affected_edges:,} cạnh")
    print("-" * 95)
    print(f"  {'Hạng mục đo hiệu năng':<44} | {'Số lần gọi':<12} | {'Tổng thời gian':<16} | {'Trung bình / lần'}")
    print("-" * 95)
    print(
        f"  {'1. compute_flood_spread (10 nguồn ngập)':<44} | {'1 lần':<12} | "
        f"{spread_ms:>11.2f} ms   | {spread_ms:>10.2f} ms"
    )
    print(
        f"  {'2. flood_at_time (cố định R)':<44} | {f'{n_queries} lần':<12} | "
        f"{total_fixed_ms:>11.2f} ms   | {avg_fixed_us:>10.2f} µs ({qps:,.0f} calls/s)"
    )
    print(
        f"  {'3. flood_at_time (co bán kính R(t))':<44} | {f'{n_queries} lần':<12} | "
        f"{total_shrink_ms:>11.2f} ms   | {avg_shrink_us:>10.2f} µs"
    )
    print(
        f"  {'4. apply_dynamic_flood (trên Hm, Hv, Hc)':<44} | {f'{n_view_loops * 3} lần':<12} | "
        f"{total_view_ms:>11.2f} ms   | {avg_view_us:>10.2f} µs"
    )
    print("-" * 95)

    # Đảm bảo flood_at_time cực nhẹ (< 5 ms / lần gọi trên bản đồ thật)
    assert avg_fixed_us < 5000.0, f"flood_at_time quá chậm trên bản đồ thật: {avg_fixed_us:.2f} µs"


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", "-s", "-rs", __file__]))