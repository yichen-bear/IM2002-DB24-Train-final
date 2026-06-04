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



-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================
-- ============================================================
-- ============================================================
-- ============================================================
--   TransitFlow PostgreSQL Schema (Final Fixed Version)
-- ============================================================

-- ============================================================
-- Section 1: Security Verification and User Infrastructure
-- ============================================================

-- ------------------------------------------------------------
-- Table: users
-- Description: Stores the profile and demographic information of 
--              registered transit passengers. It holds non-sensitive 
--              personal details while referencing security credentials.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id         VARCHAR(32)  PRIMARY KEY,
    username        VARCHAR(50)  NOT NULL UNIQUE,
    email           VARCHAR(100) NOT NULL UNIQUE,
    full_name       VARCHAR(100),
    date_of_birth   DATE,
    phone           VARCHAR(20),
    secret_question VARCHAR(255),
    registered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active       BOOLEAN DEFAULT TRUE
);

-- ------------------------------------------------------------
-- Table: user_credentials
-- Description: Manages sensitive authentication data by separating 
--              password and security answer hashes from the main users table 
--              to comply with security and isolation design patterns.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id            VARCHAR(32) PRIMARY KEY,
    password_hash      TEXT NOT NULL,
    secret_answer_hash TEXT,
    
    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- ============================================================

-- Section 5: Infrastructure and Transit Network Architecture
-- ============================================================

-- ------------------------------------------------------------
-- Table: metro_stations
-- Description: Contains configuration data for stations operating 
--              on the urban Metro network, including details on 
--              inter-system transfers to other lines or National Rail.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_stations (
    station_id                    VARCHAR(32) PRIMARY KEY,
    name                          VARCHAR(100) NOT NULL,
    lines                         VARCHAR(255) NOT NULL,
    is_interchange_metro          BOOLEAN NOT NULL,
    interchange_metro_lines       VARCHAR(255),
    is_interchange_national_rail  BOOLEAN NOT NULL,
    interchange_national_rail_station_id VARCHAR(32)
);

-- ------------------------------------------------------------
-- Table: national_rail_stations
-- Description: Contains configuration data for stations operating 
--              on the long-distance National Rail network, managing 
--              transfer links back to the urban Metro system.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS national_rail_stations (
    station_id                    VARCHAR(32) PRIMARY KEY,
    name                          VARCHAR(100) NOT NULL,
    lines                         VARCHAR(255) NOT NULL,
    is_interchange_national_rail  BOOLEAN NOT NULL,
    interchange_national_rail_lines VARCHAR(255),
    is_interchange_metro          BOOLEAN NOT NULL,
    interchange_metro_station_id  VARCHAR(32)
);

-- ------------------------------------------------------------
-- Table: station_adjacencies
-- Description: Models graph edges between adjacent stations within 
--              both Metro and National Rail networks, specifying 
--              transit lines and exact travel times for routing engines.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS station_adjacencies (
    source_station_id   VARCHAR(32) NOT NULL,
    adjacent_station_id VARCHAR(32) NOT NULL,
    network_type        VARCHAR(20) NOT NULL,
    line                VARCHAR(50) NOT NULL,
    travel_time_min     INT NOT NULL,

    PRIMARY KEY (
        source_station_id,
        adjacent_station_id,
        network_type
    ),

    CONSTRAINT chk_network_type
        CHECK (network_type IN ('metro', 'national_rail'))
);

-- ============================================================
-- Section 7: Refund and Cancellation Policies
-- ============================================================

-- ------------------------------------------------------------
-- Table: refund_policies
-- Description: Defines top-level rules governing ticket cancellations 
--              and refunds for normal and express transit services, 
--              enforcing system-wide deadlines and validity dates.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refund_policies (
    policy_id                      VARCHAR(32) PRIMARY KEY,
    service_type                   VARCHAR(20) NOT NULL,
    policy_name                    VARCHAR(100) NOT NULL,
    no_refund_before_departure_min INT NOT NULL,
    effective_from                 DATE,
    effective_until                DATE,
    created_at                     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_refund_policy_service_type
        CHECK (service_type IN ('normal', 'express')),

    CONSTRAINT chk_no_refund_min
        CHECK (no_refund_before_departure_min >= 0),

    CONSTRAINT chk_refund_policy_dates
        CHECK (
            effective_until IS NULL
            OR effective_until > effective_from
        )
);

-- ------------------------------------------------------------
-- Table: refund_cancellation_windows
-- Description: Manages multi-tiered refund percentages based on how 
--              far in advance a cancellation occurs before departure, 
--              including deduction of administrative processing fees.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refund_cancellation_windows (
    window_id                  VARCHAR(32) PRIMARY KEY,
    policy_id                  VARCHAR(32) NOT NULL,
    window_label               VARCHAR(100) NOT NULL,
    hours_before_departure_min DECIMAL(8,2) NOT NULL,
    hours_before_departure_max DECIMAL(8,2),
    refund_percent             DECIMAL(5,2) NOT NULL,
    processing_fee_usd         DECIMAL(6,2) NOT NULL DEFAULT 0.00,
    sort_order                 INT NOT NULL,

    FOREIGN KEY (policy_id)
        REFERENCES refund_policies(policy_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_window_hours_min
        CHECK (hours_before_departure_min >= 0),

    CONSTRAINT chk_refund_percent
        CHECK (refund_percent BETWEEN 0 AND 100),

    CONSTRAINT chk_processing_fee
        CHECK (processing_fee_usd >= 0),

    CONSTRAINT chk_window_hours_range
        CHECK (
            hours_before_departure_max IS NULL
            OR hours_before_departure_max > hours_before_departure_min
        )
);

-- ------------------------------------------------------------
-- Table: refund_compensation_rules
-- Description: Defines customer compensation rules when transit services 
--              experience exceptional disruptions (e.g., cancellations, 
--              route modifications, or specific delay thresholds).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refund_compensation_rules (
    compensation_id         VARCHAR(32) PRIMARY KEY,
    policy_id               VARCHAR(32) NOT NULL,
    trigger_type            VARCHAR(30) NOT NULL,
    delay_minutes_threshold INT,
    compensation_percent    DECIMAL(5,2) NOT NULL,
    compensation_type       VARCHAR(20) NOT NULL,
    description             TEXT,

    FOREIGN KEY (policy_id)
        REFERENCES refund_policies(policy_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_comp_trigger_type
        CHECK (
            trigger_type IN (
                'service_cancellation',
                'delay',
                'route_change'
            )
        ),

    CONSTRAINT chk_delay_threshold
        CHECK (
            delay_minutes_threshold IS NULL
            OR delay_minutes_threshold > 0
        ),

    CONSTRAINT chk_comp_percent
        CHECK (compensation_percent BETWEEN 0 AND 100),

    CONSTRAINT chk_comp_type
        CHECK (
            compensation_type IN (
                'refund',
                'voucher',
                'credit'
            )
        )
);

-- ============================================================
-- Section 2: Networks, Timetables, and Seating Asset Management
-- ============================================================

-- ------------------------------------------------------------
-- Table: schedules
-- Description: Master timetable definitions for the National Rail network. 
--              Contains explicit geographic origins/destinations, operational 
--              directions, multi-tiered pricing matrices, and refund policies.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id            VARCHAR(32) PRIMARY KEY,
    route_id               VARCHAR(32) NOT NULL,
    line                   VARCHAR(50) NOT NULL,

    policy_id              VARCHAR(32) NOT NULL,
    service_type           VARCHAR(20) NOT NULL,

    direction              VARCHAR(20),

    departure_time         TIME NOT NULL,
    arrival_time           TIME NOT NULL,

    origin_station_id      VARCHAR(32),
    destination_station_id VARCHAR(32),

    stops_in_order         TEXT,
    passed_through_stations TEXT,
    travel_time_offset     TEXT,

    base_fare_standard_usd DECIMAL(6,2),
    per_stop_standard_usd  DECIMAL(6,2),

    base_fare_first_usd    DECIMAL(6,2),
    per_stop_first_usd     DECIMAL(6,2),

    frequency_min          INT,
    operates_on            VARCHAR(100),
    overnight_flag         BOOLEAN,

    FOREIGN KEY (origin_station_id)
        REFERENCES national_rail_stations(station_id),

    FOREIGN KEY (destination_station_id)
        REFERENCES national_rail_stations(station_id),

    FOREIGN KEY (policy_id)
        REFERENCES refund_policies(policy_id),

    CONSTRAINT chk_schedules_direction
        CHECK (
            direction IN (
                'northbound',
                'southbound',
                'eastbound',
                'westbound'
            )
        )
);

-- ------------------------------------------------------------
-- Table: metro_schedules
-- Description: Timetable frameworks for urban Metro lines, organizing 
--              high-frequency operations by interval (headway) rather 
--              than individual departure slots, with dedicated distance fares.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_schedules (
    metro_schedule_id      VARCHAR(32) PRIMARY KEY,
    line                   VARCHAR(50) NOT NULL,
    direction              VARCHAR(20),

    origin_station_id      VARCHAR(32),
    destination_station_id VARCHAR(32),

    first_train_time       TIME NOT NULL,
    last_train_time        TIME NOT NULL,

    frequency_min          INT NOT NULL,

    stops_in_order         TEXT,
    travel_time_offset     TEXT,

    base_fare_usd          DECIMAL(5,2) NOT NULL,
    per_stop_rate_usd      DECIMAL(5,2) NOT NULL,

    operates_on            VARCHAR(100) NOT NULL,

    FOREIGN KEY (origin_station_id)
        REFERENCES metro_stations(station_id),

    FOREIGN KEY (destination_station_id)
        REFERENCES metro_stations(station_id),

    CONSTRAINT chk_metro_direction
        CHECK (
            direction IN (
                'northbound',
                'southbound',
                'eastbound',
                'westbound'
            )
        )
);

-- ------------------------------------------------------------
-- Table: rail_coaches
-- Description: Represents individual passenger physical carriages assigned 
--              to National Rail schedules, enforcing compartment numbering 
--              and cabin service classes ('standard' or 'first').
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rail_coaches (
    coach_id     VARCHAR(32) PRIMARY KEY,
    schedule_id  VARCHAR(32) NOT NULL,
    coach_number INT NOT NULL,
    fare_class   VARCHAR(20) NOT NULL,

    FOREIGN KEY (schedule_id)
        REFERENCES schedules(schedule_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_coach_fare_class
        CHECK (fare_class IN ('standard', 'first'))
);

-- ------------------------------------------------------------
-- Table: rail_seats
-- Description: Tracks concrete physical seating assets within coaches, 
--              recording spatial layout identifiers (rows/columns) 
--              and current real-time inventory booking status.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rail_seats (
    seat_real_id VARCHAR(64) PRIMARY KEY,
    coach_id      VARCHAR(32) NOT NULL,
    seat_id       VARCHAR(10) NOT NULL,
    seat_row      INT,
    seat_column   VARCHAR(5),
    is_booked     BOOLEAN NOT NULL DEFAULT FALSE,

    FOREIGN KEY (coach_id)
        REFERENCES rail_coaches(coach_id)
        ON DELETE CASCADE,

    UNIQUE (coach_id, seat_id)
);

-- ============================================================
-- Section 6: Travel History, Ticket Bookings, and User Feedback
-- ============================================================

-- ------------------------------------------------------------
-- Table: bookings
-- Description: Records commercial ticketing transactions for National Rail, 
--              capturing reserved seats, specialized routing endpoints, 
--              passenger statuses, and precise scheduling dates.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    booking_id              VARCHAR(32) PRIMARY KEY,
    user_id                 VARCHAR(32) NOT NULL,
    schedule_id             VARCHAR(32) NOT NULL,

    origin_station_id       VARCHAR(32),
    destination_station_id  VARCHAR(32),

    travel_date             DATE,
    departure_time          TIME,

    ticket_type             VARCHAR(20),
    fare_class              VARCHAR(20),

    seat_real_id            VARCHAR(64),

    stops_travelled         INT,
    amount_usd              DECIMAL(8,2),

    status                  VARCHAR(20) NOT NULL,

    booked_at               TIMESTAMP,
    travelled_at            TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id),

    FOREIGN KEY (schedule_id)
        REFERENCES schedules(schedule_id),

    FOREIGN KEY (origin_station_id)
        REFERENCES national_rail_stations(station_id),

    FOREIGN KEY (destination_station_id)
        REFERENCES national_rail_stations(station_id),

    FOREIGN KEY (seat_real_id)
        REFERENCES rail_seats(seat_real_id),

    CONSTRAINT chk_booking_ticket_type
        CHECK (ticket_type IN ('single', 'return')),

    CONSTRAINT chk_booking_fare_class
        CHECK (fare_class IN ('standard', 'first')),

    CONSTRAINT chk_booking_status
        CHECK (
            status IN (
                'confirmed',
                'cancelled',
                'completed'
            )
        )
);

-- ------------------------------------------------------------
-- Table: metro_travel_history
-- Description: Historical logs of completed or cancelled user journeys 
--              on the Metro line, distinguishing single trips from 
--              unlimited day-pass structures.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_travel_history (
    trip_id                 VARCHAR(32) PRIMARY KEY,
    user_id                 VARCHAR(32) NOT NULL,

    metro_schedule_id       VARCHAR(32),

    origin_station_id       VARCHAR(32),
    destination_station_id  VARCHAR(32),

    travel_date             DATE NOT NULL,

    ticket_type             VARCHAR(20) NOT NULL,
    day_pass_ref            VARCHAR(32),

    stops_travelled         INT,

    amount_usd              DECIMAL(6,2) NOT NULL,

    status                  VARCHAR(20) NOT NULL,

    purchased_at            TIMESTAMP,
    travelled_at            TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id),

    FOREIGN KEY (metro_schedule_id)
        REFERENCES metro_schedules(metro_schedule_id),

    FOREIGN KEY (origin_station_id)
        REFERENCES metro_stations(station_id),

    FOREIGN KEY (destination_station_id)
        REFERENCES metro_stations(station_id),

    CONSTRAINT chk_metro_hist_ticket_type
        CHECK (ticket_type IN ('single', 'day_pass')),

    CONSTRAINT chk_metro_hist_status
        CHECK (status IN ('completed', 'cancelled'))
);

-- ------------------------------------------------------------
-- Table: feedback
-- Description: Collects post-travel quantitative ratings and text 
--              commentary from passengers to review overall transit 
--              service quality.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id  VARCHAR(32) PRIMARY KEY,

    booking_id   VARCHAR(32) NOT NULL,
    user_id      VARCHAR(32) NOT NULL,

    rating       INT NOT NULL,
    comment      TEXT,

    submitted_at TIMESTAMP NOT NULL,

    FOREIGN KEY (booking_id)
        REFERENCES bookings(booking_id)
        ON DELETE CASCADE,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id),

    CONSTRAINT chk_feedback_rating
        CHECK (rating BETWEEN 1 AND 5)
);

-- ============================================================
-- Section 3: Financials and Payment Processing
-- ============================================================

-- ------------------------------------------------------------
-- Table: payments
-- Description: Tracks monetary ledger operations including payments 
--              and subsequent balancing refunds. Utilizes self-referential 
--              keys to tie credit refunds directly to parent purchases.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    payment_id        VARCHAR(32) PRIMARY KEY,

    booking_id        VARCHAR(32),

    amount_usd        DECIMAL(10,2) NOT NULL,

    payment_type      VARCHAR(20) NOT NULL,
    method            VARCHAR(30) NOT NULL,
    status            VARCHAR(20) NOT NULL,

    paid_at           TIMESTAMP,

    parent_payment_id VARCHAR(32),

    refunded_amount   DECIMAL(10,2),

    FOREIGN KEY (booking_id)
        REFERENCES bookings(booking_id),

    FOREIGN KEY (parent_payment_id)
        REFERENCES payments(payment_id),

    CONSTRAINT chk_payment_amount
        CHECK (amount_usd > 0),

    CONSTRAINT chk_payment_type
        CHECK (payment_type IN ('purchase', 'refund')),

    CONSTRAINT chk_payment_status
        CHECK (status IN ('paid', 'refunded', 'failed'))
);

-- ============================================================
-- Section 4: Metro Access and Turnstile Gate Logs
-- ============================================================

-- ------------------------------------------------------------
-- Table: metro_access_logs
-- Description: Real-time turnstile telemetry data recording exact 
--              check-in and check-out events at stations to calculate 
--              fares and dynamic route validation.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metro_access_logs (
    log_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,

    user_id          VARCHAR(32) NOT NULL,
    station_id       VARCHAR(32) NOT NULL,

    action_type      VARCHAR(10) NOT NULL,

    timestamp        TIMESTAMP NOT NULL,

    day_pass_trip_id VARCHAR(32),

    FOREIGN KEY (user_id)
        REFERENCES users(user_id),

    FOREIGN KEY (station_id)
        REFERENCES metro_stations(station_id),

    CONSTRAINT chk_access_action
        CHECK (
            action_type IN (
                'check_in',
                'check_out'
            )
        )
);

-- ============================================================
-- Section 8: Commercial Ticketing and Allocation Rules
-- ============================================================

-- ------------------------------------------------------------
-- Table: booking_rule_sets
-- Description: Version-controlled system configurations managing 
--              active parameters for purchasing windows, maximum limits, 
--              and commercial permissions across both systems.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS booking_rule_sets (
    rule_set_id     VARCHAR(32) PRIMARY KEY,

    network_type    VARCHAR(20) NOT NULL,

    version         INT NOT NULL DEFAULT 1,

    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    effective_from  DATE,
    effective_until DATE,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_rule_set_network
        CHECK (
            network_type IN (
                'national_rail',
                'metro'
            )
        ),

    CONSTRAINT chk_booking_rule_set_dates
        CHECK (
            effective_until IS NULL
            OR effective_until > effective_from
        )
);

-- ------------------------------------------------------------
-- Table: booking_rule_params
-- Description: Concrete key-value pairs assigned to active rule sets, 
--              specifying granular policies categorized by ticket type 
--              and class (e.g., baggage weights or reservation thresholds).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS booking_rule_params (
    param_id BIGSERIAL PRIMARY KEY,

    rule_set_id VARCHAR(32) NOT NULL,

    ticket_type VARCHAR(20),
    fare_class  VARCHAR(20),

    rule_key VARCHAR(100) NOT NULL,

    rule_value_numeric DECIMAL(12,4),
    rule_value_text    VARCHAR(255),

    unit VARCHAR(20),

    description TEXT,

    FOREIGN KEY (rule_set_id)
        REFERENCES booking_rule_sets(rule_set_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_param_ticket_type
        CHECK (
            ticket_type IN (
                'single',
                'return',
                'day_pass',
                '*'
            )
        ),

    CONSTRAINT chk_param_fare_class
        CHECK (
            fare_class IN (
                'standard',
                'first',
                '*'
            )
        )
);

-- ============================================================
-- Section 9: Legal Travel Policies and Compliance Rules
-- ============================================================

-- ------------------------------------------------------------
-- Table: policy_categories
-- Description: Structural lookup catalog grouping legal travel regulations 
--              and passenger conduct rules, offering multi-lingual 
--              (Chinese/English) terminology display settings.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_categories (
    category_id     VARCHAR(32) PRIMARY KEY,

    network_type    VARCHAR(20) NOT NULL,

    category_key    VARCHAR(100) NOT NULL,

    display_name_zh VARCHAR(100) NOT NULL,
    display_name_en VARCHAR(100) NOT NULL,

    sort_order      INT NOT NULL,

    UNIQUE (network_type, category_key),

    CONSTRAINT chk_cat_network
        CHECK (
            network_type IN (
                'national_rail',
                'metro',
                'both'
            )
        )
);

-- ------------------------------------------------------------
-- Table: policy_rules
-- Description: Contains explicit passenger governance constraints 
--              (e.g., allowance of pets, heavy carriage items, behavior 
--              prohibitions) tied back to specific network ticket categories.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id VARCHAR(32) PRIMARY KEY,

    category_id VARCHAR(32) NOT NULL,

    rule_key VARCHAR(100) NOT NULL,

    is_permitted BOOLEAN,

    rule_value_text VARCHAR(500),

    description_zh TEXT NOT NULL,
    description_en TEXT,

    applies_to_ticket_type VARCHAR(20),
    applies_to_fare_class  VARCHAR(20),

    effective_from DATE,
    effective_until DATE,

    version INT NOT NULL DEFAULT 1,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id)
        REFERENCES policy_categories(category_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_rule_ticket_type
        CHECK (
            applies_to_ticket_type IN (
                'single',
                'return',
                'day_pass',
                '*'
            )
        ),

    CONSTRAINT chk_rule_fare_class
        CHECK (
            applies_to_fare_class IN (
                'standard',
                'first',
                '*'
            )
        ),

    CONSTRAINT chk_policy_rule_dates
        CHECK (
            effective_until IS NULL
            OR effective_until > effective_from
        )
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_bookings_user
ON bookings(user_id);

CREATE INDEX IF NOT EXISTS idx_bookings_schedule
ON bookings(schedule_id);

CREATE INDEX IF NOT EXISTS idx_payments_booking
ON payments(booking_id);

CREATE INDEX IF NOT EXISTS idx_feedback_booking
ON feedback(booking_id);

CREATE INDEX IF NOT EXISTS idx_rail_seats_coach
ON rail_seats(coach_id);

CREATE INDEX IF NOT EXISTS idx_metro_logs_user
ON metro_access_logs(user_id);

CREATE INDEX IF NOT EXISTS idx_metro_history_user
ON metro_travel_history(user_id);
CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------
-- Table: policy_documents
-- Description: Stores raw text items of policy regulations mapped 
--              to high-dimensional vector embeddings, allowing cognitive 
--              RAG / customer support help desks to perform vector semantic lookups.
-- ------------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS idx_policy_embedding ON policy_documents USING hnsw (embedding vector_cosine_ops);