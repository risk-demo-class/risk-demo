SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE IF NOT EXISTS travel_user (
  user_id VARCHAR(50) PRIMARY KEY, name VARCHAR(100) NOT NULL,
  phone_hash VARCHAR(64) NOT NULL, real_name_status TINYINT DEFAULT 0,
  vip_level INT DEFAULT 0, account_status VARCHAR(20) DEFAULT '正常',
  register_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_travel_user_phone(phone_hash), INDEX idx_travel_user_register(register_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS travel_order (
  order_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL,
  order_type VARCHAR(20) NOT NULL, total_amount DECIMAL(12,2) NOT NULL,
  dest_country VARCHAR(50) NOT NULL, depart_date DATE NOT NULL, return_date DATE NOT NULL,
  passenger_count INT DEFAULT 1, order_status VARCHAR(20) DEFAULT '待支付',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_travel_order_user(user_id), INDEX idx_travel_order_time(create_time),
  CONSTRAINT fk_travel_order_user FOREIGN KEY(user_id) REFERENCES travel_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS passenger_info (
  passenger_id VARCHAR(50) PRIMARY KEY, user_id VARCHAR(50) NOT NULL,
  name VARCHAR(100) NOT NULL, id_type VARCHAR(20) NOT NULL,
  id_number_hash VARCHAR(64) NOT NULL, nationality VARCHAR(50) DEFAULT '中国', birthday DATE,
  UNIQUE KEY uq_user_identity(user_id,id_number_hash), INDEX idx_passenger_hash(id_number_hash),
  CONSTRAINT fk_passenger_user FOREIGN KEY(user_id) REFERENCES travel_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_passenger (
  id INT PRIMARY KEY AUTO_INCREMENT, order_id VARCHAR(50) NOT NULL, passenger_id VARCHAR(50) NOT NULL,
  UNIQUE KEY uq_order_passenger(order_id,passenger_id), INDEX idx_op_passenger(passenger_id),
  CONSTRAINT fk_op_order FOREIGN KEY(order_id) REFERENCES travel_order(order_id),
  CONSTRAINT fk_op_passenger FOREIGN KEY(passenger_id) REFERENCES passenger_info(passenger_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS visa_application (
  visa_id VARCHAR(50) PRIMARY KEY, order_id VARCHAR(50) NOT NULL, user_id VARCHAR(50) NOT NULL,
  dest_country VARCHAR(50) NOT NULL, visa_type VARCHAR(30) NOT NULL,
  application_status VARCHAR(20) DEFAULT '待审核', reject_reason VARCHAR(500),
  submit_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_visa_user(user_id), INDEX idx_visa_time(submit_time), INDEX idx_visa_status(application_status),
  CONSTRAINT fk_visa_order FOREIGN KEY(order_id) REFERENCES travel_order(order_id),
  CONSTRAINT fk_visa_user FOREIGN KEY(user_id) REFERENCES travel_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS flight_booking (
  booking_id VARCHAR(50) PRIMARY KEY, order_id VARCHAR(50) NOT NULL UNIQUE,
  flight_no VARCHAR(20) NOT NULL, depart_airport VARCHAR(20) NOT NULL,
  arrive_airport VARCHAR(20) NOT NULL, cabin_class VARCHAR(20) DEFAULT '经济舱',
  depart_time DATETIME NOT NULL, ticket_count INT DEFAULT 1,
  INDEX idx_flight_no(flight_no), CONSTRAINT fk_flight_order FOREIGN KEY(order_id) REFERENCES travel_order(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hotel_booking (
  booking_id VARCHAR(50) PRIMARY KEY, order_id VARCHAR(50) NOT NULL UNIQUE,
  hotel_id VARCHAR(50) NOT NULL, city VARCHAR(50) NOT NULL,
  check_in DATE NOT NULL, check_out DATE NOT NULL, room_count INT DEFAULT 1,
  is_refundable TINYINT DEFAULT 1,
  CONSTRAINT fk_hotel_order FOREIGN KEY(order_id) REFERENCES travel_order(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS payment_record (
  payment_id VARCHAR(50) PRIMARY KEY, order_id VARCHAR(50) NOT NULL, user_id VARCHAR(50) NOT NULL,
  payment_account_hash VARCHAR(64) NOT NULL, amount DECIMAL(12,2) NOT NULL,
  device_id VARCHAR(100) NOT NULL, ip VARCHAR(64) NOT NULL,
  payment_status VARCHAR(20) DEFAULT '成功', payment_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_payment_order(order_id), INDEX idx_payment_user(user_id),
  INDEX idx_payment_account(payment_account_hash), INDEX idx_payment_device(device_id), INDEX idx_payment_ip(ip),
  CONSTRAINT fk_payment_order FOREIGN KEY(order_id) REFERENCES travel_order(order_id),
  CONSTRAINT fk_payment_user FOREIGN KEY(user_id) REFERENCES travel_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS travel_blacklist_entry (
  entry_id INT PRIMARY KEY AUTO_INCREMENT, entry_type VARCHAR(20) NOT NULL,
  entry_value_hash VARCHAR(128) NOT NULL, reason VARCHAR(500), expire_time DATETIME,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at DATETIME,
  UNIQUE KEY uq_travel_blacklist_value(entry_type,entry_value_hash),
  INDEX idx_travel_blacklist_active(entry_type,deleted_at,expire_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS=1;
