# AI Session Context — TransitFlow (Team Verified Version)

**How to use this file:**
At the start of every AI coding session, paste the full contents of this file as your first message to your AI assistant. This gives the AI the context it needs to produce code that fits our updated codebase and remains consistent with our team's database architecture.

**Who maintains this file:**
Whoever makes a schema change or architectural decision updates this file in the same commit. Treat it like our team's technical contract.

---

## Project Overview

TransitFlow is a Python-based AI chat assistant for a transit operator. It queries three database paradigms — PostgreSQL (relational + vector) and Neo4j (graph) — using an LLM to fulfill user requests. 

Our team has established a highly robust relational schema (V9.0 Perfected) supporting a dual-network transit system (Metro & National Rail), secure user authentication with Argon2id, strict payment workflows, and advanced seat selection.

## Tech Stack

- **Language:** Python 3.11+
- **Relational DB:** PostgreSQL 15+ via `psycopg2` with `RealDictCursor`
- **Graph DB:** Neo4j via the `neo4j` official Python driver
- **Vector Search:** `pgvector` extension utilizing `vector(768)` (Ollama nomic-embed-text) or `vector(3072)` (Gemini)
- **Security:** `argon2-cffi` (Argon2id variant) for passwords and secret answers
- **Web UI:** Gradio
- **LLM:** Google Gemini or local Ollama (configured via `.env`)

## Coding Conventions

- **Naming:** Strict `snake_case` for all Python functions, variables, and SQL identifiers.
- **Docstrings:** All functions must have explicit `Args:` and `Returns:` documentation sections.
- **Return Types:** Fully type-hinted. Read-only queries must return `list[dict]` or `Optional[dict]`. Write operations return `tuple[bool, dict | str]`.
- **Empty Results:** Return `[]` or `None` as specified. Never raise unhandled exceptions for data "not found".
- **SQL Parameterization:** Always use `%s` placeholders for all SQL statements — never format strings directly into raw queries to mitigate SQL Injection.
- **Relational Connection Pattern:** Use the predefined `_connect()` helper context manager + `psycopg2.extras.RealDictCursor`:
  ```python
  with _connect() as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          cur.execute("SELECT ...", (param,))
          return [dict(row) for row in cur.fetchall()]
  ```
- **Transaction Control Pattern (Crucial for Write Actions):** For transactional write operations (e.g., booking, cancellation), manage connections manually to ensure atomic consistency:
  ```python
  conn = psycopg2.connect(PG_DSN)
  conn.autocommit = False
  try:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          # Perform operations...
          conn.commit()
          return True, result_dict
  except Exception as e:
      conn.rollback()
      return False, str(e)
  finally:
      conn.close()
  ```

---

## Agreed Relational Schema (V9.0 Perfected)

This is the final relational structure implemented in `databases/relational/schema.sql`:

```sql
-- 用戶基礎架構
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

-- 密碼獨立表 (高安全性分離設計)
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id            VARCHAR(32) PRIMARY KEY,
    password_hash      TEXT NOT NULL,
    secret_answer_hash TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- 基礎設施與雙網站點架構
CREATE TABLE IF NOT EXISTS metro_stations (
    station_id                    VARCHAR(32) PRIMARY KEY,
    name                          VARCHAR(100) NOT NULL,
    lines                         VARCHAR(255) NOT NULL,
    is_interchange_metro          BOOLEAN NOT NULL,
    interchange_metro_lines       VARCHAR(255),
    is_interchange_national_rail  BOOLEAN NOT NULL,
    interchange_national_rail_station_id VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS national_rail_stations (
    station_id                    VARCHAR(32) PRIMARY KEY,
    name                          VARCHAR(100) NOT NULL,
    lines                         VARCHAR(255) NOT NULL,
    is_interchange_national_rail  BOOLEAN NOT NULL,
    interchange_national_rail_lines VARCHAR(255),
    is_interchange_metro          BOOLEAN NOT NULL,
    interchange_metro_station_id  VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS station_adjacencies (
    source_station_id   VARCHAR(32) NOT NULL,
    adjacent_station_id VARCHAR(32) NOT NULL,
    network_type        VARCHAR(20) NOT NULL,
    line                VARCHAR(50) NOT NULL,
    travel_time_min     INT NOT NULL,
    PRIMARY KEY (source_station_id, adjacent_station_id, network_type),
    CONSTRAINT chk_network_type CHECK (network_type IN ('metro', 'national_rail'))
);

-- 退款與補償政策
CREATE TABLE IF NOT EXISTS refund_policies (
    policy_id                      VARCHAR(32) PRIMARY KEY,
    service_type                   VARCHAR(20) NOT NULL,
    policy_name                    VARCHAR(100) NOT NULL,
    no_refund_before_departure_min INT NOT NULL,
    effective_from                 DATE,
    effective_until                DATE,
    created_at                     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_refund_policy_service_type CHECK (service_type IN ('normal', 'express')),
    CONSTRAINT chk_no_refund_min CHECK (no_refund_before_departure_min >= 0),
    CONSTRAINT chk_refund_policy_dates CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE IF NOT EXISTS refund_cancellation_windows (
    window_id                  VARCHAR(32) PRIMARY KEY,
    policy_id                  VARCHAR(32) NOT NULL,
    window_label               VARCHAR(100) NOT NULL,
    hours_before_departure_min DECIMAL(8,2) NOT NULL,
    hours_before_departure_max DECIMAL(8,2),
    refund_percent             DECIMAL(5,2) NOT NULL,
    processing_fee_usd         DECIMAL(6,2) NOT NULL DEFAULT 0.00,
    sort_order                 INT NOT NULL,
    FOREIGN KEY (policy_id) REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
    CONSTRAINT chk_window_hours_min CHECK (hours_before_departure_min >= 0),
    CONSTRAINT chk_refund_percent CHECK (refund_percent BETWEEN 0 AND 100),
    CONSTRAINT chk_processing_fee CHECK (processing_fee_usd >= 0),
    CONSTRAINT chk_window_hours_range CHECK (hours_before_departure_max IS NULL OR hours_before_departure_max > hours_before_departure_min)
);

CREATE TABLE IF NOT EXISTS refund_compensation_rules (
    compensation_id         VARCHAR(32) PRIMARY KEY,
    policy_id               VARCHAR(32) NOT NULL,
    trigger_type            VARCHAR(30) NOT NULL,
    delay_minutes_threshold INT,
    compensation_percent    DECIMAL(5,2) NOT NULL,
    compensation_type       VARCHAR(20) NOT NULL,
    description             TEXT,
    FOREIGN KEY (policy_id) REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
    CONSTRAINT chk_comp_trigger_type CHECK (trigger_type IN ('service_cancellation', 'delay', 'route_change')),
    CONSTRAINT chk_delay_threshold CHECK (delay_minutes_threshold IS NULL OR delay_minutes_threshold > 0),
    CONSTRAINT chk_comp_percent CHECK (compensation_percent BETWEEN 0 AND 100),
    CONSTRAINT chk_comp_type CHECK (compensation_type IN ('refund', 'voucher', 'credit'))
);

-- 班次、車廂與座位
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
    FOREIGN KEY (origin_station_id) REFERENCES national_rail_stations(station_id),
    FOREIGN KEY (destination_station_id) REFERENCES national_rail_stations(station_id),
    FOREIGN KEY (policy_id) REFERENCES refund_policies(policy_id),
    CONSTRAINT chk_schedules_direction CHECK (direction IN ('northbound', 'southbound', 'eastbound', 'westbound'))
);

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
    FOREIGN KEY (origin_station_id) REFERENCES metro_stations(station_id),
    FOREIGN KEY (destination_station_id) REFERENCES metro_stations(station_id),
    CONSTRAINT chk_metro_direction CHECK (direction IN ('northbound', 'southbound', 'eastbound', 'westbound'))
);

CREATE TABLE IF NOT EXISTS rail_coaches (
    coach_id     VARCHAR(32) PRIMARY KEY,
    schedule_id  VARCHAR(32) NOT NULL,
    coach_number INT NOT NULL,
    fare_class   VARCHAR(20) NOT NULL,
    FOREIGN KEY (schedule_id) REFERENCES schedules(schedule_id) ON DELETE CASCADE,
    CONSTRAINT chk_coach_fare_class CHECK (fare_class IN ('standard', 'first'))
);

CREATE TABLE IF NOT EXISTS rail_seats (
    seat_real_id VARCHAR(64) PRIMARY KEY,
    coach_id      VARCHAR(32) NOT NULL,
    seat_id       VARCHAR(10) NOT NULL,
    seat_row      INT,
    seat_column   VARCHAR(5),
    is_booked     BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (coach_id) REFERENCES rail_coaches(coach_id) ON DELETE CASCADE,
    UNIQUE (coach_id, seat_id)
);

-- 訂單、行程歷史與回饋
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
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (schedule_id) REFERENCES schedules(schedule_id),
    FOREIGN KEY (origin_station_id) REFERENCES national_rail_stations(station_id),
    FOREIGN KEY (destination_station_id) REFERENCES national_rail_stations(station_id),
    FOREIGN KEY (seat_real_id) REFERENCES rail_seats(seat_real_id),
    CONSTRAINT chk_booking_ticket_type CHECK (ticket_type IN ('single', 'return')),
    CONSTRAINT chk_booking_fare_class CHECK (fare_class IN ('standard', 'first')),
    CONSTRAINT chk_booking_status CHECK (status IN ('confirmed', 'cancelled', 'completed'))
);

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
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (metro_schedule_id) REFERENCES metro_schedules(metro_schedule_id),
    FOREIGN KEY (origin_station_id) REFERENCES metro_stations(station_id),
    FOREIGN KEY (destination_station_id) REFERENCES metro_stations(station_id),
    CONSTRAINT chk_metro_hist_ticket_type CHECK (ticket_type IN ('single', 'day_pass')),
    CONSTRAINT chk_metro_hist_status CHECK (status IN ('completed', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id  VARCHAR(32) PRIMARY KEY,
    booking_id   VARCHAR(32) NOT NULL,
    user_id      VARCHAR(32) NOT NULL,
    rating       INT NOT NULL,
    comment      TEXT,
    submitted_at TIMESTAMP NOT NULL,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    CONSTRAINT chk_feedback_rating CHECK (rating BETWEEN 1 AND 5)
);

-- 金流管理
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
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id),
    FOREIGN KEY (parent_payment_id) REFERENCES payments(payment_id),
    CONSTRAINT chk_payment_amount CHECK (amount_usd > 0),
    CONSTRAINT chk_payment_type CHECK (payment_type IN ('purchase', 'refund')),
    CONSTRAINT chk_payment_status CHECK (status IN ('paid', 'refunded', 'failed'))
);
```

---

## Agreed Graph Schema

This outlines the Neo4j schema definitions used to handle high-performance route finding and network topology.

```
Node Labels:
- (:Station {station_id: STRING, name: STRING, network_type: STRING})
- (:Line {name: STRING, network_type: STRING})

Relationship Types:
- [:CONNECTS_TO {travel_time_min: INT, fare_usd: FLOAT, line: STRING}] -> Undirected/Directed tracking physical adjacencies between stations.
- [:PART_OF] -> Stations belonging to a specific Transit Line.
- [:INTERCHANGE_WITH {transfer_time_min: INT}] -> Linking Metro and National Rail nodes sharing a spatial hub.

Key Properties:
- station_id, network_type ('metro' | 'national_rail'), travel_time_min, fare_usd
```

---

## Function Signatures Implemented

### Relational Layer (`databases/relational/queries.py`)

All the functions below have been implemented and validated matching our core production schema:

```python
# ── READ-ONLY LOOKUPS ──
def query_national_rail_availability(origin_id: str, destination_id: str, travel_date: Optional[str] = None) -> list[dict]:
    """Parses schedules (supports JSON array or comma-separated string) and tracks occupied seats on a given date."""

def query_national_rail_fare(schedule_id: str, fare_class: str, stops_travelled: int) -> Optional[dict]:
    """Calculates rail fares via base_fare + (per_stop_rate * stops_travelled) dynamically based on coach class."""

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """Queries all metro schedules serving the origin and destination in correct directional sequential order."""

def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """Calculates metro fare totals for single-ticket travel."""

def query_available_seats(schedule_id: str, travel_date: str, fare_class: str) -> list[dict]:
    """Filters out 'confirmed' booked seats for a train running on a specific date, returning accurate open inventories."""

def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """Heuristic logic: prioritizes pairing passengers within the same coach and row before checking adjacent rows."""

def query_user_profile(user_email: str) -> Optional[dict]:
    """Fetches user information directly by unique email."""

def query_user_bookings(user_email: str) -> dict:
    """Returns combined history dict formatting all DateTime/Time variables into clean strings: {"national_rail": [...], "metro": [...]}."""

def query_payment_info(booking_id: str) -> Optional[dict]:
    """Fetches payment records filtered by booking or transit trip ID."""

# ── TRANSACTIONAL WRITE ACTIONS ──
def execute_booking(user_id: str, schedule_id: str, origin_station_id: str, destination_station_id: str, travel_date: str, fare_class: str, seat_id: str, ticket_type: str = "single") -> tuple[bool, dict | str]:
    """Implements Pessimistic Booking with 'FOR UPDATE NOWAIT' to resolve race-conditions on simultaneous seat selections."""

def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """Processes booking cancellations and handles automatic tier refunds according to RF001/RF002 policies via row locks."""

# ── SECURE AUTHENTICATION LAYER ──
def register_user(email, first_name, surname, year_of_birth, password, secret_question, secret_answer) -> tuple[bool, str]:
    """Saves user data while running secure password and secret answer hashing using Argon2id algorithm."""

def login_user(email: str, password: str) -> Optional[dict]:
    """Verifies credentials using Argon2id PasswordHasher and protects user_credentials records from exposure."""

def get_user_secret_question(email: str) -> Optional[str]: ...
def verify_secret_answer(email: str, answer: str) -> bool: ...
def update_password(email: str, new_password: str) -> bool: ...

# ── VECTOR SEARCH LAYER (RAG / Help Desk) — DO NOT MODIFY ──
def query_policy_vector_search(embedding: list[float], top_k: int = 5) -> list[dict]: ...
def store_policy_document(title: str, category: str, content: str, embedding: list[float], source_file: str = "") -> int: ...
```

### Graph Layer (`databases/graph/queries.py`)
*(Signatures planned for graph-based routing modules)*
```python
def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict: ...
def query_cheapest_route(origin_id: str, destination_id: str, network: str = "auto", fare_class: str = "standard") -> dict: ...
def query_alternative_routes(origin_id, destination_id, avoid_station_id, network="auto", max_routes=3) -> list[list[dict]]: ...
def query_interchange_path(origin_id: str, destination_id: str) -> dict: ...
def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]: ...
def query_station_connections(station_id: str) -> list[dict]: ...
```

---

## Team Decisions Log

- **Decision:** Split user data into `users` and `user_credentials` tables. **Why:** Separation of concerns. Keeps high-frequency read actions (like profile lookups) separate from sensitive security credentials.
- **Decision:** Use Argon2id via `argon2-cffi` for password hashing and secret answer hashing. **Why:** It provides modern, industry-standard resistance against GPU-based brute-force attacks.
- **Decision:** Parse `stops_in_order` inside python code using string inspection and fallback `json.loads`. **Why:** Ensures smart compatibility across varying mock datasets (some files store stops as JSON arrays, others use comma-separated text strings).
- **Decision:** Utilize `FOR UPDATE NOWAIT` inside `execute_booking`. **Why:** Prevents duplicate seat allocation errors by instantly failing a transaction row-lock attempt if another session is checking out the identical seat.
- **Decision:** Standardize all timestamp, date, and time objects to native python string types during user-history lookups (`query_user_bookings`). **Why:** Prevents structural crashing on outer Gradio/JSON pipeline encoders.

---

## Prompts That Worked

### Prompt for transactional code optimization:
```text
Review our custom PostgreSQL schema containing tables 'bookings', 'payments', and 'rail_seats'. Write a transaction block for `execute_booking` that implements pessimistic locking so two clients can never book the same `seat_real_id` on the same `travel_date` concurrently. Use `FOR UPDATE NOWAIT` to fail fast.
```