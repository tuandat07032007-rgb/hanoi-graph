# hanoi-graph — nền đồ thị đường bộ Hà Nội cho bài toán tìm đường

Phần nền dùng chung cho nhóm làm bài toán tìm đường ở Hà Nội. Gồm:

- **Đồ thị có hướng của toàn Hà Nội** lấy từ OpenStreetMap: 12 quận, 17 huyện, 1 thị xã; có cả đường ô tô lẫn ngõ xe
  máy; 256.974 node, 622.345 cạnh; giữ đúng chiều đường một chiều.
- **Thư viện `hanoi_graph`** với các tiện ích mà thuật toán (A\*, tránh điểm ngập, chọn phương tiện) cần dùng chung:
  - khoảng cách haversine, heuristic A\*;
  - tra quận theo toạ độ;
  - lọc đường theo loại xe, thời gian đi theo trần tốc độ;
  - snap toạ độ vào đường, đúng chiều đi;
  - mô hình điểm ngập;
  - cắt đồ thị theo bounding-box, kiểm tra liên thông.
- **Bộ data test cố định có đáp án chốt sẵn** (`golden.json`) để kiểm tra thuật toán, và script benchmark A\* trên dữ
  liệu thật.

> **Lần đầu tải về, hoặc chưa quen Git/Python?** Làm theo **[HUONG_DAN_TAI_VE.md](HUONG_DAN_TAI_VE.md)**: hướng dẫn từng
> bước cho Windows, macOS, Linux, kèm cách sửa các lỗi thường gặp.

---

## 1. Chạy nhanh

Cần **Python 3.10+** (đã thử 3.11–3.14), Git, khoảng 1,5 GB ổ trống, nên có 8 GB RAM.

**Windows (PowerShell):**

```powershell
git clone https://github.com/tuandat07032007-rgb/hanoi-graph.git
cd hanoi-graph
python -m pip install -r requirements.txt

# tải đồ thị (42 MB) và giải nén vào data\
curl.exe -L -o "$HOME\Downloads\hanoi_all_pkl.zip" https://github.com/tuandat07032007-rgb/hanoi-graph/releases/download/data-v1/hanoi_all_pkl.zip
Expand-Archive "$HOME\Downloads\hanoi_all_pkl.zip" -DestinationPath data -Force

python scripts/check_data.py        # mọi dòng phải là [OK]
python -m pytest tests -rs          # phải ra 97 passed (khoảng 2–3 phút)
```

**macOS / Linux:**

```bash
git clone https://github.com/tuandat07032007-rgb/hanoi-graph.git
cd hanoi-graph
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

curl -L -o /tmp/hanoi_all_pkl.zip https://github.com/tuandat07032007-rgb/hanoi-graph/releases/download/data-v1/hanoi_all_pkl.zip
unzip -o /tmp/hanoi_all_pkl.zip -d data

python scripts/check_data.py
python -m pytest tests -rs
```

Chỉ muốn chạy phần test không cần dữ liệu (62 test, khoảng 3 giây): `python -m pytest tests -m "not hanoi"`.

---

## 2. Dữ liệu: cái gì có sẵn, cái gì phải tải

Dữ liệu lớn không đưa vào repo vì GitHub giới hạn 100 MB mỗi file. Chúng nằm ở mục Releases, bản
**[data-v1](https://github.com/tuandat07032007-rgb/hanoi-graph/releases/tag/data-v1)**:

| Thành phần | Lấy ở đâu | Đặt vào | Có cần không |
|---|---|---|---|
| Code, cấu hình xe, test, `data/hanoi_districts.geojson`, `data/gadm41_VNM_2.json` | có sẵn khi clone | — | có sẵn |
| `hanoi_all.pkl`: đồ thị chính, nạp khoảng 5 giây | `hanoi_all_pkl.zip` (42 MB → 125 MB) | `data/` | **cần** |
| `hanoi_all.graphml`: cùng đồ thị, đọc được ở mọi phiên bản thư viện | `hanoi_all_graphml.zip` (37 MB → 346 MB) | `data/` | chỉ khi máy không mở được `.pkl` |
| `cache/`: phản hồi Overpass đã lưu | `overpass_cache.zip` (34 MB → 226 MB) | thư mục gốc | chỉ khi muốn tự build lại đồ thị |
| `outputs/`: bản đồ, báo cáo benchmark | không tải; các script tự tạo khi chạy | — | — |

Code luôn ưu tiên `data/hanoi_all.pkl`. Muốn dùng file GraphML thì đổi tên hoặc xoá file `.pkl` (xem mục 8.9 của
hướng dẫn).

---

## 3. Dùng trong code của bạn

Đặt file `.py` của bạn **trong thư mục gốc của dự án** (cùng cấp với thư mục `hanoi_graph/`) để `import hanoi_graph`
chạy được. Đặt ở chỗ khác thì xem mục 8.10 của [hướng dẫn](HUONG_DAN_TAI_VE.md#810-modulenotfounderror-no-module-named-hanoi_graph).

**Đường ngắn nhất cho ô tô:**

```python
import networkx as nx
from hanoi_graph import load_graph, get_profile, get_vehicle_graph, snap_pair, make_heuristic, path_length_m

G = load_graph()                                   # MultiDiGraph có hướng, khoảng 5 giây
car = get_profile("car_ice")
H = get_vehicle_graph(G, car)                      # chỉ còn đường ô tô được đi; cache, 10–20 giây lần đầu
s, g = snap_pair(H, (21.0288, 105.8523), (21.0050, 105.8430))   # (lat, lng) -> node, đúng chiều một chiều
h = make_heuristic(H, g.node)                      # haversine tới đích (mét)
path = nx.astar_path(H, s.node, g.node, heuristic=lambda n, _t: h(n), weight="length")
print(round(path_length_m(H, path)), "m")          # 3646 m; báo lỗi nếu đường đi sai chiều
```

**Nhanh nhất theo thời gian cho xe máy, rồi tránh một điểm ngập:**

```python
from hanoi_graph import add_vehicle_travel_times, FloodSpot, apply_flood

moto = get_profile("motorbike_ice")
M = get_vehicle_graph(G, moto)                     # có thêm cạnh đi ngược chiều nơi OSM ghi oneway:motorcycle=no
w = add_vehicle_travel_times(M, moto)              # ghi số giây vào thuộc tính "travel_time_motorbike_ice"
s, g = snap_pair(M, (21.0287, 105.7784), (21.0288, 105.8523))   # Bến xe Mỹ Đình -> Tháp Rùa
h = make_heuristic(M, g.node, mode="time", max_speed_kph=moto.speed_cap_kph)
path = nx.astar_path(M, s.node, g.node, heuristic=lambda n, _t: h(n), weight=w)
print(round(path_length_m(M, path, weight=w)), "giây")          # 635 giây

spot = FloodSpot("ngap_1", lat=21.0294, lng=105.8081, radius_m=60, depth_cm=35)
M_ngap = apply_flood(M, [spot], moto, as_view=True)              # bỏ cạnh ngập sâu hơn ngưỡng lội nước của xe máy (20 cm)
path2 = nx.astar_path(M_ngap, s.node, g.node, heuristic=lambda n, _t: h(n), weight=w)
print(round(path_length_m(M_ngap, path2, weight=w)), "giây")    # 648 giây, đi đường khác
```

**Kiểm tra thuật toán của bạn với đáp án chốt** (bộ data test có 7 case, 11 lượt case × xe):

```python
import json
from hanoi_graph import load_cases, resolve_case_bundle, paths

data = load_cases()
golden = json.loads(paths.GOLDEN.read_text(encoding="utf-8"))
for case in data["cases"]:
    b = resolve_case_bundle(G, data, case)         # mỗi xe một đồ thị đã lọc, start/goal đã snap sẵn
    for vid, run in b.runs.items():
        my_len = my_astar(run.graph, run.start_node, run.goal_node)   # thay bằng thuật toán của bạn, trả về độ dài (m)
        best = golden["cases"][case["id"]]["vehicles"][vid]["length_m"]
        assert abs(my_len - best) <= 1.0, (case["id"], vid, my_len, best)   # A* đúng phải bằng tối ưu (sai số 1 m)
```

Các ví dụ trên đều đã được chạy thử trên dữ liệu `data-v1` và cho đúng các số trong chú thích.

---

## 4. Cấu trúc thư mục

```
hanoi-graph/
├─ README.md                 file này
├─ HUONG_DAN_TAI_VE.md       hướng dẫn tải về từng bước + sửa lỗi
├─ requirements.txt          thư viện cần cài
├─ .gitignore                không đưa data lớn, cache/, outputs/, .venv/ lên git
├─ config/
│   └─ vehicle_profiles.json   nguồn duy nhất về phương tiện: ngưỡng lội nước, trần tốc độ, đường cấm
├─ data/
│   ├─ hanoi_districts.geojson 30 ranh giới quận/huyện/thị xã (có sẵn trong repo)
│   ├─ gadm41_VNM_2.json       file GADM gốc để tạo lại geojson trên (có sẵn)
│   ├─ hanoi_all.pkl           đồ thị (TẢI ở Release, xem mục 2)
│   └─ hanoi_all.graphml       cùng đồ thị, bản dự phòng (TẢI nếu cần)
├─ hanoi_graph/              thư viện dùng chung: from hanoi_graph import ...
├─ scripts/                  các lệnh chạy: build, kiểm tra, chốt đáp án, benchmark, vẽ bản đồ
├─ tests/                    pytest; tests/fixtures/ chứa bộ data test (test_cases.json) và đáp án (golden.json)
├─ cache/                    (TẢI nếu cần) cache Overpass, dùng khi build lại đồ thị
└─ outputs/                  (tự tạo) maps/ (ảnh bản đồ), benchmark*/ (báo cáo benchmark)
```

---

## 5. Thư viện `hanoi_graph/`

| File | Nội dung | Hàm/lớp chính |
|---|---|---|
| `paths.py` | Đường dẫn tuyệt đối tính từ gốc dự án, không phụ thuộc thư mục đang đứng | `DATA_DIR`, `GRAPH_PICKLE`, `GOLDEN`, `OUTPUT_DIR`... |
| `loader.py` | Tải toàn Hà Nội theo ô, gộp, simplify, hậu xử lý; lưu/nạp | `load_graph`, `save_graph`, `download_hanoi_graph` |
| `directed.py` | Đảm bảo đồ thị có hướng, thống kê một chiều | `require_directed`, `oneway_report`, `to_digraph` |
| `geo.py` | Nguồn duy nhất cho khoảng cách: haversine, độ dài cạnh, heuristic A\* | `haversine_m`, `make_heuristic`, `nearest_node`, `path_length_m` |
| `connectivity.py` | Liên thông mạnh, loại "đảo"/bẫy một chiều, giải thích vì sao không có đường | `check_connectivity`, `keep_largest_scc`, `diagnose_no_path` |
| `districts.py` | Tra quận theo toạ độ (polygon chứa điểm, dung sai 300 m) | `get_district`, `DistrictIndex`, `HANOI_UNITS` |
| `subgraph.py` | Cắt đồ thị quanh 2 điểm (bounding-box + buffer, tự nới khi mất đường) | `get_subgraph_near`, `nodes_in_bbox` |
| `vehicles.py` | Cấu hình xe; lọc đường theo xe (bỏ đường cấm, áp `oneway:motorcycle` cho xe máy, có cache); thời gian đi theo trần tốc độ | `get_profile`, `get_vehicle_graph`, `add_vehicle_travel_times`, `time_weight` |
| `spatial.py` | Chỉ mục không gian của cạnh (STRtree), dùng chung cho snap và ngập | `get_edge_index` |
| `snap.py` | Snap toạ độ vào cạnh gần nhất, chọn node đúng chiều đi, cảnh báo điểm xa đường quá 300 m | `snap_point`, `snap_pair`, `SnapResult` |
| `flood.py` | Điểm ngập → cạnh ngập (theo hình dạng thật của cạnh) → cạnh bị chặn theo xe | `FloodSpot`, `flooded_edges`, `apply_flood` |
| `testcases.py` | Giải bộ data test: mỗi xe một đồ thị, điểm ngập dùng chung, kiểm tra kỳ vọng | `load_cases`, `resolve_case_bundle`, `flood_outcome`, `check_case` |

---

## 6. Scripts

Chạy từ thư mục gốc dự án.

| Lệnh | Làm gì | Khi nào chạy | Thời gian |
|---|---|---|---|
| `python scripts/check_data.py` | Kiểm tra nhanh: file, hướng, một chiều, liên thông, quận, xe, landmark, golden | Sau khi tải/giải nén dữ liệu | 10–30 giây |
| `python scripts/benchmark_astar.py` | Đo Dijkstra / A\* / Weighted A\* / bbox trên dữ liệu thật → `outputs/benchmark/` | Khi cần số liệu tốc độ | khoảng 1 phút |
| `python scripts/show_hanoi.py` | Vẽ bản đồ (ô tô / chỉ xe máy / chỉ ô tô + ranh giới quận) → `outputs/maps/` | Khi cần ảnh minh hoạ | vài chục giây – vài phút |
| `python scripts/build_hanoi.py` | Build lại đồ thị từ OpenStreetMap → `data/hanoi_all.*` | Chỉ khi muốn dữ liệu OSM mới | xem ghi chú dưới |
| `python scripts/freeze_golden.py` | Chốt lại đáp án cho bộ data test → `tests/fixtures/golden.json` | Sau khi build lại đồ thị hoặc sửa case | khoảng 1,5 phút |
| `python scripts/import_gadm.py` | GADM → `data/hanoi_districts.geojson` (30 đơn vị) | Khi cần tạo lại ranh giới quận | vài giây |

Ba lệnh cuối chỉ dành cho người bảo trì dữ liệu; người viết thuật toán không cần chạy.

`build_hanoi.py` có thêm tuỳ chọn `--tile-km` (mặc định 15). Có thư mục `cache/` (giải nén từ `overpass_cache.zip`) thì
script lấy dữ liệu từ cache, không cần gọi Overpass, nhưng chỉ khi chạy đúng lệnh mặc định. Không có cache thì cần mạng
và mất vài chục phút. Build lại xong phải chạy `freeze_golden.py` và báo cả nhóm, vì mọi người cần dùng cùng một đồ thị.

`benchmark_astar.py` có các tuỳ chọn `--vehicle`, `--weight length|time`, `--repeat`, `--quick` và `--out`. Ví dụ:
`python scripts/benchmark_astar.py --vehicle motorbike_ice --weight time --repeat 3 --out outputs/benchmark_moto_time`.

---

## 7. Tests

```
python -m pytest tests -rs              # 97 test (khoảng 2–3 phút)
python -m pytest tests -m "not hanoi"   # 62 test không cần dữ liệu (khoảng 3 giây)
```

| File | Cần dữ liệu thật? | Kiểm tra gì |
|---|---|---|
| `test_core_offline.py` | Không | haversine, heuristic admissible/consistent, một chiều, liên thông, subgraph, quận, xe, ngập — trên lưới giả 4×4 có đáp án biết trước (`synthetic.py`) |
| `test_snap_speed.py` | Không | snap theo cạnh đúng chiều, cảnh báo điểm xa đường, trần tốc độ, A\* theo thời gian |
| `test_vehicle_graph_cache.py` | Không | đồ thị lọc theo xe dùng chung, cache, báo lỗi landmark xa, thẻ `oneway:motorcycle` (no / yes) |
| `test_bundle_flood_offline.py` | Không | ngập giữa cạnh dài, view chỉ đọc, nhiều xe với điểm ngập chung, `check_case` |
| `test_hanoi_real.py` | Có | đồ thị thật: có hướng, tỉ lệ một chiều, liên thông mạnh, đi ngược chiều bị chặn, xe máy đi hai chiều nơi có `oneway:motorcycle=no`, snap landmark |
| `test_dataset_real.py` | Có | mọi kỳ vọng trong `test_cases.json`, khớp `golden.json`, A\* bằng Dijkstra, landmark đúng quận |

Test cần dữ liệu thật mang marker `hanoi` và tự bỏ qua (skip) khi chưa có `data/hanoi_all.*`. Thấy
`63 passed, 34 skipped` nghĩa là code chạy đúng nhưng chưa có dữ liệu (xem mục 2).

---

## 8. Quy ước dùng chung

- **Toạ độ:** luôn viết `(lat, lng)` khi gọi hàm. Trong đồ thị, `y` là lat và `x` là lng (theo OSMnx). Shapely dùng
  `Point(lng, lat)`.
- **Đơn vị:** độ dài tính bằng mét (`length`), thời gian bằng giây (`travel_time*`), tốc độ bằng km/h, độ sâu ngập
  bằng **cm**.
- **Đồ thị luôn có hướng.** Không gọi `to_undirected()` hay `nx.Graph(G)`, vì làm vậy sẽ mất đường một chiều. Muốn dùng
  DiGraph đơn thì gọi `to_digraph(G)`.
- **Lọc theo xe trước, snap sau.** Snap trên đồ thị gốc rồi chạy trên đồ thị đã lọc có thể ra node không tồn tại.
  `resolve_case_bundle` và `snap_point(H, ...)` đã làm đúng thứ tự này.
- **Đồ thị trả về từ `get_vehicle_graph` được dùng chung** giữa các xe cùng kiểu hạn chế (`car_ice`, `car_ev`, `vf3`
  dùng chung một đồ thị; hai xe máy dùng chung một đồ thị). Đừng sửa trực tiếp; cần sửa thì gọi `.copy()`. Với ngập,
  dùng `apply_flood(..., as_view=True)` để khỏi copy.
- **Một chiều riêng của xe máy.** Đồ thị xe máy có thêm 1.072 cạnh ngược mang `contraflow=True`, ở những phố một chiều
  với ô tô nhưng OSM ghi `oneway:motorcycle=no` (ví dụ Hàng Bông, Hoàng Hoa Thám, Thụy Khuê). Đồ thị gốc và đồ thị ô tô
  không có các cạnh này.
- **Sửa số về xe trong `config/vehicle_profiles.json`**, không ghi cứng trong thuật toán.
- **Cache theo số node.** Nếu tự xoá hay thêm *cạnh* của đồ thị mà không đổi số node, hãy gọi
  `clear_vehicle_graph_cache(G)` và `clear_edge_index_cache(G)`.

---

## 9. Số liệu chính

- Đồ thị: 256.974 node, 622.345 cạnh. Có 19.584 cạnh một chiều (3,15%), liên thông mạnh 100%. 30 đơn vị hành chính,
  tổng 3.355 km².
- Phương tiện: xe máy xăng/điện (lội nước 20 cm, trần 50 km/h, cấm cao tốc), ô tô xăng/điện (50 cm, 60 km/h), VinFast VF 3
  (30 cm, 60 km/h).
- Bộ data test: 7 case trên 10 landmark, 51 kiểm tra kỳ vọng, tất cả đều đạt. Đáp án chốt trong `golden.json`.
- Benchmark trên 27 truy vấn (AMD Ryzen AI 9 HX 370, `--repeat 3`):
  - A\* toàn đồ thị luôn cho kết quả bằng Dijkstra. Ô tô theo mét: trung vị 13 ms, chậm nhất 258 ms. Theo thời gian:
    ô tô trung vị 18 ms (chậm nhất 267 ms), xe máy 6 ms (chậm nhất 236 ms).
  - Weighted A\* w = 1,2: nhanh hơn A\* 2–5 lần, đường kém tối ưu tối đa 2,5–6%.
  - Bbox 2 km lọc trực tiếp không nhanh hơn A\* (0,8–0,9 lần), còn làm đường kém tối ưu tới 5,7% khi tối ưu theo thời
    gian.
  - `get_subgraph_near` (copy đồ thị con): riêng bước cắt đã mất trung vị 217–253 ms, chậm nhất 2,9 s, tức chậm hơn chính
    A\*.
  - Chạy `scripts/benchmark_astar.py` để có báo cáo đầy đủ trên máy của bạn (thư mục `outputs/` không có trong repo).

---

## 10. Giới hạn đã biết
- **Ranh giới quận:** ranh giới cũ, trước đợt sáp nhập 7/2025 (lấy từ GADM). Có 45 node nằm ngoài mọi polygon hơn 300 m
  nên mang `district=None`.
- **Tốc độ:** `speed_kph` do OSMnx ước theo loại đường; trần tốc độ của xe là số đặt tạm, chưa đo thực tế.
- **Chưa có:** cấm rẽ (turn restriction); phân biệt ngõ `motorcar=destination` (hiện vẫn được dùng làm đường tắt).

---

## 11. Gặp lỗi?

| Thấy gì | Làm gì |
|---|---|
| `63 passed, 34 skipped`, hoặc thông báo bảo chạy `build_hanoi.py` | Chưa có `data/hanoi_all.pkl`: tải và giải nén theo mục 1–2. Không cần build lại |
| `ModuleNotFoundError: No module named 'hanoi_graph'` | Chạy từ thư mục gốc dự án; đặt file code của bạn trong thư mục gốc |
| `ModuleNotFoundError: No module named 'osmnx'` | Chưa cài thư viện cho đúng bản Python đang dùng: `python -m pip install -r requirements.txt` |
| Lỗi khi mở `hanoi_all.pkl` (`UnpicklingError`, `EOFError`...) | Tải lại file zip; vẫn lỗi thì dùng file GraphML (mục 8.9 của hướng dẫn) |
| `python` / `git` không được nhận diện | Cài Python (tick "Add python.exe to PATH") hoặc Git, rồi mở lại terminal |

Danh sách đầy đủ và cách sửa chi tiết: [HUONG_DAN_TAI_VE.md, mục 8](HUONG_DAN_TAI_VE.md#8-sửa-lỗi-thường-gặp).

---

## 12. Tài liệu

- Hướng dẫn tải về và sửa lỗi: [HUONG_DAN_TAI_VE.md](HUONG_DAN_TAI_VE.md)
- Quy trình chi tiết từng công đoạn (cách hoạt động, kết quả thực tế): _(dán link HackMD của nhóm vào đây)_
