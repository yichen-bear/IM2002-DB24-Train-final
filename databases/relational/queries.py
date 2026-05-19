"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import json
import random
import string
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """Example: returns the name of the connected database."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.
    """
    results = []
    
    # 開啟資料庫連線
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            
            # 1. 從資料庫撈出所有的火車班次
            sql = """
                SELECT schedule_id, route_id, line, policy_id, service_type, direction,
                       departure_time, arrival_time, origin_station_id, destination_station_id,
                       stops_in_order, base_fare_standard_usd, per_stop_standard_usd,
                       base_fare_first_usd, per_stop_first_usd
                FROM schedules;
            """
            cur.execute(sql)
            schedules = cur.fetchall()

            # 2. 用 Python 檢查每一班車的停靠站順序
            for sch in schedules:
                stops_str = sch.get("stops_in_order") or ""
                # 把資料庫儲存的 "NR01,NR02,NR03" 變成 Python 的列表 ['NR01', 'NR02', 'NR03']
                stops = [s.strip() for s in stops_str.split(",") if s.strip()]
                
                # 檢查起點和終點是不是都在這班車的路線上
                if origin_id in stops and destination_id in stops:
                    orig_idx = stops.index(origin_id)
                    dest_idx = stops.index(destination_id)
                    
                    # 確保起點的順序在終點前面（如果相反代表這班車是反方向開的）
                    if orig_idx < dest_idx:
                        sch_dict = dict(sch)
                        
                        # 3. 如果使用者有給乘車日期，去 bookings 表計算當天這班車已經有多少張「確認」的訂單
                        occupied_seats = 0
                        if travel_date:
                            cur.execute(
                                """
                                SELECT COUNT(*) FROM bookings 
                                WHERE schedule_id = %s AND travel_date = %s AND status = 'confirmed';
                                """,
                                (sch["schedule_id"], travel_date)
                            )
                            occupied_seats = cur.fetchone()["count"]
                        
                        # 把計算好的「已佔用座位數」和「搭乘站數」塞進回傳的資料裡
                        sch_dict["occupied_seats"] = occupied_seats
                        sch_dict["stops_travelled"] = dest_idx - orig_idx
                        results.append(sch_dict)
                        
    # 最後依據火車的出發時間，由早到晚幫使用者排好序
    results.sort(key=lambda x: x["departure_time"])
    return results

def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 從 schedules 表中撈出該班次的所有票價相關欄位
            cur.execute(
                """
                SELECT base_fare_standard_usd, per_stop_standard_usd,
                       base_fare_first_usd, per_stop_first_usd
                FROM schedules WHERE schedule_id = %s;
                """,
                (schedule_id,)
            )
            row = cur.fetchone()
            
            # 如果找不到這個班次，依規格回傳 None
            if not row:
                return None
            
            # 2. 根據艙等 (fare_class) 決定要使用的基本票價與每站費率
            if fare_class.lower() == "first":
                base = float(row["base_fare_first_usd"] or 0)
                per_stop = float(row["per_stop_first_usd"] or 0)
            else:
                base = float(row["base_fare_standard_usd"] or 0)
                per_stop = float(row["per_stop_standard_usd"] or 0)
                
            # 3. 計算總票價：基本費 + (每站費率 * 搭乘站數)
            total_fare = base + (per_stop * stops_travelled)
            
            # 4. 組裝成規格要求的 dict 格式回傳
            return {
                "fare_class": fare_class,
                "base_fare_usd": base,
                "per_stop_rate_usd": per_stop,
                "total_fare_usd": total_fare
            }

# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.
    """
    results = []
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 撈出所有地鐵班次資料
            cur.execute(
                """
                SELECT metro_schedule_id, line, direction, origin_station_id, destination_station_id,
                       first_train_time, last_train_time, frequency_min, stops_in_order,
                       base_fare_usd, per_stop_rate_usd, operates_on
                FROM metro_schedules;
                """
            )
            schedules = cur.fetchall()
            
            # 2. 檢查地鐵路線順序是否符合使用者的起訖站
            for sch in schedules:
                stops_str = sch.get("stops_in_order") or ""
                # 把地鐵站點字串 "MS01,MS02,MS03" 拆解成 Python 列表
                stops = [s.strip() for s in stops_str.split(",") if s.strip()]
                
                if origin_id in stops and destination_id in stops:
                    orig_idx = stops.index(origin_id)
                    dest_idx = stops.index(destination_id)
                    
                    # 確保是同一個行車方向（起點在終點前）
                    if orig_idx < dest_idx:
                        sch_dict = dict(sch)
                        # 計算這次地鐵航程一共坐了幾站
                        sch_dict["stops_travelled"] = dest_idx - orig_idx
                        results.append(sch_dict)
                        
    return results
def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 依據地鐵班次 ID 撈出對應的基本票價與每站費率
            cur.execute(
                """
                SELECT base_fare_usd, per_stop_rate_usd 
                FROM metro_schedules WHERE metro_schedule_id = %s;
                """,
                (schedule_id,)
            )
            row = cur.fetchone()
            
            # 如果找不到這條地鐵班次，回傳 None
            if not row:
                return None
            
            # 2. 轉換資料型態並計算總票價
            base = float(row["base_fare_usd"])
            per_stop = float(row["per_stop_rate_usd"])
            total_fare = base + (per_stop * stops_travelled)
            
            # 3. 組裝成規格要求的 dict 格式回傳
            return {
                "base_fare_usd": base,
                "per_stop_rate_usd": per_stop,
                "total_fare_usd": total_fare
            }


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 先撈出該班次、符合該艙等的「所有車廂和座位」
            sql_all_seats = """
                SELECT rs.seat_real_id, rs.seat_id, rc.coach_number, rs.seat_row, rs.seat_column
                FROM rail_seats rs
                JOIN rail_coaches rc ON rs.coach_id = rc.coach_id
                WHERE rc.schedule_id = %s AND rc.fare_class = %s;
            """
            cur.execute(sql_all_seats, (schedule_id, fare_class.lower()))
            all_seats = cur.fetchall()
            
            # 2. 撈出當天這班火車已經被訂走、且狀態是確定的座位
            sql_booked = """
                SELECT seat_real_id FROM bookings
                WHERE schedule_id = %s AND travel_date = %s AND status = 'confirmed' AND seat_real_id IS NOT NULL;
            """
            cur.execute(sql_booked, (schedule_id, travel_date))
            booked_seat_ids = {row["seat_real_id"] for row in cur.fetchall()}
            
            # 3. 過濾掉被訂走的座位，只保留有空的
            available = []
            for s in all_seats:
                if s["seat_real_id"] not in booked_seat_ids:
                    available.append({
                        "seat_id": s["seat_id"],       # 給 Agent 互動看的小短碼 (例如 "A1")
                        "seat_real_id": s["seat_real_id"], # 資料庫主鍵唯一碼
                        "coach": str(s["coach_number"]),   # 車廂編號
                        "row": s["seat_row"] or 0,         # 排數
                        "column": s["seat_column"] or ""   # 欄位 (A, B, C...)
                    })
                    
            # 依據車廂、排數、欄位幫座位由前到後排好序
            available.sort(key=lambda x: (x["coach"], x["row"], x["column"]))
            return available


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    # 微調：改成用 (車廂, 排數) 當作群組 key，防止把乘客塞到不同車廂的同一排
    rows: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[(seat["coach"], seat["row"])].append(seat)

    # 1. 優先尋找「同一節車廂、同一排」就能坐下所有人的完美座位
    for (coach, row), row_seats in sorted(rows.items(), key=lambda item: (item[0][0], item[0][1])):
        if len(row_seats) >= count:
            row_seats.sort(key=lambda s: s["column"])
            return [s["seat_id"] for s in row_seats[:count]]

    # 2. 如果沒辦法完美塞在同一排，就直接拿「同一節車廂鄰近排數」最靠前的座位
    sorted_seats = sorted(available_seats, key=lambda s: (s["coach"], s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]
# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 直接從 users 表透過 email 查詢使用者檔案
            cur.execute("SELECT * FROM users WHERE email = %s;", (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).
    """
    # 1. 先用剛剛寫好的函式拿到 user_id
    profile = query_user_profile(user_email)
    if not profile:
        return {"national_rail": [], "metro": []}
        
    user_id = profile["user_id"]
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 2. 撈取該使用者的「國家鐵路」訂單歷史
            cur.execute(
                """
                SELECT b.*, s.line, s.direction
                FROM bookings b
                JOIN schedules s ON b.schedule_id = s.schedule_id
                WHERE b.user_id = %s 
                ORDER BY b.booked_at DESC;
                """,
                (user_id,)
            )
            nr_list = [dict(r) for r in cur.fetchall()]
            
            # 3. 撈取該使用者的「地鐵」搭乘歷史
            cur.execute(
                """
                SELECT m.*, ms.line, ms.direction
                FROM metro_travel_history m
                LEFT JOIN metro_schedules ms ON m.metro_schedule_id = ms.metro_schedule_id
                WHERE m.user_id = %s 
                ORDER BY m.purchased_at DESC;
                """,
                (user_id,)
            )
            metro_list = [dict(r) for r in cur.fetchall()]
            
            # 4. 防呆：把所有日期、時間欄位全部轉成字串，避免外層 JSON 解析失敗
            for item in nr_list + metro_list:
                for k, v in item.items():
                    if isinstance(v, (datetime, datetime.date, datetime.time)):
                        item[k] = str(v)
                        
            return {
                "national_rail": nr_list,
                "metro": metro_list
            }

def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 依據 booking_id (或 trip_id) 撈出最新的一筆付款紀錄
            cur.execute("SELECT * FROM payments WHERE booking_id = %s ORDER BY paid_at DESC;", (booking_id,))
            row = cur.fetchone()
            if row:
                d = dict(row)
                if d["paid_at"]:
                    d["paid_at"] = str(d["paid_at"])
                return d
            return None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.
    """
    # 1. 驗證站點順序並計算搭乘站數 (stops_travelled)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stops_in_order, departure_time FROM schedules WHERE schedule_id = %s;", (schedule_id,))
            res = cur.fetchone()
            if not res or not res[0]:
                return False, "Schedule not found"
            
            stops = [s.strip() for s in res[0].split(",") if s.strip()]
            if origin_station_id not in stops or destination_station_id not in stops:
                return False, "Invalid origin or destination for this schedule"
            
            orig_idx = stops.index(origin_station_id)
            dest_idx = stops.index(destination_station_id)
            if orig_idx >= dest_idx:
                return False, "Incorrect station sequence ordering"
            
            stops_travelled = dest_idx - orig_idx
            default_dep_time = res[1]

    # 2. 計算總票價 (如果是來回票 ticket_type == "return"，金額乘二)
    fare_info = query_national_rail_fare(schedule_id, fare_class, stops_travelled)
    if not fare_info:
        return False, "Failed to calculate fare"
    amount_usd = fare_info["total_fare_usd"]
    if ticket_type == "return":
        amount_usd *= 2

    # 3. 檢查座位可用性並取得 seat_real_id
    avail_seats = query_available_seats(schedule_id, travel_date, fare_class)
    if not avail_seats:
        return False, "No seats available in this class"

    selected_real_id = None
    selected_short_id = None
    
    # 如果指定 "any"，呼叫自動選位
    if seat_id == "any":
        auto_shorts = auto_select_adjacent_seats(avail_seats, 1)
        if not auto_shorts:
            return False, "Auto seat assignment failed"
        selected_short_id = auto_shorts[0]
    else:
        selected_short_id = seat_id

    # 從可用清單比對出真實的資料庫主鍵 ID (seat_real_id)
    for s in avail_seats:
        if s["seat_id"] == selected_short_id:
            selected_real_id = s["seat_real_id"]
            break
            
    if not selected_real_id:
        return False, f"Seat {selected_short_id} is unavailable or already occupied"

    # 4. 開始執行手動交易控制（悲觀鎖防搶）
    booking_id = _gen_booking_id()
    payment_id = _gen_payment_id()
    now = datetime.now(timezone.utc)

    # 開啟全新的連線，不使用自動提交
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 【核心鎖定】利用 FOR UPDATE NOWAIT 鎖定當天、該班次的這個座位
            # 如果別人的交易正在處理這個座位，會立刻噴錯跳到 except，避免重疊預訂
            cur.execute(
                """
                SELECT 1 FROM bookings 
                WHERE schedule_id = %s AND travel_date = %s AND seat_real_id = %s AND status = 'confirmed'
                FOR UPDATE NOWAIT;
                """,
                (schedule_id, travel_date, selected_real_id)
            )
            if cur.fetchone():
                conn.rollback()
                return False, "Seat was just booked by another session"

            # 寫入 bookings 資料表
            sql_ins_booking = """
                INSERT INTO bookings (
                    booking_id, user_id, schedule_id, origin_station_id, destination_station_id,
                    travel_date, departure_time, ticket_type, fare_class, seat_real_id,
                    stops_travelled, amount_usd, status, booked_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cur.execute(sql_ins_booking, (
                booking_id, user_id, schedule_id, origin_station_id, destination_station_id,
                travel_date, default_dep_time, ticket_type, fare_class.lower(), selected_real_id,
                stops_travelled, amount_usd, "confirmed", now
            ))

            # 寫入 payments 金流資料表
            sql_ins_payment = """
                INSERT INTO payments (
                    payment_id, booking_id, amount_usd, payment_type, method, status, paid_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            cur.execute(sql_ins_payment, (
                payment_id, booking_id, amount_usd, "purchase", "credit_card", "paid", now
            ))

            # 通通成功才正式提交（Commit）到資料庫
            conn.commit()
            
            return True, {
                "booking_id": booking_id,
                "payment_id": payment_id,
                "seat_id": selected_short_id,
                "amount_usd": amount_usd,
                "status": "confirmed"
            }
            
    except Exception as e:
        # 只要中間有任何一個步驟噴錯，全部回復原狀（Rollback）
        conn.rollback()
        return False, f"Booking transaction rolled back: {str(e)}"
    finally:
        conn.close()

def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Calculates the refund amount according to the booking's service type:
      - Normal service: RF001 windows (100% / 75% / 50% / 0%)
      - Express service: RF002 windows (100% / 50% / 0%)

    Args:
        booking_id: e.g. "BK001"
        user_id:    must match the booking's user_id

    Returns:
        (True, result_dict)  with refund_amount_usd and policy note
        (False, error_msg)
    """
    raise NotImplementedError("TODO: implement after designing your schema")


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user into both 'users' and 'user_credentials' tables.
    Returns (True, user_id) on success or (False, error_message) on failure.
    """
    # 1. 隨機生成 4 位數後綴，組合出 user_id (例如: RU-4829) 與 username
    suffix = "".join(random.choices(string.digits, k=4))
    user_id = f"RU-{suffix}"
    username = email.split("@")[0] + suffix
    
    # 將出生年轉為資料庫支援的 DATE 格式 (預設該年 1 月 1 日)
    dob_str = f"{year_of_birth}-01-01" 
    full_name = f"{first_name} {surname}"

    # 2. 開始手動交易控制（因為要同時寫入兩張表，必須同步成功或同步失敗）
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    
    try:
        with conn.cursor() as cur:
            # 檢查 Email 是否已經被註冊過（維持資料唯一性限制）
            cur.execute("SELECT 1 FROM users WHERE email = %s;", (email,))
            if cur.fetchone():
                conn.rollback()
                return False, "Email already registered"

            # 步驟 A：寫入基礎資料表 'users'
            sql_user = """
                INSERT INTO users (user_id, username, email, full_name, date_of_birth, secret_question, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE);
            """
            cur.execute(sql_user, (user_id, username, email, full_name, dob_str, secret_question))

            # 步驟 B：寫入獨立憑證表 'user_credentials' (對接你的 password_hash 欄位)
            sql_cred = """
                INSERT INTO user_credentials (user_id, password_hash, secret_answer_hash)
                VALUES (%s, %s, %s);
            """
            cur.execute(sql_cred, (user_id, password, secret_answer))

            # 兩張表都寫入成功，才正式提交
            conn.commit()
            return True, user_id
            
    except Exception as e:
        # 只要其中一張表失敗（例如：Username 意外重複），立刻全部撤回
        conn.rollback()
        return False, f"Registration failed: {str(e)}"
    finally:
        conn.close()

def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 使用 JOIN 串接兩張表，透過 email 撈出使用者資料與密碼
            sql = """
                SELECT u.user_id, u.email, u.full_name, u.phone, u.date_of_birth, u.is_active, 
                       uc.password_hash
                FROM users u
                JOIN user_credentials uc ON u.user_id = uc.user_id
                WHERE u.email = %s;
            """
            cur.execute(sql, (email,))
            row = cur.fetchone()
            
            # 2. 檢查使用者是否存在，以及密碼是否正確（比對對接資料庫的 password_hash）
            if not row or row["password_hash"] != password:
                return None
            
            # 3. 解析名字 (first_name) 與姓氏 (surname)
            # 假設 full_name 是 "First Last"，用空格切成兩半
            full_name = row["full_name"] or ""
            parts = full_name.split(" ", 1)
            first_name = parts[0] if len(parts) > 0 else ""
            surname = parts[1] if len(parts) > 1 else ""

            # 4. 組裝成老師要求的欄位格式並回傳
            return {
                "user_id": row["user_id"],
                "email": row["email"],
                "full_name": full_name,
                "first_name": first_name,
                "surname": surname,
                "phone": row["phone"],
                "date_of_birth": str(row["date_of_birth"]) if row["date_of_birth"] else None,
                "is_active": row["is_active"]
            }

def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    with _connect() as conn:
        with conn.cursor() as cur:
            # 直接從 users 表中透過 email 尋找安全提問
            cur.execute("SELECT secret_question FROM users WHERE email = %s;", (email,))
            res = cur.fetchone()
            
            # 如果有找到使用者，回傳該安全提問的字串；找不到則回傳 None
            return res[0] if res else None
def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            # 使用 JOIN 透過 email 串接 user_credentials 撈出答案
            sql = """
                SELECT uc.secret_answer_hash FROM user_credentials uc
                JOIN users u ON u.user_id = uc.user_id
                WHERE u.email = %s;
            """
            cur.execute(sql, (email,))
            res = cur.fetchone()
            
            # 如果有找到紀錄且答案不為空，進行不區分大小寫與去前後空白的比對
            if res and res[0]:
                return res[0].lower().strip() == answer.lower().strip()
            
            return False


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    with _connect() as conn:
        with conn.cursor() as cur:
            # 透過子查詢，找出 email 對應的 user_id，並更新密碼
            sql = """
                UPDATE user_credentials 
                SET password_hash = %s
                WHERE user_id = (SELECT user_id FROM users WHERE email = %s);
            """
            cur.execute(sql, (new_password, email))
            
            # cur.rowcount 會回傳受影響的資料列數量
            # 如果大於 0 代表更新成功 (回傳 True)，若 email 不存在則會大於 0 失敗 (回傳 False)
            return cur.rowcount > 0
# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
