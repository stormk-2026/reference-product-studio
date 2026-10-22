# 服务器部署：公开个人站与私有 AI 工作台

当前站点由 FastAPI/Jinja、独立 Worker、Nginx HTTPS 和应用账号认证组成。首页、作品及履历公开；`/studio` 与素材、任务、历史、下载 API 必须登录。邮箱验证码注册、账号隔离和体验额度见 [账号部署](ACCOUNTS.md)。

## 目录与配置

- `/opt/storm-studio/releases/<version>`：版本化源码与 Compose 配置。
- `/opt/storm-studio/current`：指向当前已验证版本的链接。
- `/opt/storm-studio/config/runtime.env`：服务器私有运行配置，权限600，不进入 Git 或镜像。
- `/opt/storm-studio/data`：账号、任务数据库及本地素材；运行用户10001。
- `/opt/storm-studio/backups`：账号、租户数据库及引用图片的私有备份。

Compose 通过 `STUDIO_ENV_FILE`、`STUDIO_DATA_PATH`、`STUDIO_BACKUP_PATH` 支持自定义目录。Web 和 Worker 使用同一数据目录、独立进程。首次安装先配置主账户与权限，遵循[账号初始化步骤](ACCOUNTS.md)；升级时保留现有账号数据库及 runtime.env。

公开部署启用 `STUDIO_AUTH_ENABLED=1`。只有本机可信 Nginx 覆盖客户端地址且应用端口为回环绑定时，才启用 `STUDIO_TRUST_PROXY=1`。邮件实际送达验证通过后再开启注册；模型与 OSS 凭据仅填写在私有运行配置中。

## 构建与运行

在版本目录使用 `docker compose -f deploy/compose.yaml build` 构建，再通过 `docker compose -f deploy/compose.yaml up -d --wait web worker` 启动。`STUDIO_IMAGE` 可指定版本标签，Web 和 Worker 必须使用同一版本。

镜像包含本地抠图运行依赖与 Noto CJK 中文字体。发布包必须包含 portfolio.json、profile.json、templates、static；公开作品素材由[独立目录](PORTFOLIO.md)提供。

应用仅绑定 `127.0.0.1:18765`，Worker 不监听公网端口。首次内部验收可通过 SSH 本地转发连接这个端口。不要在已有项目服务器上覆盖其他站点配置或重启无关服务。

## HTTPS 与反向代理

通用配置见 [Nginx 模板](../deploy/nginx.conf.example)。将示例域名替换为自己的域名，并对应调整应用的域名白名单、HTTPS 同源校验和 Secure Cookie 条件。

1. 配置域名解析及 TCP 80/443 入站规则；应用端口继续保持回环绑定。
2. 准备 Nginx、Certbot 和 HTTP 验证目录 `/.well-known/acme-challenge/`，使用 webroot 验证签发证书。
3. 配置 HTTPS 站点、HTTP 跳转及站点专属认证/请求限流；登录由应用处理。
4. 执行 `nginx -t` 后加载配置。启用证书续期定时器，续期部署钩子执行配置检查与 Nginx reload。
5. 使用 `certbot renew --dry-run --no-random-sleep-on-renew` 验证续期；公网检查 HTTPS、备案信息及下述访问边界。

## 升级与回退

先确认所有租户没有 queued/running 任务，再创建一致性备份。构建独立新版本镜像，校验模板、公开资源和功能后，仅更新本站 Web/Worker。切换前再次检查活跃任务，避免中断刚提交的生成。

新版本健康检查通过后再更新 current；保留上一版镜像和源码供回退。运行配置、账号数据库和素材目录不由源码包覆盖，不以重新调用付费模型修复部署问题。

## 备份与验收

使用 `docker compose -f deploy/compose.yaml run --rm backup` 创建备份。备份包含账号恢复所需的密码哈希、租户数据库和引用图片，属于私有运行数据，不提交 Git。备份去除登录会话、验证码与限流事件；OSS 开启时备份容器需要读取同一存储配置。

独立核验 SQLite 完整性、引用图片 SHA256，以及更新前后任务和素材数量。验收公开首页与项目页、图片/视频、手机布局、主题和联系方式；同时确认匿名私有 API 返回401、工作台跳转登录、账号间素材隔离及原额度保持有效。不要为部署检查自动发送验证码或调用付费模型。

## 离线构建与素材存储

网络缓慢时可使用 `deploy/Dockerfile.offline`。wheelhouse 的依赖应匹配 uv.lock 的版本与哈希，项目 wheel 必须来自同一版本源代码；不得将旧 wheel 与新页面混合发布。Docker 上下文排除本地配置、运行数据和 macOS `._*` 文件。

图片支持本地及私有 OSS，见 [OSS 存储说明](OSS_STORAGE.md)。切换存储后旧本地图片仍可读取，不自动迁移或删除。公开作品媒体与私人生成素材相互独立。

源码只保存通用配置模板，不包含实际服务器 IP、密码、证书私钥、模型/OSS/SMTP 凭据或用户数据库。官网 URL、指定产品素材及 README 首页截图经用户授权公开。
