import argparse
import fcntl
import time

from studio.config import data_dir
from studio.domain.canvas import canvas_size
from studio.domain.models import FIXTURE_WARNING, PATTERN_WARNING, Request
from studio.domain.rules import back_label
from studio.providers.domestic import ProviderError
from studio.repositories.db import analyses, candidates, engine_for, identifier, jobs, now, recipes
from studio.services.composite import composite
from studio.services.real_jobs import run_real
from studio.services.workflow import Workflow


def recover(workflow):
    workflow.store.recover()


def claim(workflow):
    return workflow.store.claim()


def run_once(workflow):
    job = claim(workflow)
    if not job:
        return False
    request = Request.model_validate(job["payload"]["request"])
    started = time.monotonic()
    try:
        if request.mode == "CUTOUT":
            from studio.services.cutout import run_cutout

            run_cutout(workflow, job)
            return True
        if request.execution == "real":
            run_real(workflow, job)
            return True
        workflow.store.update(jobs, job["id"], {"phase": "dispatching"})
        record = None
        table = None
        if request.mode == "A":
            table = analyses
            record = dict(
                id=identifier(),
                job_id=job["id"],
                data=workflow.provider.analyze(
                    request.product_ids, request.instructions
                ).model_dump(),
                version=1,
                created_at=now(),
                fixture=True,
                input_ids=request.product_ids,
            )
        elif request.mode == "C_analyze":
            table = recipes
            record = dict(
                id=identifier(),
                job_id=job["id"],
                data=workflow.provider.recipe(request.preserve).model_dump(),
                version=1,
                created_at=now(),
                fixture=True,
                reference_id=request.reference_id,
            )
        else:
            size = canvas_size(request.ratio, fixture=True)
            label = back_label(bool(request.back_id)) if request.mode == "A_back" else request.mode
            image = workflow.provider.render(request.mode, size, request.background, label)
            transforms = []
            if request.mode == "B1":
                mask = workflow.image(request.mask_id) if request.mask_id else None
                image, transforms = composite(
                    workflow.image(request.product_ids[0]), image, request, mask
                )
            elif request.mode in {"B2", "C1", "C2"}:
                transforms = ["固定 Fixture 场景；未执行真实重绘、参考迁移或细节保真"]
            asset = workflow.store_image(image, FIXTURE_WARNING, True)
            data = dict(
                feature=request.mode[0],
                mode=request.mode,
                input_ids=job["payload"]["input_ids"],
                analysis=job["payload"]["analysis"],
                recipe=job["payload"]["recipe"],
                request=request.model_dump(),
                prompt=job["payload"]["prompt"],
                provider="fixture",
                model=workflow.provider.model,
                template_version="studio-v1",
                seed=None,
                provider_request_id=None,
                provider_task_id=None,
                created_at=now(),
                duration_seconds=time.monotonic() - started,
                usage=None,
                cost_estimate=None,
                cost_basis="unknown；Fixture 无外部模型调用",
                fixture=True,
                warning=PATTERN_WARNING if request.mode == "A_pattern" else FIXTURE_WARNING,
                label=label,
                transformations=transforms,
                recipient="本地 Fixture，不外发",
                sent_asset_ids=[],
            )
            table = candidates
            record = dict(
                id=identifier(),
                job_id=job["id"],
                asset_id=asset["id"],
                data=data,
                created_at=now(),
                favorite=False,
                fixture=True,
            )
        workflow.store.complete(job["id"], table, record)
    except Exception as exc:
        # Do not log raw provider responses, credentials or signed URLs.
        state = (
            exc.state
            if isinstance(exc, ProviderError)
            else (
                "outcome_unknown"
                if request.execution == "real" or isinstance(exc, (TimeoutError, ConnectionError))
                else "failed"
            )
        )
        message = (
            str(exc)
            if isinstance(exc, ProviderError)
            or (request.execution == "fixture" and isinstance(exc, ValueError))
            else f"{type(exc).__name__}；结果未确认，请查看本地任务并人工核查"
        )
        workflow.store.update(
            jobs, job["id"], {"state": state, "error": message, "finished_at": now()}
        )
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    root = data_dir()
    workflow = Workflow(engine_for(root), root)
    with (root / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("已有 Worker 在运行")
        recover(workflow)
        print(
            "Worker 已启动；Fixture 默认。真实调用仅执行已确认的单次任务，无自动重试。", flush=True
        )
        while True:
            worked = run_once(workflow)
            if args.once:
                return
            if not worked:
                time.sleep(0.5)


if __name__ == "__main__":
    main()
