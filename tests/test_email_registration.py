import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from studio.domain.models import Request
from studio.repositories.db import assets, jobs
from studio.repositories.store import QuotaError
from studio.services.accounts import Accounts, AuthError, RateLimitError, password_hash
from studio.services.email_registration import (
    EmailRegistration,
    MailUnavailable,
    SMTPMailer,
    email_key,
    normalize_email,
)
from studio.services.tenants import Tenants
from studio.web.app import create_app
from studio.worker import run_once

PASSWORD = "email-offline-test-password"
BASE = "https://stormstudio.top"


class Mailer:
    ready = True

    def __init__(self):
        self.sent = []

    def send(self, email, code):
        self.sent.append((email, code))


@pytest.fixture
def registration(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.create("studio", PASSWORD, owner=True)
    return EmailRegistration(accounts, Mailer(), True)


def test_email_ownership_single_use_and_canonical_aliases(registration):
    service = registration
    challenge = service.send_code("Owner.Test+one@gmail.com", "one-ip")
    email, code = service.mailer.sent[-1]
    assert email == "owner.test+one@gmail.com"
    assert email_key(email) == email_key("ownertest+two@googlemail.com")
    with service.accounts.connect() as db:
        assert code not in db.execute("SELECT code_hash FROM email_codes").fetchone()[0]
    with pytest.raises(AuthError):
        service.register("someoneelse@example.org", PASSWORD, challenge, code, "one-ip")
    user = service.register(email, PASSWORD, challenge, code, "one-ip")
    assert service.accounts.login(email.upper(), PASSWORD)["id"] == user["id"]
    with pytest.raises(AuthError):
        service.register(email, PASSWORD, challenge, code, "one-ip")
    service.accounts.reset_password(email, "changed-offline-password")
    assert service.accounts.login(email, "changed-offline-password")["id"] == user["id"]


def test_wrong_attempts_persist_and_expired_codes_are_rejected(registration):
    s = registration
    challenge = s.send_code("first@example.org", "peer")
    actual = s.mailer.sent[-1][1]
    wrong = "999999" if actual != "999999" else "000000"
    for _ in range(5):
        with pytest.raises(AuthError):
            s.register("first@example.org", PASSWORD, challenge, wrong, "peer")
    with s.accounts.connect() as db:
        assert (
            db.execute("SELECT attempts FROM email_codes WHERE id=?", (challenge,)).fetchone()[0]
            == 5
        )
    with pytest.raises(AuthError):
        s.register("first@example.org", PASSWORD, challenge, actual, "peer")
    second = s.send_code("second@example.org", "peer")
    with s.accounts.connect() as db:
        db.execute("UPDATE email_codes SET expires_at=0 WHERE id=?", (second,))
    with pytest.raises(AuthError):
        s.register("second@example.org", PASSWORD, second, s.mailer.sent[-1][1], "peer")
    assert len(s.accounts.users()) == 1


def test_resend_rate_and_mail_failure_fail_closed(registration):
    s = registration
    s.send_code("test@example.org", "peer")
    with pytest.raises(RateLimitError):
        s.send_code("TEST@example.org", "different-ip")
    assert len(s.mailer.sent) == 1

    def fail(email, code):
        raise RuntimeError("private-provider-response")

    s.mailer.send = fail
    with pytest.raises(MailUnavailable) as error:
        s.send_code("another@example.org", "peer")
    assert "private-provider-response" not in str(error)
    with s.accounts.connect() as db:
        row = db.execute(
            "SELECT * FROM email_codes WHERE email=?", ("another@example.org",)
        ).fetchone()
        assert row["used"] and not row["sent"]
    s.enabled = False
    with pytest.raises(MailUnavailable):
        s.send_code("more@example.org", "peer")


def test_concurrent_verified_registration_only_creates_one_account(registration):
    s = registration
    challenge = s.send_code("single@example.org", "peer")
    code = s.mailer.sent[-1][1]

    def register(_):
        try:
            return s.register("single@example.org", PASSWORD, challenge, code, "peer")
        except AuthError:
            return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(register, range(5)))
    assert sum(r is not None for r in results) == 1
    assert len(s.accounts.users()) == 2


def test_email_input_rejects_header_injection():
    for value in ["a@x", "a\r\nBcc:other@example.org", "a..b@example.org", "a@-example.org"]:
        with pytest.raises(AuthError):
            normalize_email(value)


def test_old_database_migration_preserves_owner(tmp_path):
    path = tmp_path / "accounts.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT UNIQUE,password_hash TEXT,owner INTEGER,created_at REAL)"
        )
        db.execute(
            "INSERT INTO users VALUES (?,?,?,?,?)",
            ("a" * 32, "studio", password_hash(PASSWORD), 1, time.time()),
        )
    accounts = Accounts(tmp_path)
    assert accounts.login("studio", PASSWORD)["id"] == "a" * 32
    legacy = accounts.create("legacyuser", PASSWORD)
    with pytest.raises(AuthError):
        accounts.login("legacyuser", PASSWORD)
    assert accounts.resolve(accounts.issue(legacy)) is None


def test_global_public_budget_concurrent_and_worker_prevents_provider_call(tmp_path, monkeypatch):
    accounts = Accounts(tmp_path)
    accounts.create("studio", PASSWORD, owner=True)

    def reserve(i):
        try:
            return accounts.reserve_provider_call("user" + str(i), "job" + str(i), 3)
        except QuotaError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(12))) == 3
    with accounts.connect() as db:
        previous = db.execute("SELECT job_id FROM provider_calls LIMIT 1").fetchone()[0]
    assert accounts.reserve_provider_call("someone", previous, 3) is False
    user = accounts.create("worker_user", PASSWORD)
    wf = Tenants(accounts).workflow(user)
    monkeypatch.setenv("STUDIO_PUBLIC_DAILY_CALL_LIMIT", "3")
    request = Request(mode="A_white", product_ids=["dummy"], execution="real")
    job = wf.store.enqueue("must-not-call", {"request": request.model_dump()})

    def forbidden(*args):
        raise AssertionError("provider must not be invoked")

    monkeypatch.setattr("studio.worker.run_real", forbidden)
    assert run_once(wf)
    result = wf.get(jobs, job["id"])
    assert result["state"] == "failed"
    assert "未调用模型" in result["error"]
    assert wf.store.quota()["remaining"] == 3
    assert wf.list(assets) == []


def test_api_registration_closed_without_mail_and_rate_limits(tmp_path):
    app = create_app(tmp_path, auth_enabled=True)
    app.state.accounts.create("studio", PASSWORD, owner=True)
    client = TestClient(app, base_url=BASE)
    csrf = client.get("/api/session").json()["csrf"]
    client.headers.update({"origin": BASE, "x-csrf-token": csrf})
    assert client.get("/api/auth/options").json()["email_registration"] is False
    assert client.post("/api/auth/send-code", json={"email": "one@example.org"}).status_code == 503
    assert (
        client.post(
            "/api/auth/register", json={"username": "old", "password": PASSWORD}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/auth/register",
            json={
                "email": "one@example.org",
                "password": PASSWORD,
                "challenge_id": "x" * 32,
                "code": "123456",
            },
        ).status_code
        == 503
    )
    assert (
        client.post(
            "/api/auth/login", json={"username": "studio", "password": PASSWORD}
        ).status_code
        == 200
    )
    for _ in range(4):
        assert client.post("/api/jobs", json={}).status_code == 422
    blocked = client.post("/api/jobs", json={})
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"


def test_smtp_requires_encrypted_port(monkeypatch):
    for key in ["HOST", "USERNAME", "PASSWORD", "FROM"]:
        monkeypatch.setenv("STUDIO_SMTP_" + key, "placeholder")
    monkeypatch.setenv("STUDIO_SMTP_PORT", "25")
    assert not SMTPMailer().ready
