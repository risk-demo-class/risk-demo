# -*- coding: utf-8 -*-
"""业务样例数据生成器 —— 填充 17 张业务表 + 黑名单

## 为什么要专门造「人设」？

风控系统的 25 维特征**全部来自业务表聚合**（`engine/feature.py`）。
如果业务数据全是「3 次学习、200 元投入、不申诉」的良民，那么 30 条规则一条都命中不了，
学生跑完 `/api/risk/check` 只会看到「通过 · 0 分」，什么也学不到。

所以本模块按 **9 类人设** 反向构造数据，保证 30 条规则**每条都有样本能命中**：

| # | 人设 key           | 构造手法                                       | 靶向规则                   |
|---|--------------------|------------------------------------------------|---------------------------|
| 1 | `normal`           | 3~15 次学习 / 50~800 元投入 / 不申诉             | （负样本基线）              |
| 2 | `vip`              | 20~60 次学习 / 500~3000 元投入 / 申诉率 <10%     | R007（30 天学习量）         |
| 3 | `whale`            | 单笔 6000~28000 元投入                         | R001 R002 R009 R022        |
| 4 | `refund_abuser`    | 成绩申诉率 0.55~0.95 / 申诉额 > 1 万             | R011 R012 R013 R014 R015   |
| 5 | `postsale_abuser`  | 退课率 0.45~0.8 + 申诉率 0.4+                   | R016 R017 R020             |
| 6 | `address_farmer`   | 12~24 个关联账号 / 跨 6~9 省                     | R021 R023 R024             |
| 7 | `burst_buyer`      | 7 天内 22~40 次学习                            | R006 R007 R010             |
| 8 | `new_user_burst`   | 总学习 ≤2 但 7 天内 5~9 次 / 新账号              | R010 R025 R029             |
| 9 | `complainer`       | 6~12 次反馈投诉                                | R019                       |
| 10| `combo_fraud`      | 申诉率 ≥0.5 + 均单价 ≥2000 + 关联账号 ≥3         | **R030 一票否决**          |

`combo_fraud` 是教学的高光样本：一次检查即可演示「极高 → final = max(final, 90) → 拒绝」。

## 确定性

`random.Random(seed)` 固定种子 —— 同一个 seed 生成的数据**完全一致**，
这样课堂上老师和学生跑出来的分数才对得上，也方便写断言测试。
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from app import models

logger = logging.getLogger("ai_risk.seed")

FMT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------- 字典素材
PROVINCES: List[Tuple[str, str, List[str]]] = [
    ("广东省", "深圳市", ["南山区", "福田区", "宝安区", "龙岗区"]),
    ("广东省", "广州市", ["天河区", "海珠区", "越秀区"]),
    ("北京市", "北京市", ["朝阳区", "海淀区", "西城区", "昌平区"]),
    ("上海市", "上海市", ["浦东新区", "徐汇区", "静安区"]),
    ("浙江省", "杭州市", ["西湖区", "余杭区", "滨江区"]),
    ("江苏省", "南京市", ["鼓楼区", "江宁区", "玄武区"]),
    ("四川省", "成都市", ["武侯区", "锦江区", "高新区"]),
    ("湖北省", "武汉市", ["武昌区", "洪山区", "江汉区"]),
    ("陕西省", "西安市", ["雁塔区", "碑林区", "未央区"]),
    ("福建省", "厦门市", ["思明区", "湖里区", "集美区"]),
    ("山东省", "青岛市", ["市南区", "崂山区", "李沧区"]),
    ("辽宁省", "沈阳市", ["和平区", "沈河区", "浑南区"]),
]
OVERSEAS: List[Tuple[str, str, List[str]]] = [
    ("海外", "中国香港", ["中西区", "湾仔区"]),
    ("海外", "新加坡", ["乌节路", "滨海湾"]),
]

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
GIVEN = ["伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "洋", "艳", "勇",
         "军", "杰", "娟", "涛", "明", "超", "秀兰", "霞", "平", "刚", "桂英"]

CATEGORIES: List[Tuple[str, str, List[Tuple[str, str, float]]]] = [
    ("C01", "手机数码", [("智能手机 Pro Max", "星辰", 6999.0), ("无线耳机", "星辰", 999.0),
                         ("平板电脑", "拓海", 3299.0), ("智能手表", "拓海", 1599.0)]),
    ("C02", "家用电器", [("扫地机器人", "洁净", 2699.0), ("空气净化器", "洁净", 1899.0),
                         ("电饭煲", "膳魔", 599.0), ("破壁机", "膳魔", 899.0)]),
    ("C03", "服饰鞋包", [("轻薄羽绒服", "南山", 1299.0), ("真皮单肩包", "锦岚", 2599.0),
                         ("运动跑鞋", "疾风", 699.0), ("纯棉衬衫", "南山", 259.0)]),
    ("C04", "美妆护肤", [("精华液 50ml", "花期", 1280.0), ("防晒霜", "花期", 268.0),
                         ("口红套装", "朱砂", 599.0)]),
    ("C05", "食品生鲜", [("进口车厘子 2kg", "鲜集", 328.0), ("有机大米 10kg", "鲜集", 128.0),
                         ("坚果礼盒", "果然", 199.0)]),
    ("C06", "母婴玩具", [("婴儿推车", "宝护", 2199.0), ("奶粉 3 段", "宝护", 398.0),
                         ("积木套装", "启智", 499.0)]),
    ("C07", "珠宝配饰", [("18K 金项链", "瑾玉", 8899.0), ("钻石戒指", "瑾玉", 25800.0),
                         ("机械腕表", "时序", 15800.0)]),
    ("C08", "运动户外", [("碳纤维公路车", "疾风", 12800.0), ("露营帐篷", "远行", 1580.0),
                         ("瑜伽垫", "远行", 189.0)]),
]

PAY_CHANNELS = ["支付宝", "微信", "银行卡", "云闪付"]
ORDER_SOURCES = ["APP", "H5", "小程序", "PC"]
EXPRESS = ["顺丰速运", "京东物流", "中通快递", "圆通速递", "韵达快递"]
APPEAL_REASONS = ["成绩录入有误", "评分标准不公", "系统判分异常", "答案争议", "误操作提交"]
DROPOUT_TYPES = ["退课重修", "仅退课", "延期考试", "补考申请"]
COMPLAINT_TYPES = ["延迟", "破损", "丢件", "态度"]
ABORT_REASONS = ["考试超时", "重复选课", "选错班级", "课程变动", "临时放弃"]
DEVICE_TYPES = [("iPhone 15 Pro", "iOS 17"), ("Mate 60", "HarmonyOS 4"),
                ("小米 14", "Android 14"), ("Windows PC", "Windows 11"),
                ("MacBook Pro", "macOS 14")]

# ---------------------------------------------------------------- 人设定义
# ratio: 人设占比；其余字段是构造参数（区间）
PERSONAS: List[Dict[str, Any]] = [
    {"key": "normal", "label": "学术诚信良民", "ratio": 0.34,
     "orders": (3, 15), "amount": (50, 800), "refund_rate": (0.0, 0.08),
     "postsale_rate": (0.0, 0.1), "addresses": (1, 2), "provinces": 1,
     "orders_7d": (0, 2), "complaints": (0, 1), "cancels": (0, 2), "credit": (78, 96)},

    {"key": "vip", "label": "优质学员", "ratio": 0.12,
     "orders": (22, 60), "amount": (500, 3000), "refund_rate": (0.0, 0.08),
     "postsale_rate": (0.0, 0.12), "addresses": (2, 4), "provinces": 2,
     "orders_7d": (2, 6), "complaints": (0, 2), "cancels": (0, 3), "credit": (85, 99)},

    {"key": "whale", "label": "高额投入学员", "ratio": 0.10,
     "orders": (2, 8), "amount": (6000, 28000), "refund_rate": (0.0, 0.2),
     "postsale_rate": (0.0, 0.2), "addresses": (1, 3), "provinces": 2,
     "orders_7d": (1, 3), "complaints": (0, 1), "cancels": (0, 1), "credit": (60, 88),
     "night_bias": 0.5, "new_address": True},

    {"key": "refund_abuser", "label": "成绩申诉惯犯", "ratio": 0.10,
     "orders": (12, 26), "amount": (600, 2600), "refund_rate": (0.55, 0.95),
     "postsale_rate": (0.2, 0.45), "addresses": (2, 5), "provinces": 3,
     "orders_7d": (1, 4), "complaints": (1, 4), "cancels": (2, 6), "credit": (20, 48)},

    {"key": "postsale_abuser", "label": "退课惯犯", "ratio": 0.08,
     "orders": (10, 22), "amount": (300, 1500), "refund_rate": (0.40, 0.60),
     "postsale_rate": (0.45, 0.80), "addresses": (2, 4), "provinces": 2,
     "orders_7d": (1, 3), "complaints": (2, 5), "cancels": (1, 4), "credit": (25, 52)},

    {"key": "address_farmer", "label": "多账号关联农场", "ratio": 0.07,
     "orders": (8, 20), "amount": (200, 1200), "refund_rate": (0.1, 0.3),
     "postsale_rate": (0.1, 0.3), "addresses": (12, 24), "provinces": 8,
     "orders_7d": (2, 6), "complaints": (0, 3), "cancels": (1, 5), "credit": (30, 58),
     "new_address": True},

    {"key": "burst_buyer", "label": "刷课暴走", "ratio": 0.06,
     "orders": (55, 110), "amount": (80, 600), "refund_rate": (0.1, 0.35),
     "postsale_rate": (0.05, 0.25), "addresses": (3, 6), "provinces": 4,
     "orders_7d": (22, 40), "complaints": (0, 2), "cancels": (3, 9), "credit": (28, 55),
     "night_bias": 0.4, "fast_pay": True},

    {"key": "new_user_burst", "label": "新号突袭", "ratio": 0.05,
     "orders": (1, 2), "amount": (1500, 4200), "refund_rate": (0.0, 0.2),
     "postsale_rate": (0.0, 0.2), "addresses": (1, 2), "provinces": 1,
     "orders_7d": (5, 9), "complaints": (0, 1), "cancels": (0, 2), "credit": (40, 70),
     "new_user": True, "new_address": True, "night_bias": 0.5, "fast_pay": True},

    {"key": "complainer", "label": "反馈投诉高发", "ratio": 0.04,
     "orders": (10, 24), "amount": (150, 900), "refund_rate": (0.15, 0.35),
     "postsale_rate": (0.2, 0.4), "addresses": (2, 4), "provinces": 2,
     "orders_7d": (1, 4), "complaints": (6, 12), "cancels": (2, 6), "credit": (35, 62)},

    {"key": "combo_fraud", "label": "综合高危（R030 一票否决）", "ratio": 0.04,
     "orders": (8, 16), "amount": (2200, 6800), "refund_rate": (0.55, 0.85),
     "postsale_rate": (0.4, 0.6), "addresses": (4, 9), "provinces": 5,
     "orders_7d": (2, 6), "complaints": (2, 6), "cancels": (2, 5), "credit": (5, 25),
     "night_bias": 0.5, "new_address": True, "big_basket": True},
]

assert abs(sum(p["ratio"] for p in PERSONAS) - 1.0) < 1e-9, "人设占比之和必须为 1"

PERSONA_BY_KEY: Dict[str, Dict[str, Any]] = {p["key"]: p for p in PERSONAS}


# ====================================================================== 工具
class _Gen:
    """把 random 实例 + 时间基准包起来，避免函数间传一堆参数。"""

    def __init__(self, seed: int, now: Optional[datetime] = None) -> None:
        self.rnd = random.Random(seed)
        self.now = now or datetime.now()
        self.rows: Dict[str, List[Dict[str, Any]]] = {}

    # -------------------------------------------------- 基础随机
    def pick(self, seq: List[Any]) -> Any:
        return self.rnd.choice(seq)

    def ri(self, low: int, high: int) -> int:
        return self.rnd.randint(low, high)

    def rf(self, low: float, high: float, digits: int = 2) -> float:
        return round(self.rnd.uniform(low, high), digits)

    def span(self, pair: Tuple[Any, Any]) -> Any:
        low, high = pair
        if isinstance(low, int) and isinstance(high, int):
            return self.ri(low, high)
        return self.rf(float(low), float(high))

    def chance(self, p: float) -> bool:
        return self.rnd.random() < p

    # -------------------------------------------------- 时间
    def past(self, days_low: int, days_high: int, night_bias: float = 0.12) -> datetime:
        """过去某一时刻。night_bias 概率落在 00:00-05:59（喂 order_is_night 特征）。"""
        day_offset = self.rnd.uniform(days_low, days_high)
        base = self.now - timedelta(days=day_offset)
        hour = self.ri(0, 5) if self.chance(night_bias) else self.ri(7, 23)
        return base.replace(hour=hour, minute=self.ri(0, 59), second=self.ri(0, 59),
                            microsecond=0)

    # -------------------------------------------------- 落库缓冲
    def add(self, table: str, row: Dict[str, Any]) -> None:
        self.rows.setdefault(table, []).append(row)

    def count(self, table: str) -> int:
        return len(self.rows.get(table, []))


def _fmt(dt: datetime) -> str:
    return dt.strftime(FMT)


def _name(g: _Gen) -> str:
    return g.pick(list(SURNAMES)) + g.pick(GIVEN)


def _phone(g: _Gen) -> str:
    return g.pick(["133", "138", "139", "150", "151", "159", "176", "182", "188", "199"]) + \
        "".join(str(g.ri(0, 9)) for _ in range(8))


def _ip(g: _Gen) -> str:
    return f"{g.pick([36, 58, 101, 112, 116, 183, 223])}.{g.ri(0, 255)}.{g.ri(0, 255)}.{g.ri(1, 254)}"


# ====================================================================== 商品目录
def _seed_catalog(g: _Gen) -> List[Dict[str, Any]]:
    """商品分类 / 商品 / SKU —— 全站共享，与用户无关。"""
    skus: List[Dict[str, Any]] = []
    for cid, cname, products in CATEGORIES:
        g.add("product_category", {"category_id": cid, "category_name": cname,
                                   "parent_id": "", "level": 1})
        for idx, (pname, brand, price) in enumerate(products, start=1):
            pid = f"P{cid[1:]}{idx:02d}"
            g.add("product_info", {"product_id": pid, "product_name": pname,
                                   "category_id": cid, "brand": brand,
                                   "price": price, "status": "在售"})
            for sidx, spec in enumerate(("标准版", "升级版", "礼盒装"), start=1):
                sku_price = round(price * (1.0 + 0.12 * (sidx - 1)), 2)
                sku_id = f"{pid}S{sidx}"
                g.add("product_sku", {"sku_id": sku_id, "product_id": pid,
                                      "sku_name": f"{pname}·{spec}", "price": sku_price,
                                      "stock": g.ri(0, 800)})
                skus.append({"sku_id": sku_id, "product_id": pid, "category_id": cid,
                             "price": sku_price, "name": pname})
    return skus


# ====================================================================== 单个用户
def _seed_user(g: _Gen, index: int, persona: Dict[str, Any],
               skus: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按人设生成 1 个用户的全套业务数据。返回该用户的摘要（供报表）。"""
    uid = f"{1000 + index}"
    is_new_user = bool(persona.get("new_user"))
    register_days = g.ri(1, 6) if is_new_user else g.ri(45, 900)
    register_time = g.now - timedelta(days=register_days)
    user_level = ("钻石" if persona["key"] == "vip" else
                  "黄金" if persona["key"] in ("whale", "combo_fraud") else
                  g.pick(["普通", "普通", "白银", "黄金"]))

    g.add("user_info", {
        "user_id": uid, "user_name": _name(g), "phone": _phone(g),
        "email": f"user{uid}@example.com", "user_level": user_level,
        "user_status": "冻结" if persona["key"] == "combo_fraud" and g.chance(0.3) else "正常",
        "credit_score": g.span(persona["credit"]),
        "register_time": _fmt(register_time), "deleted_at": None,
    })

    # ---------------------------------------------------------- 设备 & 登录
    device_count = 4 if persona["key"] in ("burst_buyer", "combo_fraud", "address_farmer") else g.ri(1, 2)
    for d in range(device_count):
        dtype, dos = g.pick(DEVICE_TYPES)
        g.add("device_info", {
            "device_id": f"DEV_{uid}_{d + 1}", "user_id": uid, "device_type": dtype, "os": dos,
            "device_fingerprint": "".join(g.pick(list("0123456789abcdef")) for _ in range(32)),
            "first_seen": _fmt(g.past(1, max(2, register_days))),
            "last_seen": _fmt(g.past(0, 3)),
        })
    for _ in range(g.ri(3, 14)):
        prov, city, _ = g.pick(PROVINCES)
        g.add("login_log", {
            "user_id": uid, "login_ip": _ip(g), "login_city": city,
            "login_device": g.pick(DEVICE_TYPES)[0],
            "login_status": "失败" if g.chance(0.12) else "成功",
            "login_time": _fmt(g.past(0, min(90, register_days))),
        })

    # ---------------------------------------------------------- 关联账号（风控关联实体）
    addr_count = g.span(persona["addresses"])
    province_pool = g.rnd.sample(PROVINCES, min(persona["provinces"], len(PROVINCES)))
    addresses: List[Dict[str, Any]] = []
    for a in range(addr_count):
        if g.chance(0.06):
            prov, city, districts = g.pick(OVERSEAS)
            overseas = 1
        else:
            prov, city, districts = province_pool[a % len(province_pool)] \
                if a < len(province_pool) else g.pick(province_pool)
            overseas = 0
        # new_address 人设：至少一个关联账号是 7 天内新增的（喂 addr_is_new 特征）
        if persona.get("new_address") and a == 0:
            created = g.past(0, 5)
        else:
            created = g.past(6, max(7, register_days))
        aid = f"ADDR_{uid}_{a + 1}"
        row = {
            "address_id": aid, "user_id": uid, "receiver_name": _name(g),
            "receiver_phone": _phone(g), "province": prov, "city": city,
            "district": g.pick(districts),
            "detail_address": f"{g.pick(['科技园', '文化路', '滨江大道', '人民路', '创业街'])}"
                              f"{g.ri(1, 199)}号{g.ri(1, 30)}栋{g.ri(101, 2508)}室",
            "is_default": 1 if a == 0 else 0, "is_overseas": overseas,
            "create_time": _fmt(created), "deleted_at": None,
        }
        g.add("user_address", row)
        addresses.append(row)

    # ---------------------------------------------------------- 学习行为
    total_orders = g.span(persona["orders"])
    orders_7d = min(g.span(persona["orders_7d"]), total_orders) if total_orders else 0
    amount_low, amount_high = persona["amount"]
    big_basket = bool(persona.get("big_basket"))
    night_bias = float(persona.get("night_bias", 0.12))
    fast_pay = bool(persona.get("fast_pay"))

    orders: List[Dict[str, Any]] = []
    for o in range(total_orders):
        # 前 orders_7d 单压缩到最近 7 天内，其余散布在注册至今
        if o < orders_7d:
            created = g.past(0, 6.5, night_bias)
        else:
            created = g.past(7, max(8, min(register_days, 365)), night_bias)

        item_count = g.ri(28, 40) if (big_basket and g.chance(0.4)) else g.ri(1, 5)
        chosen = [g.pick(skus) for _ in range(item_count)]
        raw_total = 0.0
        oid = f"ORD{uid}{o + 1:04d}"
        for i, sku in enumerate(chosen, start=1):
            qty = g.ri(1, 3)
            amount = round(sku["price"] * qty, 2)
            raw_total += amount
            g.add("order_item", {
                "item_id": f"IT{uid}{o + 1:04d}{i:02d}", "order_id": oid,
                "product_id": sku["product_id"], "sku_id": sku["sku_id"],
                "quantity": qty, "price": sku["price"], "amount": amount,
            })
        # 用人设的金额区间「校准」总额，避免商品单价主导
        target = float(g.span((amount_low, amount_high)))
        scale = target / raw_total if raw_total > 0 else 1.0
        total_amount = round(raw_total * scale, 2)
        # 折扣：15% 概率给极高折扣（喂 R004 order_discount_rate >= 0.7）
        if g.chance(0.15):
            discount = round(total_amount * g.rf(0.7, 0.88), 2)
        else:
            discount = round(total_amount * g.rf(0.0, 0.25), 2)
        pay_amount = round(max(total_amount - discount, 0.01), 2)

        status_pool = ["已完成", "已完成", "已支付", "已退课", "已取消", "已退款", "待支付"]
        status = g.pick(status_pool)
        pay_time: Optional[datetime] = None
        if status not in ("待支付", "已取消"):
            gap = g.ri(0, 3) if (fast_pay or g.chance(0.12)) else g.ri(20, 3600)
            pay_time = created + timedelta(seconds=gap)

        addr = g.pick(addresses)
        order_row = {
            "order_id": oid, "user_id": uid, "order_status": status,
            "total_amount": total_amount, "discount_amount": discount,
            "pay_amount": pay_amount, "receive_id": addr["address_id"],
            "order_source": g.pick(ORDER_SOURCES), "create_time": _fmt(created),
            "pay_time": _fmt(pay_time) if pay_time else None, "deleted_at": None,
        }
        g.add("order_info", order_row)
        orders.append({**order_row, "_created": created, "_pay_time": pay_time})

        if pay_time is not None:
            g.add("order_payment", {
                "payment_id": f"PAY{uid}{o + 1:04d}", "order_id": oid, "user_id": uid,
                "pay_channel": g.pick(PAY_CHANNELS), "pay_amount": pay_amount,
                "pay_status": "成功", "pay_time": _fmt(pay_time),
            })
        if discount > 0 and g.chance(0.5):
            g.add("coupon_record", {
                "coupon_record_id": f"CPN{uid}{o + 1:04d}", "user_id": uid, "order_id": oid,
                "coupon_name": g.pick(["新人立减券", "满 300 减 50", "课程 8 折券", "会员日专享"]),
                "discount_amount": discount, "use_time": _fmt(created),
            })
        if status in ("已发货", "已完成"):
            ship = created + timedelta(hours=g.ri(6, 72))
            g.add("logistics_order", {
                "logistics_id": f"LG{uid}{o + 1:04d}", "order_id": oid,
                "express_company": g.pick(EXPRESS),
                "express_no": f"SF{g.ri(10 ** 11, 10 ** 12 - 1)}",
                "logistics_status": "已签收" if status == "已完成" else "运输中",
                "ship_time": _fmt(ship),
                "sign_time": _fmt(ship + timedelta(hours=g.ri(12, 120))) if status == "已完成" else None,
            })

    # ---------------------------------------------------------- 成绩申诉 / 退课
    paid_orders = [o for o in orders if o["order_status"] not in ("待支付", "已取消")]
    refund_target = int(round(len(orders) * float(g.span(persona["refund_rate"]))))
    refund_target = min(refund_target, len(paid_orders))
    postsale_target = int(round(len(orders) * float(g.span(persona["postsale_rate"]))))
    postsale_target = min(postsale_target, len(paid_orders))

    postsale_orders = g.rnd.sample(paid_orders, postsale_target) if postsale_target else []
    postsale_ids: Dict[str, str] = {}
    for i, o in enumerate(postsale_orders, start=1):
        psid = f"PS{uid}{i:04d}"
        postsale_ids[o["order_id"]] = psid
        created = o["_created"] + timedelta(days=g.ri(1, 15))
        g.add("postsale", {
            "postsale_id": psid, "order_id": o["order_id"], "user_id": uid,
            "postsale_type": g.pick(DROPOUT_TYPES),
            "postsale_status": g.pick(["待处理", "处理中", "已完成", "已拒绝"]),
            "apply_amount": o["pay_amount"], "reason": g.pick(APPEAL_REASONS),
            "create_time": _fmt(min(created, g.now)),
            "finish_time": _fmt(min(created + timedelta(days=g.ri(1, 7)), g.now))
                           if g.chance(0.6) else None,
        })

    refund_orders = g.rnd.sample(paid_orders, refund_target) if refund_target else []
    refund_amount_total = 0.0
    for i, o in enumerate(refund_orders, start=1):
        amt = round(float(o["pay_amount"]) * g.rf(0.5, 1.0), 2)
        refund_amount_total += amt
        g.add("refund_record", {
            "refund_id": f"RF{uid}{i:04d}", "order_id": o["order_id"],
            "postsale_id": postsale_ids.get(o["order_id"], ""), "user_id": uid,
            "refund_amount": amt, "refund_status": g.pick(["成功", "成功", "成功", "处理中"]),
            "refund_time": _fmt(min(o["_created"] + timedelta(days=g.ri(1, 20)), g.now)),
        })

    # ---------------------------------------------------------- 反馈投诉 / 撤课
    complaint_total = g.span(persona["complaints"])
    for i in range(complaint_total):
        o = g.pick(orders) if orders else None
        if g.chance(0.5):
            g.add("complaint_record", {
                "complaint_id": f"CP{uid}{i + 1:04d}", "user_id": uid,
                "order_id": o["order_id"] if o else "",
                "complaint_type": g.pick(["答疑响应慢", "服务态度", "直播卡顿", "价格争议"]),
                "content": g.pick(["承诺的直播未按时开课", "助教长时间无响应", "赠课未随课发放",
                                   "实际课程与页面不符"]),
                "status": g.pick(["待处理", "处理中", "已解决"]),
                "create_time": _fmt(g.past(0, 120)),
            })
        else:
            g.add("logistics_complaints_record", {
                "order_id": o["order_id"] if o else "", "user_id": uid,
                "complaint_type": g.pick(COMPLAINT_TYPES),
                "complaint_content": g.pick(["课程视频长时间加载失败", "作业系统显示提交但未记录",
                                             "账号异常被强制下线", "客服电话不通"]),
                "complaint_status": g.pick(["待处理", "处理中", "已解决"]),
                "is_verified": 1 if g.chance(0.45) else 0,
                "create_time": _fmt(g.past(0, 120)),
            })

    cancel_orders = [o for o in orders if o["order_status"] == "已取消"]
    cancel_total = min(g.span(persona["cancels"]), len(cancel_orders)) if cancel_orders else 0
    for i, o in enumerate(cancel_orders[:cancel_total], start=1):
        g.add("cancel_record", {
            "cancel_id": f"CC{uid}{i:04d}", "order_id": o["order_id"], "user_id": uid,
            "cancel_reason": g.pick(ABORT_REASONS),
            "cancel_time": _fmt(o["_created"] + timedelta(minutes=g.ri(5, 2880))),
        })

    return {
        "user_id": uid, "persona": persona["key"], "persona_label": persona["label"],
        "orders": len(orders), "orders_7d": orders_7d, "addresses": addr_count,
        "refunds": len(refund_orders), "refund_amount": round(refund_amount_total, 2),
        "postsales": len(postsale_orders), "complaints": complaint_total,
        "refund_rate": round(len(refund_orders) / len(orders), 3) if orders else 0.0,
        "postsale_rate": round(len(postsale_orders) / len(orders), 3) if orders else 0.0,
        "avg_amount": round(sum(float(o["total_amount"]) for o in orders) / len(orders), 2)
                      if orders else 0.0,
        "max_amount": round(max((float(o["total_amount"]) for o in orders), default=0.0), 2),
        "sample_order": orders[0]["order_id"] if orders else "",
        "sample_postsale": next(iter(postsale_ids.values()), ""),
    }


# ====================================================================== 黑名单
def _seed_blacklist(g: _Gen, summaries: List[Dict[str, Any]]) -> None:
    """黑名单只拉黑「确实高危」的人设，保证撞黑演示可复现。"""
    high_risk = [s for s in summaries if s["persona"] in ("combo_fraud", "refund_abuser")]
    for s in high_risk[:6]:
        g.add("risk_blacklist", {
            "blacklist_type": "用户", "blacklist_value": s["user_id"],
            "risk_level": "极高" if s["persona"] == "combo_fraud" else "高",
            "reason": f"{s['persona_label']}：申诉通过率 {1-s['refund_rate']:.0%}、"
                      f"退课率 {s['postsale_rate']:.0%}，已确认恶意刷分",
            "source": "系统", "operator": "risk_admin", "hit_count": g.ri(0, 9),
            "expire_time": None if g.chance(0.6)
                           else _fmt(g.now + timedelta(days=g.ri(30, 180))),
            "is_enabled": 1, "create_time": _fmt(g.past(1, 60)), "deleted_at": None,
        })
    # 其他类型各来一条，覆盖 5 种 blacklist_type
    extras = [
        ("手机号", _phone(g), "高", "该号码关联多起虚假成绩申诉"),
        ("账号", "广东省深圳市宝安区某机构关联账号集群", "中", "疑似批量关联报名账号"),
        ("设备", f"DEV_{g.ri(1000, 1060)}_1", "高", "同一设备切换 30+ 账号考试"),
        ("IP", _ip(g), "中", "代理 IP 段，批量注册来源"),
    ]
    for btype, value, level, reason in extras:
        g.add("risk_blacklist", {
            "blacklist_type": btype, "blacklist_value": value, "risk_level": level,
            "reason": reason, "source": g.pick(["人工", "系统", "外部"]),
            "operator": "risk_admin", "hit_count": g.ri(0, 5),
            "expire_time": None, "is_enabled": 1,
            "create_time": _fmt(g.past(1, 90)), "deleted_at": None,
        })


# ====================================================================== 主入口
INSERT_ORDER: Tuple[str, ...] = (
    "product_category", "product_info", "product_sku",
    "user_info", "user_address", "device_info", "login_log",
    "order_info", "order_item", "order_payment", "coupon_record", "logistics_order",
    "postsale", "refund_record", "cancel_record",
    "complaint_record", "logistics_complaints_record",
    "risk_blacklist",
)

BUSINESS_TABLE_NAMES: Tuple[str, ...] = tuple(t.name for t in models.BUSINESS_TABLES)


def clear_business_data(db: Any) -> Dict[str, int]:
    """清空 17 张业务表 + 黑名单（不动 risk_event / risk_rule）。"""
    removed: Dict[str, int] = {}
    for table in reversed(INSERT_ORDER):
        cur = db.execute(f'DELETE FROM "{table}"')
        if cur.rowcount and cur.rowcount > 0:
            removed[table] = cur.rowcount
    return removed


def generate(db: Any, users: int = 60, seed: int = 42, reset: bool = False,
             progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """生成业务样例数据并落库。

    Args:
        db: `database.Session`
        users: 用户数（按 PERSONAS 占比分配人设）
        seed: 随机种子（同 seed 结果完全一致）
        reset: True 先清空业务表
        progress: 进度回调
    Returns:
        统计字典：各表行数 + 人设分布 + 高危样本清单
    """
    say = progress or (lambda msg: logger.info("%s", msg))
    g = _Gen(seed)

    if reset:
        removed = clear_business_data(db)
        say(f"已清空业务表 {len(removed)} 张（共 {sum(removed.values())} 行）")

    if db.scalar("SELECT COUNT(1) FROM user_info") > 0 and not reset:
        raise RuntimeError("业务表已有数据。加 --reset 覆盖，或先清空。")

    skus = _seed_catalog(g)
    say(f"商品目录：{g.count('product_category')} 分类 / "
        f"{g.count('product_info')} 商品 / {g.count('product_sku')} SKU")

    # 按占比展开人设队列，再打散顺序（避免 user_id 与人设强相关）
    queue: List[Dict[str, Any]] = []
    for persona in PERSONAS:
        for _ in range(max(1, int(round(users * persona["ratio"])))):
            queue.append(persona)
    queue = queue[:users] if len(queue) > users else queue
    while len(queue) < users:
        queue.append(PERSONA_BY_KEY["normal"])
    g.rnd.shuffle(queue)

    summaries: List[Dict[str, Any]] = []
    for idx, persona in enumerate(queue, start=1):
        summaries.append(_seed_user(g, idx, persona, skus))
    say(f"用户数据：{len(summaries)} 人 / {g.count('order_info')} 单 / "
        f"{g.count('refund_record')} 退款 / {g.count('postsale')} 售后")

    _seed_blacklist(g, summaries)

    # -------------------------------------------------- 批量落库
    table_stats: Dict[str, int] = {}
    for table in INSERT_ORDER:
        rows = g.rows.get(table, [])
        if not rows:
            continue
        # 同表内字段可能不完全一致（如 pay_time 为 None），按首行 key 分组批量插
        buckets: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
        for row in rows:
            buckets.setdefault(tuple(row.keys()), []).append(row)
        inserted = 0
        for bucket in buckets.values():
            inserted += db.insert_many(table, bucket)
        table_stats[table] = inserted

    persona_dist: Dict[str, int] = {}
    for s in summaries:
        persona_dist[s["persona_label"]] = persona_dist.get(s["persona_label"], 0) + 1

    highlights = [s for s in summaries
                  if s["persona"] in ("combo_fraud", "refund_abuser", "burst_buyer",
                                      "whale", "address_farmer")]
    highlights.sort(key=lambda s: (s["persona"] != "combo_fraud", -s["refund_rate"]))

    return {
        "seed": seed,
        "users": len(summaries),
        "tables": table_stats,
        "total_rows": sum(table_stats.values()),
        "persona_distribution": persona_dist,
        "highlights": highlights[:12],
        "summaries": summaries,
    }


__all__ = ["generate", "clear_business_data", "PERSONAS", "PERSONA_BY_KEY",
           "BUSINESS_TABLE_NAMES", "INSERT_ORDER"]
