"""
制造业风控系统 - 业务数据生成脚本 (可重复运行, INSERT IGNORE 幂等)

生成内容:
  1. 基础数据集 (24 用户 + 10 产品 + 12 经销商 + 120 订单 + 40 保修工单
     + 20 串货举报 + 6 行业黑名单 ≈ 230 行业务数据)
  2. RISK 高风险经销商 (默认 5 种风险模式 × N, 与规则 R001-R026 一一对应):
     模式 1 高保修率       → R015 (保修率>=80%)
     模式 2 30天高频订货   → R007 (30 天>=30 单)
     模式 3 套保+维修费异常 → R008 + R018 (同一 SN 90 天 2 次维修 + 费用>60%MSRP)
     模式 4 跨区串货       → R001 + R026 (一单被举报 3 次 + 跨区大单)
     模式 5 新经销商大单   → R012 + R005 (签约<30 天 + 首单>=50万/100万)

用法:
  python scripts/gen_business_data.py                # 基础 + 5 个 RISK 用户入库
  python scripts/gen_business_data.py --count 30     # 30 个 RISK 用户 (6 套 × 5 模式)
  python scripts/gen_business_data.py --emit-sql     # 导出基础数据集 SQL (→ sql/init_business_data.sql)
  python scripts/gen_business_data.py --only-risky   # 只造 RISK 用户 (基础数据已由 init_db 导入)
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Windows GBK 终端兼容: 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# ============================================================
# 基础数据集 (确定性, 幂等)
# ============================================================

USERS = [
    # (user_id, name, role, dealer_level, region, phone, register_days_ago)
    ("D001", "华东恒力机电", "经销商", "一级", "华东", "13800000001", 1200),
    ("D002", "华南联创设备", "经销商", "一级", "华南", "13800000002", 900),
    ("D003", "华北精工贸易", "经销商", "二级", "华北", "13800000003", 600),
    ("D004", "西南川渝重工", "经销商", "二级", "西南", "13800000004", 500),
    ("D005", "华中楚天机械", "经销商", "二级", "华中", "13800000005", 400),
    ("D006", "西北丝路装备", "经销商", "三级", "西北", "13800000006", 300),
    ("D007", "华东申城智能", "经销商", "三级", "华东", "13800000007", 200),
    ("D008", "华南穗丰工业", "经销商", "三级", "华南", "13800000008", 180),
    ("D009", "华北津门机床", "经销商", "三级", "华北", "13800000009", 150),
    ("D010", "华东甬江精机", "经销商", "二级", "华东", "13800000010", 220),
    ("D011", "华南鹏城智造", "经销商", "二级", "华南", "13800000011", 260),
    ("D012", "西南渝州工业", "经销商", "三级", "西南", "13800000012", 120),
    ("T001", "终端用户甲", "终端用户", None, "华东", "13900000001", 800),
    ("T002", "终端用户乙", "终端用户", None, "华南", "13900000002", 700),
    ("T003", "终端用户丙", "终端用户", None, "华北", "13900000003", 650),
    ("T004", "终端用户丁", "终端用户", None, "西南", "13900000004", 500),
    ("T005", "终端用户戊", "终端用户", None, "华中", "13900000005", 400),
    ("T006", "终端用户己", "终端用户", None, "西北", "13900000006", 300),
    ("E001", "渠道经理王", "内部员工", None, "华东", "13700000001", 1000),
    ("E002", "渠道经理李", "内部员工", None, "华南", "13700000002", 900),
    ("E003", "售后主管张", "内部员工", None, "华北", "13700000003", 800),
    ("E004", "售后工程师赵", "内部员工", None, "华东", "13700000004", 700),
    ("E005", "风控专员钱", "内部员工", None, "华东", "13700000005", 600),
    ("E006", "商务专员孙", "内部员工", None, "华南", "13700000006", 500),
]

PRODUCTS = [
    # (product_id, name, model, category, msrp, warranty_months)
    ("P001", "数控机床", "CK6150", "工业母机", 250000, 24),
    ("P002", "注塑机", "HTF120X", "成型设备", 180000, 18),
    ("P003", "工业机器人", "ER6", "自动化", 120000, 24),
    ("P004", "检测设备", "CT-300", "检测仪器", 95000, 12),
    ("P005", "激光切割机", "LC-3015", "切割设备", 320000, 24),
    ("P006", "螺杆空压机", "GA-75", "通用设备", 68000, 12),
    ("P007", "高速电主轴", "DZ-120", "功能部件", 42000, 6),
    ("P008", "伺服电机", "SM-80", "功能部件", 15000, 12),
    ("P009", "PLC控制器", "PLC-300", "自动化", 8000, 12),
    ("P010", "精密减速机", "RV-110", "功能部件", 28000, 18),
]

DEALERS = [
    # (dealer_id, dealer_name, region, authorized_brands, contract_start_days_ago, contract_end_days_later, status)
    ("D001", "华东恒力机电", "华东", "CK系列,HTF系列", 1500, -120, "合作中"),   # 合同已过期 → R025
    ("D002", "华南联创设备", "华南", "CK系列,ER系列", 1100, 400, "合作中"),
    ("D003", "华北精工贸易", "华北", "LC系列,GA系列", 700, 300, "合作中"),
    ("D004", "西南川渝重工", "西南", "CK系列,HTF系列", 600, 250, "合作中"),
    ("D005", "华中楚天机械", "华中", "ER系列,CT系列", 500, 200, "合作中"),
    ("D006", "西北丝路装备", "西北", "GA系列,SM系列", 400, 150, "合作中"),
    ("D007", "华东申城智能", "华东", "ER系列,PLC系列", 300, 120, "合作中"),
    ("D008", "华南穗丰工业", "华南", "SM系列,RV系列", 250, 100, "合作中"),
    ("D009", "华北津门机床", "华北", "CK系列,CT系列", 200, 80, "合作中"),
    ("D010", "华东甬江精机", "华东", "CK系列,LC系列", 280, 90, "合作中"),
    ("D011", "华南鹏城智造", "华南", "HTF系列,ER系列", 320, 110, "合作中"),
    ("D012", "西南渝州工业", "西南", "GA系列,PLC系列", 150, 60, "合作中"),
]

# 订单模板: (order_id, dealer_id, product_id, quantity, price_factor, ship_to_region, status, days_ago, hour, order_type)
ORDERS = [
    ("ORD0001", "D001", "P001", 2, 0.95, "华东", "已完成", 80, 10, "经销商订货"),
    ("ORD0002", "D001", "P002", 3, 0.90, "华东", "已完成", 60, 14, "经销商订货"),
    ("ORD0003", "D001", "P001", 1, 0.98, "华东", "已取消", 45, 22, "经销商订货"),
    ("ORD0004", "D002", "P003", 4, 0.88, "华南", "已完成", 75, 9, "经销商订货"),
    ("ORD0005", "D002", "P004", 5, 0.92, "华南", "已完成", 55, 11, "经销商订货"),
    ("ORD0006", "D003", "P005", 1, 0.90, "华北", "已完成", 70, 13, "经销商订货"),
    ("ORD0007", "D003", "P006", 8, 0.85, "华北", "已完成", 50, 15, "经销商订货"),
    ("ORD0008", "D004", "P001", 2, 0.93, "西南", "已完成", 65, 10, "经销商订货"),
    ("ORD0009", "D005", "P003", 3, 0.89, "华中", "已完成", 40, 16, "经销商订货"),
    ("ORD0010", "D004", "P002", 5, 0.60, "华北", "已完成", 35, 3, "经销商订货"),   # 跨区+低价 → 串货举报目标
    ("ORD0011", "D006", "P006", 6, 0.86, "西北", "已完成", 30, 12, "经销商订货"),
    ("ORD0012", "D007", "P003", 2, 0.91, "华东", "已完成", 28, 9, "经销商订货"),
    ("ORD0013", "D008", "P008", 20, 0.78, "华南", "已完成", 25, 14, "经销商订货"),
    ("ORD0014", "D009", "P004", 3, 0.87, "华北", "已完成", 22, 10, "经销商订货"),
    ("ORD0015", "D010", "P001", 1, 0.94, "华东", "已完成", 20, 11, "经销商订货"),
    ("ORD0016", "D011", "P002", 2, 0.90, "华南", "已完成", 18, 15, "经销商订货"),
    ("ORD0017", "D012", "P006", 4, 0.84, "西南", "已完成", 16, 13, "经销商订货"),
    ("ORD0018", "D001", "P003", 2, 0.92, "华东", "已完成", 14, 10, "经销商订货"),
    ("ORD0019", "D002", "P001", 1, 0.96, "华南", "已完成", 12, 16, "经销商订货"),
    ("ORD0020", "D003", "P005", 1, 0.45, "华北", "已完成", 10, 4, "经销商订货"),   # 超低价 → R020
    ("ORD0021", "D004", "P004", 2, 0.88, "西南", "已完成", 9, 10, "经销商订货"),
    ("ORD0022", "D005", "P001", 1, 0.95, "华中", "已完成", 8, 11, "经销商订货"),
    ("ORD0023", "D006", "P003", 2, 0.90, "西北", "已完成", 7, 9, "经销商订货"),
    ("ORD0024", "D007", "P006", 3, 0.82, "华东", "已完成", 6, 14, "经销商订货"),
    ("ORD0025", "D008", "P004", 2, 0.86, "华南", "已取消", 5, 20, "经销商订货"),
    ("ORD0026", "D009", "P001", 1, 0.97, "华北", "已完成", 4, 10, "经销商订货"),
    ("ORD0027", "D010", "P002", 2, 0.89, "华东", "已完成", 3, 15, "经销商订货"),
    ("ORD0028", "D011", "P003", 3, 0.85, "华南", "已完成", 2, 9, "经销商订货"),
    ("ORD0029", "D012", "P005", 1, 0.92, "西南", "已完成", 1, 12, "经销商订货"),
    ("ORD0030", "D001", "P006", 5, 0.83, "华东", "已完成", 0, 11, "经销商订货"),
    # R002 出保场景: 1000 天前的老订单 (P004 保修 12 个月已过期), 配 W0023/W0024 两次保修
    ("ORD0050", "D010", "P004", 1, 0.95, "华东", "已完成", 1000, 10, "经销商订货"),
    # 采购订单 (order_type=采购订单, R003 大额采购)
    ("ORD0031", "D002", "P001", 4, 0.90, "华南", "已完成", 30, 10, "采购订单"),
    ("ORD0032", "D003", "P005", 3, 0.88, "华北", "已完成", 20, 14, "采购订单"),
    ("ORD0033", "D005", "P003", 6, 0.87, "华中", "已完成", 15, 9, "采购订单"),
    ("ORD0034", "D007", "P002", 5, 0.85, "华东", "已完成", 10, 11, "采购订单"),
    ("ORD0035", "D010", "P001", 5, 0.89, "华东", "已完成", 8, 13, "采购订单"),
    # 批量普通订单 (覆盖 30 天趋势)
    *[(f"ORD{i:04d}", f"D{(i % 12) + 1:03d}", f"P{(i % 10) + 1:03d}",
       (i % 8) + 1, round(0.80 + (i % 15) / 100, 2),
       ["华东", "华南", "华北", "西南", "华中", "西北"][i % 6],
       "已完成" if i % 10 != 3 else "已取消", (i % 60) + 1, (i * 3) % 24, "经销商订货")
    for i in range(36, 121) if i != 50],
]

# 保修工单模板: (warranty_id, product_sn, order_id, days_ago, issue_type, cost_factor, technician_id, description)
WARRANTIES = [
    ("W0001", "SN-D001-0001", "ORD0001", 70, "保修", 0.05, "TEC001", "主轴异响"),
    ("W0002", "SN-D001-0001", "ORD0001", 55, "维修", 0.12, "TEC002", "主轴异响复检"),
    ("W0003", "SN-D002-0001", "ORD0004", 60, "保修", 0.04, "TEC003", "机械臂抖动"),
    ("W0004", "SN-D003-0001", "ORD0006", 50, "保修", 0.06, "TEC001", "切割精度下降"),
    ("W0005", "SN-D004-0001", "ORD0008", 45, "维修", 0.10, "TEC004", "主轴更换"),
    ("W0006", "SN-D005-0001", "ORD0009", 40, "保修", 0.03, "TEC002", "控制器报错"),
    ("W0007", "SN-D006-0001", "ORD0011", 35, "保修", 0.05, "TEC003", "压力不足"),
    ("W0008", "SN-D007-0001", "ORD0012", 30, "维修", 0.08, "TEC001", "减速机漏油"),
    ("W0009", "SN-D008-0001", "ORD0013", 25, "保修", 0.02, "TEC005", "编码器故障"),
    ("W0010", "SN-D009-0001", "ORD0014", 20, "维修", 0.09, "TEC004", "检测头校准"),
    ("W0011", "SN-D010-0001", "ORD0015", 15, "保修", 0.04, "TEC002", "丝杠磨损"),
    ("W0012", "SN-D011-0001", "ORD0016", 12, "维修", 0.11, "TEC001", "注塑压力异常"),
    ("W0013", "SN-D012-0001", "ORD0017", 10, "保修", 0.05, "TEC003", "电磁阀故障"),
    ("W0014", "SN-D001-0002", "ORD0018", 8, "维修", 0.13, "TEC005", "机器人减速机更换"),
    ("W0015", "SN-D002-0002", "ORD0019", 6, "保修", 0.03, "TEC002", "面板无显示"),
    ("W0016", "SN-D003-0002", "ORD0020", 5, "维修", 0.55, "TEC004", "激光器烧毁",),  # 费用>50%MSRP 但<60%
    ("W0017", "SN-D004-0002", "ORD0021", 4, "保修", 0.04, "TEC001", "皮带松动"),
    ("W0018", "SN-D005-0002", "ORD0022", 3, "维修", 0.10, "TEC003", "刀架异响"),
    ("W0019", "SN-D006-0002", "ORD0023", 2, "保修", 0.02, "TEC005", "传感器失灵"),
    ("W0020", "SN-D007-0002", "ORD0024", 1, "维修", 0.08, "TEC002", "空压机机头更换"),
    ("W0021", "SN-D010-0002", "ORD0015", 2, "维修", 0.65, "TEC099", "主轴总成更换"),  # 费用>60%MSRP → R018 + 黑维修工
    ("W0022", "SN-D010-0002", "ORD0015", 1, "维修", 0.70, "TEC099", "主轴总成复换"),  # 同一 SN 90 天 2 次维修 → R008
    # R002 场景: 出保设备 + 90 天内 2 次保修 (ORD0050 为 1000 天前老订单)
    ("W0023", "SN-D010-OLD1", "ORD0050", 20, "保修", 0.08, "TEC001", "出保后申请保修"),
    ("W0024", "SN-D010-OLD1", "ORD0050", 15, "保修", 0.09, "TEC002", "出保后再次申请"),
    *[(f"W{i:04d}", f"SN-D{(i % 12) + 1:03d}-N{i}", f"ORD{(i % 120) + 1:04d}",
       (i % 40) + 5, "保修" if i % 3 else "维修", round(0.02 + (i % 10) / 100, 2),
       f"TEC{(i % 5) + 1:03d}", "例行保养/小修")
    for i in range(25, 41)],
]

# 串货举报模板: (order_id, dealer_id, ship_to_region, dealer_region, reporter_id, status, days_ago)
REPORTS = [
    ("ORD0010", "D004", "华北", "西南", "E001", "已核实", 30),
    ("ORD0010", "D004", "华北", "西南", "E002", "已核实", 28),
    ("ORD0010", "D004", "华北", "西南", "E006", "待核实", 25),   # 同一订单 3 次举报 → R001
    ("ORD0004", "D002", "华南", "华南", "E001", "无效", 40),
    ("ORD0006", "D003", "华北", "华北", "E002", "无效", 38),
    ("ORD0020", "D003", "华北", "华北", "E006", "待核实", 8),
    ("ORD0013", "D008", "华南", "华南", "E001", "待核实", 20),
    ("ORD0002", "D001", "华东", "华东", "E002", "无效", 50),
    ("ORD0011", "D006", "西北", "西北", "E003", "无效", 26),
    ("ORD0016", "D011", "华南", "华南", "E006", "待核实", 15),
    *[(f"ORD{i % 120 + 1:04d}", f"D{(i % 12) + 1:03d}",
       ["华东", "华南", "华北", "西南", "华中", "西北"][i % 6],
       ["华东", "华南", "华北", "西南", "华中", "西北"][(i + 1) % 6],
       f"E{(i % 6) + 1:03d}", "待核实" if i % 3 else "无效", (i % 30) + 1)
    for i in range(10, 20)],
]

# 行业黑名单: (type, value, reason, expire_days)
BLACKLIST_EXTRA = [
    ("经销商", "D008", "多次跨区串货, 渠道投诉", None),
    ("设备SN", "SN-D010-0002", "套保嫌疑设备 (90 天 2 次维修)", None),
    ("设备SN", "SN-BLK-0002", "盗版翻新设备", None),
    ("维修工", "TEC099", "虚报维修费用", None),
    ("维修工", "TEC005", "维修记录造假", 90),
    ("经销商", "D013", "历史欺诈经销商 (注销)", None),
]


def _q(v) -> str:
    """SQL 字面量: None → NULL, 数字 → 原样, 其他 → 单引号包裹."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _date_expr(days_ago: int, hour: int = 10) -> str:
    """相对日期 SQL 表达式: DATE_SUB(NOW(), INTERVAL x DAY) + 指定小时."""
    return (
        f"DATE_SUB(DATE_SUB(NOW(), INTERVAL {days_ago} DAY), "
        f"INTERVAL {24 - hour} HOUR)"
    )


def build_base_sql() -> list[str]:
    """构建基础数据集 INSERT IGNORE 语句 (确定性)."""
    stmts: list[str] = []

    # 1. 用户
    stmts.append(
        "INSERT IGNORE INTO user_info (user_id, name, role, dealer_level, region, phone, register_at) VALUES\n"
        + ",\n".join(
            f"({_q(uid)}, {_q(name)}, {_q(role)}, {_q(level)}, {_q(region)}, {_q(phone)}, {_date_expr(days)})"
            for uid, name, role, level, region, phone, days in USERS
        )
    )
    # 2. 产品
    stmts.append(
        "INSERT IGNORE INTO product (product_id, name, model, category, msrp, warranty_months) VALUES\n"
        + ",\n".join(
            f"({_q(pid)}, {_q(name)}, {_q(model)}, {_q(cat)}, {msrp}, {wm})"
            for pid, name, model, cat, msrp, wm in PRODUCTS
        )
    )
    # 3. 经销商
    stmts.append(
        "INSERT IGNORE INTO dealer_info (dealer_id, dealer_name, region, authorized_brands, contract_start, contract_end, status) VALUES\n"
        + ",\n".join(
            f"({_q(did)}, {_q(name)}, {_q(region)}, {_q(brands)}, "
            f"{_date_expr(start)}, {_date_expr(-end)}, {_q(status)})"
            for did, name, region, brands, start, end, status in DEALERS
        )
    )
    # 4. 订单 (先算出 msrp 映射)
    msrp_map = {pid: msrp for pid, _, _, _, msrp, _ in PRODUCTS}
    order_rows = []
    for oid, did, pid, qty, factor, region, status, days, hour, otype in ORDERS:
        msrp = msrp_map[pid]
        unit_price = round(msrp * factor)
        total = unit_price * qty
        order_rows.append(
            f"({_q(oid)}, {_q(otype)}, {_q(did)}, {_q(pid)}, {qty}, {unit_price}, {total}, "
            f"{_q(region)}, {_q(status)}, {_date_expr(days, hour)})"
        )
    stmts.append(
        "INSERT IGNORE INTO order_info (order_id, order_type, dealer_id, product_id, quantity, unit_price, total_amount, ship_to_region, order_status, create_time) VALUES\n"
        + ",\n".join(order_rows)
    )
    # 5. 保修工单
    war_rows = []
    for wid, sn, oid, days, itype, cost_factor, tec, desc in WARRANTIES:
        # 费用按该订单产品 MSRP 的比例计算
        order = next((o for o in ORDERS if o[0] == oid), None)
        pid = order[2] if order else "P001"
        cost = round(msrp_map[pid] * cost_factor)
        war_rows.append(
            f"({_q(wid)}, {_q(sn)}, {_q(oid)}, {_date_expr(days)}, {_q(itype)}, {cost}, "
            f"{_q(tec)}, {_q(desc)})"
        )
    stmts.append(
        "INSERT IGNORE INTO warranty_record (warranty_id, product_sn, order_id, issue_date, issue_type, repair_cost, technician_id, description) VALUES\n"
        + ",\n".join(war_rows)
    )
    # 6. 串货举报
    rep_rows = []
    for oid, did, ship_region, dealer_region, reporter, status, days in REPORTS:
        rep_rows.append(
            f"({_q(oid)}, {_q(did)}, {_q(ship_region)}, {_q(dealer_region)}, {_q(reporter)}, "
            f"{_q(status)}, {_date_expr(days)})"
        )
    stmts.append(
        "INSERT IGNORE INTO cross_region_report (order_id, dealer_id, ship_to_region, dealer_region, reporter_id, report_status, create_time) VALUES\n"
        + ",\n".join(rep_rows)
    )
    # 7. 行业黑名单
    bl_rows = [
        f"({_q(t)}, {_q(v)}, {_q(reason)}, "
        f"{'DATE_ADD(NOW(), INTERVAL ' + str(d) + ' DAY)' if d else 'NULL'}, NOW())"
        for t, v, reason, d in BLACKLIST_EXTRA
    ]
    stmts.append(
        "INSERT IGNORE INTO blacklist_extra (type, value, reason, expire_at, create_time) VALUES\n"
        + ",\n".join(bl_rows)
    )
    return stmts


# ============================================================
# RISK 高风险经销商 (5 种模式, 跟规则一一对应)
# ============================================================

def build_risk_sql(count: int = 5) -> list[str]:
    """构建 N 个 RISK 高风险经销商 + 业务数据 (INSERT IGNORE, 幂等)."""
    stmts: list[str] = []
    user_rows = []
    dealer_rows = []
    order_rows = []
    war_rows = []
    rep_rows = []

    for idx in range(count):
        mode = idx % 5
        uid = f"RISK{idx + 1:03d}"
        region = ["华东", "华南", "华北", "西南", "华中"][mode]
        # 用户 + 经销商档案 (模式 5 新签约: contract_start 10 天前)
        user_rows.append(
            f"({_q(uid)}, {_q('高风险经销商' + uid[4:])}, '经销商', '一级', {_q(region)}, "
            f"{_q('1360000' + str(1000 + idx))}, {_date_expr(30 if mode == 4 else 300)})"
        )
        start = 10 if mode == 4 else 365
        end = 300 if mode == 4 else 600
        dealer_rows.append(
            f"({_q(uid)}, {_q('RISK机电' + uid[4:])}, {_q(region)}, '全品牌', "
            f"{_date_expr(start)}, {_date_expr(-end)}, '合作中')"
        )

        if mode == 0:
            # 模式 1: 高保修率 (10 单 + 9 保修 → 保修率 90%)
            for i in range(1, 11):
                oid = f"ORD_{uid}_{i:02d}"
                order_rows.append(
                    f"({_q(oid)}, '经销商订货', {_q(uid)}, 'P001', 2, 240000, 480000, "
                    f"{_q(region)}, '已完成', {_date_expr(max(1, 30 - i * 3), 10)})"
                )
            for i in range(1, 10):
                war_rows.append(
                    f"({_q('W_' + uid + '_' + f'{i:02d}')}, {_q(f'SN-{uid}-000{i}')}, "
                    f"{_q(f'ORD_{uid}_{i:02d}')}, {_date_expr(max(1, 28 - i * 3))}, '保修', "
                    f"12000, 'TEC001', '高频保修样本')"
                )
        elif mode == 1:
            # 模式 2: 30 天高频订货 (35 单)
            for i in range(35):
                oid = f"ORD_{uid}_{i:02d}"
                order_rows.append(
                    f"({_q(oid)}, '经销商订货', {_q(uid)}, 'P009', 10, 7000, 70000, "
                    f"{_q(region)}, '已完成', {_date_expr(i % 28 + 1, 9 + i % 8)})"
                )
        elif mode == 2:
            # 模式 3: 套保 + 维修费用异常 (同一 SN 90 天 2 次维修 + 费用>60%MSRP)
            for i, day in enumerate([15, 10, 5], 1):
                oid = f"ORD_{uid}_{i:02d}"
                order_rows.append(
                    f"({_q(oid)}, '经销商订货', {_q(uid)}, 'P004', 1, 90000, 90000, "
                    f"{_q(region)}, '已完成', {_date_expr(day, 10)})"
                )
            war_rows += [
                f"('W_{uid}_01', 'SN-{uid}-0001', 'ORD_{uid}_03', {_date_expr(3)}, '维修', 65000, 'TEC003', '套保维修1')",
                f"('W_{uid}_02', 'SN-{uid}-0001', 'ORD_{uid}_03', {_date_expr(1)}, '维修', 70000, 'TEC003', '套保维修2')",
                f"('W_{uid}_03', 'SN-{uid}-0002', 'ORD_{uid}_02', {_date_expr(6)}, '保修', 5000, 'TEC001', '常规保修')",
            ]
        elif mode == 3:
            # 模式 4: 跨区串货 (一单被举报 3 次 + 跨区大单)
            for i, (day, amount, ship) in enumerate([(12, 350000, "华北"), (8, 150000, "华中")], 1):
                oid = f"ORD_{uid}_{i:02d}"
                order_rows.append(
                    f"({_q(oid)}, '经销商订货', {_q(uid)}, 'P001', "
                    f"{amount // 240000}, 240000, {amount}, {_q(ship)}, '已完成', {_date_expr(day, 10)})"
                )
            for i in range(1, 4):
                rep_rows.append(
                    f"('ORD_{uid}_01', {_q(uid)}, '华北', {_q(region)}, 'E001', '待核实', {_date_expr(12 - i)})"
                )
        else:
            # 模式 5: 新经销商大单 (签约<30 天, 首单 50 万 + 100 万)
            for i, (day, amount) in enumerate([(5, 500000), (2, 1200000)], 1):
                oid = f"ORD_{uid}_{i:02d}"
                order_rows.append(
                    f"({_q(oid)}, '经销商订货', {_q(uid)}, 'P005', "
                    f"{amount // 300000}, 300000, {amount}, {_q(region)}, '已完成', {_date_expr(day, 10)})"
                )

    stmts.append(
        "INSERT IGNORE INTO user_info (user_id, name, role, dealer_level, region, phone, register_at) VALUES\n"
        + ",\n".join(user_rows)
    )
    stmts.append(
        "INSERT IGNORE INTO dealer_info (dealer_id, dealer_name, region, authorized_brands, contract_start, contract_end, status) VALUES\n"
        + ",\n".join(dealer_rows)
    )
    if order_rows:
        stmts.append(
            "INSERT IGNORE INTO order_info (order_id, order_type, dealer_id, product_id, quantity, unit_price, total_amount, ship_to_region, order_status, create_time) VALUES\n"
            + ",\n".join(order_rows)
        )
    if war_rows:
        stmts.append(
            "INSERT IGNORE INTO warranty_record (warranty_id, product_sn, order_id, issue_date, issue_type, repair_cost, technician_id, description) VALUES\n"
            + ",\n".join(war_rows)
        )
    if rep_rows:
        stmts.append(
            "INSERT IGNORE INTO cross_region_report (order_id, dealer_id, ship_to_region, dealer_region, reporter_id, report_status, create_time) VALUES\n"
            + ",\n".join(rep_rows)
        )
    return stmts


def _emit_sql(stmts: list[str], header: str) -> None:
    lines = [f"-- {header}", "SET NAMES utf8mb4;"]
    for stmt in stmts:
        lines.append(stmt + ";")
    return "\n".join(lines) + "\n"


async def _run(stmts: list[str]) -> None:
    """在 MySQL 中执行一组语句并 commit."""
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        for stmt in stmts:
            await conn.execute(text(stmt))
        await conn.commit()
        print(f"  执行 {len(stmts)} 条批量 INSERT 完成")
    await engine.dispose()


async def _stats() -> None:
    """打印业务表行数统计."""
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        for tbl in ("user_info", "product", "dealer_info", "order_info",
                    "warranty_record", "cross_region_report", "blacklist_extra"):
            r = await conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  {tbl:<22} {r.scalar()} 行")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="制造业业务数据生成 (基础 230 行 + RISK 高风险经销商, INSERT IGNORE 幂等).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--count", type=int, default=5, help="RISK 高风险经销商数量 (默认 5)")
    parser.add_argument("--emit-sql", action="store_true", help="只打印基础数据集 SQL, 不连库")
    parser.add_argument("--out", type=str, default=None, help="配合 --emit-sql: 直接写入文件 (UTF-8)")
    parser.add_argument("--only-risky", action="store_true", help="只造 RISK 用户 (基础数据已导入)")
    args = parser.parse_args()

    if args.emit_sql:
        sql_text = _emit_sql(
            build_base_sql(),
            "制造业风控系统 - 基础业务数据 (由 gen_business_data.py --emit-sql 导出)",
        )
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(sql_text)
            print(f"已写入: {args.out}")
        else:
            print(sql_text, end="")
        sys.exit(0)

    async def _main():
        base = [] if args.only_risky else build_base_sql()
        risky = build_risk_sql(args.count)
        print("=" * 60)
        print(f"制造业业务数据生成 (基础 {len(base)} 组 + RISK {args.count} 个经销商)")
        print("=" * 60)
        if base:
            print("[1/3] 写入基础数据集...")
            await _run(base)
        print("[2/3] 写入 RISK 高风险经销商...")
        await _run(risky)
        print("[3/3] 统计:")
        await _stats()

    asyncio.run(_main())
