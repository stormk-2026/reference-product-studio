# Storm Studio 图片存储

使用专用私有 Bucket，与其他项目隔离。建议与服务器处于同一地域；验证环境使用标准存储、本地冗余，阻止公共访问开启。仓库不记录实际 Bucket 名、服务器地址或 RAM 用户标识。

2026-09-21：用户配置专用 RAM 用户凭据后，服务器已启用 `STUDIO_ASSET_BACKEND=oss`。实际 OSS 写入、读取和内容校验通过；A_white、A_views、B2 的 Fixture 任务、PNG 下载和 ZIP 导出通过，未调用收费模型。旧本地图片继续兼容，不代表历史图片已迁移。服务器保持回环端口 18765 的私有测试部署，本机 8765 配置不随之改变。

网页上传合成图、本地抠图回存 OSS、透明 PNG 下载通过；透明通道范围0—255，无新增本地永久图片。匿名取图返回403。切换后备份 归档 经独立检查，数据库完整、20张引用图片哈希一致、快照路径全部本地化；在线数据库未改写。

使用 RAM 用户的长期 AccessKey 时，`STUDIO_OSS_SECURITY_TOKEN` 留空；仅 STS 临时凭据需要配套 Token。创建策略后还须将其授权给专用 RAM 用户。RAM“摘要 Beta”曾对符合官方资源格式的目录策略显示“无效授权”；应核对源代码、授权关系，并以实际 OSS 读写验证为准，不因此放宽为整个 OSS 管理权限。

## 启用

1. 为本项目建立专用 RAM 用户（只用于程序访问），将 `deploy/oss-ram-policy.json` 中的 `YOUR_BUCKET_NAME` 替换为自己的 Bucket 名，再授予其中的最小权限。只允许本 Bucket 的 `storm-studio/assets/` 路径读写，不允许删除、访问其他 Bucket 或管理账户。不要授予 AliyunOSSFullAccess，也不要复用其他项目的密钥。
2. 用户在 RAM 控制台创建该用户的 AccessKey，填入服务器 `/opt/storm-studio/config/runtime.env`。所需字段见 `deploy/oss.env.example`，文件权限保持600。AccessKey ID 和 Secret 均不粘贴进聊天、README 或提交到 Git。
3. 配置完成后将 `STUDIO_ASSET_BACKEND=oss`，确认没有排队/执行中任务，再重建 Web、Worker 容器使新环境生效。仅 `restart` 不会载入 Compose 新环境变量。
4. 用测试图片验证上传、下载、抠图与导出；核对数据库路径为 `oss://YOUR_BUCKET_NAME/storm-studio/assets/...png`，且服务器没有新增永久图片文件。未完成此步骤前不宣称 OSS 已真实接通。

杭州服务器使用内网 HTTPS Endpoint。本机开发如需测试 OSS 则使用公网 `https://oss-cn-hangzhou.aliyuncs.com`。日常本机开发继续 `local`，不会读取其他项目环境变量。多用户权限尚未实现，本接入不改变私有 SSH 测试部署边界。

## 行为

- 上传原图经过格式校验、去 EXIF 和 PNG 重编码，再写入私有 OSS；数据库只保存对象位置、哈希、尺寸和图片归属记录，不保存签名 URL 或凭据。
- 模型调用、抠图、预览下载、ZIP 导出统一通过存储层读取；浏览器继续使用工作台 `/api/assets/{id}`，无需开放 Bucket、绑定图片域名或放宽 CORS。当前图片经过服务器代理，仍会使用服务器向浏览器传输的带宽。
- 读图检查 SHA256，禁止配置之外的 Bucket、目录和任意远程 URL。数据库位置固定，不能随意改变 Bucket 或目录后期望旧图仍可访问。
- 正常 OSS 模式不永久保存图片到服务器。旧本地图片仍能读取；切换不自动迁移或删除旧文件。
- 上传失败不创建成功记录。收到收费模型结果后，若 OSS 写入失败，将图片保留到服务器并在结果中标记，避免丢失已收费结果；不自动重新生图。此类本地保留文件需后续处理。
- 备份下载 OSS 和旧本地图片，校验后打包；仅在数据库快照内将图片路径转换成本地路径。归档可在 `local` 模式下离线恢复，不依赖云端原对象，在线数据库不被改写。完整备份仍占用备份目录空间，应规划保留周期及异机副本。
- 未实现浏览器直传、CDN、自动历史素材迁移、自动过期删除或用户级存储配额，后续单独添加。

采用阿里云官方 Python SDK V2；依赖锁定版本，SDK 使用本项目显式凭据、HTTPS、有限超时，存储异常不保存供应商原始错误文本，防止签名信息进入日志。

参考：[官方 Python SDK](https://help.aliyun.com/zh/oss/developer-reference/2-0-manual-preview-version/)、[轻量服务器同地域内网访问](https://help.aliyun.com/zh/simple-application-server/use-cases/implement-service-interconnection-over-the-internal-endpoint-of-an-oss-resource)。
