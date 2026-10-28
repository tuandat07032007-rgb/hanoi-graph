from __future__ import annotations

from collections.abc import Hashable

from hanoi_graph.districts import HANOI_UNITS, slugify

# Hỗ trợ cả DiGraph (u, v) và MultiDiGraph (u, v, key)
EdgeKey = tuple[Hashable, Hashable] | tuple[Hashable, Hashable, Hashable]

# Tốc độ rút nước mặc định (cm / phút)
DEFAULT_DRAIN_RATE: float = 0.50

# Tốc độ rút nước cơ sở cho 30 đơn vị hành chính của Hà Nội (Đơn vị: cm / phút)
_BASE_DRAINAGE_RATES: dict[str, float] = {
    # 12 Quận nội thành
    "HoanKiem": 0.50,
    "BaDinh": 0.60,
    "DongDa": 0.40,
    "CauGiay": 0.80,
    "HaiBaTrung": 0.50,
    "ThanhXuan": 0.50,
    "TayHo": 0.70,
    "HoangMai": 0.70,
    "LongBien": 0.80,
    "NamTuLiem": 0.90,
    "BacTuLiem": 0.60,
    "HaDong": 0.70,
    # Thị xã & 17 Huyện ngoại thành
    "SonTay": 0.60,
    "BaVi": 0.80,
    "ChuongMy": 0.50,
    "DanPhuong": 0.60,
    "DongAnh": 0.75,
    "GiaLam": 0.75,
    "HoaiDuc": 0.55,
    "MeLinh": 0.70,
    "MyDuc": 0.60,
    "PhuXuyen": 0.55,
    "PhucTho": 0.65,
    "QuocOai": 0.60,
    "SocSon": 0.75,
    "ThachThat": 0.65,
    "ThanhOai": 0.55,
    "ThanhTri": 0.60,
    "ThuongTin": 0.55,
    "UngHoa": 0.50,
    "Default": DEFAULT_DRAIN_RATE,
}


def _build_drainage_rates() -> dict[str, float]:
    """
    Đồng bộ toàn bộ 30 đơn vị hành chính từ HANOI_UNITS (dạng tuple `(loại, tên)`)
    và chuẩn hóa khóa tra cứu không phân biệt hoa/thường.
    """
    slug_map: dict[str, float] = {
        slugify(k).lower(): v for k, v in _BASE_DRAINAGE_RATES.items()
    }
    for k, v in _BASE_DRAINAGE_RATES.items():
        slug_map[k.lower()] = v

    rates: dict[str, float] = dict(_BASE_DRAINAGE_RATES)
    for k, v in _BASE_DRAINAGE_RATES.items():
        rates[k.lower()] = v

    for item in HANOI_UNITS:
        unit_name = item[1] if isinstance(item, (tuple, list)) else str(item)
        s_key = slugify(unit_name)
        rate = slug_map.get(s_key.lower(), DEFAULT_DRAIN_RATE)
        rates[unit_name] = rate
        rates[s_key] = rate
        rates[s_key.lower()] = rate

    return rates


DRAINAGE_RATES: dict[str, float] = _build_drainage_rates()


def get_drain_rate_for_district(district_name: str | None) -> float:
    """Tra cứu tốc độ rút nước theo tên quận/huyện (hỗ trợ tên có dấu, PascalCase và chữ thường)."""
    if not district_name:
        return DRAINAGE_RATES["Default"]
    if district_name in DRAINAGE_RATES:
        return DRAINAGE_RATES[district_name]
    s_key = slugify(district_name)
    if s_key in DRAINAGE_RATES:
        return DRAINAGE_RATES[s_key]
    return DRAINAGE_RATES.get(s_key.lower(), DRAINAGE_RATES["Default"])


# Hằng số k trong công thức R = k * sqrt(F_0) (F_0 tính bằng cm, R tính bằng mét)
RADIUS_K: float = 50.0

DEFAULT_WEIGHT_ATTR: str = "length"