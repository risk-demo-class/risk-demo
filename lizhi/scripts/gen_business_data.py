"""
旅游行业风控系统 - 业务数据生成脚本 (异步, 可重复运行)

对应任务书"场景 A: 旅游"的 7 张业务表 (app/models_business.py), 默认造 120 笔订单 (>=100).
数据内容:
  - 40 个正常用户 + 5 个高风险模式用户 (黄牛囤票 / 拒签历史 / 新用户大单 / 黑名单护照 / 高频退改)
  - 每张订单 1-4 个乘客, 机票/酒店/跟团游订单生成对应 BookingFlight / BookingHotel 明细
  - 签证申请记录 + BlacklistExtra 业务黑名单 (护照号/设备指纹/IP/签证号/身份证号)

用法:
  python scripts/gen_business_data.py                  # 默认 120 订单, 固定 seed=42
  python scripts/gen_business_data.py --orders 200     # 指定订单数
  python scripts/gen_business_data.py --reset          # 先清空 7 张业务表再插入 (幂等)
  python scripts/gen_business_data.py --seed 7         # 换随机种子
  python scripts/gen_business_data.py --dump           # 只导出 sql/init_business_data.sql (不连库)
  python scripts/gen_business_data.py --password 123456

数据时间锚定 BASE_DATE, 保证 --dump 每次生成内容一致 (可重复/可审计).
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

from app.models_business import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    UserInfo,
    VisaApplication,
)


def _load_env_password() -> str:
    """从项目 .env 读 DB_PASSWORD (缺省 123321, 兼容老文档)."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DB_PASSWORD="):
                    return line.split("=", 1)[1].strip()
    return "123321"

# 数据时间锚点 (固定, 保证 --dump 内容稳定)
BASE_DATE = datetime(2026, 8, 1, 10, 0, 0)

# 7 张业务表 (表名, ORM Table) — dump 与 reset 共用
TABLE_ORDER = [
    ("user_info", UserInfo.__table__),
    ("order_info", OrderInfo.__table__),
    ("passenger_info", PassengerInfo.__table__),
    ("visa_application", VisaApplication.__table__),
    ("booking_hotel", BookingHotel.__table__),
    ("booking_flight", BookingFlight.__table__),
    ("blacklist_extra", BlacklistExtra.__table__),
]
RESET_ORDER = [name for name, _ in reversed(TABLE_ORDER)]

# ------------------------------------------------------------
# 业务词典
# ------------------------------------------------------------
SURNAMES = list("王李张刘陈杨赵黄周吴徐孙胡朱高林何郭马罗")
GIVEN_NAMES = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳",
               "杰", "娟", "涛", "明", "超", "秀英", "霞", "平", "刚", "桂英"]
VIP_LEVELS = ["普通", "银卡", "金卡", "铂金", "钻石"]
VIP_WEIGHTS = [45, 25, 15, 10, 5]
DOMESTIC_CITIES = ["北京", "上海", "三亚", "成都", "昆明", "西安", "哈尔滨", "厦门", "大理", "张家界"]
INTERNATIONAL_COUNTRIES = ["日本", "泰国", "新加坡", "韩国", "法国", "意大利", "澳大利亚", "新西兰", "美国", "英国"]
DOMESTIC_AIRPORTS = {
    "北京": "首都国际", "上海": "虹桥国际", "广州": "白云国际", "深圳": "宝安国际",
    "成都": "双流国际", "昆明": "长水国际", "西安": "咸阳国际", "三亚": "凤凰国际",
    "哈尔滨": "太平国际", "厦门": "高崎国际", "大理": "荒草坝机场", "张家界": "荷花机场",
}
INTERNATIONAL_AIRPORTS = {
    "日本": "东京成田", "泰国": "曼谷素万那普", "新加坡": "新加坡樟宜", "韩国": "首尔仁川",
    "法国": "巴黎戴高乐", "意大利": "罗马菲乌米奇诺", "澳大利亚": "悉尼金斯福德",
    "新西兰": "奥克兰", "美国": "洛杉矶", "英国": "伦敦希思罗",
}
AIRLINES = ["CA", "MU", "CZ", "HU", "9C", "SC", "MF"]
ORDER_STATUS = ["待支付", "已支付", "已出票", "已出行", "已完成", "已取消", "已退改"]
BLACK_PASSPORTS = ["E99990001", "G99990002", "E99990003"]


# ------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------
def _rand_name(rng: random.Random) -> str:
    return rng.choice(SURNAMES) + rng.choice(GIVEN_NAMES)


def _checksum_id18(prefix17: str) -> str:
    """GB 11643-1999 身份证校验位"""
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    code_map = "10X98765432"
    total = sum(int(prefix17[i]) * weights[i] for i in range(17))
    return code_map[total % 11]


def _gen_id_number(rng: random.Random, birth: date, id_type: str) -> str:
    """身份证: 18 位含校验位; 护照: E/G + 8 位数字"""
    if id_type == "护照":
        return rng.choice("EG") + f"{rng.randint(0, 99999999):08d}"
    region = rng.choice(["110101", "310104", "440305", "510107", "330106"])
    birth_part = birth.strftime("%Y%m%d")
    seq = f"{rng.randint(0, 999):03d}"
    return region + birth_part + seq + _checksum_id18(region + birth_part + seq)


def _passenger_pool(rng: random.Random, uid: str, size: int, international: bool) -> list[dict]:
    """为某个用户固定 1 组乘客 (跨订单复用, 保证"乘客一致性"特征有意义)"""
    pool = []
    base_birth = BASE_DATE - timedelta(days=365 * rng.randint(28, 55))
    for i in range(size):
        id_type = "护照" if international else "身份证"
        birth = base_birth - timedelta(days=365 * i * rng.randint(3, 9))
        pool.append({
            "name": _rand_name(rng),
            "id_type": id_type,
            "id_number": _gen_id_number(rng, birth, id_type),
            "nationality": "中国",
            "age": max(6, (BASE_DATE - birth).days // 365),
        })
    return pool


def _fmt(v) -> str:
    """转 SQL 字面量"""
    if v is None:
        return "NULL"
    if isinstance(v, (datetime, date)):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v, datetime) else v.isoformat()}'"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


# ------------------------------------------------------------
# 核心生成器 (纯数据, 不连库; dump 与 db 模式共用)
# ------------------------------------------------------------
def generate_business_data(seed: int = 42, target_orders: int = 120) -> dict[str, list[dict]]:
    rng = random.Random(seed)

    user_rows: list[dict] = []
    order_rows: list[dict] = []
    passenger_rows: list[dict] = []
    visa_rows: list[dict] = []
    hotel_rows: list[dict] = []
    flight_rows: list[dict] = []
    blacklist_rows: list[dict] = []

    # ---- 高风险用户计划 (跟任务书 A.2 样例规则一一对应) ----
    # RISK01 黄牛囤票: 0-5 点下单, 同航班 1 小时内 >=5 张, 占座不付款
    # RISK02 拒签历史: 90 天拒签 >=2 次, 30 天申请 >=3 国
    # RISK03 新用户大单: 注册 <7 天 + 订单 >10000
    # RISK04 黑名单护照: 乘客护照号进 blacklist_extra
    # RISK05 高频退改: 30 天内大量订单状态=已退改
    risk_plans = {
        "RISK01": ("黄牛囤票", 60 + rng.randint(0, 120), 8 + rng.randint(0, 3)),
        "RISK02": ("拒签历史", 100 + rng.randint(0, 200), 1),
        "RISK03": ("新用户大单", 1 + rng.randint(0, 5), 1 + rng.randint(0, 1)),
        "RISK04": ("黑名单护照", 90 + rng.randint(0, 180), 2 + rng.randint(0, 2)),
        "RISK05": ("高频退改", 90 + rng.randint(0, 110), 6 + rng.randint(0, 2)),
    }
    plan_orders: dict[str, int] = {}

    # 用户: 40 正常 + 5 风险
    user_plan: dict[str, tuple[str, int, int]] = {}
    for i in range(1, 41):
        uid = f"U{i:04d}"
        user_plan[uid] = ("正常", 30 + rng.randint(0, 3650), rng.randint(1, 3))
    for uid, (label, age, order_cnt) in risk_plans.items():
        user_plan[uid] = (label, age, order_cnt)
        plan_orders[uid] = order_cnt

    for idx, (uid, (label, age_days, _)) in enumerate(user_plan.items(), start=1):
        user_rows.append({
            "user_id": uid,
            "name": _rand_name(rng),
            "real_name_status": 1 if label != "新用户大单" else rng.choice([0, 1]),
            "vip_level": rng.choices(VIP_LEVELS, weights=VIP_WEIGHTS, k=1)[0],
            "account_age_days": age_days,
            "create_time": (BASE_DATE - timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M:%S"),
        })

    # 订单数: 按用户计划铺, 不够 target_orders 就随机补
    order_counts: dict[str, int] = {uid: cnt for uid, (_, _, cnt) in user_plan.items()}
    while sum(order_counts.values()) < target_orders:
        uid = rng.choice(list(order_counts))
        order_counts[uid] += 1

    order_idx = 0
    for uid, count in order_counts.items():
        label = user_plan[uid][0]
        pool = _passenger_pool(rng, uid, 2 + rng.randint(0, 2), international=False)
        scalper_flight = None  # RISK01 固定同航班
        scalper_route = None
        scalper_window = None
        scalper_depart = None
        if label == "黄牛囤票":
            scalper_flight = rng.choice(AIRLINES) + f"{rng.randint(1000, 9999)}"
            dep, arr = rng.sample(["北京", "上海", "成都", "三亚"], 2)
            scalper_route = (dep, arr)
            # 所有囤票订单: 同一天凌晨 1-4 点开始, 60 分钟内下完 (R003 黄牛囤票信号)
            scalper_window = (BASE_DATE - timedelta(days=3 + rng.randint(0, 5))).replace(
                hour=rng.randint(1, 4), minute=rng.randint(0, 10), second=0, microsecond=0)
            scalper_depart = (BASE_DATE + timedelta(days=20 + rng.randint(0, 20))).date()
            pool = _passenger_pool(rng, uid, 2, international=False)
        if label == "黑名单护照":
            pool = _passenger_pool(rng, uid, 2, international=True)
            for i, member in enumerate(pool):
                member["id_number"] = BLACK_PASSPORTS[i % len(BLACK_PASSPORTS)]

        for n in range(count):
            order_idx += 1
            oid = f"ORD{order_idx:05d}"

            # 下单时间: 黄牛同窗 60 分钟内凌晨下单 (0 点突击), 高频退改在最近 30 天
            if label == "黄牛囤票":
                create_time = scalper_window + timedelta(minutes=rng.randint(0, 55))
            elif label == "高频退改":
                create_time = BASE_DATE - timedelta(days=rng.randint(0, 30), hours=rng.randint(8, 22))
            else:
                create_time = BASE_DATE - timedelta(
                    days=rng.randint(0, 180), hours=rng.randint(8, 22), minutes=rng.randint(0, 59))
            create_time = create_time.replace(second=rng.randint(0, 59))

            # 订单类型 (黄牛只囤机票)
            if label == "黄牛囤票":
                order_type = "机票"
            else:
                order_type = rng.choices(
                    ["机票", "酒店", "跟团游", "签证"], weights=[40, 25, 20, 15], k=1)[0]

            # 目的地: 出境概率
            international = rng.random() < (0.45 if order_type == "机票" else 0.40 if order_type == "跟团游" else 0.15)
            if label == "黄牛囤票":
                international = False  # 国内热门航线囤票
            if international:
                dest = rng.choice(INTERNATIONAL_COUNTRIES)
            elif label == "黄牛囤票":
                dest = scalper_route[1]
            else:
                dest = rng.choice(DOMESTIC_CITIES)

            if label == "黄牛囤票":
                depart_date = scalper_depart  # 全部同一航班同一出发日 (囤票特征)
                return_date = depart_date + timedelta(days=3 + rng.randint(0, 3))
            else:
                depart_date = (create_time + timedelta(days=7 + rng.randint(0, 83))).date()
                return_date = depart_date + timedelta(days=3 + rng.randint(0, 12))

            # 金额 (新用户大单 >10000; 跟团游 3000-12000)
            if label == "新用户大单":
                total = Decimal(rng.randint(15000, 50000))
            elif order_type == "机票":
                total = Decimal(rng.randint(2000, 8000) if international else rng.randint(500, 3000))
            elif order_type == "酒店":
                total = Decimal(rng.randint(300, 3000))
            elif order_type == "签证":
                total = Decimal(rng.randint(300, 1500))
            else:
                total = Decimal(rng.randint(3000, 12000))

            # 乘客数
            pcount = min(4, len(pool)) if order_type == "跟团游" else rng.randint(1, min(2, len(pool)))

            # 状态 (黄牛: 占座不付款/取消; 高频退改: 全已退改)
            if label == "黄牛囤票":
                status = rng.choices(["已取消", "待支付", "已支付"], weights=[60, 30, 10], k=1)[0]
            elif label == "高频退改":
                status = "已退改"
            else:
                status = rng.choices(
                    ["已完成", "已出行", "已出票", "已支付", "待支付", "已取消"],
                    weights=[45, 20, 20, 8, 4, 3], k=1)[0]

            payment_time = None
            if status in ("已支付", "已出票", "已出行", "已完成", "已退改"):
                if label == "黄牛囤票" and rng.random() < 0.7:
                    payment_time = None  # 占座不付款
                else:
                    payment_time = (create_time + timedelta(minutes=rng.randint(1, 30))).strftime(
                        "%Y-%m-%d %H:%M:%S")

            order_rows.append({
                "order_id": oid,
                "user_id": uid,
                "order_type": order_type,
                "total_amount": total,
                "dest_country": dest,
                "depart_date": depart_date.isoformat(),
                "return_date": return_date.isoformat(),
                "passenger_count": pcount,
                "order_status": status,
                "create_time": create_time.strftime("%Y-%m-%d %H:%M:%S"),
                "payment_time": payment_time,
            })

            # 乘客 (从用户池里取, 保证同一用户跨订单乘客一致)
            for p in range(pcount):
                member = pool[p % len(pool)]
                passenger_rows.append({
                    "passenger_id": f"P{order_idx:05d}{p + 1}",
                    "order_id": oid,
                    **member,
                })

            # 酒店明细
            if order_type in ("酒店", "跟团游"):
                check_in = depart_date
                check_out = check_in + timedelta(days=2 + rng.randint(0, 5))
                hotel_rows.append({
                    "booking_id": f"H{order_idx:05d}",
                    "order_id": oid,
                    "hotel_id": f"HTL{rng.randint(1000, 9999)}",
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "room_count": rng.randint(1, 3),
                    "is_refundable": 0 if label == "黄牛囤票" else rng.choice([0, 1]),
                })

            # 机票明细
            if order_type in ("机票", "跟团游"):
                if international:
                    dep, arr = "上海", dest
                    dep_airport, arr_airport = "浦东国际", INTERNATIONAL_AIRPORTS[dest]
                elif label == "黄牛囤票":
                    dep_airport, arr_airport = (
                        DOMESTIC_AIRPORTS[scalper_route[0]], DOMESTIC_AIRPORTS[scalper_route[1]])
                else:
                    candidates = [c for c in DOMESTIC_CITIES if c != dest]
                    dep = rng.choice(candidates)
                    dep_airport, arr_airport = DOMESTIC_AIRPORTS[dep], DOMESTIC_AIRPORTS[dest]
                flight_rows.append({
                    "booking_id": f"F{order_idx:05d}",
                    "order_id": oid,
                    "flight_no": scalper_flight or (rng.choice(AIRLINES) + f"{rng.randint(1000, 9999)}"),
                    "depart_airport": dep_airport,
                    "arrive_airport": arr_airport,
                    "cabin_class": rng.choices(["经济舱", "公务舱", "头等舱"], weights=[85, 10, 5], k=1)[0],
                })

            # 签证申请 (签证订单或拒签历史用户)
            if order_type == "签证" or label == "拒签历史":
                visa_count = 3 + rng.randint(0, 4) if label == "拒签历史" else 1
                countries = rng.sample(INTERNATIONAL_COUNTRIES, k=min(visa_count, len(INTERNATIONAL_COUNTRIES)))
                for v in range(visa_count):
                    visa_id = f"V{order_idx:05d}{v + 1}"
                    submit_time = BASE_DATE - timedelta(
                        days=rng.randint(0, 30 if label == "拒签历史" else 120),
                        hours=rng.randint(9, 17))
                    if label == "拒签历史":
                        reject_history = rng.randint(2, 4)
                        status = rng.choices(["拒签", "待审核", "通过"], weights=[50, 30, 20], k=1)[0]
                    else:
                        reject_history = rng.randint(0, 1)
                        status = rng.choices(["通过", "待审核", "拒签"], weights=[60, 20, 20], k=1)[0]
                    visa_rows.append({
                        "visa_id": visa_id,
                        "user_id": uid,
                        "dest_country": countries[v % len(countries)],
                        "visa_type": rng.choice(["旅游", "商务", "探亲", "留学"]),
                        "reject_history": reject_history,
                        "submit_time": submit_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": status,
                    })

    # ---- 业务黑名单扩展表 ----
    for p in BLACK_PASSPORTS:
        blacklist_rows.append({
            "type": "护照号", "value": p,
            "reason": "黑护照拦截(历史欺诈)", "expire_at": None,
        })
    for i in range(1, 4):
        blacklist_rows.append({
            "type": "设备指纹", "value": f"DEV{rng.randint(100000, 999999)}",
            "reason": "黄牛设备(关联多账号)", "expire_at": None,
        })
    for i in range(1, 3):
        blacklist_rows.append({
            "type": "IP", "value": f"223.104.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
            "reason": "代理/秒拨IP", "expire_at": None,
        })
    blacklist_rows.append({"type": "签证号", "value": "V0000001", "reason": "伪造签证材料", "expire_at": None})
    blacklist_rows.append({"type": "身份证号", "value": "110101199001011234", "reason": "盗用他人证件", "expire_at": None})

    return {
        "user_info": user_rows,
        "order_info": order_rows,
        "passenger_info": passenger_rows,
        "visa_application": visa_rows,
        "booking_hotel": hotel_rows,
        "booking_flight": flight_rows,
        "blacklist_extra": blacklist_rows,
    }


# ------------------------------------------------------------
# dump 模式: 导出 sql/init_business_data.sql
# ------------------------------------------------------------
def dump_sql(data: dict[str, list[dict]], out_path: str, seed: int) -> int:
    lines = [
        "-- ============================================",
        "-- 旅游风控系统 - 业务表数据初始化脚本 (自动生成, 勿手改)",
        f"-- 生成: scripts/gen_business_data.py --seed {seed} --dump",
        "-- 包含 7 张旅游业务表 (场景 A), 订单数 >= 100",
        "-- ============================================",
        "",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
    ]
    total = 0
    for name, table in TABLE_ORDER:
        rows = data[name]
        total += len(rows)
        lines.append(f"-- Table `{name}`: {len(rows)} rows")
        if not rows:
            lines.append("")
            continue
        cols = list(table.columns.keys())
        lines.append(f"INSERT INTO `{name}` ({', '.join(f'`{c}`' for c in cols)}) VALUES")
        for i, row in enumerate(rows):
            values = ", ".join(_fmt(row.get(c)) for c in cols)
            lines.append(f"({values})" + ("," if i < len(rows) - 1 else ";"))
        lines.append("")
    lines.append("SET FOREIGN_KEY_CHECKS = 1;")
    lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return total


# ------------------------------------------------------------
# db 模式: 插入 MySQL
# ------------------------------------------------------------
async def insert_to_db(data: dict[str, list[dict]], args, seed: int):
    url = URL.create(
        "mysql+aiomysql",
        username=args.user,
        password=args.password,
        host=args.host,
        port=args.port,
        database=args.db,
        query={"charset": "utf8mb4"},
    )
    engine = create_async_engine(url, pool_recycle=3600)
    try:
        async with engine.begin() as conn:
            if args.reset:
                await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                for name in RESET_ORDER:
                    await conn.execute(text(f"TRUNCATE TABLE `{name}`"))
                await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
                print(f"  已清空 {len(RESET_ORDER)} 张业务表 (--reset)")

            for name, table in TABLE_ORDER:
                rows = data[name]
                if not rows:
                    continue
                # INSERT IGNORE: 重复运行不报错 (幂等)
                await conn.execute(table.insert().prefix_with("IGNORE"), rows)
                print(f"  {name:<18} 插入 {len(rows)} 条")
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="旅游风控系统 - 生成 7 张业务表测试数据 (默认 120 订单, seed=42)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--orders", type=int, default=120, help="目标订单数 (默认 120, >=100)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42, 固定数据)")
    parser.add_argument("--reset", action="store_true", help="插入前先清空 7 张业务表")
    parser.add_argument("--dump", action="store_true", help="只导出 sql/init_business_data.sql, 不连库")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=_load_env_password())
    parser.add_argument("--db", default="ecs")
    args = parser.parse_args()

    if args.orders < 100:
        print(f"[WARN] --orders={args.orders} < 100, 不满足任务书'至少 100 条'要求, 已自动提升到 100")
        args.orders = 100

    print("=" * 60)
    print("旅游风控系统 - 业务数据生成")
    print(f"seed={args.seed} 目标订单={args.orders} 模式={'dump(导出SQL)' if args.dump else 'db(插入MySQL)'}")
    print("=" * 60)

    data = generate_business_data(seed=args.seed, target_orders=args.orders)
    total = sum(len(v) for v in data.values())
    print(f"生成数据: 订单 {len(data['order_info'])} 条, 乘客 {len(data['passenger_info'])} 条, "
          f"签证 {len(data['visa_application'])} 条, 酒店 {len(data['booking_hotel'])} 条, "
          f"机票 {len(data['booking_flight'])} 条, 黑名单 {len(data['blacklist_extra'])} 条, 合计 {total} 条")

    if args.dump:
        out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "sql", "init_business_data.sql")
        dump_sql(data, out, args.seed)
        print(f"已导出: {out}")
        return 0

    asyncio.run(insert_to_db(data, args, args.seed))
    print("插入完成 (可重复运行: 默认 INSERT IGNORE; 加 --reset 先清空)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
