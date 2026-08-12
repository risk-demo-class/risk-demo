-- 教育风控后台用户与两角色权限初始化（MySQL 8）
CREATE TABLE IF NOT EXISTS `sys_user` (
    `user_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '后台用户ID',
    `username` VARCHAR(50) NOT NULL COMMENT '登录账号',
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'PBKDF2-SHA256 密码摘要',
    `display_name` VARCHAR(50) NOT NULL COMMENT '显示名称',
    `role` ENUM('ADMIN','REVIEWER') NOT NULL COMMENT 'ADMIN=风控管理员, REVIEWER=审核员',
    `is_active` TINYINT NOT NULL DEFAULT 1 COMMENT '1=启用, 0=停用',
    `last_login_time` DATETIME DEFAULT NULL COMMENT '最近登录时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`),
    UNIQUE INDEX `uk_sys_user_username` (`username`),
    INDEX `idx_sys_user_role` (`role`),
    INDEX `idx_sys_user_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='后台登录用户表';

-- 演示账号。重复初始化不会覆盖用户已修改的密码。
INSERT IGNORE INTO `sys_user`
(`username`, `password_hash`, `display_name`, `role`, `is_active`)
VALUES
('admin', 'pbkdf2_sha256$240000$grLvxcBRa0NuqdE5sId23g$-yCMDg9QDITTSLg0WDwmOaJ05bpLfAcHPkYcu4CyX98', '风控管理员', 'ADMIN', 1),
('reviewer', 'pbkdf2_sha256$240000$iAQWVMLK72W8mi_r_cDAJA$PAkp-XRB_g8WGRv1yJUhfY2LLROaxl7UbboHy6Lga0c', '审核员', 'REVIEWER', 1);

