# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

用户已指定 Python 为主要脚本语言。本次实现采用 FastAPI、Jinja2、SQLAlchemy 2、MySQL 8、XGBoost、原生 JavaScript 与 Bootstrap 5.3。部署目标是用户本地 Docker MySQL，Web 服务本地运行。

## Users

- 风控分析师：在入账和出款审核场景快速识别风险、查看命中证据并处置案件。
- 风控策略运营：维护规则、观察命中率与误报风险、核对模型效果。
- 合规与调查人员：追踪商户、付款人、虚拟账户、贸易单据、资金流和关联网络。

以上角色来自用户提供的参考项目和架构图，属于本次实现假设，后续可按真实组织分工调整。

## Product Purpose

面向 PingPong 跨境收款业务构建可运行的风控演示系统。系统把商户、店铺、虚拟账户、付款人、贸易订单与单据、入账、换汇和出款数据转为可解释特征，通过业务规则与 XGBoost 双轨评分，输出通过、标记、人工审核或拒绝，并保留案件与审计证据。

成功标准是：至少 20 条跨境收付规则可执行；模型可以从 MySQL 数据训练并报告 `val_auc` 与 `val_f1`；关键风险数据可通过 Web 工作台和 API 查询；模拟数据与真实生产结论明确区分。

## Positioning

系统以“贸易背景真实性 + 资金来源与去向一致性 + 账户和设备关联网络”为核心，而不是复用电商订单、退款率和收货地址等特征。

## Operating Context

典型链路为：商户入驻与 KYC、平台店铺或外贸买家绑定、虚拟收款账户入账、贸易材料审核、资金从暂存转可用、换汇、提现或供应商付款、风险案件调查与规则效果复盘。

## Capabilities and Constraints

- 使用当前目录已有的 25 张 SQLAlchemy 业务表与 `pingpong` MySQL 数据库。
- 模型标签来自合成业务结果和案件信息，是演示用弱监督标签，不代表真实欺诈认定。
- 所有姓名、账户、交易、损失和模型指标均为合成或本地运行结果。
- 规则极高风险命中可一票否决；模型不可覆盖制裁等业务红线。
- 生产系统仍需接入正式名单、地理位置、设备指纹、银行回执、平台授权和人工案件反馈。

## Brand Commitments

产品名使用“PingPong 跨境收款风控”。界面参考用户给出的 AI_Risk 架构，但不复制电商业务字段。语言为严谨、克制、面向风控操作人员的中文。

## Evidence on Hand

- 业务说明：[PingPong跨境收款风控业务说明.md](PingPong跨境收款风控业务说明.md)
- SQLAlchemy 模型：[models.py](models.py)
- MySQL DDL：[schema.sql](schema.sql)
- 合成数据脚本：[seed_data.py](seed_data.py)
- 用户提供的架构图：`/Users/ayan/Desktop/exec-d0e6efb0-88d9-4609-8ca3-eb780fc5d88a.png`
- 参考项目：`/Users/ayan/PycharmProjects/PythonProject/AI_Risk`
- 没有真实生产欺诈标签、内部策略阈值、商业损失数据或公司内部名单。本项目不得虚构这些事实。

## Product Principles

1. 每个决策都能追溯到原始业务字段、特征快照、规则命中和模型版本。
2. 交易时点可得特征与事后调查特征严格区分，避免训练和线上推理泄漏。
3. 规则负责明确红线，模型识别多弱信号组合，人工审核处理不确定性。
4. 高密度界面优先服务扫描、筛选、比较和处置，不做营销式装饰。
5. 合成标签和模型指标始终明确标注，不冒充生产效果。

## Accessibility & Inclusion

本次 Web 工作台目标为 WCAG AA 基础对比度、完整键盘焦点、语义化表格、移动端结构性折叠，并尊重减少动态效果偏好。
