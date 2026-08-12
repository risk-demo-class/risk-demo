"""
物流风控系统 - 造 RISK 高风险用户测试数据 (异步).

【物流版】以"物"(包裹/收件人) 为核心, 不再造电商订单/售后.
每个 RISK 用户包含: user_info + sender_info(实名) + receiver_info + parcel
(+ 危险品申报 dangerous_declaration / 代收货款 cod_transaction / 业务黑名单 blacklist_extra).

7 种物流风险模式轮换 (跟 8 条物流规则一一对应):
  模式 1: 未实名寄件 (real_name_status=未认证)          → 触发 R001 实名不一致
  模式 2: 危险品瞒报 (危险品 + 价值密度 < 50 元/kg)      → 触发 R002
  模式 3: 跨境违禁品 (国际件 + 危险品申报)               → 触发 R005 (拒绝)
  模式 4: COD 卷款   (COD 逾期 + 大额代收 ≥1000)        → 触发 R008 (拒绝)
  模式 5: 改派异常   (≥3 个收件人 + 高价值 ≥2000)       → 触发 R018
  模式 6: 大额低报   (申报 ≥3000 + 价值密度 < 100 元/kg) → 触发 R025
  模式 7: 黑地址寄件 (收件地址命中业务黑名单)            → 触发 R030 (拒绝)
  后置补充: 每个 RISK 用户补 1 票发往"共享收件人"的包裹 (24h 内),
           让 24h 同地址多寄件人信号 ≥3 → 触发 R012 (同地址高频)

例:
  python scripts/gen_risky_users.py                # 默认 24 个 (RISK001-024, 3 套 × 7 模式 + 3)
  python scripts/gen_risky_users.py --count 28     # 28 个 (RISK001-028, 4 套 × 7 模式)
  python scripts/gen_risky_users.py --count 1      # 只 1 个 (RISK001, 未实名寄件模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 用户再生成

风险模式轮换逻辑: idx % 7, 所以 count=21 → 3 套各 7 个 = 21 个; count=7 → 模式 1-7 = 7 个
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

# UTF-8 stdout (Windows GBK 终端兼容)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

# ============================================================
# 常量
# ============================================================

# 7 种物流风险模式
RISK_MODES = [
    "未实名寄件",   # 模式 0
    "危险品瞒报",   # 模式 1
    "跨境违禁品",   # 模式 2
    "COD卷款",      # 模式 3
    "改派异常",     # 模式 4
    "大额低报",     # 模式 5
    "黑地址寄件",   # 模式 6
]

# 常用省份 (必须存在于 region 表, 满足 sender/receiver_province 外键)
PROVINCES = ["北京", "上海", "广东", "浙江", "江苏", "四川", "湖北", "福建", "山东"]

# 常规物品类目 (必须存在于 item_category 表)
ITEM_CATEGORIES = ["电子产品", "服装", "食品", "普通"]

# 业务黑名单地址 (写入 blacklist_extra, 黑地址寄件模式专用 → R030)
BLACK_ADDR = "广东省深圳市龙岗区黑名单测试地址88号"

# 共享收件人 (R012 同地址高频用: 所有 RISK 用户 24h 内各发 1 票到这里)
SHARED_RECEIVER_ID = "R_SHR012"
SHARED_ADDR = "北京市通州区物流园共享收货点12号"
SHARED_PROVINCE = "北京"


# ============================================================
# 基础插入辅助函数 (INSERT IGNORE, 幂等)
# ============================================================

async def _insert_user(conn, user_id, name, real_name_status, account_type, register_at):
    """插入寄件用户."""
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name, real_name_status, account_type, register_at)
        VALUES (:uid, :name, :rns, :acc, :reg)
    """), {"uid": user_id, "name": name, "rns": real_name_status,
           "acc": account_type, "reg": register_at})


async def _insert_sender(conn, sender_id, name, id_number, phone, address, province,
                         is_blacklisted=0):
    """插入寄件人实名 (sender_id 与 user_id 一致)."""
    await conn.execute(text("""
        INSERT IGNORE INTO sender_info
        (sender_id, name, id_type, id_number, phone, address, sender_province, is_blacklisted)
        VALUES (:sid, :name, '身份证', :idnum, :phone, :addr, :prov, :bl)
    """), {"sid": sender_id, "name": name, "idnum": id_number, "phone": phone,
           "addr": address, "prov": province, "bl": is_blacklisted})


async def _insert_receiver(conn, receiver_id, name, phone, address, province,
                           is_proxy_received=0):
    """插入收件人."""
    await conn.execute(text("""
        INSERT IGNORE INTO receiver_info
        (receiver_id, name, phone, address, receiver_province, is_proxy_received)
        VALUES (:rid, :name, :phone, :addr, :prov, :proxy)
    """), {"rid": receiver_id, "name": name, "phone": phone,
           "addr": address, "prov": province, "proxy": is_proxy_received})


async def _insert_parcel(conn, parcel_id, user_id, receiver_id, weight_kg, declared_value,
                         item_category, is_international, piece_count, status, created_at):
    """插入包裹 (sender_id 恒等于 user_id, 符合项目约定)."""
    await conn.execute(text("""
        INSERT IGNORE INTO parcel
        (parcel_id, user_id, sender_id, receiver_id, weight_kg, declared_value,
         item_category, is_international, piece_count, status, created_at)
        VALUES (:pid, :uid, :sid, :rid, :w, :v, :cat, :intl, :pc, :status, :ts)
    """), {"pid": parcel_id, "uid": user_id, "sid": user_id, "rid": receiver_id,
           "w": weight_kg, "v": declared_value, "cat": item_category,
           "intl": is_international, "pc": piece_count, "status": status, "ts": created_at})


async def _insert_decl(conn, decl_id, parcel_id, item_type, is_liquid, is_battery):
    """插入危险品申报."""
    await conn.execute(text("""
        INSERT IGNORE INTO dangerous_declaration
        (decl_id, parcel_id, item_type, is_liquid, is_battery, msds_url, declared_at)
        VALUES (:did, :pid, :itype, :liq, :bat, :msds, NOW())
    """), {"did": decl_id, "pid": parcel_id, "itype": item_type,
           "liq": is_liquid, "bat": is_battery,
           "msds": f"https://msds.example.com/{decl_id.lower()}.pdf"})


async def _insert_cod(conn, cod_id, parcel_id, amount, cod_status, days_overdue=None):
    """插入代收货款流水."""
    await conn.execute(text("""
        INSERT IGNORE INTO cod_transaction
        (cod_id, parcel_id, amount, cod_status, paid_at, returned_at, days_overdue)
        VALUES (:cid, :pid, :amt, :status, NULL, NULL, :days)
    """), {"cid": cod_id, "pid": parcel_id, "amt": amount,
           "status": cod_status, "days": days_overdue})


# 收件人 ID 计数器 (全局自增, 避免跨模式碰撞)
def _receiver_seq():
    n = [0]
    return n


def _next_receiver_id(seq) -> str:
    seq[0] += 1
    return f"R_RSK{seq[0]:04d}"


# 包裹时间: 过去 N 天的一个随机时刻 (保证 7d/30d 特征有值)
def _days_ago(days: int) -> datetime:
    return datetime.now() - timedelta(days=days)


# ============================================================
# 7 种物流风险模式生成器
# ============================================================

async def _gen_unverified_user(conn, user_id: str, rc):
    """模式 0: 未实名寄件 (未认证 → R001 实名不一致).

    parcel_pickup 检查时 user_real_name_verified=0 → R001 (人工审核).
    """
    await _insert_user(conn, user_id, f"未实名{user_id[-3:]}", "未认证", "personal",
                       _days_ago(60))
    await _insert_sender(conn, user_id, f"未实名{user_id[-3:]}",
                         f"110101{user_id[-6:]}1980010100{user_id[-2:]}",
                         f"1390000{user_id[-4:]}",
                         "北京市海淀区未实名测试路1号", "北京", is_blacklisted=0)
    rec = _next_receiver_id(rc)
    await _insert_receiver(conn, rec, f"未实名收件{user_id[-3:]}",
                           f"1370000{user_id[-4:]}", "上海市静安区测试路1号", "上海")
    # 3 个正常包裹 (价值/重量正常, 只是未实名)
    for i, (w, v, cat, d) in enumerate([
        (1.2, 200.00, "服装", 45), (2.0, 500.00, "电子产品", 20), (0.8, 80.00, "食品", 3),
    ], 1):
        await _insert_parcel(conn, f"P_{user_id}_{i:02d}", user_id, rec, w, v, cat,
                             0, 1, "delivered" if i < 3 else "in_transit", _days_ago(d))


async def _gen_dangerous_hide_user(conn, user_id: str, rc):
    """模式 1: 危险品瞒报 (危险品 + 价值密度 < 50 元/kg → R002).

    dangerous_declare 检查时 order_is_dangerous_declared=1 且 order_value_per_kg < 50 → R002.
    """
    await _insert_user(conn, user_id, f"瞒报{user_id[-3:]}", "已认证", "personal",
                       _days_ago(90))
    await _insert_sender(conn, user_id, f"瞒报{user_id[-3:]}",
                         f"310101{user_id[-6:]}1990020200{user_id[-2:]}",
                         f"1390001{user_id[-4:]}",
                         "上海市浦东新区危险品瞒报测试路2号", "上海", is_blacklisted=0)
    rec = _next_receiver_id(rc)
    await _insert_receiver(conn, rec, f"瞒报收件{user_id[-3:]}",
                           f"1370001{user_id[-4:]}", "广东省广州市天河区测试路2号", "广东")
    # 包裹 A: 危险品瞒报 (锂电池 20kg 只申报 300 元 → 15 元/kg < 50)
    await _insert_parcel(conn, f"P_{user_id}_01", user_id, rec, 20.0, 300.00, "锂电池",
                         0, 1, "in_transit", _days_ago(2))
    await _insert_decl(conn, f"DCL_{user_id}_01", f"P_{user_id}_01",
                       "锂电池", is_liquid=0, is_battery=1)
    # 包裹 B/C: 正常对照
    await _insert_parcel(conn, f"P_{user_id}_02", user_id, rec, 2.0, 400.00, "服装",
                         0, 1, "delivered", _days_ago(30))
    await _insert_parcel(conn, f"P_{user_id}_03", user_id, rec, 1.0, 150.00, "食品",
                         0, 1, "delivered", _days_ago(10))


async def _gen_cross_border_user(conn, user_id: str, rc):
    """模式 2: 跨境违禁品 (国际件 + 危险品申报 → R005, 拒绝).

    cross_border_ship 检查时 order_is_international=1 且 order_is_dangerous_declared=1 → R005.
    """
    await _insert_user(conn, user_id, f"跨境{user_id[-3:]}", "已认证", "personal",
                       _days_ago(120))
    await _insert_sender(conn, user_id, f"跨境{user_id[-3:]}",
                         f"440101{user_id[-6:]}1985030300{user_id[-2:]}",
                         f"1390002{user_id[-4:]}",
                         "广东省深圳市南山区跨境测试路3号", "广东", is_blacklisted=0)
    rec = _next_receiver_id(rc)
    await _insert_receiver(conn, rec, f"跨境收件{user_id[-3:]}",
                           f"1370002{user_id[-4:]}", "美国纽约曼哈顿跨境测试路3号", "广东")
    # 国际件 + 危险品 (锂电池已申报)
    await _insert_parcel(conn, f"P_{user_id}_01", user_id, rec, 5.0, 800.00, "锂电池",
                         1, 2, "in_transit", _days_ago(1))
    await _insert_decl(conn, f"DCL_{user_id}_01", f"P_{user_id}_01",
                       "锂电池", is_liquid=0, is_battery=1)
    # 国内正常包裹对照
    await _insert_parcel(conn, f"P_{user_id}_02", user_id, rec, 3.0, 600.00, "电子产品",
                         0, 1, "delivered", _days_ago(25))
    await _insert_parcel(conn, f"P_{user_id}_03", user_id, rec, 1.5, 200.00, "服装",
                         0, 1, "delivered", _days_ago(8))


async def _gen_cod_runaway_user(conn, user_id: str, rc):
    """模式 3: COD 卷款 (COD 逾期 + 大额代收 ≥1000 → R008, 拒绝).

    cod_settlement 检查时 user_cod_overdue_count≥1 且 order_cod_amount≥1000 → R008.
    """
    await _insert_user(conn, user_id, f"卷款{user_id[-3:]}", "已认证", "enterprise",
                       _days_ago(180))
    await _insert_sender(conn, user_id, f"卷款{user_id[-3:]}",
                         f"320101{user_id[-6:]}1990040400{user_id[-2:]}",
                         f"1390003{user_id[-4:]}",
                         "江苏省南京市鼓楼区COD测试路4号", "江苏", is_blacklisted=0)
    rec = _next_receiver_id(rc)
    await _insert_receiver(conn, rec, f"卷款收件{user_id[-3:]}",
                           f"1370003{user_id[-4:]}", "浙江省杭州市余杭区测试路4号", "浙江")
    # 包裹 A: 大额代收 1500 (逾期) → cod_settlement 触发 R008
    await _insert_parcel(conn, f"P_{user_id}_01", user_id, rec, 3.0, 1500.00, "电子产品",
                         0, 2, "delivered", _days_ago(40))
    await _insert_cod(conn, f"COD_{user_id}_01", f"P_{user_id}_01", 1500.00, "overdue", 15)
    # 包裹 B: 又 1 票逾期 COD (累计逾期次数 ≥ 1)
    await _insert_parcel(conn, f"P_{user_id}_02", user_id, rec, 2.0, 800.00, "普通",
                         0, 1, "delivered", _days_ago(35))
    await _insert_cod(conn, f"COD_{user_id}_02", f"P_{user_id}_02", 800.00, "overdue", 7)
    # 包裹 C: 正常对照
    await _insert_parcel(conn, f"P_{user_id}_03", user_id, rec, 1.0, 100.00, "食品",
                         0, 1, "delivered", _days_ago(5))


async def _gen_change_dispatch_user(conn, user_id: str, rc):
    """模式 4: 改派异常 (≥3 个不同收件人 + 高价值 ≥2000 → R018).

    parcel_pickup 检查时 user_distinct_receiver_count≥3 且 order_declared_value≥2000 → R018.
    """
    await _insert_user(conn, user_id, f"改派{user_id[-3:]}", "已认证", "personal",
                       _days_ago(200))
    await _insert_sender(conn, user_id, f"改派{user_id[-3:]}",
                         f"510101{user_id[-6:]}1985050500{user_id[-2:]}",
                         f"1390004{user_id[-4:]}",
                         "四川省成都市锦江区改派测试路5号", "四川", is_blacklisted=0)
    # 4 个不同收件人 (改派异常: 频繁换收件人)
    recs = []
    for i in range(4):
        r = _next_receiver_id(rc)
        await _insert_receiver(conn, r, f"改派收件{i}{user_id[-3:]}",
                               f"1370004{user_id[-4:]}{i}", f"湖北省武汉市武昌区测试路5号-{i}", "湖北")
        recs.append(r)
    # 高价值包裹 (2500) 发给第 3 个收件人 → R018
    await _insert_parcel(conn, f"P_{user_id}_01", user_id, recs[2], 2.0, 2500.00, "电子产品",
                         0, 1, "in_transit", _days_ago(1))
    # 其余收件人各 1 票普通包裹 (拉高 distinct_receiver_count)
    for i, r in enumerate(recs, 1):
        await _insert_parcel(conn, f"P_{user_id}_0{i}", user_id, r,
                             1.5, 200.00 + i * 50, "服装", 0, 1,
                             "delivered" if i < 4 else "created", _days_ago(20 + i * 5))


async def _gen_underdeclare_user(conn, user_id: str, rc):
    """模式 5: 大额低报 (申报 ≥3000 + 价值密度 < 100 元/kg → R025).

    parcel_pickup 检查时 order_declared_value≥3000 且 order_value_per_kg<100 → R025.
    """
    await _insert_user(conn, user_id, f"低报{user_id[-3:]}", "已认证", "enterprise",
                       _days_ago(150))
    await _insert_sender(conn, user_id, f"低报{user_id[-3:]}",
                         f"330101{user_id[-6:]}1990070700{user_id[-2:]}",
                         f"1390005{user_id[-4:]}",
                         "浙江省杭州市西湖区低报测试路6号", "浙江", is_blacklisted=0)
    rec = _next_receiver_id(rc)
    await _insert_receiver(conn, rec, f"低报收件{user_id[-3:]}",
                           f"1370005{user_id[-4:]}", "山东省青岛市市南区测试路6号", "山东")
    # 包裹 A: 申报 3500, 重量 60kg → 58.3 元/kg < 100 → R025
    await _insert_parcel(conn, f"P_{user_id}_01", user_id, rec, 60.0, 3500.00, "普通",
                         0, 5, "in_transit", _days_ago(2))
    # 包裹 B/C: 正常对照
    await _insert_parcel(conn, f"P_{user_id}_02", user_id, rec, 2.0, 600.00, "电子产品",
                         0, 1, "delivered", _days_ago(20))
    await _insert_parcel(conn, f"P_{user_id}_03", user_id, rec, 1.0, 120.00, "食品",
                         0, 1, "delivered", _days_ago(6))


async def _gen_black_address_user(conn, user_id: str, rc):
    """模式 6: 黑地址寄件 (收件地址命中业务黑名单 → R030, 拒绝).

    setup 阶段已把 BLACK_ADDR 写入 blacklist_extra; 任何事件类型检查时
    addr_address_blacklist_hit=1 → R030 (通用规则) → 拒绝.
    """
    await _insert_user(conn, user_id, f"黑址{user_id[-3:]}", "已认证", "personal",
                       _days_ago(90))
    await _insert_sender(conn, user_id, f"黑址{user_id[-3:]}",
                         f"420101{user_id[-6:]}1988080800{user_id[-2:]}",
                         f"1390006{user_id[-4:]}",
                         "湖北省武汉市武昌区黑址测试路7号", "湖北", is_blacklisted=0)
    rec = _next_receiver_id(rc)
    # 收件地址 = 业务黑名单地址 → R030
    await _insert_receiver(conn, rec, f"黑址收件{user_id[-3:]}",
                           f"1370006{user_id[-4:]}", BLACK_ADDR, "广东")
    # 所有包裹都发往黑名单地址
    await _insert_parcel(conn, f"P_{user_id}_01", user_id, rec, 1.0, 100.00, "服装",
                         0, 1, "created", _days_ago(1))
    await _insert_parcel(conn, f"P_{user_id}_02", user_id, rec, 2.0, 300.00, "食品",
                         0, 1, "in_transit", _days_ago(3))


# 7 种模式生成器
MODE_GENERATORS = [
    _gen_unverified_user,      # 模式 0: 未实名寄件 → R001
    _gen_dangerous_hide_user,  # 模式 1: 危险品瞒报 → R002
    _gen_cross_border_user,    # 模式 2: 跨境违禁品 → R005
    _gen_cod_runaway_user,     # 模式 3: COD 卷款 → R008
    _gen_change_dispatch_user, # 模式 4: 改派异常 → R018
    _gen_underdeclare_user,    # 模式 5: 大额低报 → R025
    _gen_black_address_user,   # 模式 6: 黑地址寄件 → R030
]


# ============================================================
# 主流程
# ============================================================

async def gen_risky_users(count: int = 24, reset: bool = False):
    """生成 N 个 RISK 高风险物流用户 (7 种模式轮换).

    Args:
        count: 生成用户数 (默认 24, 满足验收"20-30 个"). 例: count=21 → 3 套 × 7 模式.
        reset: 是否先删旧 RISK 用户 + 相关数据 (默认 False, 用 INSERT IGNORE 增量插入).
    """
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        # ---------- 可选: 清理旧 RISK 数据 ----------
        if reset:
            print(f"[reset] 删旧 RISK 用户 + 关联数据...")
            # 先删从表 (子表), 再删主表, 避免外键约束
            # 危险品申报 / COD 靠 decl_id/cod_id 前缀删; 包裹靠 user_id 前缀删
            await conn.execute(text("DELETE FROM dangerous_declaration WHERE decl_id LIKE 'DCL_RISK%'"))
            await conn.execute(text("DELETE FROM cod_transaction WHERE cod_id LIKE 'COD_RISK%'"))
            await conn.execute(text("DELETE FROM parcel WHERE user_id LIKE 'RISK%'"))
            await conn.execute(text("DELETE FROM receiver_info WHERE receiver_id LIKE 'R_RSK%' OR receiver_id = :shr"),
                               {"shr": SHARED_RECEIVER_ID})
            await conn.execute(text("DELETE FROM sender_info WHERE sender_id LIKE 'RISK%'"))
            await conn.execute(text("DELETE FROM user_info WHERE user_id LIKE 'RISK%'"))
            # 清掉业务黑名单地址条目 (重跑幂等)
            await conn.execute(text("DELETE FROM blacklist_extra WHERE type = 'address' AND value = :addr"),
                               {"addr": BLACK_ADDR})
            await conn.execute(text("COMMIT"))
            print(f"  清理完成")

        # ---------- 基础数据 (region / item_category 已在 init_db 灌入, 幂等补充) ----------
        print(f"[setup] 基础数据 (省份 / 物品类目 / 业务黑名单地址 / 共享收件人)...")
        for prov in PROVINCES:
            await conn.execute(text("INSERT IGNORE INTO region (province, province_code) VALUES (:p, :c)"),
                               {"p": prov, "c": PROVINCES.index(prov) + 1})
        for cat in ITEM_CATEGORIES + ["锂电池", "液体", "化工品"]:
            await conn.execute(text("INSERT IGNORE INTO item_category (item_category) VALUES (:c)"),
                               {"c": cat})
        # 业务黑名单地址 (R030 前置条件)
        await conn.execute(text("""
            INSERT IGNORE INTO blacklist_extra (type, value, reason, expire_at)
            VALUES ('address', :addr, '风控黑名单测试地址 (R030)', NULL)
        """), {"addr": BLACK_ADDR})
        # 共享收件人 (R012 同地址高频前置)
        await _insert_receiver(conn, SHARED_RECEIVER_ID, "共享收货人", "13700009999",
                               SHARED_ADDR, SHARED_PROVINCE, is_proxy_received=1)
        await conn.execute(text("COMMIT"))

        # ---------- 批量生成 N 个 RISK 用户 (7 种模式轮换) ----------
        print(f"[generate] 生成 {count} 个 RISK 高风险用户 (7 模式轮换)...")
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]
        rc = _receiver_seq()  # 收件人 ID 全局计数器

        for idx, user_id in enumerate(user_ids):
            mode_idx = idx % len(RISK_MODES)  # 0-6 轮换
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {user_id} (模式 {mode_idx+1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, user_id, rc)

        # ---------- 后置: R012 共享收件人包裹 ----------
        # 每个 RISK 用户 24h 内发 1 票到 R_SHR012 → 该收件人 24h 内 distinct 寄件人数 ≥ count ≥ 3
        # → 任一 RISK 用户检查此包裹时 addr_same_address_sender_count_24h ≥ 3 → R012
        print(f"[post] 补 {count} 票发往共享收件人的包裹 (触发 R012 同地址高频)...")
        for idx, user_id in enumerate(user_ids):
            await _insert_parcel(conn, f"P_{user_id}_R12", user_id, SHARED_RECEIVER_ID,
                                 0.5, 50.00, "食品", 0, 1, "created",
                                 datetime.now() - timedelta(hours=1))
        await conn.execute(text("COMMIT"))

        # ---------- 统计 ----------
        r = await conn.execute(text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"))
        total_users = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM parcel WHERE user_id LIKE 'RISK%'"))
        total_parcels = r.scalar()
        r = await conn.execute(text("""
            SELECT COUNT(*) FROM dangerous_declaration d
            JOIN parcel p ON d.parcel_id = p.parcel_id
            WHERE p.user_id LIKE 'RISK%'
        """))
        total_decls = r.scalar()
        r = await conn.execute(text("""
            SELECT COUNT(*) FROM cod_transaction c
            JOIN parcel p ON c.parcel_id = p.parcel_id
            WHERE p.user_id LIKE 'RISK%'
        """))
        total_cods = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM receiver_info WHERE receiver_id LIKE 'R_RSK%'"))
        total_recvs = r.scalar()

        print(f"\n[完成] 高风险用户数据生成完成!")
        print(f"  RISK 用户:       {total_users} 个")
        print(f"  RISK 包裹:       {total_parcels} 个")
        print(f"  RISK 危险品申报: {total_decls} 条")
        print(f"  RISK COD 流水:   {total_cods} 条")
        print(f"  RISK 收件人:     {total_recvs} 个")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造 RISK 高风险物流用户 + 包裹/危险品申报/COD. 默认 24 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/gen_risky_users.py                # 24 个 (RISK001-024, 3 套 × 7 模式 + 3)
  python scripts/gen_risky_users.py --count 28     # 28 个 (RISK001-028, 4 套 × 7 模式)
  python scripts/gen_risky_users.py --count 1      # 1 个 (RISK001, 未实名寄件模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=24, help="生成 RISK 用户数 (默认 24)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 用户 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
