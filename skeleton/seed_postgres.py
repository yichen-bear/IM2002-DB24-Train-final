"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import hashlib
import binascii
import os
import sys

import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    stations_rows = []
    
    for s in data:
        stations_rows.append((
            s["station_id"],
            s["name"],
            s.get("lines", []),  # 直接傳入陣列
            s["is_interchange_metro"],
            s.get("interchange_metro_lines", []), # 同學多開的這個陣列也要傳
            s["is_interchange_national_rail"],
            s.get("interchange_national_rail_station_id")
        ))

    # 直接將 7 個欄位寫入主表
    n_stations = insert_many(
        cur, 
        "metro_stations", 
        [
            "station_id", 
            "name", 
            "lines", 
            "is_interchange_metro", 
            "interchange_metro_lines", 
            "is_interchange_national_rail", 
            "interchange_national_rail_station_id"
        ], 
        stations_rows
    )
    print(f"  metro_stations: {n_stations} rows")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    stations_rows = []
    
    for s in data:
        stations_rows.append((
            s["station_id"],
            s["name"],
            s.get("lines", []),
            s["is_interchange_national_rail"],
            s.get("interchange_national_rail_lines", []),
            s["is_interchange_metro"],
            s.get("interchange_metro_station_id")
        ))

    n_stations = insert_many(
        cur, 
        "national_rail_stations", 
        [
            "station_id", 
            "name", 
            "lines", 
            "is_interchange_national_rail", 
            "interchange_national_rail_lines", 
            "is_interchange_metro", 
            "interchange_metro_station_id"
        ], 
        stations_rows
    )
    print(f"  national_rail_stations: {n_stations} rows")




def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    rows = []
    
    for sch in data:
        # 將 JSON 的陣列與字典直接轉換為字串 (配合 schema 的 TEXT 欄位)
        stops_json = json.dumps(sch.get("stops_in_order", []))
        
        # 注意：JSON 裡的 key 是 travel_time_from_origin_min，Schema 改叫 travel_time_offset
        travel_time_json = json.dumps(sch.get("travel_time_from_origin_min", {}))
        
        # 營運日 (operates_on) 在 Schema 是 VARCHAR，我們轉成逗號分隔字串
        operates_on_str = ",".join(sch.get("operates_on", []))
        
        # 嚴格對齊同學在 metro_schedules 開的 13 個欄位
        rows.append((
            sch["schedule_id"],                   # 1. metro_schedule_id (JSON裡叫 schedule_id)
            sch["line"],                          # 2. line
            sch.get("direction"),                 # 3. direction
            sch.get("origin_station_id"),         # 4. origin_station_id
            sch.get("destination_station_id"),    # 5. destination_station_id
            sch["first_train_time"],              # 6. first_train_time
            sch["last_train_time"],               # 7. last_train_time
            sch["frequency_min"],                 # 8. frequency_min
            stops_json,                           # 9. stops_in_order
            travel_time_json,                     # 10. travel_time_offset
            sch["base_fare_usd"],                 # 11. base_fare_usd
            sch["per_stop_rate_usd"],             # 12. per_stop_rate_usd
            operates_on_str                       # 13. operates_on
        ))

    # 欄位名稱清單完全對齊 schema.sql
    columns = [
        "metro_schedule_id", "line", "direction", 
        "origin_station_id", "destination_station_id",
        "first_train_time", "last_train_time", 
        "frequency_min", "stops_in_order", "travel_time_offset",
        "base_fare_usd", "per_stop_rate_usd", "operates_on"
    ]
    
    n_sch = insert_many(cur, "metro_schedules", columns, rows)
    print(f"  metro_schedules: {n_sch} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    schedules_rows = []
    
    for sch in data:
        # 將陣列與字典轉換為字串
        stops_json = json.dumps(sch.get("stops_in_order", []))
        travel_time_json = json.dumps(sch.get("travel_time_from_origin_min", {}))
        operates_on_str = ",".join(sch.get("operates_on", []))
        
        # 這裡嚴格對齊 20 個值，一個都不能少
        schedules_rows.append((
            sch["schedule_id"],                                   # 1. schedule_id
            sch.get("route_id", f"RT_{sch['schedule_id']}"),      # 2. route_id
            sch.get("line", "NR_LINE"),                           # 3. line
            sch.get("policy_id", "RF001"),                        # 4. policy_id (已更新)
            sch.get("service_type", "normal"),                    # 5. service_type
            sch.get("direction", "northbound"),                   # 6. direction
            sch.get("first_train_time", "06:00:00"),              # 7. departure_time
            sch.get("last_train_time", "23:00:00"),               # 8. arrival_time
            sch.get("origin_station_id"),                         # 9. origin_station_id
            sch.get("destination_station_id"),                    # 10. destination_station_id
            stops_json,                                           # 11. stops_in_order
            None,                                                 # 12. passed_through_stations
            travel_time_json,                                     # 13. travel_time_offset
            sch.get("base_fare_standard", sch.get("base_fare_economy")), # 14. base_fare_standard_usd
            sch.get("per_stop_standard", sch.get("per_stop_economy")),   # 15. per_stop_standard_usd
            sch.get("base_fare_first", sch.get("base_fare_business")),   # 16. base_fare_first_usd
            sch.get("per_stop_first", sch.get("per_stop_business")),     # 17. per_stop_first_usd
            sch.get("frequency_min"),                             # 18. frequency_min
            operates_on_str,                                      # 19. operates_on
            sch.get("overnight_flag", False)                      # 20. overnight_flag
        ))

    # 宣告 20 個欄位名稱
    columns = [
        "schedule_id", "route_id", "line", "policy_id", "service_type", 
        "direction", "departure_time", "arrival_time", "origin_station_id", "destination_station_id",
        "stops_in_order", "passed_through_stations", "travel_time_offset",
        "base_fare_standard_usd", "per_stop_standard_usd",
        "base_fare_first_usd", "per_stop_first_usd", 
        "frequency_min", "operates_on", "overnight_flag"
    ]
    
    n_sch = insert_many(cur, "schedules", columns, schedules_rows)
    print(f"  schedules: {n_sch} rows")
    
    
def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    
    coaches_rows = []
    seats_rows = []
    
    for layout in data:
        schedule_id = layout["schedule_id"]
        
        # 1. 攤平車廂 (Coaches)
        # 使用 enumerate 來產生車廂編號 (coach_number)，從 1 開始
        for c_idx, coach_data in enumerate(layout.get("coaches", []), start=1):
            coach_letter = coach_data["coach"]
            
            # 自行組合一個全局唯一的 coach_id (例如: NR_SCH01_A)
            coach_id = f"{schedule_id}_{coach_letter}"
            
            coaches_rows.append((
                coach_id,
                schedule_id,
                c_idx,                    # 對應 coach_number
                coach_data["fare_class"]
            ))
            
            # 2. 攤平座位 (Seats)
            for seat in coach_data.get("seats", []):
                seat_id = seat["seat_id"]
                
                # 關鍵：組合出 bookings 認得的 seat_real_id
                seat_real_id = f"{schedule_id}_{coach_letter}_{seat_id}"
                
                seats_rows.append((
                    seat_real_id,
                    coach_id,
                    seat_id,
                    seat["row"],
                    seat["column"],
                    False # is_booked (預設為未訂位)
                ))

    # 寫入車廂表
    n_coaches = insert_many(
        cur, 
        "rail_coaches", 
        ["coach_id", "schedule_id", "coach_number", "fare_class"], 
        coaches_rows
    )
    print(f"  rail_coaches: {n_coaches} rows")
    
    # 寫入座位表
    n_seats = insert_many(
        cur, 
        "rail_seats", 
        ["seat_real_id", "coach_id", "seat_id", "seat_row", "seat_column", "is_booked"], 
        seats_rows
    )
    print(f"  rail_seats: {n_seats} rows")
    

def seed_refund_policies(cur):
    data = load("refund_policy.json")
    policies_rows = []
    windows_rows = []
    comp_rows = []

    for p in data:
        policy_id = p["policy_id"]
        
        # 處理 service_type: 同學的 Schema 限制只能是 'normal' 或是 'express'
        svc_type = p.get("applies_to", {}).get("service_type", "normal")
        if svc_type not in ["normal", "express"]:
            svc_type = "normal"
            
        # 計算不可退票的分鐘數 (推算如果 refund_percent == 0 的最長視窗)
        no_refund_min = 0
        for w in p.get("cancellation_windows", []):
            if w.get("refund_percent") == 0 and w.get("hours_before_departure_max"):
                no_refund_min = int(w.get("hours_before_departure_max") * 60)
        
        policies_rows.append((
            policy_id,
            svc_type,
            p["label"],
            no_refund_min,
            None, # effective_from
            None  # effective_until
        ))
        
        # 子表 1: 取消與退款視窗 (cancellation_windows)
        for idx, w in enumerate(p.get("cancellation_windows", []), start=1):
            windows_rows.append((
                w["window_id"],
                policy_id,
                w["label"],
                w.get("hours_before_departure_min", 0.0),
                w.get("hours_before_departure_max"),
                w["refund_percent"],
                w.get("admin_fee_usd", 0.00),
                idx # sort_order
            ))
        
        # 子表 2: 延誤補償規則 (compensation_rules)
        for c in p.get("compensation_rules", []):
            # 簡單判斷 JSON 內的延誤條件
            delay_min = 30 if "30" in c.get("condition", "") else (60 if "60" in c.get("condition", "") else 120)
            comp_pct = 50 if "50%" in c.get("compensation", "") else 100
            
            comp_rows.append((
                c["rule_id"],
                policy_id,
                "delay", # trigger_type 限制
                delay_min,
                comp_pct,
                "refund", # compensation_type 限制
                c["condition"]
            ))

    n_pol = insert_many(cur, "refund_policies", ["policy_id", "service_type", "policy_name", "no_refund_before_departure_min", "effective_from", "effective_until"], policies_rows)
    print(f"  refund_policies: {n_pol} rows")
    
    n_win = insert_many(cur, "refund_cancellation_windows", ["window_id", "policy_id", "window_label", "hours_before_departure_min", "hours_before_departure_max", "refund_percent", "processing_fee_usd", "sort_order"], windows_rows)
    print(f"  refund_cancellation_windows: {n_win} rows")
    
    n_comp = insert_many(cur, "refund_compensation_rules", ["compensation_id", "policy_id", "trigger_type", "delay_minutes_threshold", "compensation_percent", "compensation_type", "description"], comp_rows)
    print(f"  refund_compensation_rules: {n_comp} rows")
    
    

def seed_users(cur):
    data = load("registered_users.json")
    
    users_rows = []
    credentials_rows = []
    
    for u in data:
        # 擷取 email 前半段作為 username
        username = u["email"].split("@")[0]
        
        # 1. 準備 users 表資料
        users_rows.append((
            u["user_id"],
            username,
            u["email"],
            u["full_name"],
            u["date_of_birth"],
            u["phone"],
            u["secret_question"],
            u["registered_at"],
            u["is_active"]
        ))
        
        # 2. 準備 user_credentials 表資料 (不帶 salt 欄位)
        pwd_hash = hashlib.sha256(u["password"].encode('utf-8')).hexdigest()
        ans_hash = hashlib.sha256(u["secret_answer"].encode('utf-8')).hexdigest()
        
        credentials_rows.append((
            u["user_id"],
            pwd_hash,
            ans_hash
        ))

    # 執行寫入主表
    n_users = insert_many(
        cur, 
        "users", 
        ["user_id", "username", "email", "full_name", "date_of_birth", "phone", "secret_question", "registered_at", "is_active"], 
        users_rows
    )
    print(f"  users: {n_users} rows")
    
    # 執行寫入憑證表（這裡絕對不能出現 "password_salt"）
    n_creds = insert_many(
        cur, 
        "user_credentials", 
        ["user_id", "password_hash", "secret_answer_hash"], 
        credentials_rows
    )
    print(f"  user_credentials: {n_creds} rows")

def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = []
    
    for b in data:
        # 即使同學的表不存 coach 和 seat_id，我們依然可以用 JSON 裡的這兩個欄位
        # 來幫忙組合出正確的 seat_real_id 寫入資料庫
        seat_real_id = b.get("seat_real_id")
        if not seat_real_id and "schedule_id" in b and "coach" in b and "seat_id" in b:
            seat_real_id = f"{b['schedule_id']}_{b['coach']}_{b['seat_id']}"
            
        # 拿掉 b["coach"] 和 b["seat_id"]，對齊同學的 15 個欄位
        rows.append((
            b["booking_id"],
            b["user_id"],
            b["schedule_id"],
            b["origin_station_id"],
            b["destination_station_id"],
            b["travel_date"],
            b["departure_time"],
            b["ticket_type"],
            b["fare_class"],
            seat_real_id,             # 直接對應複合外鍵
            b["stops_travelled"],
            b["amount_usd"],
            b["status"],
            b["booked_at"],
            b.get("travelled_at")
        ))

    # 100% 對齊 schema.sql 中實際存在的 15 個欄位
    columns = [
        "booking_id", 
        "user_id", 
        "schedule_id", 
        "origin_station_id", 
        "destination_station_id",
        "travel_date", 
        "departure_time", 
        "ticket_type", 
        "fare_class", 
        "seat_real_id", 
        "stops_travelled", 
        "amount_usd", 
        "status",
        "booked_at", 
        "travelled_at"
    ]
    
    n_bookings = insert_many(cur, "bookings", columns, rows)
    print(f"  bookings: {n_bookings} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    rows = []
    
    for t in data:
        rows.append((
            t["trip_id"],
            t["user_id"],
            t.get("schedule_id"),         # JSON 裡叫 schedule_id，對接 schema 的 metro_schedule_id
            t.get("origin_station_id"),
            t.get("destination_station_id"),
            t["travel_date"],
            t["ticket_type"],
            t.get("day_pass_ref"),        # 購買一日票後的搭乘紀錄會用到
            t.get("stops_travelled"),
            t["amount_usd"],
            t["status"],
            t.get("purchased_at"),
            t.get("travelled_at")
        ))

    # 完全對齊 schema.sql 中 metro_travel_history 的 13 個欄位
    columns = [
        "trip_id", 
        "user_id", 
        "metro_schedule_id", 
        "origin_station_id", 
        "destination_station_id",
        "travel_date", 
        "ticket_type", 
        "day_pass_ref", 
        "stops_travelled", 
        "amount_usd", 
        "status",
        "purchased_at", 
        "travelled_at"
    ]
    
    n_travels = insert_many(cur, "metro_travel_history", columns, rows)
    print(f"  metro_travel_history: {n_travels} rows")


def seed_payments(cur):
    data = load("payments.json")
    rows = []
    
    for p in data:
        # 🛡️ 防禦地雷 1：過濾非 BK 開頭的 booking_id，避免違反外鍵約束
        b_id = p.get("booking_id")
        if b_id and not b_id.startswith("BK"):
            b_id = None  # 讓地鐵的付款紀錄 booking_id 留空 (NULL)
            
        # 🛡️ 防禦地雷 2：補足 JSON 缺少的 NOT NULL 欄位 payment_type
        payment_type = "purchase"
        
        # 對齊 schema.sql 中 payments 表的 9 個欄位
        rows.append((
            p["payment_id"],
            b_id,
            p["amount_usd"],
            payment_type,                # 補上的必填欄位
            p["method"],
            p["status"],
            p.get("paid_at"),
            None,                        # parent_payment_id (預設為空)
            None                         # refunded_amount (預設為空)
        ))

    columns = [
        "payment_id", 
        "booking_id", 
        "amount_usd", 
        "payment_type", 
        "method", 
        "status", 
        "paid_at", 
        "parent_payment_id", 
        "refunded_amount"
    ]
    
    n_payments = insert_many(cur, "payments", columns, rows)
    print(f"  payments: {n_payments} rows")


def seed_feedback(cur):
    data = load("feedback.json")
    rows = []
    
    for f in data:
        # 🛡️ 防禦地雷 1：過濾非 BK 開頭的 booking_id，避免違反外鍵約束
        b_id = f.get("booking_id")
        if not b_id or not b_id.startswith("BK"):
            # 如果是地鐵的評價或其他無效 ID，我們直接跳過不寫入
            continue 
            
        # 🛡️ 防禦地雷 2：確保 rating 嚴格落在 1~5 之間，配合 CHECK 限制
        rating = f.get("rating", 5)
        if rating < 1: rating = 1
        if rating > 5: rating = 5
        
        rows.append((
            f["feedback_id"],
            b_id,
            f["user_id"],
            rating,
            f.get("comment"),
            f["submitted_at"]
        ))

    columns = [
        "feedback_id", 
        "booking_id", 
        "user_id", 
        "rating", 
        "comment", 
        "submitted_at"
    ]
    
    n_fb = insert_many(cur, "feedback", columns, rows)
    print(f"  feedback: {n_fb} rows")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_metro_stations(cur)            #完成
        seed_national_rail_stations(cur)    #完成
        seed_refund_policies(cur)           #完成 
        seed_metro_schedules(cur)           #完成
        seed_national_rail_schedules(cur)   #完成
        seed_seat_layouts(cur)              #完成
        seed_users(cur)                     #完成
        seed_national_rail_bookings(cur)    #完成
        seed_metro_travels(cur)             #完成       
        seed_payments(cur)                  #完成
        seed_feedback(cur)                  #完成
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()