# 支付宝服务端传输层 · 2026-11-23

本文件记录前一阶段的组件验证。后续Provider注册、HTTP路由与前端已完成本地模拟接入，当前范围与限制以alipay-integration-verification.md为准。
新增backend/alipay_gateway.py，用于页面支付URL、交易查询、退款及退款查询。该组件尚未被工坊PaymentProvider选用，没有真实网关调用。当前网页及订单仍使用Mock。

## 实现范围

- 沙箱与正式网关由服务端布尔配置选择，地址固定，不接受客户端URL。页面支付地址绑定应用、UUID订单号、服务端整数分金额和HTTPS站点回调。
- 使用rsa库的RSA2/SHA-256签名，最小2048位密钥。请求时间显式使用UTC+8，不依赖部署宿主的本地时区。
- HTTPX请求有20秒总期限、最多5秒连接等待，禁止重定向，解码后的响应上限128KiB；不记录交易正文或密钥。
- 保留业务响应JSON的原始字节片段进行签名校验，避免重序列化改变转义或空白；重复JSON字段、非有限数值、伪造签名及SHA-1均拒绝。
- 退款请求使用调用方持久化的UUID退款号，查询使用同一退款号。超时、异常响应或验签失败时标记结果未知，组件不会自动重试退款。

返回值只证明支付宝响应的签名和基本成功码。应用业务层仍必须核对订单、交易号、金额和退款结果，再以数据库事务修改订单与权益。调用方不能仅凭code=10000交付角色。

## 验证

tests/test_alipay_gateway.py使用两对不同的临时密钥与HTTPX MockTransport，未访问网络。10项测试覆盖页面支付签名、金额及回调源、保留JSON转义的验签、篡改、SHA-1、重复字段、非有限数值、超限响应、重定向，以及退款超时和固定请求号查询。实际完整回归结果登记于verification.md。

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-alipay.txt
.\.venv\Scripts\python.exe -m pytest tests/test_alipay_gateway.py -q
```

可选依赖为rsa 4.9.1与pyasn1 0.6.5。未安装时上述测试明确skip，基础Mock应用仍能运行；启用支付组件的环境必须安装并执行这些检查。官方完整SDK只用于上一轮离线对照，位于独立data/alipay-env，现已完成安装，未加入主应用和生产镜像。

## 尚未完成

需接入工坊Provider、支付模式与历史订单隔离、可信通知与主动查询、数据库幂等和交易号唯一性、退款状态与权益冻结/恢复、前端支付跳转及退款展示。实际支付宝签约应用、凭证、通知地址及远程沙箱与正式交易验收仍缺。真实支付与退款待办保持开放。

官方协议来源见[离线协议验证](alipay-contract-verification.md)。当前实现未复制完整SDK代码，仅按公开网关协议独立构造请求，使用维护的RSA与HTTP库。
