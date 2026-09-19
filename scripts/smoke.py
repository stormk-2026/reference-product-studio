"""Offline-provider smoke test through real localhost HTTP and a separate Worker."""

import io
import json
import time
import uuid
import zipfile

import httpx
from PIL import Image

with httpx.Client(base_url="http://127.0.0.1:8765", timeout=15) as client:
    csrf = client.get("/api/session").json()["csrf"]
    client.headers.update({"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": csrf})
    response = client.post("/api/demo")
    response.raise_for_status()
    demo = response.json()
    analysis_id = recipe_id = None
    report = []
    for mode in ["A", "A_front", "A_back", "A_pattern", "B1", "B2", "C_analyze", "C1", "C2"]:
        payload = {
            "mode": mode,
            "product_ids": [demo["product_id"]],
            "instructions": "本地 HTTP 烟测：无外发、无收费",
            "preserve": "测试要求：保留纽扣",
            "reference_id": demo["reference_id"],
            "analysis_id": analysis_id,
            "recipe_id": recipe_id,
        }
        response = client.post(
            "/api/jobs", json=payload, headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        response.raise_for_status()
        job_id = response.json()["id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            detail = client.get("/api/jobs/" + job_id).json()
            if detail["job"]["state"] not in {"queued", "running"}:
                break
            time.sleep(0.2)
        assert detail["job"]["state"] == "succeeded", detail
        if detail["analysis"]:
            analysis_id = detail["analysis"]["id"]
        if detail["recipe"]:
            recipe_id = detail["recipe"]["id"]
        exported = client.get("/api/jobs/" + job_id + "/export")
        exported.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = json.loads(archive.read("FIXTURE-manifest.json"))
            assert manifest["result"]["job"]["payload"]["fixture"]
            if detail["candidate"]:
                Image.open(io.BytesIO(archive.read("FIXTURE-result.png"))).verify()
        report.append(
            {
                "mode": mode,
                "state": detail["job"]["state"],
                "job_id": job_id,
                "export_bytes": len(exported.content),
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
