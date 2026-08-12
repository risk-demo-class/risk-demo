# AI_Risk Bank Edition

银行业务风控版本，基于事件驱动、25 维特征、业务规则和 XGBoost 双轨融合构建。

## 业务场景

- 信用卡申请
- 贷款申请
- 大额转账
- 异常登录

## 快速开始

```powershell
python scripts/init_db.py --reset --yes
python run_app.py
```

访问 `http://localhost:8000/risk/check` 进行风险检查。

完整项目介绍：`docs/项目介绍_银行风控版.md`   
修改任务书：`docs/银行风控项目修改任务书意见书.md`

## 架构

```text
银行业务表 → 银行事件 → 25 维特征快照
                  ├→ 业务规则轨
                  └→ XGBoost 模型轨
                         ↓
                    双轨融合 + veto
                         ↓
风险评估 → 人工案件 / 客户画像 / 审计日志 / 运营告警
```

注意：所有身份证、银行卡、设备指纹和 IP 均为脱敏或虚拟数据；本项目是教学风控原型，不接入真实征信和真实放款。
