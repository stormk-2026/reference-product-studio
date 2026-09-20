# 商品视觉工作台 · Reference Studio

本地单用户电商图片工作台。三个入口：**商品解析、一键混图、参考重构**。支持国内 Kimi / Seedream 适配，以及本地 U²-Net 抠图。界面已简化，历史数据兼容。

## 效果展示

同一商品的正面、侧面与背面实拍，配合一张场景参考图，生成新的商品展示图。下面是工作台的实际输入与输出对照；生成结果仍需人工检查商品结构、屏幕文字和 Logo 等细节。

![多角度商品实拍与参考场景融合效果](docs/images/multiview-scene-result.png)

## 启动

Python 3.11，在项目根目录运行：

```sh
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run python scripts/setup_cutout.py
```

最后一条首次下载本地抠图权重，之后校验已安装文件，无需每次运行。

两个终端分别运行：

```sh
uv run uvicorn studio.web.app:app --host 127.0.0.1 --port 8765 --no-access-log
```

```sh
uv run python -m studio.worker
```

访问 [本地工作台](http://127.0.0.1:8765/)。仅绑定本机。Worker 必须具备外网权限才能调用真实模型，可在本机终端运行。两个终端各按 Ctrl+C 停止。

## 使用

- **商品解析**：最多 10 张图片 → 逆推完整 Prompt / 白底实物图 / 说明书草图（三视图）· Beta → 查看、复制或继续生成。
- **一键混图**：自有商品 + 参考场景 → 先生成一张。同一商品的多角度共同生成一张；多个商品则首张通过后，其余商品沿用同一场景与样张风格批量生成。
- **参考重构**：参考图 → 视觉配方（可选修改）→ 添加自己的商品 → 生成。
- **出图后**：下载、收藏、加入待处理列表，或将白底结果直接带入场景混图；支持本地抠图和三种基础宣传文字排版。
- **AI 对照检查（可选）**：确认后由 Kimi 对照原商品、场景与结果，输出问题位置、修改建议及不确定项。建议可带入修改表单，不自动重绘、不替代人工确认。

上传支持文件选择、拖放、Ctrl/⌘+V 粘贴；图片备注选填。删除从素材库移除，保留历史任务所引用的文件。开发测试素材入口收在高级选项。页面默认真实模式，但每次收费提交仍需核对图片、接收方和次数并确认；API 未指定执行方式时仍默认 Fixture。

## 配置

只读取本项目 `.env`，环境变量优先，密钥不显示在网页或导出中。填写 `MOONSHOT_API_KEY`、`ARK_API_KEY`，模型为 `kimi-k3` 与 `doubao-seedream-5-0-pro-260628`。配置项参见 `.env.example`；改配置后重启 Web 和 Worker。

```sh
uv run python -m studio.config
```

此命令仅显示配置是否已填写，不输出密钥。相对 `STUDIO_DATA_DIR` 以项目根目录为准。`.env`、模型和 `data/` 已被忽略，勿公开服务或上传本地凭据。

## 验证与边界

```sh
uv run pytest -q
uv run ruff check src tests migrations scripts
uv run ruff format --check src tests migrations scripts
node --check src/studio/web/static/app.js
node --test tests/frontend/upload.cjs
```

自动测试禁止真实网络，供应商响应使用模拟数据。现有 `scripts/smoke.py` 可在 Web/Worker 启动后运行，仅产生本地 Fixture 记录。Fixture 不代表视觉生成效果。

模型可能改变细节；保留 Logo/结构是明确提示词约束，不是像素不变的保证。三视图无工程生产精度。本地抠图需检查边缘，暂无人工修边工具。真实任务无自动重试；未知结果需先核查账单。按次数确认，不提供金额预算保证，供应商侧需设置可接受的限制。只接收图片 base64 响应，不自动下载供应商返回的 URL。

详细新流程、批量语义、验证与后续能力见 [简化工作流](docs/SIMPLE_WORKFLOWS.md)。历史阶段见 [M1 报告](docs/M1_REPORT.md)、[M2 接入记录](docs/M2_INTEGRATION_REPORT.md)。

项目维护与已验证行为约束见 [HARNESS.md](HARNESS.md)。

## 说明书插图初稿

上传同一商品的多角度实拍，可生成白底实物配图，或将实拍转换为白底三视图线稿，用作说明书外观插图、部件说明底图及设计沟通草图。当前三视图为正视、侧视、俯视，不自动编写完整说明书。使用前需人工核对部件与视图一致性，再补充部件名称、尺寸或操作说明；输出不作为生产加工图。
