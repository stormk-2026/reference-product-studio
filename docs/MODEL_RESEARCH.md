# 模型选型核实 · 2026-09-18

本文件是官方资料核实和待测建议，不是本项目实测排行榜。M1 未接入任何真实模型，也没有测量真实成本或图像质量。暂不固定供应商，不写入猜测的端点或价格。

## 视觉理解

- **Kimi K3 可以看图**。Moonshot 官方仓库介绍其原生多模态能力，包含文本、图片和视频理解，并给出 `kimi-k3` API 模型名。可作为 A 款式解析、C 场景 Recipe 的首选接入候选；这不意味着它本身能输出商品编辑图。服装细节和“不知道”的表现要用实际样例验证。[官方仓库](https://github.com/MoonshotAI/Kimi-K3)
- **Gemini 3.1 Pro Preview** 可作为复杂图片理解的对照候选，官方模型列表仍明确标为 Preview；同时列有更新的 Gemini 3.8 Flash，型号数字更新不等于与 Pro 是同一定位。[模型目录](https://ai.google.dev/gemini-api/docs/models)、[图片理解](https://ai.google.dev/gemini-api/docs/image-understanding)
- **GPT-6 Astra** 是当前 OpenAI 官方模型指引所指向的新旗舰候选；若选择 OpenAI 做理解，需在 M2 接入时核对图片输入、结构化输出和账户可用性，不能用生图模型名称代替理解模型名称。[官方当前模型指引](https://developers.openai.com/api/docs/guides/latest-model)
- 国内也可比较 **Qwen3-VL Plus** 视觉专项路线；官方视觉文档列有 `qwen3-vl-plus`。这里不将其称为所有 Qwen 系列的最新通用旗舰。[阿里云视觉理解](https://docs.modelstudio.console.alibabacloud.com/zh/model-studio/vision-model)

建议先用 Kimi K3 做理解适配器，避免同时接入多个理解服务；另取一个候选做少量相同样例盲评即可。

## 图像生成与编辑

| 具体候选 | 官方资料确认的定位 | 对本项目的建议（尚未实测） |
| --- | --- | --- |
| Seedream 5.0 Pro | 官方介绍多图融合、局部交互编辑、颜色/材质修改、图层分离；同时承认细粒度文字和编辑一致性仍可改进 | 国内接入优先的候选，适合先试 B2、C1/C2；“5”必须区分 Pro/Lite，实际 API 支持的控制方式仍需按接口文档确认 |
| Nano Banana Pro / `gemini-3-pro-image` | 图像生成/编辑，专业资产与复杂指令；输入文字和图片，输出文字和图片 | 用于复杂参考约束、多图商品场景的质量对照；不能把产品说明中的一致性宣传当绝对保真保证 |
| GPT Image 2.5 Sunburst / `gpt-image-2.5-sunburst` | 官方明确面向更重视编辑精度的生成与编辑流程 | 若优先评估编辑精度，我建议优先试此型号；这是选型建议，不是已证明胜过另两家 |
| GPT Image 2.5 Flare / `gpt-image-2.5-flare` | 官方定位更快的日常高质量图像生成 | 用于后续速度/质量权衡，不与 Sunburst 混称为一个测评结果 |

来源：[Seedream 5.0 Pro 官方发布说明](https://seed.bytedance.com/en/blog/beyond-generation-it-understands-design-introducing-seedream-5-0-pro)、[Google 图像生成文档](https://ai.google.dev/gemini-api/docs/image-generation)、[Nano Banana Pro 模型卡](https://ai.google.dev/gemini-api/docs/models/gemini-3-pro-image)、[Sunburst 模型卡](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)、[Flare 模型卡](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)。

“GPT 2.5”在此应明确为 GPT Image 2.5 的具体图像型号。先选一家实现真实图像适配器，不为比较预先搭多供应商平台。对 B1，商品保真主要依靠透明图/蒙版和确定性合成，图像模型负责背景；对 B2/C，才重点比较模型改图能力。

## 绘蛙描述的证据边界

公开的《绘蛙算法原理及信息处理情况说明》搜索索引摘要提到：电商文本算法以 Qwen-14B 开源模型为底座进行电商数据训练；电商模特试衣图像合成底座为扩散模型，使用多张商品和模特图。该说明是历史披露，页面本次直接读取失败，因此只能将索引摘要作为有限证据，不能据此确认当前线上版本。

它不足以支持“当前图像明确使用通义万相”“视频明确使用阿里视频模型”“精准保持衣服版型”这些更强结论。官网功能与底层具体 API 是两回事，当前精确图像/视频模型版本仍未知。不会将用户粘贴的描述写成已核实架构。

[绘蛙官网](https://www.ihuiwa.com/)、[公开算法说明](https://terms.alicdn.com/legal-agreement/terms/privacy_algorithm_theory_state/20241101141908157/20241101141908157.html)。

## 进入 M2 前

用户表示素材和预算稍后确定。本次未寻找/下载真实商家图片、未外发、未收费。届时明确素材清单、接收方和一次小批量调用范围，再按官方 API 文档核对能力。比较优先包含 Logo/文字、纹理、纽扣数量、轮廓、透明边缘、场景约束和一次单项返工；保留所有失败，不预设胜者。
