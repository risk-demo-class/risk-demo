SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS blacklist_extra, delivery_result, customs_declaration, shipment_item, shipment, address, user_info;
CREATE TABLE user_info (
 user_id varchar(50) PRIMARY KEY, name varchar(50) NOT NULL, id_type varchar(20) NOT NULL,
 id_number_hash varchar(128) NOT NULL, phone varchar(30) NOT NULL, real_name_status tinyint NOT NULL DEFAULT 1,
 account_type varchar(20) NOT NULL DEFAULT '个人', register_time datetime NOT NULL,
 device_id varchar(64), usual_city varchar(50), KEY idx_user_idno(id_number_hash), KEY idx_user_device(device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE address (
 address_id varchar(50) PRIMARY KEY, user_id varchar(50), contact_name varchar(50) NOT NULL,
 contact_phone varchar(30) NOT NULL, id_number_hash varchar(128), country varchar(50) NOT NULL DEFAULT '中国',
 province varchar(50) NOT NULL, city varchar(50) NOT NULL, district varchar(50) NOT NULL,
 detail_address varchar(255) NOT NULL, address_type varchar(20) NOT NULL DEFAULT '固定地址',
 is_remote_area tinyint NOT NULL DEFAULT 0, create_time datetime NOT NULL,
 KEY idx_addr_user(user_id), KEY idx_addr_phone(contact_phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE shipment (
 shipment_id varchar(50) PRIMARY KEY, sender_user_id varchar(50) NOT NULL,
 sender_address_id varchar(50) NOT NULL, receiver_address_id varchar(50) NOT NULL,
 shipment_type varchar(20) NOT NULL DEFAULT '普通件', payment_type varchar(20) NOT NULL DEFAULT '寄付',
 cod_amount decimal(12,2) NOT NULL DEFAULT 0, declared_value decimal(12,2) NOT NULL DEFAULT 0,
 actual_weight decimal(10,3) NOT NULL DEFAULT 0, declared_weight decimal(10,3) NOT NULL DEFAULT 0,
 destination_country varchar(50) NOT NULL DEFAULT '中国', is_cross_border tinyint NOT NULL DEFAULT 0,
 create_time datetime NOT NULL, shipment_status varchar(20) NOT NULL DEFAULT '已创建', device_id varchar(64),
 KEY idx_ship_user_time(sender_user_id,create_time), KEY idx_ship_recv_time(receiver_address_id,create_time),
 KEY idx_ship_device_time(device_id,create_time), KEY idx_ship_cross_time(is_cross_border,create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE shipment_item (
 item_id varchar(50) PRIMARY KEY, shipment_id varchar(50) NOT NULL, item_name varchar(100) NOT NULL,
 item_category varchar(50) NOT NULL, quantity int NOT NULL DEFAULT 1, declared_dangerous tinyint NOT NULL DEFAULT 0,
 battery_flag tinyint NOT NULL DEFAULT 0, chemical_flag tinyint NOT NULL DEFAULT 0,
 liquid_flag tinyint NOT NULL DEFAULT 0, security_check_result varchar(30) NOT NULL DEFAULT '通过',
 KEY idx_item_ship(shipment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE customs_declaration (
 declaration_id varchar(50) PRIMARY KEY, shipment_id varchar(50) NOT NULL UNIQUE,
 customs_code varchar(30) NOT NULL, declared_item_name varchar(100) NOT NULL,
 declared_quantity int NOT NULL DEFAULT 1, declared_value decimal(12,2) NOT NULL,
 declared_weight decimal(10,3) NOT NULL, currency varchar(10) NOT NULL DEFAULT 'CNY',
 origin_country varchar(50) NOT NULL DEFAULT '中国', destination_country varchar(50) NOT NULL,
 declaration_time datetime NOT NULL, inspection_result varchar(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE delivery_result (
 delivery_id varchar(50) PRIMARY KEY, shipment_id varchar(50) NOT NULL, delivery_status varchar(20) NOT NULL,
 receiver_name varchar(50) NOT NULL, receiver_phone varchar(30) NOT NULL, refuse_reason varchar(255),
 delivery_time datetime NOT NULL, cod_amount decimal(12,2) NOT NULL DEFAULT 0,
 cod_received tinyint NOT NULL DEFAULT 0, courier_id varchar(50), KEY idx_delivery_ship_status(shipment_id,delivery_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE blacklist_extra (
 entry_id bigint AUTO_INCREMENT PRIMARY KEY, type varchar(30) NOT NULL, value varchar(255) NOT NULL,
 reason text, expire_at datetime, source varchar(50) NOT NULL DEFAULT '物流业务', KEY idx_extra_value(value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SET FOREIGN_KEY_CHECKS=1;
