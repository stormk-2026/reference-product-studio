import pytest
from pydantic import SecretStr
from test_workflows import picture

from studio.config import Settings
from studio.domain.models import Request
from studio.repositories.db import engine_for, metadata
from studio.services.external import ApprovalSigner
from studio.services.workflow import Workflow


def test_approval_bound_to_payload_and_expires(monkeypatch):
    signer = ApprovalSigner()
    payload = {"sent_asset_ids": ["a"], "max_calls": 1}
    token = signer.issue(payload)
    assert signer.verify(token, payload).startswith("real-")
    with pytest.raises(ValueError, match="确认"):
        signer.verify(token, {"sent_asset_ids": ["b"]})
    monkeypatch.setattr("studio.services.external.time.time", lambda: 10**12)
    with pytest.raises(ValueError):
        signer.verify(token, payload)


def test_real_requires_preview_and_single_use_for_replayed_token(tmp_path):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    settings = Settings(
        storage_dir=tmp_path,
        moonshot_api_key=SecretStr("dummy"),
        ark_api_key=SecretStr("dummy"),
        seedream_model="doubao-seedream-5-0-pro-260628",
    )
    workflow = Workflow(engine, tmp_path, settings=settings)
    asset = workflow.upload(picture(), "image/png", "offline test", True)
    request = Request(mode="A", product_ids=[asset["id"]], execution="real")
    with pytest.raises(ValueError, match="确认"):
        workflow.submit(request, "a")
    preview = workflow.preview(request)
    assert preview["sent_assets"][0]["id"] == asset["id"]
    first = workflow.submit(request, "a", preview["confirmation_token"])
    again = workflow.submit(request, "different-key", preview["confirmation_token"])
    assert first["id"] == again["id"]
    assert first["payload"]["external_authorized"] is True
    assert first["payload"]["fixture"] is False
    assert first["payload"]["input_fixture"] is True
