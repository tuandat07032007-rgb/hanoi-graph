"""Vẽ bản đồ đường bộ Hà Nội (cả ô tô và xe máy) + ranh giới quận, LƯU ẢNH ĐỘ PHÂN GIẢI CAO.

Bấm nút Run trong VS Code là chạy được (chạy từ đâu cũng được). Mặc định chỉ lưu ảnh, KHÔNG mở cửa sổ
(tránh lag); mở file PNG bằng Photos/trình duyệt rồi phóng to. Ảnh lưu ở outputs/maps/ (tạo lại được).
    python scripts/show_hanoi.py                        -> outputs/maps/hanoi_map.png (toàn thành phố, 600 dpi)
    python scripts/show_hanoi.py --dpi 900              -> nét hơn nữa (file nặng hơn)
    python scripts/show_hanoi.py --district CauGiay     -> thêm ảnh riêng 1 quận: outputs/maps/hanoi_map_CauGiay.png
    python scripts/show_hanoi.py --district noithanh    -> thêm ảnh riêng 12 quận nội thành
    python scripts/show_hanoi.py --curves               -> vẽ đúng đường cong (chậm hơn, đẹp hơn khi zoom sâu)
    python scripts/show_hanoi.py --show                 -> mở thêm cửa sổ xem (có thể lag)

Màu: xám = cả ô tô và xe máy | xanh lá = chỉ xe máy (ngõ cấm ô tô) | tím = chỉ ô tô (cao tốc...)
     xanh nhạt = ranh giới quận/huyện
"""
import argparse
import math
import sys
import time
from pathlib import Path

import matplotlib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hanoi_graph.districts import DistrictIndex  # noqa: E402
from hanoi_graph.loader import load_graph  # noqa: E402
from hanoi_graph.paths import DISTRICTS_GEOJSON, GRAPH_GRAPHML, GRAPH_PICKLE, OUTPUT_DIR  # noqa: E402
from hanoi_graph.vehicles import get_profile  # noqa: E402

GRAPHML = GRAPH_GRAPHML
PICKLE = GRAPH_PICKLE
DISTRICTS = DISTRICTS_GEOJSON
OUT_DIR = OUTPUT_DIR / "maps"
BG = "#111111"
COLORS = {"both": "#9a9a9a", "moto_only": "#2ecc71", "car_only": "#b388ff"}
INNER_12 = ["BaDinh", "HoanKiem", "HaiBaTrung", "DongDa", "TayHo", "CauGiay", "ThanhXuan",
            "HoangMai", "LongBien", "NamTuLiem", "BacTuLiem", "HaDong"]


def build_segments(G, car, moto, curves: bool):
    """Chia cạnh theo ai được đi: cả hai / chỉ xe máy / chỉ ô tô (đường 2 chiều chỉ vẽ 1 lần)."""
    groups = {k: [] for k in COLORS}
    for u, v, d in G.edges(data=True):
        if u == v or (G.has_edge(v, u) and u > v):
            continue
        car_ok, moto_ok = car.allows_edge(d), moto.allows_edge(d)
        if not (car_ok or moto_ok):
            continue
        key = "both" if car_ok and moto_ok else ("moto_only" if moto_ok else "car_only")
        geom = d.get("geometry") if curves else None
        pts = list(geom.coords) if geom is not None else [
            (G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
        groups[key].append(pts)
    return groups


def draw(groups, idx, title, bounds=None, scale=1.0, label_size=6):
    """Vẽ 1 hình. bounds=(minx, miny, maxx, maxy) để cắt vùng; scale = hệ số độ dày nét."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(12, 13), facecolor=BG)
    ax.set_facecolor(BG)
    widths = {"both": 0.25, "moto_only": 0.3, "car_only": 0.6}
    for z, key in enumerate(["both", "moto_only", "car_only"], start=1):
        ax.add_collection(LineCollection(groups[key], colors=COLORS[key],
                                         linewidths=widths[key] * scale, zorder=z))
    if idx is not None:
        idx.gdf.boundary.plot(ax=ax, color="#4cc9f0", linewidth=0.8 * scale, zorder=4)
        for _, r in idx.gdf.iterrows():
            p = r.geometry.representative_point()
            if bounds is None or (bounds[0] <= p.x <= bounds[2] and bounds[1] <= p.y <= bounds[3]):
                ax.text(p.x, p.y, r["name"], color="white", fontsize=label_size, ha="center",
                        va="center", alpha=0.85, zorder=5)
    if bounds is None:
        ax.autoscale()
    else:
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])
    lat0 = sum(ax.get_ylim()) / 2
    ax.set_aspect(1 / math.cos(math.radians(lat0)))  # đúng tỉ lệ ngang/dọc theo vĩ độ
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_visible(False)
    legend = [
        Line2D([], [], color=COLORS["both"], lw=2, label="Cả ô tô và xe máy"),
        Line2D([], [], color=COLORS["moto_only"], lw=2, label="Chỉ xe máy (ngõ cấm ô tô)"),
        Line2D([], [], color=COLORS["car_only"], lw=2, label="Chỉ ô tô (cao tốc, cấm xe máy)"),
        Line2D([], [], color="#4cc9f0", lw=2, label="Ranh giới quận/huyện"),
    ]
    ax.legend(handles=legend, loc="lower left", fontsize=8, facecolor="#222222",
              edgecolor="#444444", labelcolor="white")
    ax.set_title(title, color="white", fontsize=10)
    fig.tight_layout()
    return fig


def save(fig, path: Path, dpi: int):
    t0 = time.perf_counter()
    fig.savefig(path, dpi=dpi, facecolor=BG)
    w, h = (fig.get_size_inches() * dpi).astype(int)
    print(f"Đã lưu: {path}  ({w:,} x {h:,} px, {path.stat().st_size / 1e6:.1f} MB, "
          f"{time.perf_counter() - t0:.0f}s)")


def district_bounds(idx, name):
    """Hộp bao của 1 quận (theo slug, vd CauGiay) hoặc 'noithanh' = 12 quận nội thành."""
    slugs = INNER_12 if name.lower() == "noithanh" else [name]
    sel = idx.gdf[idx.gdf["slug"].isin(slugs)]
    if sel.empty:
        raise SystemExit(f"Không có quận {name!r}. Có: noithanh, " + ", ".join(idx.gdf["slug"]))
    minx, miny, maxx, maxy = sel.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=600, help="độ nét ảnh (mặc định 600)")
    ap.add_argument("--district", help="lưu thêm ảnh riêng 1 quận (vd CauGiay) hoặc noithanh")
    ap.add_argument("--curves", action="store_true", help="vẽ đúng đường cong (chậm hơn)")
    ap.add_argument("--show", action="store_true", help="mở thêm cửa sổ xem (có thể lag)")
    args = ap.parse_args()
    if not args.show:
        matplotlib.use("Agg")  # chỉ lưu ảnh, không mở cửa sổ -> không lag
    import matplotlib.pyplot as plt

    t0 = time.perf_counter()
    G = load_graph(GRAPHML, PICKLE)
    print(f"Nạp đồ thị: {G.number_of_nodes():,} node, {G.number_of_edges():,} cạnh "
          f"({time.perf_counter() - t0:.1f}s)")
    idx = DistrictIndex.load(DISTRICTS) if DISTRICTS.exists() else None
    if idx is None:
        print("Chưa có", DISTRICTS, "-> vẽ không có ranh giới quận")

    groups = build_segments(G, get_profile("car_ice"), get_profile("motorbike_ice"), args.curves)
    print("Đoạn đường: " + ", ".join(f"{k}={len(v):,}" for k, v in groups.items()))

    title = f"Hà Nội — {G.number_of_nodes():,} node, {G.number_of_edges():,} cạnh"
    fig = draw(groups, idx, title)
    save(fig, OUT_DIR / "hanoi_map.png", args.dpi)

    if args.district:
        if idx is None:
            raise SystemExit("Cần data/hanoi_districts.geojson để cắt theo quận (chạy scripts/import_gadm.py)")
        b = district_bounds(idx, args.district)
        fig_d = draw(groups, idx, f"{title} — {args.district}", bounds=b, scale=2.5, label_size=10)
        save(fig_d, OUT_DIR / f"hanoi_map_{args.district}.png", args.dpi)

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()