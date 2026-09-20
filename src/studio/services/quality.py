"""Build a signed, candidate-bound comparison; never generate or approve images."""
import json

from studio.domain.models import Request
from studio.repositories.db import candidates, jobs


def check_request(workflow, candidate_id):
    candidate = workflow.get(candidates, candidate_id)
    job = workflow.get(jobs, candidate['job_id'])
    if candidate['fixture'] or job['state'] != 'succeeded':
        raise ValueError('仅支持已完成的真实商品图检查')
    original = job['payload']['request']
    roles = []
    def add(ids, role):
        for asset_id in ids:
            if asset_id:
                roles.append({'asset_id': asset_id, 'role': role})
    add(original['product_ids'], '原始商品/待编辑图')
    add(original.get('product_view_ids', []), '同一商品补充角度')
    add([original.get('subject_id')], '指定替换商品：商品保真以此图为准')
    add([original.get('back_id')], '补充背面')
    add([original.get('background_id'), original.get('reference_id')], '场景参考，不继承其商品身份')
    if original.get('anchor_candidate_id'):
        anchor = workflow.get(candidates, original['anchor_candidate_id'])
        add([anchor['asset_id']], '已通过的批量风格样张，不继承其商品身份')
    add([candidate['asset_id']], '待检查生成结果')
    ids = list(dict.fromkeys(x['asset_id'] for x in roles))
    if len(ids) > 10:
        raise ValueError('本次对照超过 10 张图片，暂不支持；未省略任何对照图，请人工检查')
    context = {'roles': roles, 'original_request': original,
               'recipe': job['payload'].get('recipe'),
               'generation_prompt': job['payload'].get('compiled_prompt', job['payload'].get('prompt'))}
    return Request(execution='real', mode='CHECK', product_ids=ids,
                   check_candidate_id=candidate_id,
                   instructions=json.dumps(context, ensure_ascii=False))
