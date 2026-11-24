# 支付宝应用集成 · 2026-11-24更新

已将支付宝Provider、签名通知、主动查询、退款状态机和前端付款/退款界面接入应用。默认PAYMENT_PROVIDER=mock不变。所有本轮网关测试均使用本地替身；尚未连接支付宝远程沙箱、未发起真实付款或退款。

## 服务端与界面

PAYMENT_PROVIDER支持mock、alipay_sandbox、alipay_live。支付宝模式要求ALIPAY_APP_ID、ALIPAY_SELLER_ID、公私钥文件路径及HTTPS APP_ORIGIN完整，配置错误明确阻止启动。正式角色收款还要求配置真实ComfyUI服务；演示及沙箱权益不能用于真实GPU生成。实际开通资格和工作流质量仍须远程验收。

订单保存创建时的支付模式，历史订单不会随服务配置切换。Mock通知使用独立HMAC Provider，仅能授权Mock订单；支付宝通知经过RSA2、应用/收款方/订单/金额验证后主动查询，再事务发一次权益。通知接口对成功返回文本success，未确认则返回failure。同步返回学习页不会授予权益。

付款查询与退款接口均要求登录并验证归属。外部调用期间释放业务数据库事务。退款先原子冻结权益和领取一次提交权，网络结果不明或进程重启后保持unknown，不自动重复退款；同一退款号查询确认成功后才完成退款。退款查询至少间隔10秒，字段尚未出现时继续冻结。已支付订单收到外部关闭状态会转payment_review并暂停未交付权益，等待核对。

界面按订单区分Mock、沙箱和正式付款，显示相应说明、金额、付款链接和状态查询。支付宝链接限定匹配环境的HTTPS官方网关。全额退款前展示金额及冻结影响，处理中可查询退款。Mock按钮只显示在Mock订单上。已消费或生成中权益、部分退款及需要人工处理的外部退款政策仍未完成公开支持流程。

## 路由

| 方法与路径（前缀/api/workshop） | 用途 |
| --- | --- |
| POST /orders/{id}/refresh | 本人订单的主动付款查询 |
| POST /payments/alipay/notify | 签名通知、主动查询与幂等授权，16KiB限制 |
| POST /orders/{id}/refund | 未使用权益的全额退款申请，单次领取提交权 |
| POST /refunds/{id}/refresh | 本人退款的固定请求号查询 |

## 验证结果

- SQLite与PostgreSQL完整回归各99项通过，包含真实RSA2算法与MockTransport组合测试、错误金额、通知查询失败、重复通知、退款超时、并发提交、重启恢复和跨账号拒绝。PostgreSQL迁移1至7、23张表，关键支付记录重复迁移保持一致，临时集群已关闭。
- 前端11项测试和生产构建通过。独立WebKit的桌面/390px手机学习、聊天与Mock工坊25项流程通过。
- Edge桌面/手机界面通过本地银行替身完成沙箱标签、支付链接检查（未导航）、付款查询、退款冻结与退款确认；页面无异常或横向溢出。记录为alipay-ui/result.json，截图同目录。脚本alipay_browser_check.py不会访问支付宝付款页面。
- 另外通过独立子进程从临时合成密钥文件启动整个应用，验证环境变量选择沙箱Provider、读取密钥和健康检查；没有调用网关。
- 首次界面检查因状态文字同时匹配下拉选项和可见span而失败，修正定位后完整通过。服务在失败和成功时均已关闭。
- 11月23日Docker Hub EOF导致的失败保留在原测试目录；11月24日改用与Docker Hub官方摘要完全匹配的Google官方缓存后，新Compose构建、健康、学习页流程、重启持久化和备份恢复均通过。当前compose-result.json为passed。实际API镜像中非root、禁网、只读合成支付密钥检查通过，见alipay-container-result.json。真实支付网关仍未调用。

## 配置

本地安装backend/requirements-alipay.txt后，设置PAYMENT_PROVIDER=alipay_sandbox及上述服务端参数。私钥需为当前实现支持的PKCS#1 PEM，支付宝公钥为SPKI PEM，至少2048位；证书和服务商代调用尚未支持。凭证不要写入前端或聊天。

Dockerfile已包含所需RSA依赖。使用compose.alipay.yaml时，通过ALIPAY_PRIVATE_KEY_HOST_PATH和ALIPAY_PUBLIC_KEY_HOST_PATH提供部署主机上的绝对路径，仅只读挂载到API容器的/run/secrets目录，不把密钥复制进镜像。实际部署主机的文件权限、HTTPS反代、Cookie和回调可达性仍待验证。

## 仍待完成

实际签约应用及商户配置、远程沙箱付款/通知/退款、正式订单与原路退款、真实角色包交付、运营规则及人工核对流程。完整网站公网部署与GPU资源也尚未具备；不能将本地银行替身记录作为真实支付宝联调或收入证据。

官方依据：[网页收款指引](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/ai-web-app-payment-integration-guide.html)、[交易查询](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/api-list/alipay-trade-query.html)、[退款查询](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/api-list/alipay-trade-fastpay-refund-query.html)。
