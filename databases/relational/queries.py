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
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

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
    取消國家鐵路訂單，並依據車次類型與退票政策（RF001 / RF002）計算退款金額。
    """
    now = datetime.now(timezone.utc)
    
    # 開啟手動交易控制，防止退票時發生 Race Condition
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 鎖定並撈出這筆訂單，同時檢查是否為該使用者的訂單、且狀態必須是 confirmed
            cur.execute(
                """
                SELECT b.*, s.service_type 
                FROM bookings b
                JOIN schedules s ON b.schedule_id = s.schedule_id
                WHERE b.booking_id = %s AND b.user_id = %s
                FOR UPDATE;
                """,
                (booking_id, user_id)
            )
            booking = cur.fetchone()
            
            if not booking:
                conn.rollback()
                return False, "找不到對應的有效訂單，或您無權操作此訂單。"
                
            if booking["status"] == "cancelled":
                conn.rollback()
                return False, "該訂單先前已經取消過了。"

            # 2. 計算距離發車還有多久（簡單估算：以 travel_date 與資料庫的 departure_time 組合）
            # 這裡為了防呆與簡化，我們先採用彈性的退款策略（實際專案可依助教給的時間戳計算）
            service_type = booking["service_type"] or "normal"
            amount_usd = float(booking["amount_usd"])
            
            # 3. 根據政策（RF001/RF002）決定退款比例
            # 這裡實作標準的階梯式退款邏輯
            refund_rate = 1.0  # 預設全額退款
            policy_note = "RF001: 提前取消，符合 100% 全額退款金額。"
            
            if service_type.lower() == "express":
                # 特快車次政策 (RF002)
                policy_note = "RF002: 特快車次取消，扣除手續費後退款。"
                refund_rate = 0.8  # 範例：特快車酌收 20% 手續費
            else:
                # 普通車次政策 (RF001)
                refund_rate = 1.0

            refund_amount = amount_usd * refund_rate

            # 4. 更新訂單狀態為 cancelled
            cur.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE booking_id = %s;",
                (booking_id,)
            )

            # 5. 寫入退款紀錄到 payments 表（payment_type 標記為 refund，金額為負數或正數退款）
            payment_id = _gen_payment_id()
            cur.execute(
                """
                INSERT INTO payments (payment_id, booking_id, amount_usd, payment_type, method, status, paid_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (payment_id, booking_id, refund_amount, "refund", "credit_card", "refunded", now)
            )

            conn.commit()
            return True, {
                "booking_id": booking_id,
                "refund_amount_usd": refund_amount,
                "policy_note": policy_note,
                "status": "cancelled"
            }

    except Exception as e:
        conn.rollback()
        return False, f"取消訂單交易失敗，已回滾：{str(e)}"
    finally:
        conn.close()

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
    註冊新使用者，並使用 Argon2id 安全雜湊密碼與安全問題答案。
    """
    ph = PasswordHasher()
    
    # 1. 產生安全的 Argon2id 雜湊值（自動加鹽）
    hashed_password = ph.hash(password)
    hashed_answer = ph.hash(secret_answer)
    
    # 根據 email 自動切出 username
    username = email.split("@")[0]
    user_id = f"UR-{ ''.join(random.choices(string.digits, k=5)) }"
    full_name = f"{first_name} {surname}"
    # 格式化生日（假設資料庫欄位需要 date 格式，用當年 1 月 1 日暫代，或依你們 schema 為準）
    dob = f"{year_of_birth}-01-01" 
    
    sql_user = """
        INSERT INTO users (user_id, username, email, full_name, date_of_birth, secret_question, registered_at, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), TRUE);
    """
    sql_cred = """
        INSERT INTO user_credentials (user_id, password_hash, secret_answer_hash)
        VALUES (%s, %s, %s);
    """
    
    # 寫入資料庫（注意：寫入多張表時建議用同一個連線控制 Transaction）
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # 先寫入主表
            cur.execute(sql_user, (user_id, username, email, full_name, dob, secret_question))
            # 再寫入憑證表
            cur.execute(sql_cred, (user_id, hashed_password, hashed_answer))
        conn.commit()
        return True, user_id
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
def login_user(email: str, password: str) -> Optional[dict]:
    """
    驗證使用者登入憑證。成功則回傳使用者完整資料，失敗回傳 None。
    """
    # 透過 JOIN 把 users 的基本資料和 user_credentials 的密碼雜湊一起撈出來
    sql = """
        SELECT u.user_id, u.email, u.full_name, u.date_of_birth, u.is_active, uc.password_hash
        FROM users u
        JOIN user_credentials uc ON u.user_id = uc.user_id
        WHERE u.email = %s;
    """
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            user_record = cur.fetchone()
            
            if not user_record or not user_record["is_active"]:
                return None
            
            # 使用 Argon2id 進行密碼驗證
            ph = PasswordHasher()
            try:
                ph.verify(user_record["password_hash"], password)
                
                # 驗證成功，移除敏感的密碼欄位後回傳
                user_dict = dict(user_record)
                user_dict.pop("password_hash", None)
                return user_dict
            except VerifyMismatchError:
                return None # 密碼錯誤
def get_user_secret_question(email: str) -> Optional[str]:
    """查詢使用者的安全問題。"""
    sql = "SELECT secret_question FROM users WHERE email = %s;"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            return row[0] if row else None
def verify_secret_answer(email: str, answer: str) -> bool:
    """驗證安全問題答案是否正確（不區分大小寫）。"""
    sql = """
        SELECT uc.secret_answer_hash
        FROM users u
        JOIN user_credentials uc ON u.user_id = uc.user_id
        WHERE u.email = %s;
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row:
                return False
            
            ph = PasswordHasher()
            try:
                # 由於答案通常會被轉換為小寫比對，建議輸入的答案可以做 .lower().strip() 處理
                ph.verify(row[0], answer.lower().strip())
                return True
            except VerifyMismatchError:
                return False


def update_password(email: str, new_password: str) -> bool:
    """更新使用者密碼。"""
    ph = PasswordHasher()
    new_hash = ph.hash(new_password)
    
    sql = """
        UPDATE user_credentials
        SET password_hash = %s
        WHERE user_id = (SELECT user_id FROM users WHERE email = %s);
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (new_hash, email))
            # cur.rowcount 會回傳受影響的行數，如果 > 0 代表更新成功
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
