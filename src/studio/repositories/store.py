from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from studio.domain.rules import recovery_state
from studio.repositories.db import identifier, jobs, now, row


class Store:
    def __init__(self, engine):
        self.engine = engine

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

    def enqueue(self, key, payload):
        def existing():
            with self.engine.connect() as conn:
                result = (
                    conn.execute(select(jobs).where(jobs.c.idempotency_key == key))
                    .mappings()
                    .first()
                )
                if result and any(
                    result["payload"].get(k) != payload.get(k)
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
                return dict(result) if result else None

        found = existing()
        if found:
            return found
        item = dict(
            id=identifier(),
            idempotency_key=key,
            payload=payload,
            state="queued",
            phase="queued",
            created_at=now(),
        )
        try:
            self.insert(jobs, item)
        except IntegrityError:
            found = existing()
            if not found:
                raise
            return found
        return self.get(jobs, item["id"])

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
