"""Each account gets a separate workflow DB, local asset directory and approval signer."""

import fcntl
from collections import OrderedDict
from contextvars import ContextVar
from threading import RLock

from studio.repositories.db import engine_for, metadata
from studio.services.workflow import Workflow

current_workflow = ContextVar("current_workflow")


class WorkflowProxy:
    def __getattr__(self, name):
        return getattr(current_workflow.get(), name)


class Tenants:
    def __init__(self, accounts):
        self.accounts = accounts
        self.cache = OrderedDict()
        self.lock = RLock()

    def workflow(self, user):
        with self.lock:
            if user["id"] not in self.cache:
                root = self.accounts.user_root(user)
                engine = engine_for(root)
                with (root / "schema.lock").open("a") as schema_lock:
                    fcntl.flock(schema_lock, fcntl.LOCK_EX)
                    metadata.create_all(engine)
                workflow = Workflow(engine, root)
                workflow.store.quota_limit = None if user["owner"] else 3
                self.cache[user["id"]] = workflow
                if len(self.cache) > 128:
                    _, old = self.cache.popitem(last=False)
                    old.engine.dispose()
            self.cache.move_to_end(user["id"])
            return self.cache[user["id"]]
