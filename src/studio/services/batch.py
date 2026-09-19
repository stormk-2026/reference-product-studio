"""An approved candidate is the durable batch style anchor; no automatic paid retries."""

from studio.domain.models import Request
from studio.repositories.db import candidates, jobs


def remaining_plan(workflow, candidate_id):
    candidate = workflow.get(candidates, candidate_id)
    job = workflow.get(jobs, candidate["job_id"])
    request = Request.model_validate(job["payload"]["request"])
    if (
        job["state"] != "succeeded"
        or request.mode != "B2"
        or request.batch_index != 0
        or len(request.batch_product_ids) < 2
    ):
        raise ValueError("请选择已完成的批量首张作为通过样张")
    plans = []
    for index, asset_id in enumerate(request.batch_product_ids[1:], 1):
        value = request.model_copy(
            update={
                "product_ids": [asset_id],
                "batch_index": index,
                "anchor_candidate_id": candidate_id,
            }
        )
        plans.append(workflow.prepare(value))
    return {
        "candidate_id": candidate_id,
        "plans": plans,
        "max_calls": len(plans) if request.execution == "real" else 0,
    }


def preview_remaining(workflow, candidate_id):
    plan = remaining_plan(workflow, candidate_id)
    return {**plan, "confirmation_token": workflow.approvals.issue(plan)}


def submit_remaining(workflow, candidate_id, token):
    plan = remaining_plan(workflow, candidate_id)
    workflow.approvals.verify(token, plan)
    results = []
    for index, payload in enumerate(plan["plans"], 1):
        payload["external_authorized"] = payload["request"]["execution"] == "real"
        # Stable across fresh previews/reloads. Never resubmit failed or unknown jobs.
        results.append(workflow.store.enqueue(f"batch-{candidate_id}-{index}", payload))
    return results
