"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
from argon2 import PasswordHasher
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
            ",".join(s.get("lines", [])),  
            s["is_interchange_metro"],
            ",".join(s.get("interchange_metro_lines", [])), 
            s["is_interchange_national_rail"],
            s.get("interchange_national_rail_station_id")
        ))

    # Insert 7 columns directly into the main table
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
            ",".join(s.get("lines", [])),
            s["is_interchange_national_rail"],
            ",".join(s.get("interchange_national_rail_lines", [])),
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
    sched_rows = []
    stops_rows = []
    
    for sch in data:
        operates_on_str = ",".join(sch.get("operates_on", []))
        sched_id = sch["schedule_id"]
        
        # 1. Collect master table rows (11 columns matching schema perfectly)
        sched_rows.append((
            sched_id,                             # metro_schedule_id
            sch["line"],                          # line
            sch.get("direction"),                 # direction
            sch.get("origin_station_id"),         # origin_station_id
            sch.get("destination_station_id"),    # destination_station_id
            sch["first_train_time"],              # first_train_time
            sch["last_train_time"],               # last_train_time
            sch["frequency_min"],                 # frequency_min
            sch["base_fare_usd"],                 # base_fare_usd
            sch["per_stop_rate_usd"],             # per_stop_rate_usd
            operates_on_str                       # operates_on
        ))
        
        # 2. Flatten JSON array and dictionary into rows for junction table
        stops_list = sch.get("stops_in_order", [])
        offsets_dict = sch.get("travel_time_from_origin_min", {})
        
        for idx, station_id in enumerate(stops_list, start=1):
            offset = offsets_dict.get(station_id, 0)
            stops_rows.append((
                sched_id,
                station_id,
                idx,  # stop_order (1=Origin, 2=Next...)
                offset
            ))

    columns = [
        "metro_schedule_id", "line", "direction", 
        "origin_station_id", "destination_station_id",
        "first_train_time", "last_train_time", 
        "frequency_min", "base_fare_usd", "per_stop_rate_usd", "operates_on"
    ]
    n_sch = insert_many(cur, "metro_schedules", columns, sched_rows)
    print(f"  metro_schedules: {n_sch} rows")
    
    stop_columns = ["metro_schedule_id", "station_id", "stop_order", "travel_time_offset"]
    n_stops = insert_many(cur, "metro_schedule_stops", stop_columns, stops_rows)
    print(f"  metro_schedule_stops: {n_stops} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    schedules_rows = []
    stops_rows = []
    
    for sch in data:
        operates_on_str = ",".join(sch.get("operates_on", []))
        sched_id = sch["schedule_id"]
        
        # Extract fares from fare_classes
        fares = sch.get("fare_classes", {})
        standard_fare = fares.get("standard", fares.get("economy", {}))
        first_fare = fares.get("first", fares.get("business", {}))

        # 1. Collect master table rows (17 columns matching normalized schema)
        schedules_rows.append((
            sched_id,                                   # 1. schedule_id
            sch.get("route_id", f"RT_{sched_id}"),      # 2. route_id
            sch.get("line", "NR_LINE"),                           # 3. line
            sch.get("policy_id", "RF001"),                        # 4. policy_id
            sch.get("service_type", "normal"),                    # 5. service_type
            sch.get("direction", "northbound"),                   # 6. direction
            sch.get("first_train_time", "06:00:00"),              # 7. departure_time
            sch.get("last_train_time", "23:00:00"),               # 8. arrival_time
            sch.get("origin_station_id"),                         # 9. origin_station_id
            sch.get("destination_station_id"),                    # 10. destination_station_id
            standard_fare.get("base_fare_usd", 0.0),              # 11. base_fare_standard_usd
            standard_fare.get("per_stop_rate_usd", 0.0),          # 12. per_stop_standard_usd
            first_fare.get("base_fare_usd", 0.0),                 # 13. base_fare_first_usd
            first_fare.get("per_stop_rate_usd", 0.0),             # 14. per_stop_first_usd
            sch.get("frequency_min"),                             # 15. frequency_min
            operates_on_str,                                      # 16. operates_on
            sch.get("overnight_flag", False)                      # 17. overnight_flag
        ))
        
        # 2. Flatten JSON array and dictionary into rows for national rail stops
        stops_list = sch.get("stops_in_order", [])
        offsets_dict = sch.get("travel_time_from_origin_min", {})
        
        for idx, station_id in enumerate(stops_list, start=1):
            offset = offsets_dict.get(station_id, 0)
            stops_rows.append((
                sched_id,
                station_id,
                idx,  # stop_order
                offset,
                False # is_pass_through defaults to False
            ))

    columns = [
        "schedule_id", "route_id", "line", "policy_id", "service_type", 
        "direction", "departure_time", "arrival_time", "origin_station_id", "destination_station_id",
        "base_fare_standard_usd", "per_stop_standard_usd",
        "base_fare_first_usd", "per_stop_first_usd", 
        "frequency_min", "operates_on", "overnight_flag"
    ]
    n_sch = insert_many(cur, "schedules", columns, schedules_rows)
    print(f"  schedules: {n_sch} rows")
    
    stop_columns = ["schedule_id", "station_id", "stop_order", "travel_time_offset", "is_pass_through"]
    n_stops = insert_many(cur, "national_rail_schedule_stops", stop_columns, stops_rows)
    print(f"  national_rail_schedule_stops: {n_stops} rows")
    
    
def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    coaches_rows = []
    seats_rows = []
    
    for layout in data:
        schedule_id = layout["schedule_id"]
        
        for c_idx, coach_data in enumerate(layout.get("coaches", []), start=1):
            coach_letter = coach_data["coach"]
            
            # Generate a globally unique coach_id
            coach_id = f"{schedule_id}_{coach_letter}"
            
            coaches_rows.append((
                coach_id,
                schedule_id,
                c_idx,                    
                coach_data["fare_class"]
            ))
            
            for seat in coach_data.get("seats", []):
                seat_id = seat["seat_id"]
                
                # Critical: Construct the unique seat_real_id recognized by bookings
                seat_real_id = f"{schedule_id}_{coach_letter}_{seat_id}"
                
                seats_rows.append((
                    seat_real_id,
                    coach_id,
                    seat_id,
                    seat["row"],
                    seat["column"],
                    False 
                ))

    n_coaches = insert_many(
        cur, 
        "rail_coaches", 
        ["coach_id", "schedule_id", "coach_number", "fare_class"], 
        coaches_rows
    )
    print(f"  rail_coaches: {n_coaches} rows")
    
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
        
        # Handle service_type validation against check constraints
        svc_type = p.get("applies_to", {}).get("service_type", "normal")
        if svc_type not in ["normal", "express"]:
            svc_type = "normal"
            
        # Calculate no-refund minutes based on cancellation windows
        no_refund_min = 0
        for w in p.get("cancellation_windows", []):
            if w.get("refund_percent") == 0 and w.get("hours_before_departure_max"):
                no_refund_min = int(w.get("hours_before_departure_max") * 60)
        
        policies_rows.append((
            policy_id,
            svc_type,
            p["label"],
            no_refund_min,
            None, 
            None  
        ))
        
        # Child table 1: Cancellation and refund windows
        for idx, w in enumerate(p.get("cancellation_windows", []), start=1):
            windows_rows.append((
                w["window_id"],
                policy_id,
                w["label"],
                w.get("hours_before_departure_min", 0.0),
                w.get("hours_before_departure_max"),
                w["refund_percent"],
                w.get("admin_fee_usd", 0.00),
                idx 
            ))
        
        # Child table 2: Delay compensation rules
        for c in p.get("compensation_rules", []):
            delay_min = 30 if "30" in c.get("condition", "") else (60 if "60" in c.get("condition", "") else 120)
            comp_pct = 50 if "50%" in c.get("compensation", "") else 100
            
            comp_rows.append((
                c["rule_id"],
                policy_id,
                "delay", 
                delay_min,
                comp_pct,
                "refund", 
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
    
    ph = PasswordHasher()
    
    for u in data:
        # Extract username from the prefix of email
        username = u["email"].split("@")[0]
        
        # 1. Prepare users table data (excluding sensitive credentials)
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
        
        # 2. Prepare user_credentials table data
        # 🔒 Securely hash sensitive data using Argon2id with automatic salting
        pwd_hash = ph.hash(u["password"])
        ans_hash = ph.hash(u["secret_answer"])
        
        credentials_rows.append((
            u["user_id"],
            pwd_hash,
            ans_hash
        ))

    n_users = insert_many(
        cur, 
        "users", 
        ["user_id", "username", "email", "full_name", "date_of_birth", "phone", "secret_question", "registered_at", "is_active"], 
        users_rows
    )
    print(f"  users: {n_users} rows")
    
    n_creds = insert_many(
        cur, 
        "user_credentials", 
        ["user_id", "password_hash", "secret_answer_hash"], 
        credentials_rows
    )
    print(f"  user_credentials (Argon2id secured): {n_creds} rows")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = []
    
    for b in data:
        # Construct seat_real_id even if standalone fields are omitted
        seat_real_id = b.get("seat_real_id")
        if not seat_real_id and "schedule_id" in b and "coach" in b and "seat_id" in b:
            seat_real_id = f"{b['schedule_id']}_{b['coach']}_{b['seat_id']}"
            
        # Align fields to match the 15-column schema structure
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
            seat_real_id,             
            b["stops_travelled"],
            b["amount_usd"],
            b["status"],
            b["booked_at"],
            b.get("travelled_at")
        ))

    # 100% aligned with the 15 columns in schema.sql
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
            t.get("schedule_id"),         
            t.get("origin_station_id"),
            t.get("destination_station_id"),
            t["travel_date"],
            t["ticket_type"],
            t.get("day_pass_ref"),        
            t.get("stops_travelled"),
            t["amount_usd"],
            t["status"],
            t.get("purchased_at"),
            t.get("travelled_at")
        ))

    # Fully aligned with the 13 columns in metro_travel_history
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
        # 🛡️ Shield 1: Filter out non-BK booking IDs to prevent FK constraint violations
        b_id = p.get("booking_id")
        if b_id and not b_id.startswith("BK"):
            b_id = None  
            
        # 🛡️ Shield 2: Supply missing NOT NULL field values
        payment_type = "purchase"
        
        rows.append((
            p["payment_id"],
            b_id,
            p["amount_usd"],
            payment_type,                
            p["method"],
            p["status"],
            p.get("paid_at"),
            None,                        
            None                         
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
        # 🛡️ Shield 1: Filter out non-BK booking IDs to prevent FK constraint violations
        b_id = f.get("booking_id")
        if not b_id or not b_id.startswith("BK"):
            continue 
            
        # 🛡️ Shield 2: Enforce rating range between 1 and 5 to satisfy CHECK constraint
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
        seed_metro_stations(cur)            
        seed_national_rail_stations(cur)    
        seed_refund_policies(cur)            
        seed_metro_schedules(cur)           
        seed_national_rail_schedules(cur)   
        seed_seat_layouts(cur)              
        seed_users(cur)                     
        seed_national_rail_bookings(cur)    
        seed_metro_travels(cur)                    
        seed_payments(cur)                  
        seed_feedback(cur)                  
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