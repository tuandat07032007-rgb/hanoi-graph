"""hanoi_graph — đồ thị đường bộ có hướng của toàn Hà Nội + tiện ích dùng chung cho B/C/D."""
from .geo import (
    EARTH_RADIUS_M, haversine_m, haversine_km, make_heuristic, nearest_node,
    node_distance_m, path_length_m, recompute_edge_lengths,
)
from .directed import oneway_report, require_directed, to_digraph
from .connectivity import check_connectivity, diagnose_no_path, keep_largest_scc, scc_labels
from .subgraph import get_subgraph_near, nodes_in_bbox, subgraph_stats
from .districts import DistrictIndex, HANOI_UNITS, get_district, slugify
from .vehicles import (
    VehicleProfile, add_vehicle_travel_times, apply_vehicle_restrictions, clear_vehicle_graph_cache,
    get_profile, get_vehicle_graph, load_profiles, restriction_signature, time_weight, travel_time_attr,
    vehicle_speed_kph,
)
from .snap import SnapResult, clear_snap_index_cache, snap_pair, snap_point
from .spatial import clear_edge_index_cache, get_edge_index
from . import paths
from .flood import FloodSpot, apply_flood, blocked_edges, flooded_edges
from .testcases import (
    CaseBundle, FloodOutcome, ResolvedCase, VehicleRun, check_case, flood_outcome, load_cases, resolve_case,
    resolve_case_bundle, resolve_case_for_vehicle,
)
from .loader import download_hanoi_graph, get_or_build_graph, load_graph, save_graph

__all__ = [n for n in dir() if not n.startswith("_")]
