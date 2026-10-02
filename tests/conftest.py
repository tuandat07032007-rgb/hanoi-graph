import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from synthetic import build_synthetic_graph, synthetic_districts  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "hanoi: cần đồ thị Hà Nội thật (data/hanoi_all.pkl|graphml); tự skip nếu chưa có. Chỉ chạy test offline: pytest -m \"not hanoi\"")


@pytest.fixture()
def G():
    return build_synthetic_graph()


@pytest.fixture()
def district_index():
    from hanoi_graph.districts import DistrictIndex
    return DistrictIndex(synthetic_districts())


@pytest.fixture(scope="session")
def hanoi_graph():
    from hanoi_graph.loader import load_graph
    try:
        return load_graph(ROOT / "data/hanoi_all.graphml", ROOT / "data/hanoi_all.pkl")
    except FileNotFoundError:
        pytest.skip("Chưa có data/hanoi_all.* — chạy scripts/build_hanoi.py trước")


@pytest.fixture(scope="session")
def hanoi_districts():
    from hanoi_graph.districts import DistrictIndex
    p = ROOT / "data/hanoi_districts.geojson"
    if not p.exists():
        pytest.skip("Chưa có data/hanoi_districts.geojson")
    return DistrictIndex.load(p)
