"""Verified email signup. Fail closed without configured delivery; codes are never logged."""

import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr

from studio.services.accounts import AuthError, password_hash, password_matches


class MailUnavailable(AuthError):
    pass


def normalize_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+", value):
        raise AuthError("请输入有效邮箱地址")
    local, domain = value.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        raise AuthError("请输入有效邮箱地址")
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in labels
    ):
        raise AuthError("请输入有效邮箱地址")
    return value


def email_key(email):
    local, domain = email.split("@")
    if domain in {"gmail.com", "googlemail.com"}:
        return local.split("+")[0].replace(".", "") + "@gmail.com"
    return email


def initialize_schema(db):
    db.execute("BEGIN IMMEDIATE")
    columns = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    for name, kind in [("email", "TEXT"), ("email_key", "TEXT"), ("email_verified_at", "REAL")]:
        if name not in columns:
            db.execute(f"ALTER TABLE users ADD COLUMN {name} {kind}")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS unique_email ON users(email_key) WHERE email_key IS NOT NULL"
    )
    db.execute("""CREATE TABLE IF NOT EXISTS email_codes (
        id TEXT PRIMARY KEY, email TEXT NOT NULL, email_key TEXT NOT NULL,
        code_hash TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, used INTEGER NOT NULL DEFAULT 0,
        sent INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS provider_calls (
        job_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, day INTEGER NOT NULL,
        created_at REAL NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS provider_call_day ON provider_calls(day)")


class SMTPMailer:
    def __init__(self):
        self.host = os.environ.get("STUDIO_SMTP_HOST", "")
        try:
            self.port = int(os.environ.get("STUDIO_SMTP_PORT") or "465")
        except ValueError:
            self.port = 0
        self.username = os.environ.get("STUDIO_SMTP_USERNAME", "")
        self.password = os.environ.get("STUDIO_SMTP_PASSWORD", "")
        self.sender = os.environ.get("STUDIO_SMTP_FROM", "")
        self.ready = bool(
            self.host
            and self.username
            and self.password
            and self.sender
            and self.port in {465, 587}
        )

    def send(self, recipient, code):
        if not self.ready:
            raise MailUnavailable("邮件服务尚未配置，暂未开放注册")
        message = EmailMessage()
        message["From"] = formataddr(("Storm Studio", normalize_email(self.sender)))
        message["To"] = normalize_email(recipient)
        message["Subject"] = "Storm Studio 邮箱注册验证码"
        message.set_content(
            f"你的注册验证码为：{code}\n\n10 分钟内有效，请勿转发。\n如果不是你本人操作，请忽略此邮件。"
        )
        try:
            if self.port == 465:
                connection = smtplib.SMTP_SSL(
                    self.host, self.port, timeout=10, context=ssl.create_default_context()
                )
            else:
                connection = smtplib.SMTP(self.host, self.port, timeout=10)
            with connection as client:
                if self.port == 587:
                    client.starttls(context=ssl.create_default_context())
                client.login(self.username, self.password)
                client.send_message(message)
        except Exception:
            raise MailUnavailable("验证码发送未确认，请稍后再试；未自动重发") from None


class EmailRegistration:
    def __init__(self, accounts, mailer, enabled):
        self.accounts, self.mailer = accounts, mailer
        self.enabled = bool(enabled and mailer.ready)

    def require_enabled(self):
        if not self.enabled:
            raise MailUnavailable("邮箱注册暂未开放；已有主账户可以正常登录")

    def send_code(self, value, peer):
        self.require_enabled()
        email = normalize_email(value)
        key = email_key(email)
        self.accounts.throttle_many(
            [
                ("mail-global", 50, 86400),
                ("mail-ip-hour:" + peer, 3, 3600),
                ("mail-ip-day:" + peer, 10, 86400),
                ("mail-email-minute:" + key, 1, 60),
                ("mail-email-day:" + key, 3, 86400),
            ]
        )
        challenge = secrets.token_urlsafe(24)
        code = f"{secrets.randbelow(1000000):06d}"
        encoded = password_hash(code)
        with self.accounts.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute("SELECT id FROM users WHERE email_key=?", (key,)).fetchone()
            if exists:
                return challenge  # Same response for used addresses; no mail or valid challenge.
            db.execute("DELETE FROM email_codes WHERE created_at < ?", (time.time() - 86400,))
            db.execute("UPDATE email_codes SET used=1 WHERE email_key=?", (key,))
            db.execute(
                """INSERT INTO email_codes(id,email,email_key,code_hash,created_at,expires_at)
                          VALUES (?,?,?,?,?,?)""",
                (challenge, email, key, encoded, time.time(), time.time() + 600),
            )
        try:
            self.mailer.send(email, code)
        except Exception:
            with self.accounts.connect() as db:
                db.execute("UPDATE email_codes SET used=1 WHERE id=?", (challenge,))
            raise MailUnavailable("验证码发送未确认，请稍后再试；未自动重发") from None
        with self.accounts.connect() as db:
            db.execute("UPDATE email_codes SET sent=1 WHERE id=?", (challenge,))
        return challenge

    def register(self, value, password, challenge, code, peer):
        self.require_enabled()
        email = normalize_email(value)
        if not 10 <= len(password) <= 128:
            raise AuthError("密码须为 10–128 个字符")
        self.accounts.throttle_many([("verify-ip:" + peer, 15, 900)])
        user = None
        with self.accounts.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM email_codes WHERE id=? AND email=?", (challenge, email)
            ).fetchone()
            valid = bool(
                row
                and row["sent"]
                and not row["used"]
                and row["expires_at"] > time.time()
                and row["attempts"] < 5
            )
            if valid:
                db.execute("UPDATE email_codes SET attempts=attempts+1 WHERE id=?", (challenge,))
                valid = password_matches(code, row["code_hash"])
            if valid:
                key = email_key(email)
                exists = db.execute(
                    "SELECT id FROM users WHERE email_key=? OR username=?", (key, email)
                ).fetchone()
                recent = db.execute(
                    "SELECT count(*) FROM attempts WHERE scope=? AND occurred_at>?",
                    ("registered-ip:" + peer, time.time() - 86400),
                ).fetchone()[0]
                has_owner = db.execute("SELECT id FROM users WHERE owner=1").fetchone()
                if not exists and recent < 3 and has_owner:
                    user = {"id": secrets.token_hex(16), "username": email, "owner": 0}
                    db.execute(
                        """INSERT INTO users(id,username,password_hash,owner,created_at,email,email_key,email_verified_at)
                                  VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            user["id"],
                            email,
                            password_hash(password),
                            0,
                            time.time(),
                            email,
                            key,
                            time.time(),
                        ),
                    )
                    db.execute("UPDATE email_codes SET used=1 WHERE id=?", (challenge,))
                    db.execute(
                        "INSERT INTO attempts VALUES (?,?)", ("registered-ip:" + peer, time.time())
                    )
        if not user:
            raise AuthError("邮箱或验证码无效、已使用或已达注册限制，请检查后重试")
        return user
