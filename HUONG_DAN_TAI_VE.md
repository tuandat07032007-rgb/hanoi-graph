# Hướng dẫn tải về và chạy hanoi-graph

Làm lần lượt từ bước 0 đến bước 6 là chạy được, mất khoảng 10–15 phút (phần lớn là thời gian tải). Mỗi bước có
lệnh cho **Windows (PowerShell)** và **macOS / Linux (Terminal)**. Gặp lỗi ở đâu thì xem [mục 8 — Sửa lỗi thường
gặp](#8-sửa-lỗi-thường-gặp).

Cuối cùng bạn sẽ có thư mục `hanoi-graph` chứa code, dữ liệu đồ thị toàn Hà Nội, và chạy được 97 test.

Repo: <https://github.com/tuandat07032007-rgb/hanoi-graph> · Dữ liệu:
<https://github.com/tuandat07032007-rgb/hanoi-graph/releases/tag/data-v1>

---

## 0. Cần chuẩn bị

| Thứ cần có | Yêu cầu | Ghi chú |
|---|---|---|
| Máy | Windows 10/11, macOS hoặc Linux | |
| RAM | nên có **8 GB** trở lên | chạy test dùng khoảng 3 GB; nạp bằng GraphML (cách dự phòng) dùng khoảng 5 GB |
| Ổ đĩa trống | khoảng **1,5 GB** | thư viện Python khoảng 450 MB; nếu chỉ tải file `.pkl` thì tổng cộng khoảng 650 MB |
| Python | **3.10 trở lên** | đã thử chạy đủ 97 test trên 3.11, 3.12, 3.13 và 3.14 |
| Git | không bắt buộc | không có Git thì tải code bằng nút Download ZIP (bước 1, cách B) |

**Kiểm tra đã có Python chưa.** Mở PowerShell (bấm Start, gõ `PowerShell`, Enter) hoặc Terminal, gõ:

```
python --version
```

- Hiện `Python 3.10.x` trở lên là được.
- Báo lỗi không nhận lệnh, hoặc tự mở Microsoft Store: chưa cài Python. Vào <https://www.python.org/downloads/>, tải
  bản mới, chạy file cài và **nhớ tick ô "Add python.exe to PATH"** ở màn hình đầu tiên. Cài xong thì **đóng PowerShell
  và mở lại**.
- macOS/Linux thường dùng lệnh `python3` thay cho `python`. Trong hướng dẫn này, phần macOS/Linux đã ghi sẵn `python3`.

**Kiểm tra đã có Git chưa** (chỉ cần nếu tải code bằng cách A):

```
git --version
```

Chưa có thì cài ở <https://git-scm.com/downloads>, cứ bấm Next với lựa chọn mặc định, rồi mở lại PowerShell.

---

## 1. Tải code

### Cách A — dùng Git (khuyên dùng, sau này cập nhật chỉ cần một lệnh)

1. Mở thư mục muốn để dự án trong File Explorer (ví dụ `D:\Projects`).
2. Bấm chuột phải vào chỗ trống → **Open in Terminal** (Windows 11). Windows 10: giữ **Shift** + chuột phải →
   **Open PowerShell window here**.
3. Chạy:

```
git clone https://github.com/tuandat07032007-rgb/hanoi-graph.git
cd hanoi-graph
```

### Cách B — không dùng Git

1. Mở <https://github.com/tuandat07032007-rgb/hanoi-graph>.
2. Bấm nút xanh **Code** → **Download ZIP**.
3. Giải nén file vừa tải. Bạn sẽ có thư mục `hanoi-graph-main`; tên khác một chút nhưng dùng y hệt `hanoi-graph`.
4. Mở thư mục đó, chuột phải vào chỗ trống → **Open in Terminal** như cách A.

> **Mọi lệnh từ đây trở đi đều chạy trong thư mục gốc của dự án** — thư mục có `README.md`, `requirements.txt`,
> `hanoi_graph\`, `scripts\`... Nếu mở terminal ở chỗ khác thì `cd` vào trước. Đường dẫn có dấu cách thì để trong
> ngoặc kép, ví dụ `cd "D:\Do an nhom\hanoi-graph"`.

---

## 2. Cài thư viện Python

**Windows:**

```powershell
python -m pip install -r requirements.txt
```

**macOS / Linux** (dùng môi trường ảo `.venv` — trên các máy này cài thẳng thường bị chặn):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Mất khoảng 1–3 phút tuỳ mạng. Lệnh cài các thư viện: osmnx, networkx, geopandas, shapely, numpy, matplotlib, pytest.

> Trên macOS/Linux, mỗi lần mở Terminal mới phải chạy lại `source .venv/bin/activate` trước khi dùng dự án (đầu dòng
> lệnh sẽ hiện `(.venv)`).
>
> Windows cũng dùng `.venv` được nếu muốn tách riêng thư viện cho dự án: `python -m venv .venv` rồi
> `.venv\Scripts\Activate.ps1`. Không bắt buộc. Thư mục `.venv` đã được `.gitignore` bỏ qua.

---

## 3. Tải dữ liệu đồ thị

Dữ liệu lớn không nằm trong code (GitHub không cho file trên 100 MB), mà để ở mục **Releases**, bản `data-v1`:

| File | Dung lượng | Có cần không |
|---|---|---|
| `hanoi_all_pkl.zip` | 42 MB (giải nén 125 MB) | **Cần.** Đồ thị chính, nạp nhanh (khoảng 5 giây) |
| `hanoi_all_graphml.zip` | 37 MB (giải nén 346 MB) | Dự phòng: chỉ cần khi máy không mở được file `.pkl` (xem lỗi 8.9) |
| `overpass_cache.zip` | 34 MB (giải nén 226 MB) | Chỉ cần khi muốn tự build lại đồ thị từ OpenStreetMap |

Người chỉ dùng đồ thị để viết thuật toán: tải **`hanoi_all_pkl.zip`** là đủ.

### Cách A — tải bằng trình duyệt

Mở <https://github.com/tuandat07032007-rgb/hanoi-graph/releases/tag/data-v1>, kéo xuống phần **Assets**, bấm vào tên
file để tải. File sẽ nằm trong thư mục **Downloads**.

### Cách B — tải bằng lệnh

**Windows (PowerShell)** — phải gõ `curl.exe`, có đuôi `.exe`:

```powershell
curl.exe -L -o "$HOME\Downloads\hanoi_all_pkl.zip" https://github.com/tuandat07032007-rgb/hanoi-graph/releases/download/data-v1/hanoi_all_pkl.zip
```

**macOS / Linux:**

```bash
mkdir -p ~/Downloads
curl -L -o ~/Downloads/hanoi_all_pkl.zip https://github.com/tuandat07032007-rgb/hanoi-graph/releases/download/data-v1/hanoi_all_pkl.zip
```

Cần file khác thì thay `hanoi_all_pkl.zip` ở **cả hai chỗ** trong lệnh bằng `hanoi_all_graphml.zip` hoặc
`overpass_cache.zip`.

---

## 4. Giải nén vào đúng chỗ

Đích đến:

- `hanoi_all_pkl.zip` và `hanoi_all_graphml.zip` → vào thư mục **`data`** của dự án.
- `overpass_cache.zip` → vào **thư mục gốc** của dự án (bên trong file nén đã có sẵn thư mục `cache`).

**Windows (PowerShell, đang đứng ở thư mục gốc dự án):**

```powershell
Expand-Archive "$HOME\Downloads\hanoi_all_pkl.zip" -DestinationPath data -Force
# nếu có tải thêm:
Expand-Archive "$HOME\Downloads\hanoi_all_graphml.zip" -DestinationPath data -Force
Expand-Archive "$HOME\Downloads\overpass_cache.zip" -DestinationPath . -Force
```

**macOS / Linux:**

```bash
unzip -o ~/Downloads/hanoi_all_pkl.zip -d data
# nếu có tải thêm:
unzip -o ~/Downloads/hanoi_all_graphml.zip -d data
unzip -o ~/Downloads/overpass_cache.zip -d .
```

Riêng `overpass_cache.zip`, `unzip` sẽ in cảnh báo *"appears to use backslashes as path separators"*. Đó là bình
thường, vì file được nén trên Windows; `unzip` vẫn giải nén đúng vào thư mục `cache`. Trên macOS nên dùng lệnh `unzip`
như trên thay vì bấm đúp vào file nén.

**Kiểm tra vị trí file.** Chạy `dir data` (Windows) hoặc `ls data` (macOS/Linux), phải thấy:

```
data
├─ hanoi_all.pkl              ← nằm THẲNG trong data
├─ hanoi_all.graphml          (nếu có tải)
├─ hanoi_districts.geojson    (có sẵn trong repo)
└─ gadm41_VNM_2.json          (có sẵn trong repo)
```

> **Lỗi hay gặp nhất:** giải nén bằng chuột phải → **Extract All** thì Windows mặc định giải vào một thư mục mới tên
> `hanoi_all_pkl`. Chép nguyên thư mục đó vào `data` sẽ thành `data\hanoi_all_pkl\hanoi_all.pkl`, và code không thấy
> file. Hãy chuyển `hanoi_all.pkl` ra thẳng `data\` rồi xoá thư mục con, hoặc dùng lệnh `Expand-Archive` ở trên. Với
> `overpass_cache.zip` cũng vậy: phải thành `hanoi-graph\cache\<các file .json>`, không phải
> `hanoi-graph\overpass_cache\cache\...`.

Giải nén xong có thể xoá các file `.zip` trong Downloads.

---

## 5. Kiểm tra

```
python scripts/check_data.py
```

(macOS/Linux: vẫn lệnh `python` nếu đã `source .venv/bin/activate`; nếu không thì dùng `python3`.)

Lệnh chạy khoảng 10–30 giây. **Mọi dòng đều phải là `[OK]`**, ví dụ:

```
2) ĐỒ THỊ
   Nạp trong 4.8 s: MultiDiGraph, 256,974 node, 622,345 cạnh
   [OK] có hướng (DiGraph/MultiDiGraph)
   ...
   [OK] golden.json chốt lúc 2026-10-02T19:59:40 trên đồ thị 256,974 node
```

Dòng `[!!] hanoi_all.graphml chưa có` thì không sao nếu bạn không tải file GraphML. Dòng `[!!]` ở chỗ khác thì xem
mục 8.

Sau đó chạy toàn bộ test:

```
python -m pytest tests -rs
```

Lệnh chạy khoảng 2–3 phút. Dòng cuối phải là **`97 passed`**. Nếu thấy `63 passed, 34 skipped` thì code đúng nhưng
chưa thấy dữ liệu: quay lại bước 4.

---

## 6. Chạy thử tìm đường

Tạo file `thu_tim_duong.py` **trong thư mục gốc của dự án** (cùng chỗ với `README.md`), dán nội dung sau:

```python
import networkx as nx
from hanoi_graph import load_graph, get_profile, get_vehicle_graph, snap_pair, make_heuristic, path_length_m

G = load_graph()                                   # đồ thị toàn Hà Nội, khoảng 5 giây
car = get_profile("car_ice")                       # ô tô xăng
H = get_vehicle_graph(G, car)                      # chỉ giữ đường ô tô được đi, khoảng 10–20 giây lần đầu
s, g = snap_pair(H, (21.0288, 105.8523), (21.0050, 105.8430))   # Tháp Rùa -> ĐH Bách khoa, dạng (lat, lng)
h = make_heuristic(H, g.node)
path = nx.astar_path(H, s.node, g.node, heuristic=lambda n, _t: h(n), weight="length")
print("Quãng đường:", round(path_length_m(H, path)), "m")
```

Chạy:

```
python thu_tim_duong.py
```

Lệnh chạy khoảng 30–60 giây (lần đầu phải dựng chỉ mục) và in ra `Quãng đường: 3646 m`. Tới đây là đã chạy được
hoàn toàn. Các ví dụ khác (tìm theo thời gian, tránh điểm ngập, so với đáp án chốt) nằm ở mục 3 của
[README](README.md#3-dùng-trong-code-của-bạn).

---

## 7. Cập nhật khi nhóm có bản mới

- **Code mới** (đã tải bằng Git): chạy `git pull` trong thư mục dự án. Tải bằng ZIP thì phải tải ZIP mới.
- **Dữ liệu mới** (nhóm build lại đồ thị và tạo Release mới, ví dụ `data-v2`): tải file zip của bản mới, giải nén
  đè như bước 4 (`-Force` / `-o` sẽ ghi đè), rồi chạy lại bước 5.

---

## 8. Sửa lỗi thường gặp

Mỗi lỗi ghi theo dạng: **thông báo bạn thấy** → nguyên nhân → cách sửa. Tìm nhanh bằng Ctrl+F, gõ một đoạn trong
thông báo lỗi.

### 8.1. `python : The term 'python' is not recognized...` hoặc gõ `python` lại mở Microsoft Store

Chưa cài Python, hoặc lúc cài quên tick "Add python.exe to PATH".

- Cài lại Python từ <https://www.python.org/downloads/>, tick **Add python.exe to PATH**, rồi đóng và mở lại PowerShell.
- Hoặc dùng lệnh `py` thay cho `python`: `py --version`, `py -m pip install -r requirements.txt`,
  `py scripts/check_data.py`...
- Vẫn mở Microsoft Store: vào **Settings → Apps → Advanced app settings → App execution aliases** (Windows 10:
  **Settings → Apps → Apps & features → App execution aliases**), tắt hai dòng `python.exe` và `python3.exe`.

### 8.2. `git : The term 'git' is not recognized...`

Chưa cài Git, hoặc cài rồi nhưng chưa mở lại terminal. Cài ở <https://git-scm.com/downloads> rồi mở lại PowerShell.
Không muốn cài Git thì dùng cách B ở bước 1.

### 8.3. `pip : The term 'pip' is not recognized...` hoặc `pytest : The term 'pytest' is not recognized...`

Luôn gọi qua Python: `python -m pip ...` và `python -m pytest ...`.

### 8.4. Lỗi khi cài thư viện (`pip install`)

| Thông báo | Cách sửa |
|---|---|
| `error: externally-managed-environment` (macOS/Linux) | Dùng môi trường ảo như bước 2: `python3 -m venv .venv` → `source .venv/bin/activate` → cài lại |
| `Microsoft Visual C++ 14.0 or greater is required`, `Failed building wheel for ...` | Phiên bản Python chưa có gói cài sẵn cho thư viện đó. Nâng pip trước: `python -m pip install --upgrade pip` rồi cài lại. Vẫn lỗi thì dùng Python 3.11–3.13 |
| `Permission denied`, `Access is denied` | Thêm `--user`: `python -m pip install --user -r requirements.txt`, hoặc dùng `.venv` |
| `Read timed out`, `Connection reset` | Mạng chập chờn: chạy lại, hoặc thêm `--default-timeout 120` |

### 8.5. `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system`

PowerShell đang chặn chạy script. Chạy một lần:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

rồi kích hoạt lại. Hoặc khỏi kích hoạt, gọi thẳng `.venv\Scripts\python.exe` thay cho `python`.

### 8.6. `curl` báo `A parameter cannot be found that matches parameter name 'L'`

Trong PowerShell, `curl` (không có `.exe`) là tên khác của một lệnh khác. Gõ đúng **`curl.exe`**, hoặc tải bằng trình
duyệt (bước 3, cách A).

### 8.7. `Expand-Archive` báo file đã tồn tại, hoặc không tìm thấy file zip

- Báo *already exists*: thêm `-Force` vào cuối lệnh để ghi đè.
- Báo *path does not exist*: file zip không nằm trong Downloads (trình duyệt lưu chỗ khác). Sửa đường dẫn trong lệnh
  cho đúng chỗ file đang nằm, hoặc kéo file vào cửa sổ PowerShell để tự điền đường dẫn.
- Giải nén xong mà code vẫn không thấy dữ liệu: xem lại "Lỗi hay gặp nhất" ở bước 4 (thư mục con thừa).

### 8.8. Báo chưa có dữ liệu, hoặc bảo chạy `build_hanoi.py`

Ví dụ các thông báo:

- `FileNotFoundError: Chưa có ...\data\hanoi_all.graphml. Chạy: python scripts/build_hanoi.py`
- Khi chạy test: `SKIPPED ... Chưa có data/hanoi_all.* — chạy scripts/build_hanoi.py trước`, kết quả
  `63 passed, 34 skipped`

Code không tìm thấy `data\hanoi_all.pkl`. **Không cần build lại** (build cần mạng và mất nhiều thời gian). Hãy:

1. Kiểm tra đang đứng ở thư mục gốc dự án (`dir` phải thấy `README.md` và thư mục `data`).
2. Kiểm tra `data\hanoi_all.pkl` nằm thẳng trong `data` (bước 4).
3. Chưa tải thì làm lại bước 3–4.

### 8.9. Lỗi khi mở file `.pkl`

Ví dụ: `UnpicklingError`, `EOFError: Ran out of input`, `invalid load key`, `AttributeError: Can't get attribute ...`,
`ModuleNotFoundError` xuất hiện ngay khi nạp đồ thị.

File `.pkl` bị tải thiếu hoặc hỏng, hoặc máy bạn có phiên bản thư viện quá khác máy tạo file. Sửa theo thứ tự:

1. Xoá `data\hanoi_all.pkl`, tải lại `hanoi_all_pkl.zip`, giải nén lại. Kiểm tra file giải nén ra đúng 125.092.006
   byte (chuột phải → Properties).
2. Vẫn lỗi thì dùng file GraphML (đọc được ở mọi phiên bản):
   - tải `hanoi_all_graphml.zip` và giải nén vào `data` (bước 3–4);
   - đổi tên file pkl để code bỏ qua nó, vì code luôn ưu tiên `.pkl` nếu file này tồn tại:

     ```powershell
     Rename-Item data\hanoi_all.pkl hanoi_all.pkl.bak       # macOS/Linux: mv data/hanoi_all.pkl data/hanoi_all.pkl.bak
     ```

   - chạy lại `python scripts/check_data.py`. Nạp GraphML chậm hơn (khoảng 30 giây – vài phút) và cần khoảng 5 GB RAM,
     nhưng kết quả y hệt.

### 8.10. `ModuleNotFoundError: No module named 'hanoi_graph'`

Python không thấy thư viện của dự án. Thường do:

- **Chạy lệnh ở sai thư mục:** `cd` vào thư mục gốc dự án rồi chạy lại.
- **File code của bạn nằm ngoài thư mục gốc**, ví dụ để ở Desktop: Python chỉ tìm thư viện cạnh file đang chạy. Chuyển
  file vào thư mục gốc dự án, hoặc thêm hai dòng này lên đầu file (sửa đường dẫn cho đúng máy bạn):

  ```python
  import sys
  sys.path.insert(0, r"D:\Projects\hanoi-graph")
  ```

### 8.11. `ModuleNotFoundError: No module named 'osmnx'` (hoặc `networkx`, `geopandas`...)

Thư viện được cài vào một bản Python khác bản đang chạy. Hay gặp khi máy có nhiều bản Python, hoặc quên kích hoạt
`.venv`.

- Cài lại bằng đúng lệnh Python bạn dùng để chạy: `python -m pip install -r requirements.txt` (hoặc `py -m pip ...`
  nếu bạn chạy bằng `py`).
- Dùng `.venv` thì kích hoạt trước (bước 2).
- Trong VS Code: bấm **Ctrl+Shift+P** → **Python: Select Interpreter** → chọn đúng bản Python đã cài thư viện (hoặc
  `.venv`). Cách này cũng hết các dòng báo đỏ "Import could not be resolved".

### 8.12. Chữ tiếng Việt bị lỗi font, hoặc `UnicodeEncodeError: 'charmap' codec can't encode character`

Terminal của Windows đang không dùng UTF-8. Chạy trước trong PowerShell:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

rồi chạy lại lệnh. Nên dùng **Windows Terminal** thay cho cửa sổ cmd cũ.

### 8.13. `MemoryError`, máy đơ khi nạp đồ thị

Không đủ RAM. Tắt bớt trình duyệt và ứng dụng khác rồi chạy lại. Nạp bằng `.pkl` cần ít RAM hơn nhiều so với GraphML,
nên tránh dùng GraphML nếu không cần. Máy dưới 8 GB RAM vẫn chạy được phần test không cần dữ liệu:

```
python -m pytest tests -m "not hanoi"
```

(62 test, khoảng 3 giây.)

### 8.14. Test báo sai lệch với golden, hoặc `check_data` báo "đồ thị đã đổi"

File đồ thị trên máy bạn khác bản đã dùng để chốt đáp án (`tests/fixtures/golden.json`), thường do tự build lại đồ thị.

- Tải lại file zip ở Release và giải nén đè (bước 3–4).
- Nếu bạn cố ý build lại và muốn dùng đồ thị mới: `python scripts/freeze_golden.py` để chốt lại đáp án theo đồ thị mới.
  Báo nhóm trước khi làm, vì cả nhóm cần dùng cùng một đồ thị.

### 8.15. Tự build lại đồ thị bị lỗi mạng (`build_hanoi.py`)

Chỉ cần đọc nếu muốn build lại từ OpenStreetMap; người chỉ dùng đồ thị có sẵn thì bỏ qua.

- Báo timeout, `429 Too Many Requests`, hoặc không có mạng: giải nén `overpass_cache.zip` vào thư mục gốc (thành thư
  mục `cache`). Script sẽ lấy dữ liệu từ cache thay vì gọi máy chủ Overpass.
- Cache chỉ dùng được khi chạy **đúng lệnh mặc định** `python scripts/build_hanoi.py`. Thêm `--tile-km` khác thì câu truy
  vấn khác đi, cache không khớp và script lại phải gọi mạng.
- Build lại xong phải chạy `python scripts/freeze_golden.py` (xem 8.14).

### 8.16. Vẫn không được?

Chạy hai lệnh sau và gửi **toàn bộ** kết quả (copy chữ, đừng chụp ảnh) cho nhóm, hoặc mở một Issue trên GitHub
(trang repo → **Issues** → **New issue**):

```
python --version
python scripts/check_data.py
```

Ghi kèm hệ điều hành và bạn đang làm tới bước nào trong hướng dẫn này.
