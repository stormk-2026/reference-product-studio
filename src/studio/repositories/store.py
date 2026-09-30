from sqlalchemy import select

from studio.domain.rules import recovery_state
from studio.repositories.db import identifier, jobs, now, row

IMAGE_MODES = {"A_white", "A_views", "B2", "CONTENT_SCENE"}


class QuotaError(ValueError):
    pass


class Store:
    def __init__(self, engine):
        self.engine = engine
        self.quota_limit = None

    def get(self, table, resource_id):
        with self.engine.connect() as conn:
            result = row(conn, table, resource_id)
            if result is None:
                raise ValueError("找不到指定资源")
            return dict(result)

    def list(self, table, limit=100):
        with self.engine.connect() as conn:
            return [
                dict(item)
                for item in conn.execute(
                    select(table).order_by(table.c.created_at.desc()).limit(limit)
                ).mappings()
            ]

    def insert(self, table, item):
        with self.engine.begin() as conn:
            conn.execute(table.insert().values(**item))
        return item

    def update(self, table, resource_id, values):
        self.get(table, resource_id)
        with self.engine.begin() as conn:
            conn.execute(table.update().where(table.c.id == resource_id).values(**values))
        return self.get(table, resource_id)

    def quota(self):
        with self.engine.connect() as conn:
            return self._quota(conn)

    def _quota(self, conn):
        used = sum(
            1
            for job in conn.execute(select(jobs)).mappings()
            if job["payload"].get("request", {}).get("mode") in IMAGE_MODES
            and job["payload"].get("request", {}).get("execution") == "real"
            and job["state"] not in {"failed", "cancelled"}
        )
        return {
            "limit": self.quota_limit,
            "used": used,
            "remaining": None if self.quota_limit is None else max(0, self.quota_limit - used),
        }

    def enqueue(self, key, payload):
        return self.enqueue_many([(key, payload)])[0]

    def enqueue_many(self, entries):
        # Lock before checking both quotas and idempotency. Entire batches commit or roll back.
        results = []
        with self.engine.begin() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            for key, payload in entries:
                found = (
                    conn.execute(select(jobs).where(jobs.c.idempotency_key == key))
                    .mappings()
                    .first()
                )
                if found:
                    if any(
                        found["payload"].get(k) != payload.get(k)
                        for k in (
                            "request",
                            "prompt",
                            "model",
                            "provider",
                            "sent_assets",
                            "analysis",
                            "recipe",
                            "anchor_asset_id",
                        )
                    ):
                        raise ValueError("幂等键已用于不同输入，请创建新任务")
                    results.append(dict(found))
                    continue
                if self.quota_limit is not None:
                    recent = conn.execute(
                        select(jobs.c.id).where(jobs.c.created_at > now() - 86400)
                    ).all()
                    if len(recent) >= 20:
                        raise QuotaError("今日任务次数已达上限，请明天再试")
                    request = payload.get("request", {})
                    if request.get("mode") in IMAGE_MODES and request.get("execution") == "real":
                        if self._quota(conn)["remaining"] < 1:
                            raise QuotaError(
                                "图片生成额度不足；新账号共 3 次，批量每张计 1 次。未提交本批任务。"
                            )
                item = dict(
                    id=identifier(),
                    idempotency_key=key,
                    payload=payload,
                    state="queued",
                    phase="queued",
                    created_at=now(),
                )
                conn.execute(jobs.insert().values(**item))
                results.append(dict(row(conn, jobs, item["id"])))
        return results

    def for_job(self, table, job_id):
        with self.engine.connect() as conn:
            item = (
                conn.execute(
                    select(table)
                    .where(table.c.job_id == job_id)
                    .order_by(table.c.created_at.desc())
                )
                .mappings()
                .first()
            )
            return dict(item) if item else None

    def revise(self, table, resource_id, value, version):
        with self.engine.begin() as conn:
            # SQLite serializes this short revision transaction; acquire write lock before read.
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            original = row(conn, table, resource_id)
            if not original:
                raise ValueError("找不到原版本")
            latest = (
                conn.execute(
                    select(table)
                    .where(table.c.job_id == original["job_id"])
                    .order_by(table.c.version.desc())
                )
                .mappings()
                .first()
            )
            if latest["id"] != resource_id or int(original["version"]) != version:
                raise ValueError("内容已有新版本，请刷新后编辑")
            item = dict(original)
            item.update(id=identifier(), data=value, version=version + 1, created_at=now())
            conn.execute(table.insert().values(**item))
        return item

    def recover(self):
        # Caller holds OS worker lock; do not preempt a live worker.
        with self.engine.begin() as conn:
            for job in conn.execute(select(jobs).where(jobs.c.state == "running")).mappings().all():
                conn.execute(
                    jobs.update()
                    .where(jobs.c.id == job["id"])
                    .values(
                        state=recovery_state(job["phase"]),
                        error="Worker 中断；未自动重试。未知结果需人工核查。",
                        finished_at=now(),
                    )
                )

    def claim(self):
        with self.engine.begin() as conn:
            job_id = conn.execute(
                select(jobs.c.id)
                .where(jobs.c.state == "queued")
                .order_by(jobs.c.created_at)
                .limit(1)
            ).scalar()
            if not job_id:
                return None
            changed = conn.execute(
                jobs.update()
                .where(jobs.c.id == job_id, jobs.c.state == "queued")
                .values(
                    state="running",
                    phase="claimed",
                    worker_id=identifier(),
                    lease_until=now() + 300,
                    started_at=now(),
                )
            )
            if changed.rowcount != 1:
                return None
        return self.get(jobs, job_id)

    def complete(self, job_id, table, record):
        with self.engine.begin() as conn:
            conn.execute(table.insert().values(**record))
            conn.execute(
                jobs.update()
                .where(jobs.c.id == job_id)
                .values(state="succeeded", phase="stored", finished_at=now())
            )
