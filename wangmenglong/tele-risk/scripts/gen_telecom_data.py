"""
电信风控系统 - 业务数据造数脚本
==============================
往 telecom 库灌入 300 张号卡 (50 风险 + 250 正常), 含 5 类风险画像.
特征分布刻意设计为 "有区分度但不完美", 让 XGBoost 能学到真实模式.

规模:
  - region/plan/cell/channel/device: 基础维度表 (扩充)
  - customer: 50 条 (含 5 风险客户)
  - card: 300 条 (核心: 50 风险 + 250 正常)
  - cdr: ~1500 条 (通话记录, 含风险画像)
  - sms: ~500 条
  - data_usage: ~1500 条
  - 其余: binding/order/iot 配套

风险画像 (50 张):
  - GOIP 虚拟拨号 : 8 张, 1h 内 15-30 次主叫, 固定基站, 机卡异地
  - 猫池养卡     : 10 张, 2 组共享 IMEI (每组 5 张), 基站相同
  - 一证多卡     : 10 张, 同一客户名下 10 张卡, 异地开卡
  - 国际诈骗来电 : 7 张, 24h 内 10-20 次国际漫游被叫
  - 物联网滥用   : 15 张, 机卡分离 + 流量突增 (5-10x 均值)

幂等: 重复跑会先 DELETE 清空 (按依赖顺序), 再插入.
连接: localhost:3306 root/123321 telecom (可环境变量覆盖).

用法: python scripts/gen_telecom_data.py
"""
import os
import random
import sys
from datetime import datetime, timedelta

import pymysql
from faker import Faker

# ============================================================
# 配置
# ============================================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123321")
DB_NAME = os.getenv("DB_NAME", "telecom")

random.seed(20260812)
fake = Faker("zh_CN")
Faker.seed(20260812)

NOW = datetime(2026, 8, 12, 18, 0, 0)

PROVINCES = [
    ("北京", "北京市", "朝阳区"), ("北京", "北京市", "海淀区"),
    ("上海", "上海市", "浦东新区"), ("上海", "上海市", "黄浦区"),
    ("广东", "广州市", "天河区"), ("广东", "深圳市", "南山区"),
    ("浙江", "杭州市", "西湖区"), ("江苏", "南京市", "鼓楼区"),
    ("四川", "成都市", "锦江区"), ("湖北", "武汉市", "武昌区"),
    ("福建", "厦门市", "思明区"), ("山东", "济南市", "历下区"),
]
BRANDS = [
    ("华为", "Mate 60", "HarmonyOS"), ("华为", "Pura 70", "HarmonyOS"),
    ("小米", "14", "Android"), ("小米", "Redmi K70", "Android"),
    ("OPPO", "Find X7", "Android"), ("vivo", "X100", "Android"),
    ("苹果", "iPhone 15", "iOS"), ("苹果", "iPhone 14", "iOS"),
    ("三星", "Galaxy S24", "Android"), ("荣耀", "Magic6", "Android"),
]
IOT_SCENES = [
    ("车联网", "车载T-Box"), ("智能表计", "智能水表"),
    ("POS", "无线POS机"), ("工业", "工业网关"), ("其他", "通用模组"),
]

# ============================================================
# 工具函数
# ============================================================
def _msisdn(idx: int) -> str:
    return f"138{idx:08d}"

def _imsi(idx: int) -> str:
    return f"4600{idx:011d}"

def _iccid(idx: int) -> str:
    return f"8986{idx:015d}"

def _imei(idx: int) -> str:
    return f"{idx:015d}"

def _mac(idx: int) -> str:
    return f"{(idx % 256):02X}:{(idx // 256 % 256):02X}:{(idx // 65536 % 256):02X}:{(idx // 16777216 % 256):02X}:AA:BB"

def _rand_msisdn() -> str:
    op = random.choice(["138", "139", "136", "158", "159", "188", "186", "133"])
    return op + "".join(str(random.randint(0, 9)) for _ in range(8))

def _rand_lac() -> str:
    return f"{random.randint(1000, 9999)}"

def _rand_time(days_back: int = 30) -> datetime:
    return NOW - timedelta(
        days=random.randint(0, days_back),
        seconds=random.randint(0, 86400),
    )

def _date_days_ago(n: int):
    return (NOW - timedelta(days=n)).date()


# ============================================================
# 各表生成
# ============================================================
def gen_region():
    return [(p, c, d) for p, c, d in PROVINCES]


def gen_plan():
    return [
        ("P001", "全球通128元套餐", "融合套餐", 128.00, 30720, 1000, 200),
        ("P002", "动感地带59元套餐", "流量套餐", 59.00, 20480, 200, 100),
        ("P003", "神州行29元套餐", "语音套餐", 29.00, 5120, 500, 50),
        ("P004", "物联网30元套餐", "物联网套餐", 30.00, 10240, 0, 100),
        ("P005", "政企融合199元套餐", "融合套餐", 199.00, 61440, 3000, 500),
    ]


def gen_channel():
    return [
        ("CH01", "北京朝阳旗舰营业厅", "营业厅", "北京", None, "正常", _date_days_ago(900)),
        ("CH02", "上海浦东营业厅", "营业厅", "上海", None, "正常", _date_days_ago(800)),
        ("CH03", "广州天河代理商A", "代理商", "广东", "AG001", "正常", _date_days_ago(500)),
        ("CH04", "深圳南山代理商B", "代理商", "广东", "AG002", "整改中", _date_days_ago(300)),
        ("CH05", "杭州西湖营业厅", "营业厅", "浙江", None, "正常", _date_days_ago(600)),
        ("CH06", "成都锦江代理商C", "代理商", "四川", "AG003", "正常", _date_days_ago(400)),
        ("CH07", "线上自助大厅", "线上自助", "北京", None, "正常", _date_days_ago(1000)),
        ("CH08", "武汉高校代办点", "代理商", "湖北", "AG004", "正常", _date_days_ago(250)),
        ("CH09", "南京鼓楼代理商D", "代理商", "江苏", "AG005", "正常", _date_days_ago(200)),
        ("CH10", "厦门思明营业厅", "营业厅", "福建", None, "正常", _date_days_ago(700)),
    ]


def gen_cell():
    cells = []
    for i, (p, c, d) in enumerate(PROVINCES):
        cells.append((
            f"CELL{i+1:03d}", _rand_lac(), p, c, d,
            random.choice(["宏站", "微站", "室内分布"]),
            round(random.uniform(73, 135), 6), round(random.uniform(18, 53), 6),
        ))
    for j in range(10):
        p, c, d = random.choice(PROVINCES)
        cells.append((
            f"CELL{13+j:03d}", _rand_lac(), p, c, d, "宏站",
            round(random.uniform(73, 135), 6), round(random.uniform(18, 53), 6),
        ))
    return cells


def gen_device():
    devs = []
    for i, (brand, model, os_) in enumerate(BRANDS):
        devs.append((_imei(i + 1), _mac(i + 1), brand, model, os_, _rand_time(120)))
    for j in range(30):
        devs.append((_imei(11 + j), _mac(11 + j), "山寨", "未知型号", "其他", _rand_time(60)))
    return devs


def gen_customer():
    """52 个客户: 7 高风险 + 45 正常 (含部分中风险)"""
    custs = []
    # 7 风险客户
    risk_profiles = [
        ("C00000001", "高风险", "GOIP嫌疑"),
        ("C00000002", "高风险", "猫池养卡"),
        ("C00000003", "高风险", "一证多卡"),
        ("C00000004", "高风险", "国际诈骗"),
        ("C00000005", "高风险", "物联网滥用"),
        ("C00000006", "高风险", "话费套现"),
        ("C00000007", "高风险", "集团诈骗"),
    ]
    for cid, tag, _desc in risk_profiles:
        custs.append(_make_customer(cid, risk_tag=tag))
    # 45 普通客户 (从 C00000008 开始, 避免与风险客户 ID 冲突)
    for i in range(8, 53):
        cid = f"C{i:08d}"
        tag = random.choices(["正常", "中风险"], weights=[80, 20])[0]
        custs.append(_make_customer(cid, risk_tag=tag))
    return custs


def _make_customer(cid: str, risk_tag: str = "正常"):
    gender = random.choice(["男", "女"])
    return (
        cid, "个人", "身份证", fake.ssn(),
        fake.name(), gender,
        fake.date_of_birth(minimum_age=18, maximum_age=75),
        random.choices(["通过", "未核验"], weights=[90, 10])[0],
        _rand_time(365), risk_tag,
    )


def gen_card():
    """300 张号卡: 60 风险 + 240 正常."""
    cards = []

    # ---- RISK001: GOIP (8 张, 机卡异地 + 异地开卡 + 1h 高频) ----
    for i in range(1, 9):
        cards.append(_make_card(
            i, "C00000001", "CH04", "广东",
            imei=_imei(101 + i), roam_status="省间漫游", risk="goip",
        ))

    # ---- RISK002: 猫池 (10 张, 2 组共享 IMEI, 每组 5 张) ----
    shared_imei_1 = _imei(201)
    shared_imei_2 = _imei(202)
    for i in range(9, 14):
        cards.append(_make_card(i, "C00000002", "CH04", "广东", imei=shared_imei_1, risk="catpool"))
    for i in range(14, 19):
        cards.append(_make_card(i, "C00000002", "CH06", "四川", imei=shared_imei_2, risk="catpool"))

    # ---- RISK003: 一证多卡 (10 张, 同一客户, 异地开卡) ----
    for i in range(19, 29):
        cards.append(_make_card(i, "C00000003", "CH08", "湖北",
                                imei=_imei(110 + i), risk="multi_card"))

    # ---- RISK004: 国际诈骗 (7 张, 国际漫游 + 高频国际来电) ----
    for i in range(29, 36):
        cards.append(_make_card(i, "C00000004", "CH03", "广东",
                                imei=_imei(120 + i), intl=True,
                                roam_status="国际漫游", risk="intl_fraud"))

    # ---- RISK005: 物联网卡滥用 (15 张, 机卡分离) ----
    for i in range(36, 51):
        cards.append(_make_card(i, "C00000005", "CH07", "北京",
                                imei=None, is_iot=True, risk="iot_abuse"))

    # ---- RISK006: 话费套现 (5 张, 高频充值+转出) ----
    for i in range(295, 300):
        cards.append(_make_card(i, "C00000006", "CH03", "广东",
                                imei=_imei(130 + i), risk="cash_out"))

    # ---- RISK007: 集团子号异常 (5 张, 集团子号+高频外呼) ----
    for i in range(290, 295):
        cards.append(_make_card(i, "C00000007", "CH01", "北京",
                                imei=_imei(140 + i), risk="group_sub"))

    # ---- 240 张正常卡 (idx 51-289, 290-299 已分配给风险) ----
    cust_ids_normal = [f"C{i:08d}" for i in range(8, 53)]
    channel_ids_normal = ["CH01", "CH02", "CH03", "CH05", "CH06", "CH07", "CH09", "CH10"]
    risk_indices = set(range(1, 51)) | set(range(290, 300))
    for i in range(51, 300):
        if i in risk_indices:
            continue
        cid = random.choice(cust_ids_normal)
        ch = random.choice(channel_ids_normal)
        prov = random.choice(PROVINCES)[0]
        risk = "normal" if random.random() > 0.12 else "remote_open"
        cards.append(_make_card(i, cid, ch, prov, risk=risk))

    return cards


def _make_card(idx, customer_id, channel_id, open_province,
               imei=None, is_iot=False, intl=False,
               roam_status="归属地", risk="normal"):
    plan_id = "P004" if is_iot else random.choice(["P001", "P002", "P003", "P005"])
    open_time = _rand_time(180)
    if risk in ("goip", "catpool"):
        roam_status = "省间漫游"
    if risk == "intl_fraud":
        roam_status = "国际漫游"
    return (
        _msisdn(idx), _imsi(idx), _iccid(idx),
        customer_id, imei, plan_id, channel_id,
        open_time, open_province,
        "正常", roam_status, 1 if intl else 0, 1 if is_iot else 0,
        open_time,
    )


def gen_iot_card(cards):
    rows = []
    iot_cards = [c for c in cards if c[12] == 1]
    for i, c in enumerate(iot_cards):
        msisdn = c[0]
        scene, dev_type = IOT_SCENES[i % len(IOT_SCENES)]
        # RISK005: 机卡分离 (bound_device_imei 跟 card.current_imei 不一致 / 为空)
        if i < 10:
            bound_imei = None  # 前 10 张物联网卡无绑定 → 机卡分离
        else:
            bound_imei = _imei(400 + i)
        rows.append((
            msisdn, scene, bound_imei, dev_type, "仅数据",
            _rand_time(90),
        ))
    return rows


def gen_card_device_binding(cards):
    rows = []
    for c in cards:
        msisdn = c[0]
        imei = c[4]
        if not imei:
            continue
        bind_time = c[7]
        bind_prov = c[8]
        rows.append((msisdn, imei, bind_time, None, bind_prov))
        if random.random() < 0.25:
            old_imei = _imei(random.randint(500, 600))
            old_time = bind_time - timedelta(days=random.randint(1, 30))
            rows.append((msisdn, old_imei, old_time, bind_time, bind_prov))
    return rows


def gen_service_order(cards):
    rows = []
    seq = 0
    for c in cards:
        seq += 1
        msisdn, customer_id, channel_id = c[0], c[3], c[6]
        open_time, open_prov = c[7], c[8]
        oid = f"SO{open_time.strftime('%Y%m%d%H%M%S')}{seq:04d}"
        face = "通过" if random.random() > 0.05 else "未通过"
        rows.append((
            oid, msisdn, customer_id, channel_id, "新开户",
            open_time, open_prov, "成功", face, None,
        ))
    # 补卡/解除限制业务
    extra = [
        ("C00000003", "13800000019", "CH08", "补卡", "湖北"),
        ("C00000003", "13800000020", "CH08", "补卡", "湖北"),
        ("C00000003", "13800000021", "CH08", "销户", "湖北"),
        ("C00000004", "13800000029", "CH03", "解除限制", "广东"),
    ]
    for cid, msisdn, ch, otype, prov in extra:
        seq += 1
        t = _rand_time(60)
        oid = f"SO{t.strftime('%Y%m%d%H%M%S')}{seq:04d}"
        rows.append((oid, msisdn, cid, ch, otype, t, prov, "成功", "通过", "风险业务"))
    # CH04 渠道批量开卡 (短时间)
    ch04_cards = [c for c in cards if c[6] == "CH04"]
    base_t = NOW - timedelta(hours=2)
    for k, c in enumerate(ch04_cards[:15]):
        seq += 1
        t = base_t + timedelta(minutes=k * 2)
        oid = f"SO{t.strftime('%Y%m%d%H%M%S')}{seq:04d}"
        rows.append((oid, c[0], c[3], "CH04", "实名核验", t, "广东", "成功", "通过", "渠道批量核验"))
    return rows


def gen_billing(cards):
    """话费账单: 套现卡(295-299)高频充值+转出, 其他卡正常消费."""
    rows = []
    bill_month = NOW.strftime("%Y-%m")
    cash_out_msisdns = {_msisdn(i) for i in range(295, 300)}

    for c in cards:
        msisdn = c[0]
        if msisdn in cash_out_msisdns:
            # 套现画像: 1h 内 3-5 次充值, 然后大额转出
            base = NOW - timedelta(minutes=30)
            for k in range(random.randint(3, 5)):
                t = base + timedelta(minutes=k * 5)
                amount = random.choice([500, 800, 1000, 2000])
                rows.append((
                    msisdn, bill_month, "充值", amount,
                    0, amount, "支付宝", "话费套现-充值", t,
                ))
            # 紧接着大额转出
            for k in range(random.randint(2, 4)):
                t = base + timedelta(minutes=40 + k * 10)
                amount = random.choice([800, 1200, 1500, 2000])
                rows.append((
                    msisdn, bill_month, "转出", amount,
                    3000 - amount, 3000 - 2 * amount, "银行转账", "话费套现-转出", t,
                ))
            # 少量正常消费
            for k in range(random.randint(1, 3)):
                t = _rand_time(30)
                amount = random.randint(10, 80)
                rows.append((
                    msisdn, bill_month, "消费", amount,
                    5000, 5000 - amount, None, "正常通话消费", t,
                ))
        else:
            # 普通卡: 每月 2-5 条消费记录
            for k in range(random.randint(2, 5)):
                t = _rand_time(30)
                amount = random.randint(5, 200)
                rows.append((
                    msisdn, bill_month, "消费", amount,
                    random.randint(100, 500), random.randint(50, 400),
                    random.choice(["支付宝", "微信", None]), "正常消费", t,
                ))
            # 偶尔充值
            if random.random() < 0.3:
                t = _rand_time(15)
                amount = random.choice([50, 100, 200])
                rows.append((
                    msisdn, bill_month, "充值", amount,
                    0, amount, random.choice(["支付宝", "微信", None]), "正常充值", t,
                ))
    return rows


def gen_group_customer():
    """集团客户: 政企集团 (C00000007 为集团主客户)."""
    return [
        ("G00000001", "北京恒通科技集团", "政企", "C00000007",
         "张经理", "13800000001", _date_days_ago(500), "正常"),
    ]


def gen_cdr(cards):
    """通话记录. 含 GOIP 短时高频/凌晨 / 猫池多卡 / 国际来电 / 集团子号 / 正常."""
    rows = []
    cell_all = [f"CELL{i:03d}" for i in range(1, 21)]

    # ---- GOIP (8 张): 1h 内 15-30 次主叫, 固定基站 CELL130 + 凌晨呼叫 ----
    goip_msisdns = [_msisdn(i) for i in range(1, 9)]
    goip_cell = "CELL130"
    for msisdn in goip_msisdns:
        n_calls = random.randint(15, 30)
        base = NOW - timedelta(hours=2)
        for k in range(n_calls):
            t = base + timedelta(seconds=k * (3600 // n_calls))
            dur = random.randint(3, 25)
            idx = int(msisdn[3:])
            rows.append((
                msisdn, _rand_msisdn(), "主叫", t, t + timedelta(seconds=dur),
                dur, goip_cell, _imei(100 + idx), "省间漫游", None,
            ))
        # 凌晨(0-6点)额外高频呼叫 (R015: 凌晨密集呼叫)
        night_base = NOW.replace(hour=2, minute=0, second=0, microsecond=0)
        for k in range(random.randint(10, 20)):
            t = night_base + timedelta(minutes=k * 2)
            dur = random.randint(3, 15)
            idx = int(msisdn[3:])
            rows.append((
                msisdn, _rand_msisdn(), "主叫", t, t + timedelta(seconds=dur),
                dur, goip_cell, _imei(100 + idx), "省间漫游", None,
            ))

    # ---- 猫池 (10 张): 2 组, 同组同基站同 IMEI ----
    catpool_group1 = [_msisdn(i) for i in range(9, 14)]
    catpool_group2 = [_msisdn(i) for i in range(14, 19)]
    for group, cell, imei_base in [(catpool_group1, "CELL131", 201), (catpool_group2, "CELL132", 202)]:
        for msisdn in group:
            n_calls = random.randint(5, 12)
            for k in range(n_calls):
                t = NOW - timedelta(hours=random.randint(1, 12))
                dur = random.randint(2, 15)
                rows.append((
                    msisdn, _rand_msisdn(), "主叫", t, t + timedelta(seconds=dur),
                    dur, cell, _imei(imei_base), "省间漫游", None,
                ))

    # ---- 国际诈骗 (7 张): 24h 内 10-20 次国际漫游被叫 ----
    intl_msisdns = [_msisdn(i) for i in range(29, 36)]
    for msisdn in intl_msisdns:
        n_calls = random.randint(10, 20)
        for k in range(n_calls):
            t = NOW - timedelta(hours=random.randint(1, 24))
            dur = random.randint(10, 120)
            rows.append((
                _rand_msisdn(), msisdn, "被叫", t, t + timedelta(seconds=dur),
                dur, random.choice(cell_all), None, "国际", "缅甸",
            ))

    # ---- 物联网卡: 无 CDR (数据专用) ----

    # ---- 集团子号 (5 张): 高频外呼 (R014: 集团子号异常) ----
    group_msisdns = [_msisdn(i) for i in range(290, 295)]
    for msisdn in group_msisdns:
        n_calls = random.randint(25, 40)
        base = NOW - timedelta(hours=12)
        idx = int(msisdn[3:])
        for k in range(n_calls):
            t = base + timedelta(minutes=k * 20)
            dur = random.randint(5, 30)
            rows.append((
                msisdn, _rand_msisdn(), "主叫", t, t + timedelta(seconds=dur),
                dur, random.choice(cell_all), _imei(140 + idx), "本地", None,
            ))

    # ---- 套现卡 (5 张): 正常通话 (风险在账单不在通话) ----
    cash_msisdns = [_msisdn(i) for i in range(295, 300)]
    for msisdn in cash_msisdns:
        n_calls = random.randint(2, 6)
        idx = int(msisdn[3:])
        for k in range(n_calls):
            t = _rand_time(30)
            dur = random.randint(30, 300)
            rows.append((
                msisdn, _rand_msisdn(), "主叫", t, t + timedelta(seconds=dur),
                dur, random.choice(cell_all), _imei(130 + idx), "本地", None,
            ))

    # ---- 正常卡: 每卡 2-8 条通话 ----
    normal_exclude = set(goip_msisdns) | set(catpool_group1) | set(catpool_group2) \
                    | set(intl_msisdns) | set(group_msisdns) | set(cash_msisdns)
    normal_cards = [c for c in cards if c[0] not in normal_exclude and c[12] == 0]
    for c in normal_cards:
        n = random.randint(2, 8)
        for _ in range(n):
            t = _rand_time(30)
            dur = random.randint(10, 600)
            cell = random.choice(cell_all)
            imei = c[4]
            roam = random.choices(["本地", "省内漫游", "省间漫游"], weights=[80, 15, 5])[0]
            rows.append((
                c[0], _rand_msisdn(), "主叫", t, t + timedelta(seconds=dur),
                dur, cell, imei, roam, None,
            ))
    return rows


def gen_sms(cards):
    rows = []
    cell_all = [f"CELL{i:03d}" for i in range(1, 21)]

    # 猫池: 群发短信
    catpool_group1 = [_msisdn(i) for i in range(9, 14)]
    catpool_group2 = [_msisdn(i) for i in range(14, 19)]
    for group, _cell in [(catpool_group1, "CELL131"), (catpool_group2, "CELL132")]:
        for caller in group:
            for _ in range(random.randint(3, 8)):
                t = NOW - timedelta(hours=random.randint(1, 24))
                rows.append((caller, _rand_msisdn(), t, "端口短信", _cell, None))

    # 正常卡: 每卡 0-3 条 (跳过风险卡 idx 1-50)
    for c in cards:
        idx = int(c[0][3:])  # MSISDN = "138" + 8位索引
        if idx <= 50:
            continue
        for _ in range(random.randint(0, 3)):
            t = _rand_time(30)
            rows.append((c[0], _rand_msisdn(), t, "普通短信", random.choice(cell_all), c[4]))
    return rows


def gen_data_usage(cards):
    """每卡近 7 天流量. 物联网风险卡流量突增 5-10x."""
    rows = []
    for c in cards:
        msisdn = c[0]
        is_iot = c[12] == 1
        idx = int(msisdn[3:])  # MSISDN = "138" + 8位索引
        for d in range(7):
            day = (NOW - timedelta(days=d)).date()
            # 物联网风险卡 (idx 36-45): 前 10 张流量突增
            if is_iot and 36 <= idx <= 45:
                if d == 0:
                    vol = random.randint(5000, 15000)  # 今日异常高
                else:
                    vol = random.randint(200, 800)  # 历史正常
            elif is_iot:
                vol = random.randint(50, 500)
            else:
                vol = random.randint(10, 2000)
            rows.append((
                msisdn, day, vol,
                random.choice([f"CELL{i:03d}" for i in range(1, 21)]),
                random.choices(["本地", "省内漫游"], weights=[90, 10])[0],
            ))
    return rows


# ============================================================
# 写入
# ============================================================
INSERT_SQL = {
    "telecom_region": "INSERT INTO telecom_region (province,city,district) VALUES (%s,%s,%s)",
    "telecom_plan": "INSERT INTO telecom_plan (plan_id,plan_name,plan_type,monthly_fee,data_quota_mb,voice_quota_min,sms_quota) VALUES (%s,%s,%s,%s,%s,%s,%s)",
    "telecom_channel": "INSERT INTO telecom_channel (channel_id,channel_name,channel_type,province,agent_id,status,open_date) VALUES (%s,%s,%s,%s,%s,%s,%s)",
    "telecom_cell": "INSERT INTO telecom_cell (cell_id,lac,province,city,district,cell_type,longitude,latitude) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
    "telecom_device": "INSERT INTO telecom_device (imei,mac_address,brand,model,os_type,first_seen_time) VALUES (%s,%s,%s,%s,%s,%s)",
    "telecom_customer": "INSERT INTO telecom_customer (customer_id,customer_type,id_type,id_no,real_name,gender,birthday,face_verify_status,register_time,risk_tag) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "telecom_card": "INSERT INTO telecom_card (msisdn,imsi,iccid,customer_id,current_imei,plan_id,open_channel_id,open_time,open_province,card_status,roam_status,intl_call_enabled,is_iot,status_update_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "telecom_iot_card": "INSERT INTO telecom_iot_card (msisdn,iot_scene,bound_device_imei,device_type,function_scope,activate_time) VALUES (%s,%s,%s,%s,%s,%s)",
    "telecom_card_device_binding": "INSERT INTO telecom_card_device_binding (msisdn,imei,bind_time,unbind_time,bind_province) VALUES (%s,%s,%s,%s,%s)",
    "telecom_service_order": "INSERT INTO telecom_service_order (order_id,msisdn,customer_id,channel_id,order_type,order_time,order_province,order_status,face_verify_result,remark) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "telecom_cdr": "INSERT INTO telecom_cdr (calling_no,called_no,call_type,start_time,end_time,duration,cell_id,imei,roam_type,call_from_country) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "telecom_sms": "INSERT INTO telecom_sms (sending_no,receiving_no,send_time,sms_type,cell_id,imei) VALUES (%s,%s,%s,%s,%s,%s)",
    "telecom_data_usage": "INSERT INTO telecom_data_usage (msisdn,usage_date,data_volume_mb,cell_id,roam_type) VALUES (%s,%s,%s,%s,%s)",
    "telecom_billing_record": "INSERT INTO telecom_billing_record (msisdn,bill_month,bill_type,amount,balance_before,balance_after,pay_channel,remark,create_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "telecom_group_customer": "INSERT INTO telecom_group_customer (group_id,group_name,group_type,customer_id,contact_person,contact_phone,open_date,group_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
}

DELETE_ORDER = [
    "telecom_billing_record", "telecom_group_customer",
    "telecom_data_usage", "telecom_sms", "telecom_cdr",
    "telecom_service_order", "telecom_card_device_binding",
    "telecom_iot_card", "telecom_card", "telecom_customer",
    "telecom_device", "telecom_cell", "telecom_channel",
    "telecom_plan", "telecom_region",
]


def main():
    print("=" * 60)
    print("电信风控系统 - 业务数据造数")
    print(f"  目标库: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("=" * 60)

    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4", autocommit=False,
    )

    # 0. 清空
    print("[0/2] 清空旧数据...")
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in DELETE_ORDER:
            cur.execute(f"DELETE FROM {t}")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()

    # 1. 生成
    print("[1/2] 生成数据...")
    region = gen_region()
    plan = gen_plan()
    channel = gen_channel()
    cell = gen_cell()
    device = gen_device()
    customer = gen_customer()
    group_cust = gen_group_customer()
    card = gen_card()
    iot = gen_iot_card(card)
    binding = gen_card_device_binding(card)
    order = gen_service_order(card)
    cdr = gen_cdr(card)
    sms = gen_sms(card)
    usage = gen_data_usage(card)
    billing = gen_billing(card)

    buckets = [
        ("telecom_region", region), ("telecom_plan", plan),
        ("telecom_channel", channel), ("telecom_cell", cell),
        ("telecom_device", device), ("telecom_customer", customer),
        ("telecom_group_customer", group_cust), ("telecom_card", card),
        ("telecom_iot_card", iot), ("telecom_card_device_binding", binding),
        ("telecom_service_order", order), ("telecom_cdr", cdr),
        ("telecom_sms", sms), ("telecom_data_usage", usage),
        ("telecom_billing_record", billing),
    ]

    # 2. 写入
    print("[2/2] 写入数据库...")
    with conn.cursor() as cur:
        for table, rows in buckets:
            if not rows:
                continue
            cur.executemany(INSERT_SQL[table], rows)
            print(f"  {table:<30} {len(rows):>5} 条")
    conn.commit()
    conn.close()

    total = sum(len(r) for _, r in buckets)
    n_risk = sum(1 for c in card if c[0] and int(c[0][3:]) <= 50) + \
             sum(1 for c in card if c[0] and 290 <= int(c[0][3:]) <= 299)
    print("=" * 60)
    print(f"[OK] 造数完成, 共 {total} 条业务数据")
    print(f"  号卡总数: {len(card)} 张 (风险 {n_risk} + 正常 {len(card)-n_risk})")
    print(f"  CDR: {len(cdr)} 条, SMS: {len(sms)} 条, 流量: {len(usage)} 条, 账单: {len(billing)} 条")
    print("风险样本号段 (训练用):")
    print("  GOIP 虚拟拨号 : 13800000001~008 (1h内15-30次主叫+凌晨呼叫, 固定基站)")
    print("  猫池养卡     : 13800000009~018 (2组共享IMEI, 一机5卡)")
    print("  一证多卡     : 13800000019~028 (客户C00000003, 10张卡)")
    print("  国际诈骗来电 : 13800000029~035 (国际漫游, 高频被叫)")
    print("  物联网滥用   : 13800000036~050 (机卡分离, 流量突增)")
    print("  集团子号异常 : 13800000290~294 (集团客户C00000007, 高频外呼)")
    print("  话费套现     : 13800000295~299 (高频充值+大额转出)")
    print("  正常卡       : 其余 (240张, 正常通信行为)")
    print("=" * 60)
    print("[OK] 下一步: python scripts/train_xgb_model.py")


if __name__ == "__main__":
    main()