import json

import httpx
import pytest
from test_real_providers import png, settings

from studio.domain.models import Request
from studio.providers.domestic import DomesticProvider
from studio.repositories.db import candidates, engine_for, metadata
from studio.services.quality import check_request
from studio.services.workflow import Workflow
from studio.worker import run_once


def setup_candidate(tmp_path):
    engine = engine_for(tmp_path)
    metadata.create_all(engine)
    w = Workflow(engine, tmp_path, settings=settings(tmp_path))
    product = w.upload(png(), 'image/png', 'product')['id']
    scene = w.upload(png(), 'image/png', 'scene')['id']
    job = w.submit(Request(mode='B2', product_ids=[product], background_id=scene), 'seed')
    run_once(w)
    candidate = w.detail(job['id'])['candidate']
    # Offline seed record represents a completed real result for the check boundary tests.
    w.store.update(candidates, candidate['id'], {'fixture': False})
    return w, candidate, product, scene


def test_check_signed_snapshot_and_single_text_call(tmp_path, monkeypatch):
    w, c, product, scene = setup_candidate(tmp_path)
    request = check_request(w, c['id'])
    assert request.product_ids == [product, scene, c['asset_id']]
    preview = w.preview(request)
    assert preview['plan']['model'] == 'kimi-k3'
    assert preview['plan']['max_output_images'] == 0
    assert '待检查生成结果' in preview['plan']['prompt']
    with pytest.raises(ValueError):
        w.submit(request, 'no-approval')
    with pytest.raises(ValueError):
        w.preview(request.model_copy(update={'product_ids': [product]}))
    calls = []
    def respond(req):
        body = json.loads(req.content)
        calls.append(body)
        assert '商品图对照检查员' in body['messages'][0]['content']
        report = {'summary': '按钮位置存在差异', 'limitations': '仅视觉观察，需人工核验',
                  'checks': [{'topic': '部件', 'status': 'issue', 'observation': '按钮偏移',
                              'location': '商品右下角', 'asset_ids': [product, c['asset_id']],
                              'suggestion': '按原图恢复按钮位置'}]}
        return httpx.Response(200, json={'model': 'kimi-k3', 'choices': [
            {'finish_reason': 'stop', 'message': {'content': json.dumps(report)}}]})
    adapter = DomesticProvider(w.settings, transport=httpx.MockTransport(respond))
    monkeypatch.setattr('studio.services.real_jobs.DomesticProvider', lambda settings: adapter)
    job = w.submit(request, 'check', preview['confirmation_token'])
    assert w.submit(request, 'duplicate', preview['confirmation_token'])['id'] == job['id']
    run_once(w)
    detail = w.detail(job['id'])
    assert detail['job']['state'] == 'succeeded', detail['job']['error']
    assert detail['analysis']['data']['checks'][0]['status'] == 'issue'
    assert detail['candidate'] is None
    assert len(calls) == 1
    assert not run_once(w)


def test_fixture_cannot_be_checked(tmp_path):
    w, c, _, _ = setup_candidate(tmp_path)
    w.store.update(candidates, c['id'], {'fixture': True})
    with pytest.raises(ValueError, match='真实'):
        check_request(w, c['id'])
