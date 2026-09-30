"""The first approved AI page anchors a bounded, idempotent paid carousel batch."""

from studio.domain.models import Request
from studio.repositories.db import candidates, jobs


def series_plan(workflow, candidate_id):
    candidate = workflow.get(candidates, candidate_id)
    job = workflow.get(jobs, candidate["job_id"])
    first = Request.model_validate(job["payload"]["request"])
    if (
        job["state"] != "succeeded"
        or candidate["fixture"]
        or first.mode != "CONTENT_SCENE"
        or first.content_page_index != 0
    ):
        raise ValueError("请选择已完成的 Seedream 首页样张")
    plans = []
    for index in range(1, first.content_brief.page_count):
        request = first.model_copy(
            update={"content_page_index": index, "anchor_candidate_id": candidate_id}
        )
        plans.append(workflow.prepare(request))
    return {"candidate_id": candidate_id, "plans": plans, "max_calls": len(plans)}


def preview_series(workflow, candidate_id):
    plan = series_plan(workflow, candidate_id)
    return {**plan, "confirmation_token": workflow.approvals.issue(plan)}


def submit_series(workflow, candidate_id, token):
    plan = series_plan(workflow, candidate_id)
    workflow.approvals.verify(token, plan)
    results = []
    for index, payload in enumerate(plan["plans"], 1):
        payload["external_authorized"] = True
        results.append(workflow.store.enqueue(f"content-series-{candidate_id}-{index}", payload))
    return results


def series_status(workflow, candidate_id):
    plan = series_plan(workflow, candidate_id)
    tasks = []
    all_jobs = workflow.list(jobs, 10000)
    for index in range(1, len(plan["plans"]) + 1):
        key = f"content-series-{candidate_id}-{index}"
        job = next((item for item in all_jobs if item["idempotency_key"] == key), None)
        detail = workflow.detail(job["id"]) if job else None
        tasks.append(
            {
                "index": index,
                "job_id": job["id"] if job else None,
                "state": job["state"] if job else "not_started",
                "error": job["error"] if job else None,
                "asset_id": detail["candidate"]["asset_id"]
                if detail and detail["candidate"]
                else None,
            }
        )
    first = workflow.get(candidates, candidate_id)
    return {
        "candidate_id": candidate_id,
        "first_asset_id": first["asset_id"],
        "deck": first["data"]["deck"],
        "tasks": tasks,
        "complete": all(t["state"] == "succeeded" for t in tasks),
    }
