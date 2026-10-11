import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


@pytest.fixture
def client(tmp_path):
    cfg = Settings(data_dir=tmp_path / "data")
    app = create_app(cfg)
    with TestClient(app) as c:
        yield c
