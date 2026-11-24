# 真实模型接入实验 · 2026-11-24

用户已授予本项目全部授权。本轮使用已连接的Cloudflare账户执行真实推理，全部教材为原创，未采购主机、发起付款或申请商户。授权已具备，具体账户凭证和运行资源仍需实际取得。

## 已发生的结果

- Qwen2.5-Coder真实直接调用返回中文定义与逐字引用，110 token、8.0836 neurons，耗时1.885秒。
- 三轮隔离应用实验各完成两份原创DOCX的云端提炼，分别为检索练习和速度关系；每份两条草稿，逐字引用与账号隔离均通过。各次结果保存在test-results/cloud-live-*/result.json。单次提炼包含解析和网络等待，约11至18秒。
- Qwen剧情返回Markdown代码块，且样本只含一个结局，未满足JSON及剧情约束，应用拒绝发布。原始响应5274字节、2083 token、160.68 neurons，留在隔离测试目录。此前还有连接超时；未通过后续判分和三角色聊天验收。
- 改用GLM-4.7-Flash的短JSON直连成功，70 token、1.3738 neurons；应用中首次知识提炼达到90秒总超时，另一次插件直连也超时。最新cloud-live-result.json如实保留failed。
- 11月24日网关短请求返回HTTP 200与合法JSON，13.187秒、50 token、0.893 neurons，见cloud-gateway-probe.json。这只能证明该次短推理成功，不能替代完整学习链路验收。默认HTTPX TLS与限制TLS 1.2的健康探测均返回200，暂未发现需要修改生产TLS配置的证据。

以上用量为具体响应返回值，不能代表所有尝试的累计费用。失败或客户端断开后，供应商仍可能完成推理并计量，实际扣费尚未核对。未宣称全学科教学质量、稳定剧情生成或真实聊天已验收。

## 私有模型网关

已部署galstudy-llm-gateway，HTTPS地址为 https://galstudy-llm-gateway.2025538744.workers.dev 。这只是服务端模型适配网关，完整GalStudy网站尚未发布。既有ai-focus-agent未修改。

11月24日最新部署ID为0bcea2d1cf65458f86c59457e2eb8ddd，来自本地infra/llm-gateway/worker.mjs，文件SHA256为7ab88b93e6d0995360b5931c665afc1a4c051ce120bb1af7119ae9bb451ecfab。上传响应etag为9b587acf45d137bb8e7e3cfd6cb53aa264f1bf1c3cbd0dd8ce1b74c9ff443323；该值由平台返回，不等同于本地文件摘要。固定GLM模型、Bearer密钥鉴权、64KiB请求限制、8192输出上限和字段白名单；无CORS开放，响应禁止缓存，日志仅记录用量或通用失败事件。密钥保存在Cloudflare secret binding、忽略的data与.env中，文档和前端不含密钥。

此前公开健康请求使用默认Python客户端时返回1010；明确标识GalStudy后返回200。历史实验出现连接失败和读取超时，11月24日健康与短推理恢复，长请求仍待重验。已在两类后端模型请求中设置GalStudy User-Agent；生成读取超时与配置总超时保持一致，连接上限15秒，聊天连接上限10秒。没有通过修改JSON或图校验掩盖模型输出问题。

网关6项单测通过，覆盖鉴权、模型及工具白名单、体积、JSON与finish_reason、UTF-8流分片、上游错误及缺少DONE。后端修改后55项回归通过（29.85秒）。本轮未改前端，未重复构建或声称真实浏览器云链路通过。

## 配置与继续方式

本机.env已经创建，但LLM_MODE与LLM_CHAT_MODE保持demo，避免未验收服务影响学习流程。网关配置私有保留。现有Windows HTTPS代理仅适用于此工作站，不应把.env原样复制到Linux部署主机。

scripts/cloud_live_check.py会使用真实模型、独立测试库和原创教材，不能作为无费用的普通回归运行。脚本独立开启cloud模式，执行上传、知识确认、剧情图校验、服务器判分和三角色聊天，任一失败立即记录并停止。测试数据与失败报告保留供排查。应用额度按各数据库计数，独立实验库的额度不构成供应商账户级总上限。

Cloudflare OAuth工具返回403并明确说明不能访问/user/tokens/permission_groups，无法经该连接签发新的模型API Token。下一步可在账户侧创建仅针对当前账户的Workers AI Read/Write Token，用原生OpenAI兼容端点替代额外网关，并重新验收。凭证只能放本地服务端配置。GPU、支付宝和目标主机还需具体账户或已登录控制台，已无需重复征询项目授权。

## 官方依据

- [Workers AI定价与免费额度](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [GLM参数及输出结构](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/)
- [Workers AI绑定](https://developers.cloudflare.com/workers-ai/configuration/bindings/)
- [1010与API客户端标识](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)

Cloudflare推理区域不能据此视为中国内地正式部署；本轮只发送原创验收材料，国内正式服务的数据区域和适用条件仍待目标环境核对。

## 当前交接

用户选择自行创建并将CLOUDFLARE_API_TOKEN保存到本地.env，待保存完成后继续权限、直连与完整业务验收。不要在聊天中发送Token。自动审批拒绝了读取尚未确认目标的现有Firefox窗口，原因是可能暴露无关浏览内容；未继续读取该窗口。

11月24日检查时该Token尚未保存，现有私有网关仍可执行推理。尝试启动scripts/cloud_live_check.py时，自动审批拒绝了出站请求，理由是尚未明确授权该脚本内两段具体原创样本发往该具体网关。该次脚本未启动，没有新的完整链路结果。已向用户列明样本（检索练习与匀速运动）和目的地，请求确认；等待期间不改用其他执行方式发送相同材料。

另核对了[Cloudflare拒绝容量排队选项](https://developers.cloudflare.com/workers-ai/features/reject-if-busy/)：Workers绑定须在AI.run第三参数传入rejectIfBusy，容量不足返回429/3040。已在网关加入该选项，现有6项单测全部通过，包含参数位置断言。11月24日独立发布该改动，metadata.keep_bindings保留已有secret_text，部署后配置查询仍包含AI和GATEWAY_TOKEN。健康检查200、无凭证空JSON返回401、有凭证空JSON返回400，见cloud-gateway-deployment-result.json；这些请求不包含教材，也不会触发推理。此版本尚未做真实推理验收，前文短推理证据属于此前版本；未将历史超时直接归因于容量队列。网关异常仍返回通用502，不向客户端披露上游错误详情。
