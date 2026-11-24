# 支付宝协议验证 · 2026-11-23

使用官方alipay-sdk-python 3.7.1411和隔离data/alipay-env验证页面支付请求及通知签名。相互独立的商户与支付宝两对临时2048位RSA密钥仅存内存，应用号、收款方和订单均为合成值；没有调用支付宝网关，没有真实付款或退款。15项检查通过，结果见alipay-contract-result.json，依赖锁定见alipay-environment.txt，pip check通过。

## 已完成的工程部分

官方SDK构造沙箱页面支付URL，检查请求签名实际使用SHA-256、目标为沙箱网关、订单号与服务端9.90元快照一致。测试只解析URL，不打开支付页。

新增backend/alipay_protocol.py作为尚未接入运行路由的通知校验模块。它限定16KiB、128个表单字段、UTF-8和唯一字段名；校验签名真实算法为SHA-256，再核对可信订单快照的应用、收款方、订单号与金额。金额按十进制转换成分，不接受指数或超出分精度的表示。交易关闭通知不视为支付成功。

测试覆盖商户密钥不能冒充支付宝签发通知、正确通知，以及重新签名后仍属于其他应用、收款方、订单、金额的通知；还覆盖篡改、重复字段、指数金额、多余小数位和把SHA-1签名标为RSA2。测试观察到SDK通用verify_with_rsa会接受有效SHA-1，因此本模块另外检查底层rsa.verify返回的哈希算法。本观察仅描述这个通用函数的行为，不代表完成SDK整体安全评估。

当前PaymentProvider与工坊路由仍使用Mock，未开放真实回调、真实订单和退款。新模块不会自行发放权益或调用资金接口，SDK也未加入主应用依赖及生产镜像。

## 接入与真实验收尚需完成

1. 将支付宝作为独立Provider接入订单快照，明确区分Mock、沙箱和正式模式；历史Mock订单不能切换成真实收款。
2. 根据官方应用及密钥类型配置服务端，核对具体收款产品、卖家身份及通知字段；当前原型仅支持直接商户、公钥模式，证书及服务商代调用需另行实现。
3. 通知验签后主动查询并核对交易，再复用应用事务发一次权益。支付状态和退款状态应单调推进，不能让迟到支付通知恢复已退款订单。重复通知、并发查询和跨订单交易号须有数据库约束与回归。
4. 退款先冻结未使用权益，固定退款请求号；超时先查退款结果，再决定是否重试。运行中任务与已交付角色的退款政策需结合实际商品约定实现。
5. 使用有效应用、已签约账号、真实回调地址及沙箱账户完成远程验证，再执行已授权的正式支付和原路退款验收。

页面同步返回不能直接触发权益。SDK默认使用宿主本地时间构造时间戳，部署时需核对支付宝时区要求与宿主时区。还需验证SDK实际网络超时、响应签名与响应大小约束。以上事项尚未由本轮离线结果证明。

## 复跑

```powershell
.\data\alipay-env\Scripts\python.exe scripts/alipay_contract_check.py
```

此脚本无需.env或商户凭证，协议测试本身的网络调用数为零。隔离环境安装包时需要访问PyPI。

## 官方来源

- [Vibe Pay网页收款、交易查询与退款指引](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/ai-web-app-payment-integration-guide.html)
- [官方Python SDK仓库](https://github.com/alipay/alipay-sdk-python-all)
- [SDK 3.7.1411发行包](https://pypi.org/project/alipay-sdk-python/3.7.1411/)
- [SDK签名工具](https://github.com/alipay/alipay-sdk-python-all/blob/master/alipay/aop/api/util/SignatureUtils.py)
- [SDK Apache-2.0许可证](https://github.com/alipay/alipay-sdk-python-all/blob/master/LICENSE)

发布时应按实际包含的SDK与依赖保留许可证和通知；当前隔离环境不随网站分发。
