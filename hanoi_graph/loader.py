"""Tải / lưu / nạp đồ thị đường bộ CẢ THÀNH PHỐ HÀ NỘI (nội thành + huyện + thị xã ngoại thành).

Vì sao chia ô (tile)? Hà Nội ~3.360 km², một truy vấn Overpass duy nhất dễ timeout/hết RAM.
Cách làm: lấy polygon Hà Nội -> chia lưới `tile_km` -> tải từng ô CHƯA simplify -> gộp
(nx.compose_all, node trùng OSM id tự hợp nhất) -> simplify MỘT lần ở cuối (simplify từng ô
sẽ tạo node giả ở biên ô) -> giữ thành phần liên thông mạnh lớn nhất.

Đồ thị kết quả là MultiDiGraph CÓ HƯỚNG (đường một chiều giữ đúng chiều OSM), gồm đường của CẢ ô tô và
xe máy (ALL_VEHICLES_FILTER). Đây là kiểu build DUY NHẤT của dự án: đồ thị riêng cho từng loại xe được lọc
ra từ đồ thị chung này bằng vehicles.get_vehicle_graph, không tải riêng.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path

import networkx as nx
import numpy as np

from .connectivity import check_connectivity, keep_largest_scc
from .directed import require_directed
from .geo import recompute_edge_lengths
from .paths import GRAPH_GRAPHML, GRAPH_PICKLE, PROJECT_ROOT

log = logging.getLogger(__name__)

DEFAULT_PLACE = "Hà Nội, Việt Nam"
DEFAULT_GRAPHML = GRAPH_GRAPHML   # <gốc dự án>/data/hanoi_all.graphml (đường dẫn tuyệt đối, không phụ thuộc cwd)
DEFAULT_PICKLE = GRAPH_PICKLE

# Mọi đường mà ÍT NHẤT MỘT loại xe cơ giới đi được (ô tô HOẶC xe máy). KHÔNG lọc motorcar=no,
# vì ngõ cấm ô tô vẫn là đường của xe máy. Cấm theo từng loại xe làm sau, ở vehicles.py.
ALL_VEHICLES_FILTER = (
    '["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential'
    '|living_street|service|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"]'
    '["area"!~"yes"]["access"!~"private|no"]["motor_vehicle"!~"no"]'
    '["service"!~"parking_aisle|driveway|emergency_access"]'
)
# Thẻ cần GIỮ trên cạnh (OSMnx mặc định bỏ chúng): vehicles.py dùng để biết đường nào cấm xe nào.
# "oneway:motorcycle" (phố một chiều với ô tô nhưng xe máy đi 2 chiều) đã được giữ nhưng CHƯA được dùng.
VEHICLE_TAGS = ["motorcycle", "motorcar", "motor_vehicle", "access", "service", "oneway:motorcycle"]


def hanoi_polygon(place: str = DEFAULT_PLACE):
    """Polygon ranh giới thành phố (gồm toàn bộ quận/huyện/thị xã) từ Nominatim."""
    import osmnx as ox

    gdf = ox.geocode_to_gdf(place)
    geom = gdf.geometry.iloc[0]
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"{place!r} trả về {geom.geom_type}, cần Polygon/MultiPolygon")
    return geom


def make_tiles(polygon, tile_km: float = 15.0):
    """Chia polygon thành các ô lưới ~tile_km x tile_km (đã cắt theo polygon, bỏ ô rỗng)."""
    from shapely.geometry import box

    minx, miny, maxx, maxy = polygon.bounds
    step_lat = tile_km / 111.195
    step_lng = tile_km / (111.195 * np.cos(np.radians((miny + maxy) / 2)))
    tiles = []
    y = miny
    while y < maxy:
        x = minx
        while x < maxx:
            piece = polygon.intersection(box(x, y, min(x + step_lng, maxx), min(y + step_lat, maxy)))
            if not piece.is_empty and piece.area > 0:
                tiles.append(piece)
            x += step_lng
        y += step_lat
    return tiles


def download_hanoi_graph(
    place: str = DEFAULT_PLACE,
    tile_km: float = 15.0,
    custom_filter: str = ALL_VEHICLES_FILTER,
    verbose: bool = True,
) -> nx.MultiDiGraph:
    """Tải đồ thị toàn Hà Nội — đường của cả ô tô và xe máy (cần mạng tới Overpass/Nominatim).

    Lần đầu mất vài chục phút; phản hồi Overpass được cache ở <gốc dự án>/cache/ nên lần sau nhanh hơn
    nhiều (xoá cache/ nếu muốn lấy dữ liệu OSM mới nhất).
    """
    import osmnx as ox

    ox.settings.use_cache = True          # cache HTTP -> chạy lại nhanh, chịu ngắt quãng
    ox.settings.cache_folder = str(PROJECT_ROOT / "cache")   # luôn cache/ ở gốc dự án, chạy từ đâu cũng vậy
    ox.settings.useful_tags_way = sorted(set(ox.settings.useful_tags_way) | set(VEHICLE_TAGS))
    ox.settings.log_console = verbose
    polygon = hanoi_polygon(place)
    tiles = make_tiles(polygon, tile_km)
    log.info("Hà Nội: chia %d ô (~%s km)", len(tiles), tile_km)

    parts = []
    for i, tile in enumerate(tiles, 1):
        log.info("Tải ô %d/%d ...", i, len(tiles))
        try:
            g = ox.graph_from_polygon(
                tile,
                network_type=None,         # dùng custom_filter thay cho network_type có sẵn
                custom_filter=custom_filter,
                simplify=False,            # simplify 1 lần ở cuối
                retain_all=True,           # giữ mảnh ở biên ô, lọc liên thông sau khi gộp
                truncate_by_edge=True,     # giữ cạnh vắt qua biên ô
            )
        except Exception as exc:  # ô không có đường (vd. toàn sông) -> bỏ qua
            msg = str(exc).lower()
            if ("no data elements" in msg or "found no graph nodes" in msg
                    or "insufficientresponse" in type(exc).__name__.lower()):
                log.warning("Ô %d không có đường, bỏ qua", i)
                continue
            raise
        parts.append(g)

    if not parts:
        raise RuntimeError("Không tải được ô nào")
    G = nx.compose_all(parts)
    del parts
    G = ox.simplify_graph(G)
    return finalize_graph(G)


def finalize_graph(G: nx.MultiDiGraph, keep_scc: bool = True) -> nx.MultiDiGraph:
    """Bước hậu xử lý chung: kiểm tra có hướng, tính lại length bằng haversine, giữ SCC lớn nhất,
    thêm speed_kph/travel_time nếu osmnx hỗ trợ."""
    require_directed(G)
    before = check_connectivity(G)
    log.info("Trước lọc: %s", before.summary())
    if keep_scc:
        G = keep_largest_scc(G)
    recompute_edge_lengths(G)  # cùng một hàm haversine với heuristic h(n)
    try:
        import osmnx as ox
        G = ox.routing.add_edge_speeds(G)
        G = ox.routing.add_edge_travel_times(G)
    except Exception as exc:  # noqa: BLE001
        log.warning("Không thêm được speed/travel_time: %s", exc)
    G.graph["crs"] = G.graph.get("crs", "EPSG:4326")
    G.graph.pop("_node_arrays", None)
    log.info("Sau lọc:   %s", check_connectivity(G).summary())
    return G


def save_graph(G, graphml: Path | str = DEFAULT_GRAPHML, pickle_path: Path | str | None = DEFAULT_PICKLE) -> None:
    """Lưu GraphML (trao đổi) và pickle (nạp nhanh hơn nhiều cho đồ thị lớn)."""
    import osmnx as ox

    G.graph.pop("_node_arrays", None)
    Path(graphml).parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, graphml)
    if pickle_path:
        with open(pickle_path, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_graph(
    graphml: Path | str = DEFAULT_GRAPHML,
    pickle_path: Path | str | None = DEFAULT_PICKLE,
) -> nx.MultiDiGraph:
    """Nạp đồ thị đã lưu (ưu tiên pickle). KHÔNG bao giờ trả về đồ thị vô hướng.

    Pickle nạp nhanh (~10 s) nhưng phụ thuộc phiên bản Python/networkx; nếu máy khác không mở được pickle,
    xoá/đổi tên file .pkl để hàm tự dùng GraphML (chậm hơn nhiều nhưng đọc được ở mọi phiên bản).
    """
    import osmnx as ox

    if pickle_path and Path(pickle_path).exists():
        with open(pickle_path, "rb") as f:
            G = pickle.load(f)
    elif Path(graphml).exists():
        G = ox.load_graphml(graphml)
        _normalize_after_graphml(G)
    else:
        raise FileNotFoundError(
            f"Chưa có {graphml}. Chạy: python scripts/build_hanoi.py (cần mạng, tải vài chục phút)"
        )
    require_directed(G)
    return G


def _normalize_after_graphml(G) -> None:
    """GraphML lưu mọi thứ thành chuỗi: node không thuộc quận nào (district=None) bị nạp lại thành "None".
    OSMnx đã tự chuyển số/bool/list; ở đây chỉ trả lại None cho các thuộc tính node tự thêm."""
    for _, d in G.nodes(data=True):
        if d.get("district") in ("None", "nan", ""):
            d["district"] = None


def get_or_build_graph(**kwargs) -> nx.MultiDiGraph:
    """Nạp nếu đã có file, chưa có thì tải + lưu (KHÔNG gán quận cho node — muốn đủ thuộc tính thì
    dùng scripts/build_hanoi.py)."""
    try:
        return load_graph()
    except FileNotFoundError:
        G = download_hanoi_graph(**kwargs)
        save_graph(G)
        return G
