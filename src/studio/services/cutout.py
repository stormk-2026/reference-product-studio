"""Offline foreground segmentation. Explicit local path prevents runtime model downloads."""

from functools import lru_cache
from pathlib import Path

from studio.repositories.db import assets, candidates, identifier, jobs, now


@lru_cache(maxsize=1)
def session(path: str):
    if not Path(path).is_file():
        raise ValueError("本地抠图模型尚未安装，请运行 scripts/setup_cutout.py")
    import os

    os.environ["U2NET_HOME"] = str(Path(path).parent)
    import onnxruntime as ort
    from rembg import new_session

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    return new_session(
        "u2net_custom", model_path=path, providers=["CPUExecutionProvider"], sess_opts=options
    )


def remove_background(image, root):
    import onnxruntime as ort

    ort.disable_telemetry_events()
    from rembg import remove

    output = remove(image, session=session(str(root / "models" / "u2net.onnx")))
    if output.mode != "RGBA" or output.getchannel("A").getextrema()[0] == 255:
        raise ValueError("抠图未产生透明背景，请换清晰图片或使用人工蒙版")
    return output


def run_cutout(workflow, job):
    import time

    start = time.monotonic()
    payload = job["payload"]
    source = workflow.get(assets, payload["request"]["product_ids"][0])
    output = remove_background(workflow.image(source["id"]), workflow.root)
    item = workflow.store_image(output, "本地抠图 · 透明 PNG", source["fixture"])
    payload.update(
        fixture=source["fixture"],
        provider="local-rembg",
        model="u2net",
        duration_seconds=time.monotonic() - start,
    )
    workflow.store.update(jobs, job["id"], {"payload": payload})
    data = dict(
        mode="CUTOUT",
        request=payload["request"],
        warning="本地自动抠图；请检查透明壶身、细杆、镂空和边缘，不保证分割完全准确。",
        duration_seconds=time.monotonic() - start,
        transformations=[
            "本地 U²-Net 分割，只修改透明通道，保留前景颜色；无外发、无模型调用费用。"
        ],
        provider="local-rembg",
        model="u2net",
        fixture=source["fixture"],
        cost_estimate=0,
        input_ids=[source["id"]],
    )
    workflow.store.complete(
        job["id"],
        candidates,
        dict(
            id=identifier(),
            job_id=job["id"],
            asset_id=item["id"],
            data=data,
            created_at=now(),
            favorite=False,
            fixture=source["fixture"],
        ),
    )
