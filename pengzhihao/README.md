# 物流风控系统 AI_Risk

基于原 AI_Risk 风控核心迁移的物流寄递风控系统。业务覆盖寄递实名、禁限寄
物品、跨境申报、代收货款、异常地址和高频/凌晨寄件；规则引擎、案件、画像、
告警、评估历史和 XGBoost 双轨决策继续复用。

## 业务范围

- 实名收寄：证件只保存 SHA-256 哈希和掩码，识别未核验、信息不符和过期状态。
- 收寄验视：比对申报品类与验视结果，识别锂电池、化学品等禁限寄物品瞒报。
- 跨境申报：比较申报/实际重量、申报/海关评估价值及通关状态。
- 代收货款：统计 COD 拒收次数、拒收率和金额敞口。
- 地址风险：识别临时、偏远、首次使用和多人共用地址。
- 行为风险：识别七日高频和凌晨寄件。

设计参考：

- [邮件快件实名收寄管理办法](https://xxgk.mot.gov.cn/2020/gz/202112/t20211224_3632993.html)
- [禁止寄递物品管理规定](https://www.spb.gov.cn/gjyzj/c200047/201611/49447a84bdba429eb401a9e027c83f94.shtml)
- [快递暂行条例](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_ccea5d29862840979d0ff2304edabbb2.html)
- [海关进出境邮件常见问题](https://online.customs.gov.cn/ociswebserver/pages/jcjybcx/question.html)

本项目为教学演示，不构成合规或法律意见；所有初始化数据均为虚构数据。

## 核心复用边界

以下文件及 9 张风控表保持原样：

- `app/models_risk.py`、`sql/init_risk_tables.sql`
- `app/engine/decision.py`、`app/engine/rule.py`、`app/engine/ml_model.py`
- `risk_rule / risk_event / risk_feature / risk_assessment / risk_case`
- `risk_blacklist / risk_user_profile / risk_action_log / risk_alert`

业务层只有 5 张表：`user_info`、`address`、`shipment`、`shipment_item`、
`blacklist_extra`。`OrderInfo` 与 `ReceiveInfo` 只是供未修改核心引擎使用的 ORM
别名，不会创建电商表。

### 事件适配

| 对外物流事件 | 核心 ENUM | source_id |
|---|---|---|
| 寄件受理 | 下单 | shipment_id |
| 安检验视 | 支付 | shipment_id |
| 跨境申报 | 售后申请 | shipment_id |
| 代收货款 | 物流投诉 | shipment_id |

`process_event` 保持四步：业务校验 → 运单/地址补全和枚举适配 → 黑名单前置
拦截 → 调用 `run_risk_check` 七步核心流水线。

## 安装和运行

需要 Python 3.11+、MySQL 8.0。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

修改 `.env` 中的 MySQL 账号后执行：

```powershell
python scripts/init_db.py --db logistics_risk --reset --yes
python scripts/gen_train_dataset.py --reset
python scripts/train_xgb_model.py
python run_app.py
```

访问 <http://localhost:8000>。`init_db.py --reset` 会删除目标数据库；默认目标是
独立演示库 `logistics_risk`，不要把参数改成存有业务数据的数据库。

一条龙命令：

```powershell
python scripts/one_command.py --start
```

## 风险检查 API

公开请求严格只有四个字段：

```http
POST /api/risk/check
Content-Type: application/json

{
  "event_type": "安检验视",
  "source_id": "SHP0001",
  "user_id": "U_DANGER",
  "event_data": {"channel": "demo"}
}
```

演示风险用户：`U_RNAME / U_DANGER / U_CROSS / U_COD / U_FREQ / U_ADDR`。
运单可从 `shipment` 表或风险检查页选择；固定造数中 `SHP0001` 起共 300 条。

事件业务校验：

- 所有事件要求运单存在且属于请求寄件人。
- 安检验视要求至少一条物品明细。
- 跨境申报只接受 `is_cross_border=1` 的运单。
- 代收货款只接受 `payment_type='代收货款'` 的运单。

## 25 维兼容特征

XGBoost 特征键不变，物流语义如下：

| 兼容键 | 物流含义 |
|---|---|
| user_total_orders | 历史寄件总数 |
| user_orders_30d / user_orders_7d | 近 30/7 天寄件数 |
| user_total_amount / user_avg_order_amount / user_max_order_amount | COD 总/均/最大敞口 |
| user_refund_count / user_refund_rate / user_refund_amount | COD 拒收次数/率/金额 |
| user_postsale_count / user_postsale_rate | 危险品验视异常次数/率 |
| user_cancel_count | 取消或拒收退回次数 |
| user_complaint_count | 实名异常标志 |
| user_address_count | 寄件人使用的收件地址数 |
| order_total_amount | 当前运单申报价值 |
| order_item_count / order_sku_count | 物品行数/数量 |
| order_discount_amount / order_discount_rate | 重量偏差值/偏差率 |
| order_pay_interval_sec | 创建到揽收间隔秒数 |
| order_is_night | 是否凌晨寄件 |
| order_category_count | 未申报危险品明细数 |
| addr_total_count | 当前标准化地址关联寄件人数 |
| addr_province_count | 寄件人目的省份数 |
| addr_is_new | 新、临时或偏远地址标志 |

风控核心表中的 `订单` 实体和画像字段名同样保持兼容，页面分别显示为运单、
COD 拒收和物流异常含义。

## 规则与黑名单

初始化包含 `L001-L010` 十条规则，覆盖实名异常、危险品瞒报、跨境重量、
高价值跨境件、COD 拒收、高频、凌晨和地址风险。

核心黑名单 API `/api/blacklist` 支持寄件人、收件地址、联系电话，对应核心表
原有用户、地址、手机号 ENUM。扩展 API `/api/blacklist/extra` 支持实名证件哈希、
设备指纹、IP 地址、海关主体；两类名单都在决策前短路拦截。

## 数据、模型和测试

```powershell
# 重建 80 用户、100 地址、300 运单和物品明细
python scripts/gen_business_data.py

# 重新生成静态初始化 SQL
python scripts/gen_business_data.py --emit-sql sql/init_business_data.sql --emit-only

# 生成真实七步流水的特征快照并训练
python scripts/gen_risk_data.py --reset
python scripts/train_xgb_model.py

# 测试
pytest -q
```

训练标签取自虚构运单的 `shipment.risk_label`，而不是规则决策结果，避免把规则
输出直接当标签造成目标泄漏。验收阈值为 `val_auc >= 0.70`、`val_f1 >= 0.50`。

---

![](.\IMG\屏幕截图_12-8-2026_111937_0.0.0.0.jpeg)

![](.\IMG\屏幕截图_12-8-2026_111844_0.0.0.0.jpeg)

![](.\IMG\屏幕截图_12-8-2026_111724_0.0.0.0.jpeg)
