-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
--
--  Start from the mock data in train-mock-data/:
--    metro_stations.json, national_rail_stations.json
--    metro_schedules.json, national_rail_schedules.json
--    national_rail_seat_layouts.json
--    registered_users.json
--    bookings.json, metro_travel_history.json
--    payments.json, feedback.json
--
--  Think about:
--    - What tables do you need?
--    - What columns and data types?
--    - Which fields are primary keys? Which are foreign keys?
--    - What constraints make sense?
--
--  Apply your schema with:
--    docker-compose down -v && docker-compose up -d
-- ============================================================
-- ============================================================
--  STUDENT TASK — Relational Tables (V9.0 Schema)
-- ============================================================

-- ------------------------------------------------------------
-- ============================================================
--  STUDENT TASK — Relational Tables (V9.0 Schema Perfected)
-- ============================================================

-- ------------------------------------------------------------
-- 第五卷: 基礎設施與路網站點架構 (提至最前以符合外鍵參照順序)
-- ------------------------------------------------------------

-- 5.1 metro_stations (地鐵車站主表)
CREATE TABLE IF NOT EXISTS metro_stations (
    station_id                    VARCHAR(32)  PRIMARY KEY,
    name                          VARCHAR(100) NOT NULL,
    lines                         VARCHAR(255) NOT NULL,
    is_interchange_metro          BOOLEAN      NOT NULL,
    interchange_metro_lines       VARCHAR(255),
    is_interchange_national_rail  BOOLEAN      NOT NULL,
    interchange_national_rail_station_id VARCHAR(32)
);

-- 5.2 national_rail_stations (國鐵車站主表)
CREATE TABLE IF NOT EXISTS national_rail_stations (
    station_id                    VARCHAR(32)  PRIMARY KEY,
    name                          VARCHAR(100) NOT NULL,
    lines                         VARCHAR(255) NOT NULL,
    is_interchange_national_rail  BOOLEAN      NOT NULL,
    interchange_national_rail_lines VARCHAR(255),
    is_interchange_metro          BOOLEAN      NOT NULL,
    interchange_metro_station_id  VARCHAR(32)
);

-- 5.3 station_adjacencies (路網相鄰站點權重表)
CREATE TABLE IF NOT EXISTS station_adjacencies (
    source_station_id   VARCHAR(32) NOT NULL,
    adjacent_station_id VARCHAR(32) NOT NULL,
    network_type        VARCHAR(20) NOT NULL CHECK (network_type IN ('metro', 'national_rail')),
    line                VARCHAR(50) NOT NULL,
    travel_time_min     INT         NOT NULL,
    PRIMARY KEY (source_station_id, adjacent_station_id, network_type)
);

-- ------------------------------------------------------------
-- 第一卷: 安全驗證與用戶基礎架構
-- ------------------------------------------------------------

-- 1.1 users (身分識別表)
CREATE TABLE IF NOT EXISTS users (
    user_id          VARCHAR(32)  PRIMARY KEY,
    username         VARCHAR(50)  NOT NULL UNIQUE,
    email            VARCHAR(100) NOT NULL UNIQUE,
    full_name        VARCHAR(100),
    date_of_birth    DATE,
    phone            VARCHAR(20),
    secret_question  VARCHAR(255),
    registered_at    TIMESTAMP,
    is_active        BOOLEAN      DEFAULT TRUE
);

-- 1.2 user_credentials (身分憑證安全表)
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id            VARCHAR(32)  PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    password_hash      VARCHAR(255) NOT NULL,
    password_salt      VARCHAR(64)  NOT NULL,
    secret_answer_hash VARCHAR(255) NOT NULL
);

-- ------------------------------------------------------------
-- 第二卷: 路網、班次與座位實體架構
-- ------------------------------------------------------------

-- 2.1 schedules (國鐵班次調度表)
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id            VARCHAR(32)  PRIMARY KEY,
    line                   VARCHAR(50)  NOT NULL,
    service_type           VARCHAR(20)  CHECK (service_type IN ('normal', 'express')),
    direction              VARCHAR(20)  CHECK (direction IN ('northbound', 'southbound', 'eastbound', 'westbound')),
    departure_time         TIME         NOT NULL,
    arrival_time           TIME         NOT NULL,
    origin_station_id      VARCHAR(32)  REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(32)  REFERENCES national_rail_stations(station_id),
    stops_in_order         TEXT,        
    passed_through_stations TEXT,       
    travel_time_offset     TEXT,        
    base_fare_standard     DECIMAL(6,2),
    per_stop_standard      DECIMAL(6,2),
    base_fare_first        DECIMAL(6,2),
    per_stop_first         DECIMAL(6,2),
    frequency_min          INT,
    operates_on            VARCHAR(100),
    overnight_flag         BOOLEAN
);

-- 2.2 metro_schedules (地鐵班次與費率主表)
CREATE TABLE IF NOT EXISTS metro_schedules (
    metro_schedule_id      VARCHAR(32)  PRIMARY KEY,
    line                   VARCHAR(50)  NOT NULL,
    direction              VARCHAR(20)  CHECK (direction IN ('northbound', 'southbound', 'eastbound', 'westbound')),
    origin_station_id      VARCHAR(32)  REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(32)  REFERENCES metro_stations(station_id),
    first_train_time       TIME         NOT NULL,
    last_train_time        TIME         NOT NULL,
    frequency_min          INT          NOT NULL,
    stops_in_order         TEXT,        
    travel_time_offset     TEXT,        
    base_fare_usd          DECIMAL(5,2) NOT NULL,
    per_stop_rate_usd      DECIMAL(5,2) NOT NULL,
    operates_on            TEXT         NOT NULL -- 放大為 TEXT 防止寫入時爆掉
);

-- 2.3 rail_coaches (國鐵車廂表)
CREATE TABLE IF NOT EXISTS rail_coaches (
    coach_id        VARCHAR(32) PRIMARY KEY,
    schedule_id     VARCHAR(32) NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,
    coach_number    INT         NOT NULL,
    fare_class      VARCHAR(20) NOT NULL CHECK (fare_class IN ('standard', 'first'))
);

-- 2.4 rail_seats (國鐵座位狀態與庫存表)
CREATE TABLE IF NOT EXISTS rail_seats (
    seat_real_id    VARCHAR(64) PRIMARY KEY, 
    coach_id        VARCHAR(32) NOT NULL REFERENCES rail_coaches(coach_id) ON DELETE CASCADE,
    seat_id         VARCHAR(10) NOT NULL,
    seat_row        INT,
    seat_column     VARCHAR(5),
    is_booked       BOOLEAN     NOT NULL DEFAULT FALSE
);

-- ------------------------------------------------------------
-- 第四卷: 地鐵高頻運營刷卡日誌架構
-- ------------------------------------------------------------

-- 4.1 metro_access_logs (地鐵刷卡運營日誌表)
CREATE TABLE IF NOT EXISTS metro_access_logs (
    log_id           BIGINT      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    user_id          VARCHAR(32) NOT NULL REFERENCES users(user_id),
    station_id       VARCHAR(32) NOT NULL REFERENCES metro_stations(station_id),
    action_type      VARCHAR(10) NOT NULL CHECK (action_type IN ('check_in', 'check_out')),
    timestamp        TIMESTAMP   NOT NULL,
    day_pass_trip_id VARCHAR(32) 
);

-- ------------------------------------------------------------
-- 第六卷: 大眾運輸乘車歷史與旅客回饋架構
-- ------------------------------------------------------------

-- 6.1 bookings (國鐵訂位主表)
CREATE TABLE IF NOT EXISTS bookings (
    booking_id              VARCHAR(32)  PRIMARY KEY,
    user_id                 VARCHAR(32)  NOT NULL REFERENCES users(user_id),
    schedule_id             VARCHAR(32)  NOT NULL REFERENCES schedules(schedule_id),
    origin_station_id       VARCHAR(32)  REFERENCES national_rail_stations(station_id),
    destination_station_id  VARCHAR(32)  REFERENCES national_rail_stations(station_id),
    travel_date             DATE,
    departure_time          TIME,
    ticket_type             VARCHAR(20)  CHECK (ticket_type IN ('single', 'return')),
    fare_class              VARCHAR(20)  CHECK (fare_class IN ('standard', 'first')),
    coach                   VARCHAR(10),
    seat_real_id            VARCHAR(64)  REFERENCES rail_seats(seat_real_id),
    seat_id                 VARCHAR(10), 
    stops_travelled         INT,
    amount_usd              DECIMAL(8,2),
    status                  VARCHAR(20)  NOT NULL CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    booked_at               TIMESTAMP,
    travelled_at            TIMESTAMP
);

-- 6.2 metro_travel_history (地鐵乘車歷史紀錄表)
CREATE TABLE IF NOT EXISTS metro_travel_history (
    trip_id                 VARCHAR(32)  PRIMARY KEY,
    user_id                 VARCHAR(32)  NOT NULL REFERENCES users(user_id),
    schedule_id             VARCHAR(32)  REFERENCES metro_schedules(metro_schedule_id),
    origin_station_id       VARCHAR(32)  REFERENCES metro_stations(station_id),
    destination_station_id  VARCHAR(32)  REFERENCES metro_stations(station_id),
    travel_date             DATE         NOT NULL,
    ticket_type             VARCHAR(20)  NOT NULL CHECK (ticket_type IN ('single', 'day_pass')),
    day_pass_ref            VARCHAR(32),
    stops_travelled         INT,
    amount_usd              DECIMAL(6,2) NOT NULL,
    status                  VARCHAR(20)  NOT NULL CHECK (status IN ('completed', 'cancelled')),
    purchased_at            TIMESTAMP,
    travelled_at            TIMESTAMP
);

-- 6.3 feedback (旅客意見回饋表)
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id   VARCHAR(32) PRIMARY KEY,
    booking_id    VARCHAR(64) NOT NULL, -- 放大長度以容納多型對接
    user_id       VARCHAR(32) NOT NULL REFERENCES users(user_id),
    rating        INT         NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    submitted_at  TIMESTAMP   NOT NULL
);

-- ------------------------------------------------------------
-- 第三卷: 金融級金流、審計與溢退防禦架構
-- ------------------------------------------------------------

-- 3.1 payments (金流主總帳表)
CREATE TABLE IF NOT EXISTS payments (
    payment_id         VARCHAR(32)    PRIMARY KEY,
    booking_id         VARCHAR(64),   -- 放大長度以容納多型對接
    amount_usd         DECIMAL(10,2)  NOT NULL CHECK (amount_usd > 0), 
    payment_type       VARCHAR(20)    NOT NULL CHECK (payment_type IN ('purchase', 'refund')),
    method             VARCHAR(50)    NOT NULL, -- 放大適配不同字串長度
    status             VARCHAR(20)    NOT NULL CHECK (status IN ('paid', 'refunded', 'failed')),
    paid_at            TIMESTAMP,
    parent_payment_id  VARCHAR(32)    REFERENCES payments(payment_id), 
    refunded_amount    DECIMAL(10,2)  
);

-- ------------------------------------------------------------
-- 第七卷: 退款政策正規化架構 (V9.0 新增)
-- ------------------------------------------------------------

-- 7.1 refund_policies (退款政策主表)
CREATE TABLE IF NOT EXISTS refund_policies (
    policy_id                     VARCHAR(32)  PRIMARY KEY,
    service_type                  VARCHAR(20)  NOT NULL UNIQUE CHECK (service_type IN ('normal', 'express')),
    policy_name                   VARCHAR(100) NOT NULL,
    no_refund_before_departure_min INT         NOT NULL CHECK (no_refund_before_departure_min >= 0),
    effective_from                DATE,
    effective_until               DATE,
    created_at                    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_refund_effective_dates CHECK (effective_until IS NULL OR effective_until > effective_from)
);

-- 7.2 refund_cancellation_windows (退款時間視窗與費率表)
CREATE TABLE IF NOT EXISTS refund_cancellation_windows (
    window_id                  VARCHAR(32)    PRIMARY KEY,
    policy_id                  VARCHAR(32)    NOT NULL REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
    window_label               VARCHAR(100)   NOT NULL,
    hours_before_departure_min DECIMAL(8,2)   NOT NULL CHECK (hours_before_departure_min >= 0),
    hours_before_departure_max DECIMAL(8,2),
    refund_percent             DECIMAL(5,2)   NOT NULL CHECK (refund_percent BETWEEN 0 AND 100),
    processing_fee_usd         DECIMAL(6,2)   NOT NULL DEFAULT 0.00 CHECK (processing_fee_usd >= 0),
    sort_order                 INT            NOT NULL,
    CONSTRAINT chk_hours_duration CHECK (hours_before_departure_max IS NULL OR hours_before_departure_max > hours_before_departure_min)
);

-- 7.3 refund_compensation_rules (補償規則表)
CREATE TABLE IF NOT EXISTS refund_compensation_rules (
    compensation_id         VARCHAR(32)  PRIMARY KEY,
    policy_id               VARCHAR(32)  NOT NULL REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
    trigger_type            VARCHAR(30)  NOT NULL CHECK (trigger_type IN ('service_cancellation', 'delay', 'route_change')),
    delay_minutes_threshold INT          CHECK (delay_minutes_threshold > 0),
    compensation_percent    DECIMAL(5,2) NOT NULL CHECK (compensation_percent BETWEEN 0 AND 100),
    compensation_type       VARCHAR(20)  NOT NULL CHECK (compensation_type IN ('refund', 'voucher', 'credit')),
    description             TEXT
);

-- ------------------------------------------------------------
-- 第八卷: 訂位規則參數化架構 (V9.0 新增)
-- ------------------------------------------------------------

-- 8.1 booking_rule_sets (訂位規則集主表)
CREATE TABLE IF NOT EXISTS booking_rule_sets (
    rule_set_id     VARCHAR(32) PRIMARY KEY,
    network_type    VARCHAR(20) NOT NULL CHECK (network_type IN ('national_rail', 'metro')),
    version         INT         NOT NULL DEFAULT 1,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    effective_from  DATE,
    effective_until DATE,
    created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_booking_effective_dates CHECK (effective_until IS NULL OR effective_until > effective_from)
);

-- 8.2 booking_rule_params (訂位規則參數明細表)
CREATE TABLE IF NOT EXISTS booking_rule_params (
    param_id            BIGINT         PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    rule_set_id         VARCHAR(32)    NOT NULL REFERENCES booking_rule_sets(rule_set_id) ON DELETE CASCADE,
    ticket_type         VARCHAR(20)    CHECK (ticket_type IN ('single', 'return', 'day_pass', '*')),
    fare_class          VARCHAR(20)    CHECK (fare_class IN ('standard', 'first', '*')),
    rule_key            VARCHAR(100)   NOT NULL,
    rule_value_numeric  DECIMAL(12,4),
    rule_value_text     VARCHAR(255),
    unit                VARCHAR(20),
    description         TEXT
);

-- ------------------------------------------------------------
-- 第九卷: 旅行政策入庫架構 (V9.0 新增)
-- ------------------------------------------------------------

-- 9.1 policy_categories (政策類別主表)
CREATE TABLE IF NOT EXISTS policy_categories (
    category_id     VARCHAR(32)  PRIMARY KEY,
    network_type    VARCHAR(20)  NOT NULL CHECK (network_type IN ('national_rail', 'metro', 'both')),
    category_key    VARCHAR(100) NOT NULL,
    display_name_zh VARCHAR(100) NOT NULL,
    display_name_en VARCHAR(100) NOT NULL,
    sort_order      INT          NOT NULL,
    CONSTRAINT uq_network_category UNIQUE (network_type, category_key)
);

-- 9.2 policy_rules (政策規則明細表)
CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id                 VARCHAR(32)  PRIMARY KEY,
    category_id             VARCHAR(32)  NOT NULL REFERENCES policy_categories(category_id) ON DELETE CASCADE,
    rule_key                VARCHAR(100) NOT NULL,
    is_permitted            BOOLEAN,     
    rule_value_text         VARCHAR(500),
    description_zh          TEXT         NOT NULL,
    description_en          TEXT,
    applies_to_ticket_type  VARCHAR(20)  CHECK (applies_to_ticket_type IN ('single', 'return', 'day_pass', '*')),
    applies_to_fare_class   VARCHAR(20)  CHECK (applies_to_fare_class IN ('standard', 'first', '*')),
    effective_from          DATE,
    effective_until         DATE,
    version                 INT          NOT NULL DEFAULT 1,
    is_active               BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_policy_effective_dates CHECK (effective_until IS NULL OR effective_until > effective_from)
);


-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS ON policy_documents USING hnsw (embedding vector_cosine_ops);
