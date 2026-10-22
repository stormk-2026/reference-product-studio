# Storm Studio.

**简体中文** | [English](README.en.md)

stormg（郭慧康）的个人产品站与 AI 创作工作台。**[访问网站](https://stormstudio.top)** · [作品集](https://stormstudio.top/projects) · [在线简历](https://stormstudio.top/resume)。

支持明暗主题的毛玻璃界面展示个人产品、商业项目与工程经历。流境、觅境提供真实截图和流境操作演示，目前标注上架中，暂不开放 APK 下载。OkChat、杭麻馆提供真实产品图片及商店链接；AI 视觉工作台位于作品首位。完整档案共10个项目，包含 Android / OpenClaw 远程播控、带真实截图的 Trundertrack DApp、心犀、海外发行、运营商大屏。作品详情与在线简历共用资料，缺少实际截图的项目明确展示能力概念示意。

![Storm Studio 个人站首页](docs/images/portfolio-home.png)

## 访问与账号

作品集、产品演示、关于我、在线简历与工作台项目详情公开浏览；`/studio` 工作台需要登录（本地未启用认证时除外）。公开展示素材来自独立目录，不读取任何账号的上传或生成记录。配置扩展见 [个人站维护](docs/PORTFOLIO.md)。

普通账号通过邮箱验证码注册，共 3 张图片生成额度，主账户不限次数。文案、下载与本地抠图不扣图片额度；普通账号每日最多 20 个任务，全站公共模型调用默认 30 次/日。现有账号隔离、幂等确认、限流及私有 OSS 读取保持有效，见 [账号部署](docs/ACCOUNTS.md)。版本变更见 [CHANGELOG.md](CHANGELOG.md)。

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

Linux 使用宣传排版前需安装中文字体：`sudo apt-get install fonts-noto-cjk`；Docker 镜像已包含，macOS 使用系统字体。

两个终端分别运行：

```sh
uv run uvicorn studio.web.app:app --host 127.0.0.1 --port 8765 --no-access-log
```

```sh
uv run python -m studio.worker
```

访问 [本地个人站](http://127.0.0.1:8765/) 或 [工作台](http://127.0.0.1:8765/studio)。仅绑定本机。Worker 必须具备外网权限才能调用真实模型，可在本机终端运行。两个终端各按 Ctrl+C 停止。

## 使用

从作品集首位的「AI 视觉工作台」进入，再选择一个工具，点击商品图片卡添加素材，也可直接拖入或粘贴；“图片资产”抽屉可随时展开管理。白底页用两张卡展示商品与成图；场景和工业草图页用三张卡展示商品、参考场景 / 补充角度和生成结果，下方展示本地真实作品。

- **宣传图物料**：单张商品实拍（白底阶段不接收辅助角度） → 纯净白底展示图 → 直接下载 / 抠图为透明 PNG；也可继续选择参考场景，通过混图生成自己的场景宣传图。混图结果不提供抠图入口。
- **说明书工业草图 · Beta**：同一商品的三视图或多角度实拍 → 纯净三视图线稿。用于说明书外观插图初稿，需人工核对并补充标注，不用于生产加工。

生成前预览图片、要求和调用次数，确认后才调用模型。混图多个商品时先确认首张，再授权剩余批量。已有作品从“历史作品”打开。

画布支持 1:1、3:4、4:3、4:5、5:4、2:3、3:2、9:16、16:9。返回首页再进入工具会开始空白任务，也可用右上角“新建任务”清空当前配置；资产和历史作品保留。

宣传图文使用独立入口：提供 App 截图或商品图 → 填写真实卖点 → Kimi 起草 / 可选二次润色 → 编辑文案 → Seedream 生成首页视觉样张 → 确认后生成余下 3–6 页套图。模型生成视觉背景，原始素材和文字由程序叠放，固定 3:4。详见 [宣传图文使用说明](docs/CONTENT_STUDIO.md)。

当前界面仅保留以上三条生产流程。旧实验接口和记录保留兼容，不作为当前工具入口。

## 配置

只读取本项目 `.env`，环境变量优先，密钥不显示在网页或导出中。填写 `MOONSHOT_API_KEY`、`ARK_API_KEY`，模型为 `kimi-k3` 与 `doubao-seedream-5-0-pro-260628`。配置项参见 `.env.example`；改配置后重启 Web 和 Worker。

```sh
uv run python -m studio.config
```

此命令仅显示配置是否已填写，不输出密钥。相对 `STUDIO_DATA_DIR` 以项目根目录为准。`.env`、模型和 `data/` 已被忽略，不上传运行凭据；公开站点通过 HTTPS 访问，工作台及私有数据由应用登录保护。

## 验证与边界

```sh
uv run pytest -q
uv run ruff check src tests migrations scripts
uv run ruff format --check src tests migrations scripts
node --check src/studio/web/static/app.js
node --check src/studio/web/static/content.js
node --check src/studio/web/static/portfolio.js
node --check src/studio/web/static/portfolio-theme.js
node --check src/studio/web/static/login.js
node --test tests/frontend/*.cjs
```

自动测试禁止真实网络，供应商响应使用模拟数据。现有 `scripts/smoke.py` 可在 Web/Worker 启动后运行，仅产生本地 Fixture 记录。Fixture 不代表视觉生成效果。

模型可能改变细节；保留 Logo/结构是明确提示词约束，不是像素不变的保证。三视图无工程生产精度。本地抠图需检查边缘，暂无人工修边工具。真实任务无自动重试；未知结果需先核查账单。按次数确认，不提供金额预算保证，供应商侧需设置可接受的限制。只接收图片 base64 响应，不自动下载供应商返回的 URL。

详细新流程、批量语义、验证与后续能力见 [简化工作流](docs/SIMPLE_WORKFLOWS.md)。历史阶段见 [M1 报告](docs/M1_REPORT.md)、[M2 接入记录](docs/M2_INTEGRATION_REPORT.md)。

项目维护与已验证行为约束见 [HARNESS.md](HARNESS.md)。

服务器使用 HTTPS 反向代理，应用端口仅绑定回环。公网必须启用账号验证，工具及用户素材不能匿名访问。见 [部署说明](docs/SERVER_DEPLOYMENT.md) 与 [账号部署](docs/ACCOUNTS.md)。

图片支持本地或私有 OSS 存储，配置及权限说明见 [OSS 接入](docs/OSS_STORAGE.md)。默认本地；切换后旧本地图片仍可读取。

## 说明书插图初稿

单张实拍可生成白底实物配图；一张主视图及最多五张补充角度可生成白底三视图线稿，用作说明书外观插图、部件说明底图及设计沟通草图。当前三视图为正视、侧视、俯视，不自动编写完整说明书。使用前需人工核对部件与视图一致性，再补充部件名称、尺寸或操作说明；输出不作为生产加工图。
