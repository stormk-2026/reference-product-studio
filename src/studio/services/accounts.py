"""Server-side accounts and revocable sessions; credentials never enter workflow records."""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from threading import BoundedSemaphore

_password_slots = BoundedSemaphore(2)


class AuthError(ValueError):
    pass


class RateLimitError(AuthError):
    pass


def password_hash(password):
    salt = secrets.token_hex(16)
    with _password_slots:
        key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return salt + ":" + key.hex()


def password_matches(password, encoded):
    salt, expected = encoded.split(":")
    with _password_slots:
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return hmac.compare_digest(actual.hex(), expected)


def validate_credentials(username, password):
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
        raise AuthError("用户名须为 3–32 位小写字母、数字或下划线")
    if not 10 <= len(password) <= 128:
        raise AuthError("密码须为 10–128 个字符")
    return username


class Accounts:
    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "accounts.db"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, owner INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS single_owner ON users(owner) WHERE owner=1;
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (scope TEXT, occurred_at REAL);
                CREATE INDEX IF NOT EXISTS attempts_scope ON attempts(scope, occurred_at);
            """)
            from studio.services.email_registration import initialize_schema

            initialize_schema(db)
        self.path.chmod(0o600)
        self.dummy_hash = password_hash(secrets.token_urlsafe(24))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def throttle(self, scope, limit, period):
        self.throttle_many([(scope, limit, period)])

    def throttle_many(self, limits):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempts WHERE occurred_at < ?", (time.time() - 86400,))
            for scope, limit, period in limits:
                count = db.execute(
                    "SELECT count(*) FROM attempts WHERE scope=? AND occurred_at>?",
                    (scope, time.time() - period),
                ).fetchone()[0]
                if count >= limit:
                    raise RateLimitError("操作过于频繁，请稍后再试")
            db.executemany(
                "INSERT INTO attempts VALUES (?,?)",
                [(scope, time.time()) for scope, _, _ in limits],
            )

    def reserve_provider_call(self, user_id, job_id, limit):
        from studio.repositories.store import QuotaError

        day = int((time.time() + 8 * 3600) // 86400)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT job_id FROM provider_calls WHERE job_id=?", (job_id,)).fetchone():
                return False
            count = db.execute(
                "SELECT count(*) FROM provider_calls WHERE day=?", (day,)
            ).fetchone()[0]
            if count >= limit:
                raise QuotaError("今日全站公共体验调用额度已用完，请明天再试；本次未调用模型")
            db.execute(
                "INSERT INTO provider_calls VALUES (?,?,?,?)", (job_id, user_id, day, time.time())
            )
        return True

    def users(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT id,username,owner FROM users ORDER BY created_at")
            ]

    def create(self, username, password, *, owner=False):
        username = validate_credentials(username, password)
        if not owner and (username == "studio" or not any(u["owner"] for u in self.users())):
            raise AuthError("暂不能注册此账号")
        encoded = password_hash(password)
        user = dict(id=secrets.token_hex(16), username=username, owner=int(owner))
        try:
            with self.connect() as db:
                db.execute(
                    "INSERT INTO users(id,username,password_hash,owner,created_at) VALUES (?,?,?,?,?)",
                    (user["id"], username, encoded, user["owner"], time.time()),
                )
        except sqlite3.IntegrityError:
            raise AuthError("用户名不可用") from None
        return user

    def login(self, username, password):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE username=?", (username.strip().lower(),)
            ).fetchone()
        valid = password_matches(password, row["password_hash"] if row else self.dummy_hash)
        if not row or not valid or (not row["owner"] and not row["email_verified_at"]):
            raise AuthError("用户名或密码不正确")
        return {k: row[k] for k in ("id", "username", "owner")}

    def issue(self, user):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), user["id"], time.time() + 7 * 86400),
            )
        return token

    def resolve(self, token):
        if not token or len(token) > 100:
            return None
        with self.connect() as db:
            row = db.execute(
                """SELECT u.id,u.username,u.owner FROM users u JOIN sessions s
                                ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?
                                AND (u.owner=1 OR u.email_verified_at IS NOT NULL)""",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )

    def reset_password(self, username, password):
        if "@" in username:
            from studio.services.email_registration import normalize_email

            username = normalize_email(username)
            if not 10 <= len(password) <= 128:
                raise AuthError("密码须为 10–128 个字符")
        else:
            username = validate_credentials(username, password)
        encoded = password_hash(password)
        with self.connect() as db:
            user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not user:
                raise AuthError("账号不存在")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))

    def user_root(self, user):
        # IDs are exclusively server-generated, never accepted as directory names from clients.
        if not re.fullmatch(r"[a-f0-9]{32}", user["id"]):
            raise AuthError("无效账号")
        return self.root if user["owner"] else self.root / "users" / user["id"]
