"""案件状态机单测"""
import pytest

from app.service.case import validate_case_transition


@pytest.mark.parametrize("current,target", [
    ("待审核", "审核中"), ("待审核", "已通过"), ("待审核", "已拒绝"), ("待审核", "已关闭"),
    ("审核中", "已通过"), ("审核中", "已拒绝"), ("审核中", "已关闭"),
])
def test_valid_transitions(current, target):
    validate_case_transition(current, target)  # 不抛异常


@pytest.mark.parametrize("current,target", [
    ("已通过", "待审核"), ("已拒绝", "已通过"), ("已关闭", "审核中"),
    ("待审核", "未知状态"), ("审核中", "待审核"),
])
def test_invalid_transitions(current, target):
    with pytest.raises(ValueError):
        validate_case_transition(current, target)
