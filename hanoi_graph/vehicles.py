"""Đọc config/vehicle_profiles.json — nguồn chung về phương tiện cho B/C/D."""
from __future__ import annotations

import json
import weakref
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .directed import _truthy
from .paths import VEHICLE_PROFILES

DEFAULT_PATH = VEHICLE_PROFILES


@dataclass(frozen=True)
class VehicleProfile:
    id: str
    name_vi: str
    category: str            # "motorbike" | "car"
    powertrain: str          # "ice" | "ev"
    max_wading_depth_cm: float
    speed_cap_kph: float
    forbidden_highway_types: tuple
    value_source: str = "user_specified"
    safety_factor: float = 1.0
    forbidden_tags: tuple = ()   # ((tag, (giá trị cấm, ...)), ...) — vd. (("motorcar", ("no",)),)
    # Thẻ OSM một chiều RIÊNG cho loại xe này, vd. "oneway:motorcycle" với xe máy (None = theo chiều chung):
    #   "no"  -> xe được đi cả hai chiều trên đường một chiều với ô tô (thêm cạnh ngược)
    #   "yes" -> xe chỉ được đi theo chiều vẽ way trên đường hai chiều với ô tô (bỏ cạnh ngược)
    oneway_tag: str | None = None

    @property
    def max_wading_depth_mm(self) -> float:
        return self.max_wading_depth_cm * 10.0

    @property
    def effective_wading_cm(self) -> float:
        return self.max_wading_depth_cm * self.safety_factor

    def can_pass(self, flood_depth_cm: float) -> bool:
        """True nếu đi qua được điểm ngập sâu `flood_depth_cm` (so sánh <=)."""
        return flood_depth_cm <= self.effective_wading_cm

    def allows_highway(self, highway) -> bool:
        """`highway` có thể là str hoặc list (OSMnx gộp nhiều giá trị)."""
        types = highway if isinstance(highway, (list, tuple, set)) else [highway]
        return not any(t in self.forbidden_highway_types for t in types)

    def allows_tags(self, data: dict) -> bool:
        """False nếu cạnh có thẻ OSM cấm loại xe này (vd. motorcar=no với ô tô).
        Cạnh đã simplify có thể mang list giá trị -> chỉ cần MỘT đoạn bị cấm là cấm cả cạnh."""
        for tag, banned in self.forbidden_tags:
            val = data.get(tag)
            if val is None:
                continue
            vals = val if isinstance(val, (list, tuple, set)) else [val]
            if any(str(x).strip().lower() in banned for x in vals):
                return False
        return True

    def allows_edge(self, data: dict) -> bool:
        return self.allows_highway(data.get("highway", "")) and self.allows_tags(data)

    def oneway_override(self, data: dict) -> str | None:
        """Giá trị thẻ một chiều riêng của xe trên cạnh này ("no" / "yes"), None nếu không có.
        Cạnh đã simplify mang list giá trị thì chỉ tính khi MỌI đoạn cùng một giá trị."""
        if not self.oneway_tag:
            return None
        val = data.get(self.oneway_tag)
        if val is None:
            return None
        vals = {str(x).strip().lower() for x in (val if isinstance(val, (list, tuple, set)) else [val])}
        return vals.pop() if len(vals) == 1 and vals <= {"no", "yes"} else None


@lru_cache(maxsize=4)
def _load_raw(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_profiles(path: Path | str = DEFAULT_PATH, safety_factor: float | None = None) -> dict[str, VehicleProfile]:
    raw = _load_raw(str(path))
    sf = raw.get("default_safety_factor", 1.0) if safety_factor is None else safety_factor
    out = {}
    for vid, v in raw["vehicles"].items():
        out[vid] = VehicleProfile(
            id=vid,
            name_vi=v["name_vi"],
            category=v["category"],
            powertrain=v["powertrain"],
            max_wading_depth_cm=float(v["max_wading_depth_cm"]),
            speed_cap_kph=float(v["speed_cap_kph"]),
            forbidden_highway_types=tuple(v.get("forbidden_highway_types", [])),
            value_source=v.get("value_source", "user_specified"),
            safety_factor=float(sf),
            forbidden_tags=tuple(
                (tag, tuple(str(x).lower() for x in vals))
                for tag, vals in v.get("forbidden_tags", {}).items()
            ),
            oneway_tag=v.get("oneway_tag"),
        )
    return out


def get_profile(vehicle_id: str, path: Path | str = DEFAULT_PATH, safety_factor: float | None = None) -> VehicleProfile:
    profiles = load_profiles(path, safety_factor)
    if vehicle_id not in profiles:
        raise KeyError(f"Không có phương tiện {vehicle_id!r}; có: {sorted(profiles)}")
    return profiles[vehicle_id]


def apply_oneway_overrides(H, profile: VehicleProfile) -> tuple[int, int]:
    """Áp thẻ một chiều riêng của xe (profile.oneway_tag) lên H — SỬA H TẠI CHỖ. Trả về (số cạnh thêm, số cạnh bỏ).

    * "no" trên cạnh một chiều (oneway=True): thêm cạnh ngược v->u, chép thuộc tính, `geometry` đảo chiều,
      `reversed=True`, đánh dấu `contraflow=True` (vd. xe máy đi hai chiều trên phố một chiều với ô tô).
    * "yes" trên cạnh ngược chiều vẽ way (`reversed=True`) của đường hai chiều: bỏ cạnh đó (xe chỉ đi theo
      chiều vẽ way).
    """
    if not profile.oneway_tag:
        return 0, 0
    import shapely

    multi = H.is_multigraph()
    it = H.edges(keys=True, data=True) if multi else ((u, v, None, d) for u, v, d in H.edges(data=True))
    add, drop = [], []
    for u, v, k, d in it:
        rule = profile.oneway_override(d)
        if rule == "no" and u != v and _truthy(d.get("oneway", False)):
            nd = dict(d)
            if d.get("geometry") is not None:
                nd["geometry"] = shapely.reverse(d["geometry"])
            nd["reversed"] = True
            nd["contraflow"] = True
            add.append((v, u, nd))
        elif rule == "yes" and d.get("reversed") is True:
            drop.append((u, v, k) if multi else (u, v))
    H.remove_edges_from(drop)
    for v, u, nd in add:
        if multi or not H.has_edge(v, u):
            H.add_edge(v, u, **nd)
    return len(add), len(drop)


def apply_vehicle_restrictions(G, profile: VehicleProfile, keep_largest_scc: bool = True):
    """Bản sao G chỉ còn các cạnh `profile` được đi, theo thứ tự:

    1. bỏ loại đường cấm (vd. xe máy trên cao tốc) và cạnh có thẻ cấm (vd. ngõ motorcar=no với ô tô);
    2. áp thẻ một chiều riêng của xe (apply_oneway_overrides; xe máy: "oneway:motorcycle");
    3. keep_largest_scc=True: bỏ các node bị "kẹt" sau khi cắt cạnh (vd. ngõ chỉ xe máy vào được) để A*
       của xe này không báo nhầm "không tìm thấy đường". Nhớ snap điểm đi/đến trên đồ thị TRẢ VỀ.
    """
    H = G.copy()
    H.graph.pop("_node_arrays", None)
    if H.is_multigraph():
        bad = [(u, v, k) for u, v, k, d in H.edges(keys=True, data=True) if not profile.allows_edge(d)]
    else:
        bad = [(u, v) for u, v, d in H.edges(data=True) if not profile.allows_edge(d)]
    H.remove_edges_from(bad)
    added, dropped = apply_oneway_overrides(H, profile)
    if keep_largest_scc:
        from .connectivity import keep_largest_scc as _keep
        H = _keep(H)
        H.graph.pop("_node_arrays", None)
    H.graph["vehicle"] = profile.id
    H.graph["oneway_overrides"] = {"contraflow_added": added, "oneway_removed": dropped}
    return H

# ---------------------------------------------------------------- cache đồ thị theo hạn chế
# 5 xe chỉ có vài "kiểu hạn chế" khác nhau (ô tô: motorcar=no; xe máy: cấm cao tốc + motorcycle=no
# + thẻ một chiều riêng oneway:motorcycle).
# Ngưỡng lội nước KHÔNG ảnh hưởng đồ thị (xử lý ở flood.py), nên các xe cùng kiểu dùng chung 1 đồ thị.
_VEHICLE_GRAPH_CACHE: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def restriction_signature(profile: VehicleProfile) -> tuple:
    return (tuple(sorted(profile.forbidden_highway_types)), tuple(sorted(profile.forbidden_tags)),
            profile.oneway_tag or "")


def get_vehicle_graph(G, profile: VehicleProfile, keep_largest_scc: bool = True):
    """Đồ thị đã lọc cho `profile`, dựng 1 lần rồi dùng lại (cache theo kiểu hạn chế, không theo tên xe).

    * Các xe cùng kiểu hạn chế (vd. car_ice, car_ev, vf3) nhận CHUNG MỘT đối tượng đồ thị => KHÔNG sửa
      trực tiếp kết quả (apply_flood, get_subgraph_near đều tự copy nên an toàn). Cần sửa thì .copy().
    * Cache gắn với đối tượng G (giải phóng khi G bị thu hồi). Nếu bạn sửa G sau khi đã gọi hàm này,
      gọi clear_vehicle_graph_cache(G). Số node của G được kiểm tra làm chốt chặn thô (sửa cạnh
      mà không đổi số node thì cache KHÔNG tự biết).
    * Snap start/goal (nearest_node, resolve_case) phải làm trên đồ thị TRẢ VỀ: bước giữ SCC có thể
      loại node. Dùng testcases.resolve_case_for_vehicle để làm đúng thứ tự này.
    """
    per_graph = _VEHICLE_GRAPH_CACHE.setdefault(G, {})
    # chỉ so số node (O(1)); number_of_edges() của MultiDiGraph phải duyệt cả đồ thị (~1 s với Hà Nội)
    key = restriction_signature(profile) + (keep_largest_scc, G.number_of_nodes())
    H = per_graph.get(key)
    if H is None:
        H = apply_vehicle_restrictions(G, profile, keep_largest_scc=keep_largest_scc)
        H.graph["vehicle_ids"] = []
        per_graph[key] = H
    if profile.id not in H.graph["vehicle_ids"]:
        H.graph["vehicle_ids"].append(profile.id)
    return H


def clear_vehicle_graph_cache(G=None) -> None:
    """Xoá cache của G (hoặc toàn bộ nếu G=None)."""
    if G is None:
        _VEHICLE_GRAPH_CACHE.clear()
    else:
        _VEHICLE_GRAPH_CACHE.pop(G, None)


# ---------------------------------------------------------------- thời gian đi theo trần tốc độ của xe
def vehicle_speed_kph(profile: VehicleProfile, data: dict) -> float:
    """Tốc độ dùng cho cạnh: min(tốc độ đường `speed_kph`, trần tốc độ xe). Thiếu speed_kph -> trần của xe."""
    sp = data.get("speed_kph")
    if isinstance(sp, (list, tuple)):
        sp = min(float(x) for x in sp)
    try:
        sp = float(sp) if sp is not None else profile.speed_cap_kph
    except (TypeError, ValueError):
        sp = profile.speed_cap_kph
    if not sp > 0:
        sp = profile.speed_cap_kph
    return min(sp, profile.speed_cap_kph)


def travel_time_attr(profile: VehicleProfile) -> str:
    return f"travel_time_{profile.id}"


def add_vehicle_travel_times(G, profile: VehicleProfile) -> str:
    """Ghi thời gian đi (giây) theo trần tốc độ của xe vào thuộc tính `travel_time_<id_xe>` của mọi cạnh.

    Không ghi đè `travel_time` gốc (theo tốc độ đường) vì đồ thị lọc được DÙNG CHUNG giữa các xe cùng
    kiểu hạn chế (car_ice, car_ev, vf3) mà mỗi xe có thể đặt trần tốc độ riêng. Trả về tên thuộc tính để dùng làm weight:

        H = get_vehicle_graph(G, p); w = add_vehicle_travel_times(H, p)
        nx.astar_path(H, s, g, heuristic=make_heuristic(H, g, mode="time", max_speed_kph=p.speed_cap_kph), weight=w)

    Heuristic theo thời gian với max_speed_kph = speed_cap_kph vẫn admissible vì mọi cạnh đều <= trần.
    """
    attr = travel_time_attr(profile)
    for _, _, d in G.edges(data=True):
        d[attr] = d["length"] / (vehicle_speed_kph(profile, d) / 3.6)
    return attr


def time_weight(profile: VehicleProfile):
    """Hàm weight cho networkx (không cần ghi thuộc tính): giây đi cạnh theo trần tốc độ của xe.
    Với MultiDiGraph, networkx truyền dict {key: data} -> lấy cạnh song song nhanh nhất."""
    def w(u, v, d):
        if "length" in d:
            return d["length"] / (vehicle_speed_kph(profile, d) / 3.6)
        return min(dd["length"] / (vehicle_speed_kph(profile, dd) / 3.6) for dd in d.values())
    return w
