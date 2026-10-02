"""Bảng tra quận/huyện/thị xã theo tọa độ: get_district(lat, lng) -> "TayHo".

Nguồn ranh giới (file data/hanoi_districts.geojson, 30 đơn vị: 12 quận, 1 thị xã, 17 huyện):
  * ĐANG DÙNG: GADM 4.1 cấp 2 (ranh giới cũ, trước sáp nhập 7/2025), tạo bằng scripts/import_gadm.py.
  * Phương án tải trực tiếp từ OSM: download_districts() gọi ox.geocode_to_gdf("Quận X, Hà Nội, Việt Nam")
    cho từng đơn vị (Nominatim). Từ 7/2025 cấp huyện bị bãi bỏ nên Nominatim có thể trả kết quả thiếu/khác;
    hàm báo rõ tên nào lỗi. Chỉ chạy khi gọi DistrictIndex.load(refresh=True) hoặc file geojson chưa có.

Cách tra (DistrictIndex.get):
  1. Tạo Point(lng, lat), hỏi chỉ mục không gian (STRtree) xem polygon nào CHỨA điểm (predicate "covers",
     tính cả điểm nằm đúng trên ranh giới; nếu trên ranh giới chung của 2 quận thì lấy quận có chỉ số nhỏ hơn).
  2. Nếu không polygon nào chứa (điểm ngoài ranh giới do sai số ranh giới/snap), chiếu sang UTM 48N (mét)
     và lấy quận gần nhất nếu cách <= NEAREST_TOLERANCE_M (300 m); xa hơn -> None (ngoài Hà Nội).
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Iterable, Optional

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

from .paths import DISTRICTS_GEOJSON

# (loại, tên có dấu)
HANOI_UNITS: list[tuple[str, str]] = (
    [("Quận", n) for n in [
        "Ba Đình", "Hoàn Kiếm", "Hai Bà Trưng", "Đống Đa", "Tây Hồ", "Cầu Giấy",
        "Thanh Xuân", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Bắc Từ Liêm", "Hà Đông",
    ]]
    + [("Thị xã", "Sơn Tây")]
    + [("Huyện", n) for n in [
        "Ba Vì", "Chương Mỹ", "Đan Phượng", "Đông Anh", "Gia Lâm", "Hoài Đức", "Mê Linh",
        "Mỹ Đức", "Phú Xuyên", "Phúc Thọ", "Quốc Oai", "Sóc Sơn", "Thạch Thất",
        "Thanh Oai", "Thanh Trì", "Thường Tín", "Ứng Hòa",
    ]]
)

DEFAULT_CACHE = DISTRICTS_GEOJSON   # <gốc dự án>/data/hanoi_districts.geojson
_PROJ_CRS = "EPSG:32648"  # UTM 48N — phủ Hà Nội, đơn vị mét
# Điểm nằm ngoài mọi polygon nhưng cách ranh giới <= giá trị này (m) vẫn gán cho quận gần nhất
NEAREST_TOLERANCE_M = 300.0


def slugify(name: str) -> str:
    """'Tây Hồ' -> 'TayHo', 'Đống Đa' -> 'DongDa', 'Bắc Từ Liêm' -> 'BacTuLiem'."""
    name = name.replace("Đ", "D").replace("đ", "d")
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return "".join(part.capitalize() for part in name.replace("-", " ").split())


def download_districts(
    units: Iterable[tuple[str, str]] = HANOI_UNITS,
    city: str = "Hà Nội, Việt Nam",
    cache_path: Path | str | None = DEFAULT_CACHE,
) -> gpd.GeoDataFrame:
    """Tải ranh giới từng đơn vị qua Nominatim (cần mạng) và lưu cache GeoJSON."""
    import osmnx as ox  # import trễ để module dùng được khi chỉ đọc cache

    rows, failed = [], []
    for kind, name in units:
        query = f"{kind} {name}, {city}"
        try:
            gdf = ox.geocode_to_gdf(query)
            geom = gdf.geometry.iloc[0]
            if geom.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError(f"kết quả là {geom.geom_type}, không phải polygon")
            rows.append({"name": name, "kind": kind, "slug": slugify(name), "geometry": geom})
        except Exception as exc:  # noqa: BLE001 — gom lỗi để báo một lần
            failed.append(f"{query}: {exc}")
    if failed:
        raise RuntimeError("Không lấy được ranh giới cho:\n  " + "\n  ".join(failed))
    out = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        out.to_file(cache_path, driver="GeoJSON")
    return out


class DistrictIndex:
    """Tra cứu điểm -> quận bằng spatial index (STRtree của geopandas)."""

    def __init__(self, gdf: gpd.GeoDataFrame):
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        self.gdf = gdf.to_crs("EPSG:4326").reset_index(drop=True)
        self._proj = self.gdf.to_crs(_PROJ_CRS)
        self._sindex = self.gdf.sindex

    @classmethod
    def load(cls, cache_path: Path | str = DEFAULT_CACHE, refresh: bool = False) -> "DistrictIndex":
        p = Path(cache_path)
        if refresh or not p.exists():
            return cls(download_districts(cache_path=p))
        return cls(gpd.read_file(p))

    def get(self, lat: float, lng: float) -> Optional[str]:
        """Slug quận chứa điểm (vd 'TayHo'); None nếu nằm ngoài Hà Nội."""
        pt = Point(lng, lat)
        hits = list(self._sindex.query(pt, predicate="covers"))
        if hits:
            return str(self.gdf.loc[min(hits), "slug"])  # điểm trên ranh giới: lấy chỉ số nhỏ nhất (ổn định)
        # ngoài mọi polygon: thử quận gần nhất trong ngưỡng dung sai (sai số snap / ranh giới OSM)
        ptp = gpd.GeoSeries([pt], crs="EPSG:4326").to_crs(_PROJ_CRS).iloc[0]
        d = self._proj.geometry.distance(ptp)
        i = int(np.argmin(d.values))
        return str(self.gdf.loc[i, "slug"]) if d.iloc[i] <= NEAREST_TOLERANCE_M else None

    def tag_graph_nodes(self, G, attr: str = "district") -> dict:
        """Gán `attr` cho mọi node của G (vector hoá bằng sjoin). Trả về thống kê node/quận."""
        ids = list(G.nodes)
        pts = gpd.GeoDataFrame(
            {"nid": ids},
            geometry=[Point(G.nodes[n]["x"], G.nodes[n]["y"]) for n in ids],
            crs="EPSG:4326",
        )
        joined = gpd.sjoin(pts, self.gdf[["slug", "geometry"]], how="left", predicate="within")
        joined = joined.drop_duplicates("nid")  # node trên ranh giới có thể khớp 2 quận
        lookup = dict(zip(joined["nid"], joined["slug"]))
        counts: dict = {}
        for n in ids:
            slug = lookup.get(n)
            slug = None if (slug is None or slug != slug) else slug  # NaN -> None
            G.nodes[n][attr] = slug
            counts[slug] = counts.get(slug, 0) + 1
        return counts


_default_index: Optional[DistrictIndex] = None


def set_default_index(index: DistrictIndex) -> None:
    global _default_index
    _default_index = index


def get_district(lat: float, lng: float, index: Optional[DistrictIndex] = None) -> Optional[str]:
    """get_district(21.0583, 105.8190) -> 'TayHo'. None nếu ngoài Hà Nội.

    Lần gọi đầu tự nạp data/hanoi_districts.geojson (nếu file chưa có thì tải qua Nominatim — cần mạng).
    """
    global _default_index
    idx = index or _default_index
    if idx is None:
        idx = _default_index = DistrictIndex.load()
    return idx.get(lat, lng)
