import pytest
from fastapi.testclient import TestClient

from studio.repositories.db import engine_for, metadata
from studio.web.app import create_app


@pytest.fixture
def client(tmp_path):
    metadata.create_all(engine_for(tmp_path))
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1:8765") as client:
        yield client


def test_host_origin_and_csrf(client):
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400
    assert client.post("/api/demo").status_code == 403
    token = client.get("/api/session").json()["csrf"]
    assert (
        client.post(
            "/api/demo", headers={"origin": "http://evil.example", "x-csrf-token": token}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/demo", headers={"origin": "http://127.0.0.1:8765", "x-csrf-token": token}
        ).status_code
        == 200
    )


def test_read_only_root_and_safety_headers(client):
    result = client.get("/")
    assert result.status_code == 200
    assert "生成宣传图物料" in result.text
    assert "生成说明书工业草图" in result.text
    assert "载入开发测试素材" not in result.text
    assert "default-src 'self'" in result.headers["content-security-policy"]
    assert client.get("/api/assets/not-a-file").status_code == 404


def test_requests_reject_unknown_fields_and_unsafe_upload(client):
    token = client.get("/api/session").json()["csrf"]
    headers = {"origin": "http://127.0.0.1:8765", "x-csrf-token": token}
    assert (
        client.post(
            "/api/jobs", headers=headers, json={"mode": "A", "product_ids": ["x"], "secret": "x"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/assets",
            headers=headers,
            files={"file": ("image.png", b"<script>", "image/png")},
            data={"source": "test"},
        ).status_code
        == 400
    )


def test_optional_notes_and_delete_keeps_historical_file(client):
    from test_workflows import picture

    token = client.get("/api/session").json()["csrf"]
    headers = {"origin": "http://127.0.0.1:8765", "x-csrf-token": token}
    response = client.post(
        "/api/assets", headers=headers, files={"file": ("product.png", picture(), "image/png")}
    )
    assert response.status_code == 200
    asset_id = response.json()["id"]
    assert client.delete("/api/assets/" + asset_id, headers=headers).status_code == 200
    assert asset_id not in [a["id"] for a in client.get("/api/state").json()["assets"]]
    assert client.get("/api/assets/" + asset_id).status_code == 200
