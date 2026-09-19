# M1 实施与验证记录 · 2026-09-18

## 状态

M0 已获用户确认。M1 最小纵向切片已实现，并在 macOS ARM64 / Python 3.11.15 上运行。**工程链路可运行；真实模型接入 0，真实视觉质量未验证。**没有进入 M2/M3 的真实模型验收，未外发任何图片，未执行收费调用，未提交/推送/部署。

## 实际完成

- 共用安全上传、随机资源 ID、PNG 重编码、hash、来源与 Fixture 记录。
- SQLite / SQLAlchemy 六类领域记录、Alembic 初始迁移、独立 Worker、数据库原子领取、幂等提交。
- A：多图输入、补充信息、证据状态、可编辑资料及尺寸/工艺表、正背面测试候选、独立纸样实验入口。缺失背面时只标设计假设；纸样警示写入页面、图片及 ZIP。
- B1：真实 Pillow alpha 合成；透明图/蒙版替代抠图、背景测试图、画布比例、缩放/位置、羽化、投影和处理记录。B2：固定测试图链路，明确未执行模型重绘。
- C：参考解析、全部 Recipe 字段、继承/修改/忽略、版本保存、配方编译、C1/C2 及原参考/文字策略入口、同商品/参考对照。
- 结果与输入对照、PNG 下载、本地收藏标记、人工特征检查与评价、ZIP 导出。编辑产生新版本，已提交任务与候选快照不变。
- Host/Origin、CSRF、上传字节/像素/静态格式检查、资源路径限制、模板/DOM 转义、CSP。没有外部图片 URL 下载接口。
- Worker 使用 OS 排他锁。重启不重试不明任务；区分 interrupted / outcome_unknown / failed，不虚构请求 ID、用量和费用。

## 命令与真实结果

| 命令 | 结果 |
| --- | --- |
| `uv --cache-dir /private/tmp/reference-product-studio-uv-cache sync` | 安装完成，32 packages resolved，uv.lock 已生成 |
| `uv --cache-dir /private/tmp/reference-product-studio-uv-cache sync --locked --offline` | 成功，确认锁定依赖可用 |
| `.venv/bin/alembic upgrade head` | 成功 |
| `.venv/bin/alembic current` | `0001 (head)` |
| `.venv/bin/python -m pytest -q` | **23 passed, 2 warnings**，0.49 秒（最终记录） |
| `.venv/bin/ruff check src tests migrations scripts` | All checks passed |
| `.venv/bin/ruff format --check src tests migrations scripts` | 21 files already formatted |
| `.venv/bin/uvicorn studio.web.app:app --host 127.0.0.1 --port 8765 --no-access-log` | 本机服务成功启动 |
| `.venv/bin/python -m studio.worker` | 独立 Fixture Worker 成功启动 |
| `.venv/bin/python scripts/smoke.py` | 九条操作通过真实 localhost HTTP + 独立 Worker 完成；ZIP 均可打开，七个图像结果实际解码通过 |

两条 warning 来自 Starlette 测试客户端对 httpx / AnyIO 接口的弃用提示，不是业务断言失败；未为消除 warning 更改测试语义。初次沙箱联网与绑定端口受限，经工具授权安装与 localhost 启动后成功；未扩大监听到公网。

RED→GREEN→REFACTOR：先写规则/工作流/Web 测试，初次因模块未实现失败；逐层实现后变绿。另有实际回归失败：`test_preserve_is_compiled_for_image_requests` 发现保留项遗漏于 prompt，修复后通过。随后将 SQL 事务收敛到 repository，格式化并重跑全套测试。

默认 pytest 使用 socket 阻断，无法意外请求付费服务。unit、integration、fixture_workflow 可分别用 marker 执行；真实模型评估尚未执行。

## 本机烟测记录

| 模式 | Job ID | 导出字节数 | 状态 |
| --- | --- | ---: | --- |
| A | c835aa8227ab4494ae3b2078ba80b019 | 1394 | succeeded / Fixture |
| A_front | 3df95c9780dc46be9bb5cc45f81b7913 | 21354 | succeeded / Fixture |
| A_back | db29fbca84194952b4795f78ddf2b7ec | 24369 | succeeded / Fixture |
| A_pattern | ef32aeb3785f4958acabc415b698c026 | 26178 | succeeded / Fixture |
| B1 | 60441f709a0b4d58b41d8332bbcf3879 | 37560 | succeeded / Fixture |
| B2 | 6dc21a3f4724438282f7acd8eb9f0539 | 14476 | succeeded / Fixture |
| C_analyze | abe563ae94e64203ad0630d52984e0b5 | 1646 | succeeded / Fixture |
| C1 | 42c0c74d8b14497293aec4f4b63ea7ea | 14545 | succeeded / Fixture |
| C2 | 5fe6079dbadd47c79522cb9bc85643a1 | 15084 | succeeded / Fixture |

测试输入由本地程序绘制，无真实商家素材。记录可在任务历史打开。自动测试也覆盖异常、超时、并发领取和旧版本编辑冲突；这些是模拟失败，不是模型失败样例。

## 浏览器验证

通过本机浏览器操作完成：载入素材、A 提交与完成、人工填写类别并保存 v2、B1 提交并查看原图/合成图、C 解析、单项背景修改并保存 v2、C1/C2 提交及同素材四图对照，浏览器 error/warn 日志为空。实际按 Tab 后焦点落到配方选择框，CSS outline 为 solid。输入有标签；编辑表格证据状态可操作。已查看 B1 对照截图，Fixture 水印及处理说明可见。非全面无障碍审计。

## 未验证与下一步

- 当前 Fixture 不识别用户图片；A 字段与 C 解析值默认为 unknown，不以固定假答案冒充识别。
- 技术图/纸样是固定测试轮廓；B2/C1/C2 是固定测试场景，不证明还原、保真或参考迁移能力。
- 无自动分割模型；B1 使用透明图/蒙版，光影仅本地投影，尚无模型级主体光照协调。
- 无真实供应商适配器、价格/预算执行、外部任务查询、结果 URL 下载；这些按 M2 选型落实。
- 当前仅最近100条列表；完整收藏筛选、分页、回收/孤立文件处理与易用性后续按实际需要推进。没有通用管理平台。
- A/B/C 的真实失败样例和质量评价为零，不预设 C2 更好。M4 真实求职证据尚未建立。

用户现在可打开 `http://127.0.0.1:8765` 体验 M1。M2 等待具体服务商/模型配置、素材和外发/调用范围确认；用户已表示这些稍后确定，不需要为继续试用 M1 再次授权。M3 仍需先查看 M2 真实输出。
