"""Tạo data/hanoi_districts.geojson từ GADM 4.1 cấp 2 (ranh giới quận/huyện cũ, trước 7/2025).

    python scripts/import_gadm.py                          # đọc data/gadm41_VNM_2.json
    python scripts/import_gadm.py duong/dan/khac.json

File GADM tải ở https://gadm.org (Vietnam, level 2, GeoJSON). Tên quận trong GADM viết liền không dấu cách
(vd. "TâyHồ") nên được khớp với danh sách chuẩn HANOI_UNITS qua slugify; tên nào không khớp sẽ báo lỗi.
"""
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hanoi_graph.districts import slugify  # noqa: E402
from hanoi_graph.paths import DISTRICTS_GEOJSON, GADM_JSON  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else GADM_JSON
g = gpd.read_file(src).to_crs("EPSG:4326")
print("Tên tỉnh có trong file:", sorted(g["NAME_1"].unique())[:5], "...")

hn = g[g["NAME_1"].str.replace(" ", "").str.lower().isin(["hànội", "hanoi"])]
from hanoi_graph.districts import HANOI_UNITS

# Khớp tên GADM (không dấu cách) với danh sách chuẩn -> lấy lại tên có dấu cách, loại, slug đúng
chuan = {slugify(name).lower(): (name, kind, slugify(name)) for kind, name in HANOI_UNITS}
rows, geoms, khong_khop = [], [], []
for ten, geom in zip(hn["NAME_2"], hn.geometry):
    key = slugify(ten).lower()
    if key in chuan:
        rows.append(chuan[key])
        geoms.append(geom)
    else:
        khong_khop.append(ten)
if khong_khop:
    sys.exit(f"Tên GADM không khớp danh sách chuẩn: {khong_khop}")

out = gpd.GeoDataFrame(
    {"name": [r[0] for r in rows], "kind": [r[1] for r in rows], "slug": [r[2] for r in rows]},
    geometry=geoms, crs="EPSG:4326",
)

km2 = out.to_crs(32648).area / 1e6
print(out.assign(km2=km2.round(1)).drop(columns="geometry").to_string())
print("Số đơn vị:", len(out), "| Tổng diện tích:", round(km2.sum()), "km2 (thật ~3.360)")
if len(out) == 0:
    sys.exit("Không thấy Hà Nội trong file — xem dòng 'Tên tỉnh có trong file' ở trên.")

out.to_file(DISTRICTS_GEOJSON, driver="GeoJSON")
print("Đã ghi", DISTRICTS_GEOJSON)