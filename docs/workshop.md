# 角色工坊与模拟交易

更新于2026-11-17。

## 当前闭环

学习页登录后进入角色工坊，上传有权使用的参考图，确认权利和适用的真人同意，执行明确标示的模拟审核。创建服务端SKU订单，模拟付款成功后获得一次角色生成权益，提交人物名字、人设、称呼和外观偏好，任务经过排队、生成、结果审核后进入角色库。角色选择绑定当前账号，可用于剧情和悬浮陪学。

默认演示价为990分，即页面显示的¥9.90，由 CHARACTER_PACK_PRICE_CENTS 配置。这个数值是开发时的临时 Mock 展示值，正式商业售价和退款规则仍待确认。支付服务当前仅实现本地 Mock，界面和订单均保存 mock 标识。

Mock 交付主立绘1项、表情6项、姿态3项。立绘来自项目原创演示素材，表情和姿态条目标示为共用演示立绘占位。用户参考图用于演示私有上传与审核流程。真实身份一致性和各表情姿态的独立生成需要后续GPU工作流验证。

## 订单与权益

- 商品价格和角色包配置保存在服务端，订单创建时保存金额、币种与角色包数量快照。
- 创建订单与生成任务均接受request_id，重复请求返回已有结果，冲突内容返回409。
- Mock通知使用服务端HMAC-SHA256验签，核对金额、币种、订单、通知编号与交易编号。通知记录和权益在同一事务内提交。
- 重复通知具有幂等行为，付款成功后到达的失败通知保留已付款状态。每张订单只产生一个权益。
- 权益按available、reserved、consumed流转，任务失败、取消或超时恢复可用权益。交付后权益保持已使用状态。
- 数据库唯一约束、用户级写入锁和任务绑定防止并发请求重复占用或重复交付。

Mock签名密钥优先读取PAYMENT_MOCK_SECRET，缺省时写入已被git忽略的data/mock-payment.key。Compose的api_data卷保留开发签名密钥。实际支付宝签名、商户交易、退款通知与真实对账属于阶段6。

## 参考图和隐私

支持静态PNG/JPEG/WebP，上传限制5MB，尺寸128至4096像素，总像素不超过1600万。Pillow按照片方向转正后复制纯像素并重编码PNG，清除EXIF、ICC和嵌入工作流元数据，同时限制最多两个并行图片解码。参考图和生成资产保存在私有数据库字段中，通过当前账号授权读取，响应使用private/no-store缓存策略。

参考图默认保留7天，REFERENCE_RETENTION_DAYS可配置1至30天，每账号最多保存10张。用户可立即删除参考图，未完成任务会取消并恢复权益。已交付角色保留在角色库，用户可单独删除其图片、角色信息和角色聊天。删除已交付角色后，订单权益继续保持已使用。

Mock参考图审核由页面明确模拟。真实模式通过后台审核token及operator接口审核参考图和生成结果。token仅由服务端配置，当前浏览器界面未包含token。敏感图像识别质量、人工审核规范和真人同意材料还需在正式运营前完善。

## 图像服务

MockCharacterGenerator与ComfyUICharacterGenerator实现相同submit/poll/cancel接口。ComfyUI地址、凭证、工作流文件、节点绑定与输出节点均来自服务端配置。客户端请求仅接受人物属性、参考图ID和权益ID。任意工作流JSON或服务URL字段会被拒绝。

backend/workflows/character.template.json是禁用状态的空配置模板。当前可变输入白名单为内建LoadImage.image、CLIPTextEncode.text、KSampler.seed。配置经过许可核查的模型、节点、三个输入绑定及完整输出节点后，设置IMAGE_GENERATOR=comfyui。其他输入节点需要扩展并测试适配器。适配器调用/upload/image、/prompt、/history/{id}和/view，按固定服务地址查询状态及读取输出。真实模式的结果进入待审核状态，由审核人员批准后交付。[ComfyUI官方接口](https://docs.comfy.org/development/comfyui-server/comms_routes)

任务最多尝试3次，生成阶段默认300秒超时。每账号每日最多创建5个任务，全局最多创建20个新任务。每次实际提交另计入当天额度，默认15次/用户、60次/全局，包含失败提交和跨日旧任务重试，按UTC+8划分。迁移005之前的历史提交不回填。达到上限会恢复权益并提示次日重试，计数与状态变更在同一事务中提交。配置项为IMAGE_USER_DAILY_SUBMISSION_LIMIT及IMAGE_GLOBAL_DAILY_SUBMISSION_LIMIT。实际GPU费用和远端执行中图片的删除能力仍需真实验证。

当前仅运行单API/单图像worker。提交阶段重启会将任务标记失败并恢复权益，已经持久化remote_id的生成任务继续轮询。真实ComfyUI在提交后响应丢失时的远端幂等恢复与资源清理仍待真实集成验证。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/workshop/products | 服务端商品、价格和角色包配置 |
| GET/POST | /api/workshop/orders | 私有订单列表或按request_id创建 |
| POST | /api/workshop/orders/{id}/simulate | 模拟成功或失败，经共同验签处理逻辑发权益 |
| POST | /api/workshop/payments/mock/notify | 验证X-Mock-Signature的模拟通知 |
| GET/POST | /api/workshop/references | 私有参考图列表与上传 |
| GET/DELETE | /api/workshop/references/{id} | 私有图片读取或删除 |
| POST | /api/workshop/references/{id}/review | Mock参考图审核模拟 |
| GET/POST | /api/workshop/jobs | 任务列表或创建任务 |
| POST | /api/workshop/jobs/{id}/retry | 恢复权益后的失败任务重试 |
| GET/DELETE | /api/workshop/characters | 角色库及角色删除接口，删除需追加角色ID |
| GET | /api/workshop/assets/{id} | 已交付资产的授权读取 |
| PUT | /api/workshop/selection | 保存选定角色或清空为剧情预设 |
| GET | /api/workshop/operator/queue | 需审核token的待审队列 |
| POST | /api/workshop/operator/references/{id}/review | 后台参考图审核 |
| POST | /api/workshop/operator/jobs/{id}/review | 后台输出审核和交付 |

## 已验证与待验证

专项API测试覆盖价格篡改、验签失败、金额不符、重复通知、付款失败、账号隔离、参考图验证、元数据清理、并发占用、失败恢复、重试次数、超时、取消、未审核资产、角色选择和删除。ComfyUI适配器通过模拟HTTP传输测试。

桌面与手机浏览器已执行上传参考图、模拟审核、模拟付款失败及成功、生成交付、角色库选择、剧情使用及悬浮角色对话。真实GPU、真实支付、正式审核服务、对象存储与公网部署继续保持未验证状态。
