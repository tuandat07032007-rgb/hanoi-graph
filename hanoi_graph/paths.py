"""Đường dẫn chuẩn của dự án — tính từ vị trí THƯ MỤC GỐC, không phụ thuộc thư mục đang đứng (cwd).

Trước đây các mặc định là đường dẫn tương đối kiểu Path("data/hanoi_all.pkl"): chạy script từ thư mục
khác (vd. bấm Run trong VS Code khi đang mở file ở scripts/) sẽ không thấy file, thậm chí DistrictIndex
còn tự tải lại ranh giới từ mạng và ghi ra một thư mục data/ lạc chỗ. Mọi module dùng các hằng dưới đây.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "outputs"          # ảnh bản đồ, kết quả benchmark... (tạo lại được, không phải dữ liệu gốc)
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

GRAPH_GRAPHML = DATA_DIR / "hanoi_all.graphml"   # đồ thị ô tô + xe máy (build_hanoi.py mặc định)
GRAPH_PICKLE = DATA_DIR / "hanoi_all.pkl"
DISTRICTS_GEOJSON = DATA_DIR / "hanoi_districts.geojson"
GADM_JSON = DATA_DIR / "gadm41_VNM_2.json"
VEHICLE_PROFILES = CONFIG_DIR / "vehicle_profiles.json"
TEST_CASES = FIXTURES_DIR / "test_cases.json"
GOLDEN = FIXTURES_DIR / "golden.json"
