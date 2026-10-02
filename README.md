# hanoi-graph — nền đồ thị đường bộ Hà Nội cho bài toán tìm đường

Phần nền dùng chung cho cả nhóm. Gồm đồ thị **có hướng** của toàn Hà Nội (12 quận, 17 huyện, 1 thị xã; cả đường
ô tô lẫn ngõ xe máy) lấy từ OpenStreetMap, cùng các tiện ích mà các thành viên B/C/D dùng chung khi viết thuật toán
(A*, tránh điểm ngập, chọn phương tiện):

- khoảng cách haversine;
- tra quận theo toạ độ;
- cắt đồ thị theo bounding-box;
- cấu hình phương tiện;
- kiểm tra liên thông;
- snap toạ độ vào đồ thị;
- mô hình ngập;
- bộ data test cố định có đáp án chốt sẵn;
- benchmark A* trên dữ liệu thật.

> Quy trình chi tiết từng công đoạn (cách hoạt động, cách chạy, kết quả thực tế) nằm trong tài liệu
> **[Quy trình xây dựng nền đồ thị Hà Nội](https://claude.ai/code/artifact/c627bf60-89e5-4126-a5e1-ef47388b6732)**.

---

## 1. Bắt đầu nhanh

```powershell
cd "D:\Hanoi OSM2 - Copy\hanoi-graph"
python -m pip install -r requirements.txt     # Python >= 3.10
python scripts/check_data.py                  # ~15–30 s: kiểm tra dữ liệu có đủ và đúng không
python -m pytest tests -v -rs                 # 97 test: 62 offline (~3 s) + 35 trên dữ liệu thật (~2–3 phút)
python -m pytest tests -m "not hanoi"         # chỉ chạy test offline, không cần dữ liệu
```

Dữ liệu `data/hanoi_all.pkl` và `data/hanoi_all.graphml` khá nặng (125 MB và 347 MB), nên được chia sẻ qua Drive/USB
thay vì đưa lên git. Nếu chưa có, chạy `python scripts/build_hanoi.py`. Lệnh này cần mạng; lần đầu mất vài chục phút,
lần sau nhanh hơn nhiều nhờ `cache/`. Chỉ có một kiểu build (ô tô + xe máy); đồ thị riêng cho từng xe được lọc ra
từ đó bằng `get_vehicle_graph`, không tải riêng.

Đoạn code tối thiểu để tìm đường cho một loại xe:

```python
import networkx as nx
from hanoi_graph import load_graph, get_profile, get_vehicle_graph, snap_pair, make_heuristic, path_length_m

G = load_graph()                                   # MultiDiGraph có hướng, ~5–10 s
car = get_profile("car_ice")
H = get_vehicle_graph(G, car)                      # đồ thị chỉ còn đường ô tô được đi (cache, ~20 s lần đầu)
s, g = snap_pair(H, (21.0288, 105.8523), (21.0050, 105.8430))   # (lat, lng) -> node, đúng chiều một chiều
h = make_heuristic(H, g.node)                      # haversine tới đích (mét)
path = nx.astar_path(H, s.node, g.node, heuristic=lambda n, _t: h(n), weight="length")
print(path_length_m(H, path), "m")                 # báo lỗi nếu đường đi sai chiều
```

---

## 2. Pipeline

```
OpenStreetMap ──(scripts/build_hanoi.py)──────────────────────────────────────────────────────────┐
  polygon Hà Nội → chia ô 15 km → tải từng ô (chưa simplify) → gộp → simplify 1 lần               │
  → giữ thành phần liên thông mạnh lớn nhất → tính lại length bằng haversine → speed_kph/travel_time │
GADM ──(scripts/import_gadm.py)──→ data/hanoi_districts.geojson ──→ gán "district" cho từng node ─┘
                                                     │
                                                     ▼
                             data/hanoi_all.pkl + .graphml   (MultiDiGraph có hướng)
                                                     │  load_graph()
                                                     ▼
        get_vehicle_graph(G, xe)  ──  lọc đường cấm theo xe (cao tốc, motorcar=no...) + giữ SCC
                                                     │
            snap_point / nearest_node  ──  toạ độ → node (trên ĐỒ THỊ ĐÃ LỌC)
                                                     │
            thuật toán của nhóm (A*, Weighted A*...)  ±  apply_flood (bỏ cạnh ngập theo xe)
                                                     │
        kiểm chứng: tests/ + bộ data test (test_cases.json → golden.json) + benchmark_astar.py
```

---

## 3. Cấu trúc thư mục

```
hanoi-graph/
├─ README.md                 file này
├─ requirements.txt          thư viện cần cài
├─ .gitignore                không đưa data/, cache/, outputs/ lên git
├─ config/
│   └─ vehicle_profiles.json   NGUỒN DUY NHẤT về phương tiện (ngưỡng lội nước, trần tốc độ, đường cấm)
├─ data/                     dữ liệu gốc (không sửa tay)
│   ├─ hanoi_all.pkl           đồ thị (nạp nhanh, phụ thuộc phiên bản Python/networkx)
│   ├─ hanoi_all.graphml       cùng đồ thị, định dạng trao đổi (đọc được ở mọi phiên bản, nạp chậm)
│   ├─ hanoi_districts.geojson 30 ranh giới quận/huyện/thị xã (từ GADM)
│   └─ gadm41_VNM_2.json       file GADM gốc để tạo lại geojson trên
├─ hanoi_graph/              thư viện dùng chung (import hanoi_graph)
├─ scripts/                  các lệnh chạy (build, kiểm tra, chốt đáp án, benchmark, vẽ bản đồ)
├─ tests/                    pytest + fixtures/ (bộ data test cố định và đáp án)
├─ outputs/                  kết quả tạo lại được: maps/ (ảnh), benchmark*/ (báo cáo benchmark)
└─ cache/                    cache tải OSM — giữ lại để build lại nhanh (xoá nếu muốn lấy dữ liệu OSM mới)
```

---

## 4. Thư viện `hanoi_graph/`

| File | Nội dung | Hàm/lớp chính |
|---|---|---|
| `paths.py` | Đường dẫn tuyệt đối tính từ gốc dự án, không phụ thuộc thư mục đang đứng | `DATA_DIR`, `GRAPH_PICKLE`, `OUTPUT_DIR`... |
| `loader.py` | Tải toàn Hà Nội theo ô, gộp, simplify, hậu xử lý; lưu/nạp | `download_hanoi_graph`, `finalize_graph`, `save_graph`, `load_graph` |
| `directed.py` | Đảm bảo đồ thị có hướng, thống kê một chiều | `require_directed`, `oneway_report`, `to_digraph` |
| `geo.py` | **Nguồn duy nhất** cho khoảng cách: haversine, độ dài cạnh, heuristic A* | `haversine_m/km`, `recompute_edge_lengths`, `make_heuristic`, `nearest_node`, `path_length_m` |
| `connectivity.py` | Liên thông mạnh, loại "đảo"/bẫy một chiều, giải thích vì sao không có đường | `check_connectivity`, `keep_largest_scc`, `diagnose_no_path` |
| `districts.py` | Tra quận theo toạ độ (polygon chứa điểm, dung sai 300 m) | `get_district`, `DistrictIndex`, `HANOI_UNITS`, `slugify` |
| `subgraph.py` | Cắt đồ thị quanh 2 điểm (bounding-box + buffer, tự nới khi mất đường) | `get_subgraph_near`, `nodes_in_bbox` |
| `vehicles.py` | Đọc cấu hình xe; lọc đường theo xe: bỏ đường cấm, áp thẻ một chiều riêng của xe máy (`oneway:motorcycle`), có cache; thời gian đi theo trần tốc độ | `get_profile`, `get_vehicle_graph`, `apply_oneway_overrides`, `add_vehicle_travel_times`, `time_weight` |
| `spatial.py` | Chỉ mục không gian của cạnh (STRtree), dùng chung cho snap và ngập | `get_edge_index`, `clear_edge_index_cache` |
| `snap.py` | Snap toạ độ vào **cạnh** gần nhất, chọn node đúng chiều đi | `snap_point`, `snap_pair`, `SnapResult` |
| `flood.py` | Điểm ngập → cạnh ngập (theo hình dạng thật của cạnh) → cạnh bị chặn theo xe | `FloodSpot`, `flooded_edges`, `blocked_edges`, `apply_flood` |
| `testcases.py` | Giải bộ data test: mỗi xe một đồ thị, điểm ngập dùng chung, kiểm tra kỳ vọng | `load_cases`, `resolve_case_bundle`, `flood_outcome`, `check_case` |

Mọi hàm đều import được trực tiếp: `from hanoi_graph import ...`.

---

## 5. Scripts

| Lệnh | Làm gì | Khi nào chạy | Thời gian* |
|---|---|---|---|
| `python scripts/build_hanoi.py` | Tải đồ thị toàn Hà Nội (ô tô + xe máy) từ OSM → `data/hanoi_all.*` | Lần đầu, hoặc khi muốn dữ liệu OSM mới | lần đầu vài chục phút, có `cache/` thì nhanh hơn nhiều (cần mạng) |
| `python scripts/import_gadm.py` | GADM → `data/hanoi_districts.geojson` (30 đơn vị) | Khi cần tạo lại ranh giới quận | vài giây |
| `python scripts/check_data.py` | Kiểm tra nhanh: file, hướng, một chiều, liên thông, quận, xe, landmark, golden | Sau khi build/copy dữ liệu | 15–30 s |
| `python scripts/freeze_golden.py` | Chốt đáp án đúng cho bộ data test → `tests/fixtures/golden.json` | Sau khi build lại đồ thị / sửa case | ~1,5 phút |
| `python scripts/benchmark_astar.py` | Đo Dijkstra / A* / Weighted A* / bbox trên dữ liệu thật → `outputs/benchmark/` | Khi cần số liệu báo nhóm | ~1 phút mỗi lệnh |
| `python scripts/show_hanoi.py` | Vẽ bản đồ (ô tô / chỉ xe máy / chỉ ô tô + ranh giới quận) → `outputs/maps/` | Khi cần ảnh minh hoạ | vài chục giây – vài phút tuỳ `--dpi` |

\* benchmark đo trên máy nhóm (AMD Ryzen AI 9 HX 370); các dòng khác đo trên máy Xeon 2,1 GHz, máy laptop đời mới thường nhanh hơn.

---

## 6. Tests

| File | Cần dữ liệu thật? | Kiểm tra gì |
|---|---|---|
| `test_core_offline.py` | Không | haversine, heuristic admissible/consistent, một chiều, liên thông, subgraph, quận, xe, ngập — trên lưới giả 4×4 có đáp án biết trước (`synthetic.py`) |
| `test_snap_speed.py` | Không | snap theo cạnh đúng chiều, cảnh báo điểm xa đường, trần tốc độ, A* theo thời gian |
| `test_vehicle_graph_cache.py` | Không | đồ thị lọc theo xe dùng chung, cache, `resolve_case` báo lỗi landmark xa, thẻ `oneway:motorcycle` (no / yes) |
| `test_bundle_flood_offline.py` | Không | ngập giữa cạnh dài, view chỉ đọc, bundle nhiều xe + điểm ngập chung, `check_case` |
| `test_hanoi_real.py` | Có | đồ thị thật: có hướng, tỉ lệ một chiều, liên thông mạnh, đi ngược chiều bị chặn, xe máy đi hai chiều nơi có `oneway:motorcycle=no`, đồ thị lọc theo xe, snap landmark |
| `test_dataset_real.py` | Có | mọi kỳ vọng trong `test_cases.json`, khớp `golden.json`, A* == Dijkstra, landmark đúng quận |

Test cần dữ liệu thật mang marker `hanoi` và tự bỏ qua (skip) nếu chưa có `data/hanoi_all.*`.

---

## 7. Quy ước dùng chung

- **Toạ độ:** luôn viết `(lat, lng)` khi gọi hàm. Trong đồ thị, `y` là lat và `x` là lng (theo OSMnx). Shapely dùng `Point(lng, lat)`.
- **Đơn vị:** độ dài tính bằng mét (`length`), thời gian bằng giây (`travel_time*`), tốc độ bằng km/h, độ sâu ngập bằng **cm**.
- **Đồ thị luôn có hướng.** Không gọi `to_undirected()` hay `nx.Graph(G)`, vì làm vậy sẽ mất đường một chiều. Muốn dùng DiGraph đơn thì gọi `to_digraph(G)`.
- **Lọc theo xe trước, snap sau.** Snap trên đồ thị gốc rồi chạy trên đồ thị đã lọc có thể ra node không tồn tại. Hàm `resolve_case_bundle` và `snap_point(H, ...)` đã làm đúng thứ tự này.
- **Đồ thị trả về từ `get_vehicle_graph` được dùng chung** giữa các xe cùng kiểu hạn chế (car_ice, car_ev, vf3). Đừng sửa trực tiếp; cần sửa thì gọi `.copy()`. Với ngập, dùng `apply_flood(..., as_view=True)` để khỏi copy.
- **Một chiều riêng của xe máy.** Đồ thị xe máy có thêm 1.072 cạnh ngược mang `contraflow=True`: phố một chiều với ô tô nhưng OSM ghi `oneway:motorcycle=no` (ví dụ Hàng Bông, Hoàng Hoa Thám, Thụy Khuê). Đồ thị gốc và đồ thị ô tô không có các cạnh này. Cấu hình ở trường `oneway_tag` trong `vehicle_profiles.json`.
- **Cache theo số node.** Nếu tự xoá hay thêm *cạnh* của đồ thị mà không đổi số node, hãy gọi `clear_vehicle_graph_cache(G)` và `clear_edge_index_cache(G)`.

---

## 8. Số liệu chính

- Đồ thị: 256.974 node, 622.345 cạnh. Có 19.584 cạnh một chiều (3,15%), đồ thị liên thông mạnh 100%. Tổng diện tích 30 đơn vị hành chính là 3.355 km².
- Bộ data test có 7 case, gồm 51 kiểm tra kỳ vọng, tất cả đều đạt. Đáp án đã chốt trong `golden.json`.
- Benchmark trên 27 truy vấn (máy AMD Ryzen AI 9 HX 370, `--repeat 3`; chi tiết ở mục 11 của tài liệu quy trình):
  - A* toàn đồ thị, ô tô theo mét: trung vị 13 ms, chậm nhất 258 ms. Kết quả luôn bằng Dijkstra, duyệt ít node hơn khoảng 6 lần.
  - Theo thời gian: ô tô trung vị 18 ms (chậm nhất 267 ms), xe máy 6 ms (chậm nhất 236 ms); vẫn luôn bằng Dijkstra.
  - WA* w=1.2: nhanh hơn A* 2–5 lần, đường kém tối ưu tối đa 2,5–6%.
  - Bbox 2 km lọc trực tiếp không nhanh hơn A* (0,8–0,9 lần), còn làm đường kém tối ưu tới 5,7% khi tối ưu theo thời gian.
  - `get_subgraph_near` (copy đồ thị con): riêng bước cắt đã mất trung vị 217–253 ms, chậm nhất 2,9 s, tức chậm hơn chính A*.
  - Báo cáo đầy đủ: `outputs/benchmark/` (ô tô theo mét), `outputs/benchmark_car_time/`, `outputs/benchmark_moto_time/`.

---

## 9. Giới hạn đã biết

- **Đơn vị ngưỡng lội nước:** bảng phân công ghi "xe máy = 20 mm, ô tô = 50 mm, VF3 = 30 mm", nhưng config dùng **cm** (20/50/30 cm). 20 mm (2 cm) nước gần như không cản xe máy, nên nhiều khả năng bảng ghi nhầm đơn vị. Nhóm cần xác nhận lại. Nếu muốn đọc theo mm, dùng `VehicleProfile.max_wading_depth_mm`.
- **Ranh giới quận:** đây là ranh giới cũ, trước đợt sáp nhập 7/2025 (lấy từ GADM). Có 45 node nằm ngoài mọi polygon hơn 300 m nên mang `district=None`.
- **Chưa có:**
  - cấm rẽ (turn restriction);
  - phân biệt ngõ `motorcar=destination` (hiện vẫn được dùng làm đường tắt).

---

## 10. Tài liệu

- Quy trình chi tiết từng công đoạn: [Quy trình xây dựng nền đồ thị Hà Nội](https://claude.ai/code/artifact/c627bf60-89e5-4126-a5e1-ef47388b6732)
- Báo cáo benchmark mới nhất: `benchmark_summary.md` trong `outputs/benchmark/`, `outputs/benchmark_car_time/` và `outputs/benchmark_moto_time/` (lệnh tạo lại ở mục 11 của tài liệu quy trình)
