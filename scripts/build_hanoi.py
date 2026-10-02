"""Tải đồ thị toàn Hà Nội (đường của CẢ ô tô và xe máy), gán quận cho từng node, lưu data/hanoi_all.*.

Cần mạng (Overpass/Nominatim); lần đầu mất vài chục phút. Phản hồi Overpass được cache ở cache/ nên chạy
lại nhanh hơn nhiều (vài phút); xoá cache/ nếu muốn tải dữ liệu OSM mới nhất. Chạy từ đâu cũng được.

    python scripts/build_hanoi.py                 # -> data/hanoi_all.graphml + data/hanoi_all.pkl
    python scripts/build_hanoi.py --tile-km 10    # ô nhỏ hơn nếu Overpass timeout / thiếu RAM

Chỉ có MỘT kiểu build: đồ thị riêng cho từng loại xe (ô tô, xe máy) được lọc ra từ đồ thị chung này bằng
hanoi_graph.get_vehicle_graph, không tải riêng. Bộ lọc đường và các thẻ OSM được giữ: hanoi_graph/loader.py
(ALL_VEHICLES_FILTER, VEHICLE_TAGS).

Ranh giới quận/huyện: dùng file data/hanoi_districts.geojson đã có (bản GADM), KHÔNG tải lại.
Build xong nhớ chạy: python scripts/freeze_golden.py (đồ thị mới -> đáp án golden cũ có thể không còn đúng).
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hanoi_graph.connectivity import check_connectivity  # noqa: E402
from hanoi_graph.directed import oneway_report  # noqa: E402
from hanoi_graph.districts import DistrictIndex  # noqa: E402
from hanoi_graph.loader import download_hanoi_graph, save_graph  # noqa: E402
from hanoi_graph.paths import DISTRICTS_GEOJSON, GRAPH_GRAPHML, GRAPH_PICKLE  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Tải đồ thị toàn Hà Nội (ô tô + xe máy) -> data/hanoi_all.*")
    ap.add_argument("--tile-km", type=float, default=15.0, help="cạnh mỗi ô tải (km), mặc định 15")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    G = download_hanoi_graph(tile_km=args.tile_km)

    # Gán quận cho từng node TRƯỚC khi lưu, để file đồ thị có sẵn thuộc tính "district".
    # refresh=False: dùng file ranh giới đã có; refresh=True sẽ tải lại từ Nominatim và GHI ĐÈ nó.
    if DISTRICTS_GEOJSON.exists():
        idx = DistrictIndex.load(DISTRICTS_GEOJSON, refresh=False)
        counts = idx.tag_graph_nodes(G)
        # Node nằm đúng trên ranh giới / lệch mép: gán lại theo quy tắc của get_district (dung sai 300 m)
        for n, d in G.nodes(data=True):
            if d.get("district") is None:
                d["district"] = idx.get(d["y"], d["x"])
        print("Số quận/huyện/thị xã:", len(idx.gdf))
        print("Node theo quận (top 5):", sorted(((k, v) for k, v in counts.items() if k), key=lambda kv: -kv[1])[:5])
        print("Node không thuộc quận nào:", sum(1 for _, d in G.nodes(data=True) if d.get("district") is None))
    else:
        print("Chưa có", DISTRICTS_GEOJSON, "-> bỏ qua gán quận (chạy scripts/import_gadm.py trước)")

    save_graph(G, GRAPH_GRAPHML, GRAPH_PICKLE)
    print("Đã lưu:", GRAPH_GRAPHML, "và", GRAPH_PICKLE)
    print("Đồ thị:", check_connectivity(G).summary())
    print("Một chiều:", oneway_report(G))
    print("Nhớ chạy lại: python scripts/freeze_golden.py  (đồ thị mới -> đáp án golden cũ có thể không còn đúng)")


if __name__ == "__main__":
    main()
