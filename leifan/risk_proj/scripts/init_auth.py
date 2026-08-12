from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import select

from app.auth import PERMISSIONS, hash_password
from app.database import SessionLocal
from app.models import Permission, Role, RolePermission, StaffUser, StaffUserRole


ROLE_DEFINITIONS = (
    (
        "ADMINISTRATOR",
        "系统管理员",
        "拥有平台全部功能和权限管理能力",
        {code for code, _, _, _ in PERMISSIONS},
        True,
    ),
    (
        "RISK_REVIEWER",
        "风控审核员",
        "查看订单并处理人工审核案件",
        {
            "dashboard:view",
            "orders:view",
            "reviews:view",
            "reviews:decide",
            "rules:view",
            "blacklist:view",
        },
        False,
    ),
    (
        "RISK_OPERATOR",
        "规则运营",
        "维护风险规则和黑名单并查看审计日志",
        {
            "dashboard:view",
            "orders:view",
            "reviews:view",
            "rules:view",
            "rules:manage",
            "blacklist:view",
            "blacklist:manage",
            "audit:view",
        },
        False,
    ),
    (
        "READ_ONLY",
        "只读人员",
        "只读查看主面板、订单、规则和名单",
        {
            "dashboard:view",
            "orders:view",
            "reviews:view",
            "rules:view",
            "blacklist:view",
            "audit:view",
        },
        False,
    ),
)


def main() -> None:
    username = os.getenv("ADMIN_USERNAME", "administer").strip()
    password = os.getenv("ADMIN_INITIAL_PASSWORD", "")
    if len(password) < 6:
        raise RuntimeError("ADMIN_INITIAL_PASSWORD must contain at least 6 characters")
    now = datetime.now()

    with SessionLocal.begin() as session:
        permissions_by_code: dict[str, Permission] = {}
        for code, name, module, description in PERMISSIONS:
            permission = session.scalar(
                select(Permission).where(Permission.permission_code == code)
            )
            if permission is None:
                permission = Permission(
                    permission_code=code,
                    permission_name=name,
                    module=module,
                    description=description,
                    created_at=now,
                )
                session.add(permission)
                session.flush()
            permissions_by_code[code] = permission

        roles_by_code: dict[str, Role] = {}
        for role_code, role_name, description, permission_codes, is_system in ROLE_DEFINITIONS:
            role = session.scalar(select(Role).where(Role.role_code == role_code))
            if role is None:
                role = Role(
                    role_code=role_code,
                    role_name=role_name,
                    description=description,
                    is_system=is_system,
                    created_at=now,
                    updated_at=now,
                )
                session.add(role)
                session.flush()
            roles_by_code[role_code] = role
            existing_ids = set(
                session.scalars(
                    select(RolePermission.permission_id).where(
                        RolePermission.role_id == role.role_id
                    )
                )
            )
            for permission_code in permission_codes:
                permission = permissions_by_code[permission_code]
                if permission.permission_id not in existing_ids:
                    session.add(
                        RolePermission(
                            role_id=role.role_id,
                            permission_id=permission.permission_id,
                        )
                    )

        admin = session.scalar(select(StaffUser).where(StaffUser.username == username))
        if admin is None:
            admin = StaffUser(
                username=username,
                password_hash=hash_password(password),
                display_name="系统管理员",
                is_active=True,
                session_version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            session.flush()

        administrator_role = roles_by_code["ADMINISTRATOR"]
        assignment = session.get(
            StaffUserRole,
            {"staff_user_id": admin.staff_user_id, "role_id": administrator_role.role_id},
        )
        if assignment is None:
            session.add(
                StaffUserRole(
                    staff_user_id=admin.staff_user_id,
                    role_id=administrator_role.role_id,
                    assigned_at=now,
                    assigned_by=admin.staff_user_id,
                )
            )

    print(f"Initialized {len(PERMISSIONS)} permissions and {len(ROLE_DEFINITIONS)} roles.")
    print(f"Administrator account: {username}")


if __name__ == "__main__":
    main()

