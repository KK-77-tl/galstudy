# 支付宝业务适配器 · 2026-11-23

本文件记录前一阶段的组件验证。后续Provider注册、HTTP路由与前端已完成本地模拟接入，当前范围与限制以alipay-integration-verification.md为准。
backend/alipay_provider.py将已验签的网关结果转换为内部支付/退款凭据，并提供服务端配置入口。该类尚未注册到运行中的PaymentProvider，未公开新支付路由或付款按钮；本机继续Mock。

## 当前能力

- 构造时绑定沙箱或正式网关、应用、收款方和HTTPS站点。历史Mock或另一环境的订单不能被本适配器重新标记。
- 页面支付URL仅在订单待支付时提供，由服务端订单快照确定金额、币种和订单号。
- 通知先执行严格RSA2、app_id、seller_id、订单和金额验证。实际HTTP通知路由仍须在验签后调用主动查询，不能仅凭浏览器返回确认付款。
- 主动查询核对订单、总额、交易号、已知交易状态；响应若带应用或卖家字段也必须匹配。查询响应不一定返回卖家字段，因此直接商户的应用与账户对应关系仍须在真实配置验收时核对。等待支付且尚无交易号时不产生支付凭据。
- 退款提交绑定原订单、交易号、金额和持久化退款号，最终成功以同退款号查询的REFUND_SUCCESS及原订单/交易/金额匹配为依据。查询未返回成功状态时保持未知，不恢复权益。
- 仅支持直接商户、公钥模式；配置函数缺少应用、收款方、公私钥文件或HTTPS源时显式报错，不推测凭证，也不退回Mock冒充真实接入。

## 验证与范围

tests/test_alipay_provider.py以本地假网关模拟已经通过传输层验签的数据，15项测试覆盖混用环境、历史订单、错误应用/卖家/金额/交易号、未知状态、无最终交易号、重复查询稳定事件ID、退款号及退款金额核对、退款结果未知，以及配置缺失。传输层真实RSA2和响应体约束由test_alipay_gateway.py单独验证，当前测试不证明支付宝远程沙箱可用。

完整后端与PostgreSQL回归结果见verification.md和postgresql-result.json。本轮没有调用支付宝网关、没有真实付款或退款。

## 下一步

将适配器注册到payments.py，新增登录用户主动查询、可信通知、退款发起与查询路由，补齐调用前后数据库事务边界、并发提交和崩溃恢复；前端按订单自身模式展示Mock、沙箱和正式付款。完成应用级组合测试后，使用实际应用和凭证验收。当前不要仅通过修改PAYMENT_PROVIDER环境变量认为真实支付已启用。

参考：[交易查询字段](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/api-list/alipay-trade-query.html)、[退款查询字段与状态说明](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/api-list/alipay-trade-fastpay-refund-query.html)。退款查询可能暂时缺少成功字段，官方建议发起退款后留出处理时间再查询。
