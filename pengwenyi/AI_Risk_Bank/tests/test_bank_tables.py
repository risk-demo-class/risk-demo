"""
【银行版】测试 - 8 张业务表 ORM 字段结构 (models_business.py)

覆盖: UserInfo / BankCard / Transaction / LoanApplication / LoginLog /
      DeviceFingerprint / IpGeoLocation / BlacklistExtra
"""
from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, Integer, Numeric, String

from app.models_business import (
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)


def _cols(model):
    """表字段名 → 类型 映射 (SQLAlchemy 元数据)."""
    return {c.name: c.type for c in model.__table__.columns}


def _pk_name(model):
    return list(model.__table__.primary_key.columns)[0].name


class TestUserInfo:
    """用户信息表: user_id/name/id_card_hash/credit_score/register_at/kyc_level"""

    def test_tablename_and_pk(self):
        assert UserInfo.__tablename__ == "user_info"
        assert _pk_name(UserInfo) == "user_id"

    def test_fields_and_types(self):
        cols = _cols(UserInfo)
        assert isinstance(cols["user_id"], String) and cols["user_id"].length == 50
        assert isinstance(cols["name"], String)
        assert isinstance(cols["id_card_hash"], String) and cols["id_card_hash"].length == 64
        assert isinstance(cols["credit_score"], Integer), "人行信用分 (300-850)"
        assert isinstance(cols["register_at"], DateTime)
        assert isinstance(cols["kyc_level"], Integer), "KYC 等级 1-4"


class TestBankCard:
    """银行卡表: card_id/user_id/card_no_hash/bank_code/card_type/credit_limit"""

    def test_tablename_and_pk(self):
        assert BankCard.__tablename__ == "bank_card"
        assert _pk_name(BankCard) == "card_id"

    def test_fields_and_types(self):
        cols = _cols(BankCard)
        assert isinstance(cols["card_id"], String)
        assert isinstance(cols["user_id"], String)
        assert isinstance(cols["card_no_hash"], String) and cols["card_no_hash"].length == 64
        assert isinstance(cols["bank_code"], String)
        assert isinstance(cols["card_type"], SAEnum), "卡类型枚举"
        assert list(cols["card_type"].enums) == ["借记卡", "信用卡"]
        assert isinstance(cols["credit_limit"], Numeric), "授信额度(信用卡)"


class TestTransaction:
    """交易表: txn_id/from_card/to_card/amount/channel/device_id/ip/geo/txn_time"""

    def test_tablename_and_pk(self):
        assert Transaction.__tablename__ == "transaction"
        assert _pk_name(Transaction) == "txn_id"

    def test_fields_and_types(self):
        cols = _cols(Transaction)
        assert isinstance(cols["txn_id"], String)
        assert isinstance(cols["from_card"], String), "付款卡ID (归属校验依赖)"
        assert isinstance(cols["to_card"], String), "收款卡ID"
        assert isinstance(cols["amount"], Numeric)
        assert isinstance(cols["channel"], SAEnum), "交易渠道枚举"
        assert list(cols["channel"].enums) == ["APP", "网银", "ATM", "第三方"]
        assert isinstance(cols["device_id"], String)
        assert isinstance(cols["ip"], String)
        assert isinstance(cols["geo"], String), "地理位置(省-市)"
        assert isinstance(cols["txn_time"], DateTime)


class TestLoanApplication:
    """贷款申请表: loan_id/user_id/amount/term_months/purpose/monthly_income/debt_ratio/apply_time"""

    def test_tablename_and_pk(self):
        assert LoanApplication.__tablename__ == "loan_application"
        assert _pk_name(LoanApplication) == "loan_id"

    def test_fields_and_types(self):
        cols = _cols(LoanApplication)
        assert isinstance(cols["loan_id"], String)
        assert isinstance(cols["user_id"], String)
        assert isinstance(cols["amount"], Numeric)
        assert isinstance(cols["term_months"], Integer), "期限(月)"
        assert isinstance(cols["purpose"], String), "贷款用途"
        assert isinstance(cols["monthly_income"], Numeric), "月收入"
        assert isinstance(cols["debt_ratio"], Numeric), "负债率(月还款/月收入)"
        assert isinstance(cols["apply_time"], DateTime)


class TestLoginLog:
    """登录日志表: login_id/user_id/device_id/ip/geo/success/login_at"""

    def test_tablename_and_pk(self):
        assert LoginLog.__tablename__ == "login_log"
        assert _pk_name(LoginLog) == "login_id"

    def test_fields_and_types(self):
        cols = _cols(LoginLog)
        assert isinstance(cols["login_id"], String)
        assert isinstance(cols["user_id"], String)
        assert isinstance(cols["device_id"], String)
        assert isinstance(cols["ip"], String)
        assert isinstance(cols["geo"], String)
        assert isinstance(cols["success"], Integer), "是否登录成功(1/0)"
        assert isinstance(cols["login_at"], DateTime)


class TestDeviceFingerprint:
    """设备指纹表: device_id/user_id/fingerprint_hash/first_seen/last_seen/os/browser"""

    def test_tablename_and_pk(self):
        assert DeviceFingerprint.__tablename__ == "device_fingerprint"
        assert _pk_name(DeviceFingerprint) == "device_id"

    def test_fields_and_types(self):
        cols = _cols(DeviceFingerprint)
        assert isinstance(cols["device_id"], String) and cols["device_id"].length == 64
        assert isinstance(cols["user_id"], String), "归属用户(可能多人共用)"
        assert isinstance(cols["fingerprint_hash"], String) and cols["fingerprint_hash"].length == 64
        assert isinstance(cols["first_seen"], DateTime)
        assert isinstance(cols["last_seen"], DateTime)
        assert isinstance(cols["os"], String)
        assert isinstance(cols["browser"], String)


class TestIpGeoLocation:
    """IP 地理位置表: ip/country/province/city/isp/is_proxy/is_tor"""

    def test_tablename_and_pk(self):
        assert IpGeoLocation.__tablename__ == "ip_geo_location"
        assert _pk_name(IpGeoLocation) == "ip"

    def test_fields_and_types(self):
        cols = _cols(IpGeoLocation)
        assert isinstance(cols["ip"], String)
        assert isinstance(cols["country"], String)
        assert isinstance(cols["province"], String)
        assert isinstance(cols["city"], String)
        assert isinstance(cols["isp"], String), "运营商"
        assert isinstance(cols["is_proxy"], Integer), "是否代理IP(1/0)"
        assert isinstance(cols["is_tor"], Integer), "是否Tor出口(1/0)"


class TestBlacklistExtra:
    """黑名单扩展表: entry_id/type/value/reason/expire_at (银行业专属类型)"""

    def test_tablename_and_pk(self):
        assert BlacklistExtra.__tablename__ == "blacklist_extra"
        assert _pk_name(BlacklistExtra) == "entry_id"

    def test_fields_and_types(self):
        cols = _cols(BlacklistExtra)
        assert isinstance(cols["entry_id"], BigInteger), "自增主键"
        assert isinstance(cols["type"], SAEnum), "黑名单类型枚举"
        assert list(cols["type"].enums) == ["设备指纹", "IP", "银行卡号", "身份证号"]
        assert isinstance(cols["value"], String) and cols["value"].length == 200
        assert isinstance(cols["reason"], String), "加入原因"
        assert isinstance(cols["expire_at"], DateTime), "过期时间(NULL=永久)"


class TestEightTablesComplete:
    """8 张业务表齐全 + 每张都有主键"""

    def test_all_tables_present(self):
        tables = [
            UserInfo, BankCard, Transaction, LoanApplication,
            LoginLog, DeviceFingerprint, IpGeoLocation, BlacklistExtra,
        ]
        assert len(tables) == 8
        names = {t.__tablename__ for t in tables}
        assert names == {
            "user_info", "bank_card", "transaction", "loan_application",
            "login_log", "device_fingerprint", "ip_geo_location", "blacklist_extra",
        }

    def test_every_table_has_primary_key(self):
        for model in (UserInfo, BankCard, Transaction, LoanApplication,
                      LoginLog, DeviceFingerprint, IpGeoLocation, BlacklistExtra):
            assert model.__table__.primary_key, f"{model.__name__} 必须有主键"
