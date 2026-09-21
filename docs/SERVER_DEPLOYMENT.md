# 服务器部署：私有测试阶段

当前基线为 v0.1 Beta，仍是单用户应用。本部署只通过 SSH 隧道访问，不是多用户公网发布版。备案期间不开放网站公网端口；后续完成登录、用户数据隔离、额度控制和 HTTPS 后，再启用正式域名。

## 目录与边界

- `/opt/storm-studio/releases/v0.1.0b1-server2`：应用代码和部署配置。
- `/opt/storm-studio/config/runtime.env`：模型与存储配置，root 读取，权限 600；不进入 Git 或镜像。
- `/opt/storm-studio/data`：此服务器独立的数据与模型目录；容器用户 10001。
- `/opt/storm-studio/backups`：数据库及其引用图片的备份；不包含密钥、权重。

Compose 项目名为 `storm-studio`。Web 仅映射 `127.0.0.1:18765`，Worker 不映射端口。不会改动已有 Docker 项目的端口、网络、卷或配置。两服务共享同一数据目录；只启动一个 Web 进程和一个 Worker，保留当前内存签名及任务锁语义。

Web 限制 384MiB、0.5 CPU，Worker 限制 1536MiB、1 CPU。首次 512×512 合成图本地抠图验证得到透明 RGBA，初始化及推理耗时约102秒，进程峰值约1249MiB；真实大图仍需观察峰值，不能据此宣称高并发可用。服务资源不足时先排查，不能自动重试收费生成。

## 首次部署

在上述发布目录执行：

```sh
docker compose -f deploy/compose.yaml build web
docker compose -f deploy/compose.yaml run --rm --no-deps web alembic upgrade head
docker compose -f deploy/compose.yaml up -d web worker
docker compose -f deploy/compose.yaml ps
```

模型权重安装在 `data/models/u2net.onnx`，固定校验和沿用 `scripts/setup_cutout.py`。服务器可下载，也可从已验证的本地安装复制公开权重，不迁移本地用户图片。默认不开付费任务，真实生成仍需要页面预览和确认。

## 访问

本机终端建立隧道，替换服务器地址：

```sh
ssh -N -L 127.0.0.1:18765:127.0.0.1:18765 root@服务器地址
```

浏览器打开 `http://127.0.0.1:18765/`。该地址通过 SSH 到达服务器；原本机开发环境仍用 8765。停止此 SSH 进程只关闭访问通道，不停止服务器服务。不要把 Compose 映射改成 `0.0.0.0` 来绕过域名与登录适配。

## 备份与恢复

```sh
docker compose -f deploy/compose.yaml --profile ops run --rm --no-deps backup
```

使用 SQLite 在线备份 API 获取一致数据库快照，再打包快照所引用的所有图片；缺失图片会使备份失败，不把不完整归档标成成功。恢复时先停止本项目服务，将归档解压到新的数据目录，补充公开模型权重并设为 UID/GID 10001，使用 `STUDIO_DATA_PATH` 指向新目录后验证。不要直接覆盖正在使用的数据目录。当前备份仍在同一服务器，正式开放前还应配置定时与异机备份和保留周期。

## 正式多用户上线前

- 注册、密码哈希、登录会话与登出，注册邀请或审核方式。
- 图片、任务、候选、批量样张、导出、删除、评价等接口全部按用户隔离，不能仅隐藏前端列表。
- 按用户分配生成额度，提交时原子扣留额度，处理失败与结果未知，不开放无限免费生成。
- 正式域名白名单、可信反向代理、Secure Cookie、上传与登录限速。
- 备案完成后配置域名解析、HTTPS、备案信息展示，进行跨账号越权和收费幂等回归。

这些是下一阶段改造项，当前部署不宣称已经支持多人注册。

## 下载较慢时的离线构建

验证环境使用了 `deploy/Dockerfile.offline`：先下载 Python 3.11 / Linux x86_64 所需 wheel，按 `uv.lock` 的 SHA256 校验，放进发布目录下的 `wheelhouse/`；再在对应源代码版本上执行 `uv build --wheel --out-dir wheelhouse`，一并放入本项目的纯 Python wheel。安装时再次使用从锁文件导出的 requirements 与 `--require-hashes`，不重新选择依赖版本。缓存目录不进入 Git。

```sh
docker build --network host \
  --build-arg DEBIAN_MIRROR=https://mirrors.aliyun.com \
  --build-arg PYTHON_INDEX=https://mirrors.aliyun.com/pypi/simple \
  -f deploy/Dockerfile.offline -t storm-studio:0.1.0b1-server2 .
```

使用同版本源代码生成项目 wheel，不能用旧 wheel 部署新代码。正常联网时可使用前面的 Compose 构建方式。镜像上下文采用白名单，并排除 macOS 的 `._*` 元数据文件，避免将其误识别成数据库迁移脚本。


## OSS 适配版本

`server2` 增加私有 OSS 存储支持，2026-09-21 已验证专用 RAM 凭据的实际读写并启用 `STUDIO_ASSET_BACKEND=oss`，详见 [OSS 存储说明](OSS_STORAGE.md)。三条 Fixture 路线、PNG 下载和 ZIP 导出通过，未调用收费模型。旧图片不会自动迁移。备份容器也需要存储配置，以便打包云端图片。
