import io
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from studio.repositories.db import assets, jobs
from studio.repositories.store import QuotaError
from studio.services.accounts import Accounts, AuthError
from studio.services.tenants import Tenants
from studio.web.app import create_app

PASSWORD = "offline-test-password-only"
BASE = "https://stormstudio.top"


class FakeMailer:
    ready = True

    def __init__(self):
        self.codes = {}

    def send(self, email, code):
        self.codes[email] = code


def sign_in(app, username, register=True):
    client = TestClient(app, base_url=BASE)
    csrf = client.get("/api/session").json()["csrf"]
    client.headers.update({"origin": BASE, "x-csrf-token": csrf})
    if register:
        email = username + "@example.org"
        challenge = client.post("/api/auth/send-code", json={"email": email}).json()["challenge_id"]
        response = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "challenge_id": challenge,
                "code": app.state.registration.mailer.codes[email],
            },
        )
    else:
        response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def app(tmp_path):
    application = create_app(
        tmp_path, auth_enabled=True, mailer=FakeMailer(), registration_enabled=True
    )
    application.state.accounts.create("studio", PASSWORD, owner=True)
    return application


def test_auth_protects_all_data_and_real_upload(app):
    anonymous = TestClient(app, base_url=BASE)
    for path in [
        "/api/state",
        "/api/account",
        "/api/jobs/anything",
        "/api/assets/anything",
        "/api/jobs/anything/export",
        "/api/content/series/anything/export",
    ]:
        assert anonymous.get(path).status_code == 401
    assert anonymous.get("/").url.path == "/login"
    alice = sign_in(app, "alice")
    bob = sign_in(app, "bobby")
    owner = sign_in(app, "studio", register=False)
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(image, format="PNG")
    response = alice.post(
        "/api/assets",
        files={"file": ("a.png", image.getvalue(), "image/png")},
        data={"source": "private"},
    )
    assert response.status_code == 200
    aid = response.json()["id"]
    assert alice.get("/api/assets/" + aid).status_code == 200
    for client in [bob, owner]:
        assert client.get("/api/state").json()["assets"] == []
        assert client.get("/api/assets/" + aid).status_code == 404
        assert client.delete("/api/assets/" + aid).status_code == 400
    assert alice.get("/api/account").json()["quota"]["remaining"] == 3
    assert owner.get("/api/account").json()["quota"]["limit"] is None
    assert "httponly" in response.request.headers.get("cookie", "").lower() or alice.cookies.get(
        "studio_session"
    )
    token = alice.cookies.get("studio_session")
    assert app.state.accounts.resolve(token)["username"] == "alice@example.org"
    alice.post("/api/auth/logout")
    assert app.state.accounts.resolve(token) is None
    assert alice.get("/api/state").status_code == 401


def test_session_security_and_registration_validation(app):
    client = TestClient(app, base_url=BASE)
    token = client.get("/api/session").json()["csrf"]
    headers = {"origin": BASE, "x-csrf-token": token}
    assert (
        client.post(
            "/api/auth/register", json={"username": "alice", "password": PASSWORD}
        ).status_code
        == 403
    )
    response = client.post(
        "/api/auth/register",
        headers=headers,
        json={"username": "alice", "password": PASSWORD, "owner": True},
    )
    assert response.status_code == 422
    sent = client.post(
        "/api/auth/send-code", headers=headers, json={"email": "alice@example.org"}
    ).json()
    response = client.post(
        "/api/auth/register",
        headers=headers,
        json={
            "email": "alice@example.org",
            "password": PASSWORD,
            "challenge_id": sent["challenge_id"],
            "code": app.state.registration.mailer.codes["alice@example.org"],
        },
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    token = client.cookies.get("studio_session")
    with app.state.accounts.connect() as db:
        assert token not in str([tuple(r) for r in db.execute("select * from sessions")])
        assert PASSWORD not in str([tuple(r) for r in db.execute("select * from users")])
        db.execute("update sessions set expires_at=?", (time.time() - 1,))
    assert client.get("/api/state").status_code == 401


def test_login_errors_throttle_and_password_reset(app):
    accounts = app.state.accounts
    for username in ["studio", "absent"]:
        with pytest.raises(AuthError, match="用户名或密码不正确"):
            accounts.login(username, "wrong-password")
    accounts.throttle("test", 1, 900)
    with pytest.raises(AuthError, match="频繁"):
        accounts.throttle("test", 1, 900)
    user = accounts.login("studio", PASSWORD)
    session = accounts.issue(user)
    accounts.reset_password("studio", "new-offline-password")
    assert accounts.resolve(session) is None
    assert accounts.login("studio", "new-offline-password")["owner"]


def workflow(tmp_path, owner=False):
    accounts = Accounts(tmp_path)
    primary = accounts.create("studio", PASSWORD, owner=True)
    user = primary if owner else accounts.create("alice", PASSWORD)
    return Tenants(accounts).workflow(user)


def payload(mode="A_white"):
    return {"request": {"mode": mode, "execution": "real"}}


def test_quota_atomic_under_concurrent_requests_and_duplicate_keys(tmp_path):
    wf = workflow(tmp_path)

    def submit(index):
        try:
            return wf.store.enqueue(str(index), payload())["id"]
        except QuotaError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(submit, range(12)))
    assert len([v for v in values if v]) == 3
    assert wf.store.quota()["remaining"] == 0
    job = wf.list(jobs)[0]
    assert wf.store.enqueue(job["idempotency_key"], payload())["id"] == job["id"]
    assert len(wf.list(jobs)) == 3
    wf.store.update(jobs, job["id"], {"state": "outcome_unknown"})
    with pytest.raises(QuotaError):
        wf.store.enqueue("unknown-does-not-refund", payload())
    wf.store.update(jobs, job["id"], {"state": "failed"})
    assert wf.store.quota()["remaining"] == 1
    wf.store.enqueue("replacement", payload())
    assert wf.store.quota()["remaining"] == 0


def test_batches_rollback_and_text_free_but_rate_limited(tmp_path):
    wf = workflow(tmp_path)
    wf.store.enqueue("first", payload())
    with pytest.raises(QuotaError):
        wf.store.enqueue_many([(str(i), payload()) for i in range(3)])
    assert len(wf.list(jobs)) == 1
    assert wf.store.quota()["remaining"] == 2
    first = wf.store.enqueue_many([("second", payload()), ("third", payload())])
    assert wf.store.enqueue_many([("second", payload()), ("third", payload())]) == first
    wf.store.enqueue("copy", payload("CONTENT_COPY"))
    assert wf.store.quota()["used"] == 3
    for index in range(16):
        wf.store.enqueue("text" + str(index), payload("CONTENT_POLISH"))
    with pytest.raises(QuotaError, match="今日"):
        wf.store.enqueue("too-many", payload("CONTENT_POLISH"))


def test_owner_unlimited_and_existing_data_retained(tmp_path):
    wf = workflow(tmp_path, owner=True)
    assert wf.root == tmp_path
    for i in range(25):
        wf.store.enqueue(str(i), payload())
    assert wf.store.quota()["remaining"] is None
    assert len(wf.list(jobs)) == 25


def test_cross_account_preview_worker_outputs_and_old_routes(app):
    from studio.domain.models import Request
    from studio.worker import run_once

    owner = sign_in(app, "studio", register=False)
    alice = sign_in(app, "alice")
    users = app.state.accounts.users()
    main = app.state.tenants.workflow(next(u for u in users if u["owner"]))
    other = app.state.tenants.workflow(next(u for u in users if not u["owner"]))
    asset = main.store_image(Image.new("RGB", (32, 32)), "owner", True)
    job = main.submit(Request(mode="A_white", product_ids=[asset["id"]]), "fixture-test")
    assert run_once(main)
    candidate = main.detail(job["id"])["candidate"]
    assert owner.get("/api/jobs/" + job["id"]).status_code == 200
    assert alice.get("/api/jobs/" + job["id"]).status_code == 400
    assert alice.get("/api/assets/" + candidate["asset_id"]).status_code == 404
    assert alice.post("/api/candidates/" + candidate["id"] + "/cutout").status_code == 400
    assert alice.post("/api/batch/" + candidate["id"] + "/preview").status_code == 400
    assert alice.get("/api/jobs/" + job["id"] + "/export").status_code == 400
    assert alice.post("/api/demo").status_code == 404
    assert other.list(assets) == []
    with pytest.raises(ValueError, match="正式工具"):
        other.prepare(Request(mode="A_white", product_ids=["anything"]))
    signed = main.approvals.issue({"hello": "world"})
    with pytest.raises(ValueError):
        other.approvals.verify(signed, {"hello": "world"})


def test_multiuser_backup_preserves_accounts_and_isolated_assets(tmp_path):
    import importlib.util
    import sqlite3
    import tarfile
    from pathlib import Path

    root = tmp_path / "data"
    accounts = Accounts(root)
    owner = accounts.create("studio", PASSWORD, owner=True)
    user = accounts.create("alice", PASSWORD)
    tenants = Tenants(accounts)
    one = tenants.workflow(owner).store_image(Image.new("RGB", (8, 8), "red"), "owner", True)
    two = tenants.workflow(user).store_image(Image.new("RGB", (8, 8), "blue"), "alice", True)
    accounts.issue(owner)
    spec = importlib.util.spec_from_file_location(
        "multi_backup", Path(__file__).parents[1] / "scripts/backup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = module.backup(root, tmp_path / "backups")
    with tarfile.open(output) as archive:
        assert "accounts.db" in archive.getnames()
        assert "assets/" + one["id"] + ".png" in archive.getnames()
        assert "users/" + user["id"] + "/assets/" + two["id"] + ".png" in archive.getnames()
        snapshot = tmp_path / "accounts-copy.db"
        snapshot.write_bytes(archive.extractfile("accounts.db").read())
    with sqlite3.connect(snapshot) as db:
        assert db.execute("select count(*) from users").fetchone()[0] == 2
        assert db.execute("select count(*) from sessions").fetchone()[0] == 0
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"


def test_web_and_worker_initialize_one_tenant_concurrently(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.create("studio", PASSWORD, owner=True)
    user = accounts.create("alice", PASSWORD)

    def open_workflow(_):
        tenants = Tenants(accounts)
        wf = tenants.workflow(user)
        count = len(wf.list(jobs))
        wf.engine.dispose()
        return count

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(open_workflow, range(8))) == [0] * 8
