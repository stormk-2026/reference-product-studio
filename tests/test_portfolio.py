from fastapi.testclient import TestClient

from studio.web.app import create_app
from studio.web.portfolio import PROJECTS, PUBLIC_PAGES


def test_public_portfolio_does_not_create_private_workflow(tmp_path, monkeypatch):
    app = create_app(tmp_path, auth_enabled=True, registration_enabled=False)
    user = app.state.accounts.create("studio", "offline-password-only", owner=True)
    token = app.state.accounts.issue(user)

    def private_workflow_forbidden(*args):
        raise AssertionError("Public browsing must not load private tenant data")

    monkeypatch.setattr(app.state.tenants, "workflow", private_workflow_forbidden)
    with TestClient(app, base_url="https://stormstudio.top") as client:
        for authenticated in (False, True):
            if authenticated:
                client.cookies.set("studio_session", token)
            for path in PUBLIC_PAGES:
                response = client.get(path)
                assert response.status_code == 200, path
                if response.headers["content-type"].startswith("text/html"):
                    assert "Storm Studio" in response.text
                    assert "浙ICP备2026082439号-1" in response.text
                    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            assert client.get("/projects/unknown").status_code == 404
            legacy_tools = client.get("/tools", follow_redirects=False)
            assert legacy_tools.status_code == 308
            assert legacy_tools.headers["location"] == "/projects/visual-workbench"
    assert not (tmp_path / "studio.db").exists()


def test_workspace_requires_login_and_preserves_only_allowed_tool(tmp_path):
    app = create_app(tmp_path, auth_enabled=True, registration_enabled=False)
    with TestClient(app, base_url="https://stormstudio.top", follow_redirects=False) as client:
        for tool in ("promo", "drawing", "content"):
            response = client.get("/studio?tool=" + tool)
            assert response.status_code == 303
            assert response.headers["location"] == "/login?tool=" + tool
        assert client.get("/studio?tool=https://evil.example").headers["location"] == "/login"
        for path in (
            "/api/state",
            "/api/account",
            "/api/assets/private",
            "/api/jobs/private/export",
        ):
            assert client.get(path).status_code == 401
        user = app.state.accounts.create("studio", "offline-password-only", owner=True)
        client.cookies.set("studio_session", app.state.accounts.issue(user))
        assert client.get("/login?tool=content").headers["location"] == "/studio?tool=content"
        assert client.get("/studio?tool=content").status_code == 200
        assert client.get("/api/account").json()["quota"]["limit"] is None


def test_public_media_range_and_upcoming_release_links(tmp_path):
    with TestClient(create_app(tmp_path, auth_enabled=True), base_url="http://localhost") as client:
        for project in PROJECTS:
            for filename, _ in project["images"]:
                response = client.get("/static/portfolio/" + filename)
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("image/")
                assert response.headers["cache-control"] == "public, max-age=86400"
        video = client.get("/static/portfolio/flow-demo.mp4", headers={"Range": "bytes=0-1023"})
        assert video.status_code == 206
        assert len(video.content) == 1024
        assert video.headers["content-type"] == "video/mp4"
        for slug in ("flow", "seek"):
            page = client.get("/projects/" + slug).text
            assert "上架中" in page
            assert '.apk"' not in page
        assert 'preload="none"' in client.get("/projects/flow").text
        sitemap = client.get("/sitemap.xml").text
        assert "/studio<" not in sitemap
        assert "/api/" not in sitemap
        assert "/tools<" not in sitemap
