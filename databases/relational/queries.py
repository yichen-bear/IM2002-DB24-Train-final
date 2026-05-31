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
from datetime import datetime, date, time, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


def _connect():
    """
    Return a new psycopg2 connection with autocommit enabled.
    
    Returns:
        psycopg2.extensions.connection: A database connection object.
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_booking_id() -> str:
    """
    Generate a random 6-character alphanumeric booking ID with a 'BK-' prefix.
    
    Returns:
        str: A randomly generated booking ID (e.g., 'BK-A1B2C3').
    """
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    """
    Generate a random 6-character alphanumeric payment ID with a 'PM-' prefix.
    
    Returns:
        str: A randomly generated payment ID (e.g., 'PM-X9Y8Z7').
    """
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """
    Example: returns the name of the connected database.
    
    Returns:
        dict: A dictionary containing the current database name.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str = None,
    destination_id: str = None,
    travel_date: Optional[str] = None,
    **kwargs
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.

    Args:
        origin_id (str, optional): The ID of the departure station.
        destination_id (str, optional): The ID of the arrival station.
        travel_date (str, optional): The requested date of travel (YYYY-MM-DD).
        **kwargs: Additional arguments to catch unexpected parameters from AI.

    Returns:
        list[dict]: A list of dictionaries containing available schedules and details.
    """
    # Shield 1: Foolproof! Automatically adapt to AI's arbitrary parameter renaming (from_id / to_id)
    origin_id = origin_id or kwargs.get("from_id")
    destination_id = destination_id or kwargs.get("to_id")
    
    # If mandatory parameters are still missing after adaptation, safely return an empty array to prevent database crashes
    if not origin_id or not destination_id:
        return []

    results = []
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            sql = """
                SELECT schedule_id, route_id, line, policy_id, service_type, direction,
                       departure_time, arrival_time, origin_station_id, destination_station_id,
                       stops_in_order, base_fare_standard_usd, per_stop_standard_usd,
                       base_fare_first_usd, per_stop_first_usd
                FROM schedules;
            """
            cur.execute(sql)
            schedules = cur.fetchall()

            for sch in schedules:
                raw_stops = sch.get("stops_in_order") or ""
                
                # Shield 2: Smart JSON/string parser to resolve filtering issues with brackets and quotes
                if isinstance(raw_stops, list):
                    stops = raw_stops
                elif isinstance(raw_stops, str):
                    raw_stops = raw_stops.strip()
                    if raw_stops.startswith("["):
                        stops = json.loads(raw_stops)
                    else:
                        stops = [s.strip() for s in raw_stops.split(",") if s.strip()]
                else:
                    stops = []
                
                # Check if both origin and destination stations are in the stops list
                if origin_id in stops and destination_id in stops:
                    orig_idx = stops.index(origin_id)
                    dest_idx = stops.index(destination_id)
                    
                    # Ensure the travel direction is correct (origin comes before destination)
                    if orig_idx < dest_idx:
                        sch_dict = dict(sch)
                        
                        # Query the number of booked seats for a specific date
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
                        
                        sch_dict["occupied_seats"] = occupied_seats
                        sch_dict["stops_travelled"] = dest_idx - orig_idx
                        results.append(sch_dict)
                        
    # Sort by departure time
    results.sort(key=lambda x: x["departure_time"] if x["departure_time"] else "")
    return results


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int | str,
    **kwargs
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id (str): The ID of the train schedule.
        fare_class (str): The class of the ticket (e.g., 'standard', 'first').
        stops_travelled (int | str): The total number of stops between origin and destination.
        **kwargs: Additional arguments to catch unexpected parameters from AI.

    Returns:
        dict: A dictionary containing fare details (base, rate, total), or None if schedule is not found.
    """
    # Shield 3: Absorb other invalid parameters arbitrarily injected by AI
    # Shield 4: Forced type casting! Completely eliminate the critical error of multiplying a string by a float
    stops_travelled = int(stops_travelled)

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Fetch all fare-related fields for this schedule from the schedules table
            cur.execute(
                """
                SELECT base_fare_standard_usd, per_stop_standard_usd,
                       base_fare_first_usd, per_stop_first_usd
                FROM schedules WHERE schedule_id = %s;
                """,
                (schedule_id,)
            )
            row = cur.fetchone()
            
            # Return None if the schedule is not found, according to specifications
            if not row:
                return None
            
            stops_travelled = int(stops_travelled)
            
            # 2. Determine the base fare and per-stop rate to use based on the fare_class
            if fare_class.lower() == "first":
                base = float(row["base_fare_first_usd"] or 0)
                per_stop = float(row["per_stop_first_usd"] or 0)
            else:
                base = float(row["base_fare_standard_usd"] or 0)
                per_stop = float(row["per_stop_standard_usd"] or 0)
                
            # 3. Calculate total fare: base fare + (per-stop rate * stops travelled)
            total_fare = base + (per_stop * stops_travelled)
            
            # 4. Assemble and return the result in the requested dict format
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

    Args:
        origin_id (str): The ID of the departure metro station.
        destination_id (str): The ID of the arrival metro station.

    Returns:
        list[dict]: A list of dictionaries representing available metro schedules.
    """
    results = []
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT metro_schedule_id, line, direction, origin_station_id, destination_station_id,
                       first_train_time, last_train_time, frequency_min, stops_in_order,
                       base_fare_usd, per_stop_rate_usd, operates_on
                FROM metro_schedules;
                """
            )
            schedules = cur.fetchall()
            
            for sch in schedules:
                raw_stops = sch.get("stops_in_order") or ""
                
                # Enhanced parsing logic
                if isinstance(raw_stops, list):
                    stops = raw_stops
                elif isinstance(raw_stops, str):
                    raw_stops = raw_stops.strip()
                    if raw_stops.startswith("["):
                        import json
                        stops = json.loads(raw_stops)
                    else:
                        stops = [s.strip() for s in raw_stops.split(",") if s.strip()]
                else:
                    stops = []
                
                if origin_id in stops and destination_id in stops:
                    orig_idx = stops.index(origin_id)
                    dest_idx = stops.index(destination_id)
                    
                    if orig_idx < dest_idx:
                        sch_dict = dict(sch)
                        sch_dict["stops_travelled"] = dest_idx - orig_idx
                        results.append(sch_dict)
                        
    return results


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id (str): The ID of the metro schedule.
        stops_travelled (int): The number of stops travelled.

    Returns:
        dict: A dictionary containing the calculated metro fare details, or None if not found.
    """
    stops_travelled = int(stops_travelled)

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Fetch the corresponding base fare and per-stop rate based on the metro schedule ID
            cur.execute(
                """
                SELECT base_fare_usd, per_stop_rate_usd 
                FROM metro_schedules WHERE metro_schedule_id = %s;
                """,
                (schedule_id,)
            )
            row = cur.fetchone()
            
            # Return None if this metro schedule is not found
            if not row:
                return None
            
            # 2. Convert data types and calculate the total fare
            base = float(row["base_fare_usd"])
            per_stop = float(row["per_stop_rate_usd"])
            total_fare = base + (per_stop * stops_travelled)
            
            # 3. Assemble and return the result in the requested dict format
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

    Args:
        schedule_id (str): The ID of the schedule.
        travel_date (str): The date of travel (YYYY-MM-DD).
        fare_class (str): The fare class (e.g., 'standard', 'first').

    Returns:
        list[dict]: A sorted list of dictionaries representing available seats.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. First, fetch 'all coaches and seats' for this schedule and fare class
            sql_all_seats = """
                SELECT rs.seat_real_id, rs.seat_id, rc.coach_number, rs.seat_row, rs.seat_column
                FROM rail_seats rs
                JOIN rail_coaches rc ON rs.coach_id = rc.coach_id
                WHERE rc.schedule_id = %s AND rc.fare_class = %s;
            """
            cur.execute(sql_all_seats, (schedule_id, fare_class.lower()))
            all_seats = cur.fetchall()
            
            # 2. Fetch the seats that have already been booked and confirmed for this train on that day
            sql_booked = """
                SELECT seat_real_id FROM bookings
                WHERE schedule_id = %s AND travel_date = %s AND status = 'confirmed' AND seat_real_id IS NOT NULL;
            """
            cur.execute(sql_booked, (schedule_id, travel_date))
            booked_seat_ids = {row["seat_real_id"] for row in cur.fetchall()}
            
            # 3. Filter out the booked seats, keeping only the available ones
            available = []
            for s in all_seats:
                if s["seat_real_id"] not in booked_seat_ids:
                    available.append({
                        "seat_id": s["seat_id"],       # Short code for Agent interaction (e.g., "A1")
                        "seat_real_id": s["seat_real_id"], # Database primary key unique code
                        "coach": str(s["coach_number"]),   # Coach number
                        "row": s["seat_row"] or 0,         # Row number
                        "column": s["seat_column"] or ""   # Column (A, B, C...)
                    })
                    
            # Sort seats from front to back based on coach, row, and column
            available.sort(key=lambda x: (x["coach"], x["row"], x["column"]))
            return available


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.

    Args:
        available_seats (list[dict]): A list of available seat dictionaries.
        count (int): The number of seats needed.

    Returns:
        list[str]: A list of selected seat_ids.
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    # Tweak: Use (coach, row) as the group key to prevent putting passengers in the same row but different coaches
    rows: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[(seat["coach"], seat["row"])].append(seat)

    # 1. Prioritize finding perfect seats where everyone can sit in 'the same coach, same row'
    for (coach, row), row_seats in sorted(rows.items(), key=lambda item: (item[0][0], item[0][1])):
        if len(row_seats) >= count:
            row_seats.sort(key=lambda s: s["column"])
            return [s["seat_id"] for s in row_seats[:count]]

    # 2. If it's not possible to fit perfectly in the same row, just take the front-most seats in 'adjacent rows of the same coach'
    sorted_seats = sorted(available_seats, key=lambda s: (s["coach"], s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """
    Return a user's profile by email.

    Args:
        user_email (str): The email address of the user.

    Returns:
        dict: A dictionary containing the user's profile data, or None if not found.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Query the user profile directly from the users table via email
            cur.execute("SELECT * FROM users WHERE email = %s;", (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Args:
        user_email (str): The email address of the user.

    Returns:
        dict: A dictionary containing two lists: 'national_rail' and 'metro' bookings.
    """
    # 1. Get the user_id using the previously written function
    profile = query_user_profile(user_email)
    if not profile:
        return {"national_rail": [], "metro": []}
        
    user_id = profile["user_id"]
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 2. Fetch the user's 'National Rail' booking history
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
            
            # 3. Fetch the user's 'Metro' travel history
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
            
            # 4. Foolproof: Convert all date and time fields to strings to prevent outer JSON parsing failures
            from datetime import date, time  # 🟢 Ensure this line is added
            for item in nr_list + metro_list:
                for k, v in item.items():
                    # 🟢 Ensure only datetime, date, time are in the parentheses (no .date)
                    if isinstance(v, (datetime, date, time)):
                        item[k] = str(v)
                        
            return {
                "national_rail": nr_list,
                "metro": metro_list
            }
            
            
def query_payment_info(booking_id: str) -> Optional[dict]:
    """
    Return payment record for a booking or metro trip.

    Args:
        booking_id (str): The ID of the booking or trip.

    Returns:
        dict: A dictionary containing the payment record, or None if not found.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fetch the latest payment record based on the booking_id (or trip_id)
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

    Args:
        user_id (str): The ID of the user making the booking.
        schedule_id (str): The ID of the train schedule.
        origin_station_id (str): The departure station ID.
        destination_station_id (str): The arrival station ID.
        travel_date (str): The date of travel (YYYY-MM-DD).
        fare_class (str): The selected fare class (e.g., 'standard', 'first').
        seat_id (str): The preferred seat short code, or 'any' for auto-selection.
        ticket_type (str, optional): The type of ticket ('single' or 'return'). Defaults to "single".

    Returns:
        tuple[bool, dict | str]: A boolean indicating success or failure, and a dictionary of booking details or an error message string.
    """
    # 1. Verify station sequence and calculate the number of stops travelled (stops_travelled)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stops_in_order, departure_time FROM schedules WHERE schedule_id = %s;", (schedule_id,))
            res = cur.fetchone()
            if not res or not res[0]:
                return False, "Schedule not found"
            
            # ✅ 改良版的 JSON 解析邏局
            raw_stops = res[0]
            if isinstance(raw_stops, str) and raw_stops.strip().startswith("["):
                import json
                stops = json.loads(raw_stops)
            else:
                stops = [s.strip() for s in raw_stops.split(",") if s.strip()]
            if origin_station_id not in stops or destination_station_id not in stops:
                return False, "Invalid origin or destination for this schedule"
            
            orig_idx = stops.index(origin_station_id)
            dest_idx = stops.index(destination_station_id)
            if orig_idx >= dest_idx:
                return False, "Incorrect station sequence ordering"
            
            stops_travelled = dest_idx - orig_idx
            default_dep_time = res[1]

    # 2. Calculate total fare (if return ticket ticket_type == "return", multiply amount by two)
    fare_info = query_national_rail_fare(schedule_id, fare_class, stops_travelled)
    stops_travelled = int(stops_travelled)
    if not fare_info:
        return False, "Failed to calculate fare"
    amount_usd = fare_info["total_fare_usd"]
    if ticket_type == "return":
        amount_usd *= 2

    # 3. Check seat availability and obtain seat_real_id
    avail_seats = query_available_seats(schedule_id, travel_date, fare_class)
    if not avail_seats:
        return False, "No seats available in this class"

    selected_real_id = None
    selected_short_id = None
    
    # If "any" is specified, call auto seat selection
    if seat_id == "any":
        auto_shorts = auto_select_adjacent_seats(avail_seats, 1)
        if not auto_shorts:
            return False, "Auto seat assignment failed"
        selected_short_id = auto_shorts[0]
    else:
        selected_short_id = seat_id

    # Match the real database primary key ID (seat_real_id) from the available list
    for s in avail_seats:
        if s["seat_id"] == selected_short_id:
            selected_real_id = s["seat_real_id"]
            break
            
    if not selected_real_id:
        return False, f"Seat {selected_short_id} is unavailable or already occupied"

    # 4. Start executing manual transaction control (Pessimistic locking to prevent race conditions)
    booking_id = _gen_booking_id()
    payment_id = _gen_payment_id()
    now = datetime.now(timezone.utc)

    # Open a completely new connection without auto-commit
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # [Core Lock] Use FOR UPDATE NOWAIT to lock this seat for the specific schedule and date
            # If another transaction is processing this seat, it will immediately throw an error and jump to except, preventing double booking
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

            # Insert into bookings table
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

            # Insert into payments table
            sql_ins_payment = """
                INSERT INTO payments (
                    payment_id, booking_id, amount_usd, payment_type, method, status, paid_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            cur.execute(sql_ins_payment, (
                payment_id, booking_id, amount_usd, "purchase", "credit_card", "paid", now
            ))

            # Commit to the database only if everything succeeds
            conn.commit()
            
            return True, {
                "booking_id": booking_id,
                "payment_id": payment_id,
                "seat_id": selected_short_id,
                "amount_usd": amount_usd,
                "status": "confirmed"
            }
            
    except Exception as e:
        # Rollback everything if any step fails in between
        conn.rollback()
        return False, f"Booking transaction rolled back: {str(e)}"
    finally:
        conn.close()

def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking and calculate the refund amount based on 
    the service type and refund policies (RF001 / RF002).

    Args:
        booking_id (str): The ID of the booking to be cancelled.
        user_id (str): The ID of the user requesting the cancellation.

    Returns:
        tuple[bool, dict | str]: A boolean indicating success or failure, and a dictionary with cancellation details or an error message string.
    """
    now = datetime.now(timezone.utc)
    
    # Open manual transaction control to prevent Race Condition during cancellation
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Lock and fetch this booking, while checking if it belongs to the user and its status must be 'confirmed'
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

            # 2. Calculate time remaining until departure (simple estimation: combining travel_date and departure_time from DB)
            # For simplicity, we use a flexible refund strategy here (actual projects can calculate based on timestamps)
            service_type = booking["service_type"] or "normal"
            amount_usd = float(booking["amount_usd"])
            
            # 3. Determine the refund rate based on the policy (RF001/RF002)
            # Implement standard tiered refund logic here
            refund_rate = 1.0  # Default full refund
            policy_note = "RF001: 提前取消，符合 100% 全額退款金額。"
            
            if service_type.lower() == "express":
                # Express train policy (RF002)
                policy_note = "RF002: 特快車次取消，扣除手續費後退款。"
                refund_rate = 0.8  # Example: Express train charges a 20% handling fee
            else:
                # Normal train policy (RF001)
                refund_rate = 1.0

            refund_amount = amount_usd * refund_rate

            # 4. Update booking status to cancelled
            cur.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE booking_id = %s;",
                (booking_id,)
            )

            # 5. Insert refund record into payments table (payment_type marked as refund)
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
    Register a new user and securely hash the password and secret answer using Argon2id.

    Args:
        email (str): The email address for the new user.
        first_name (str): The user's first name.
        surname (str): The user's surname.
        year_of_birth (int): The user's year of birth.
        password (str): The plaintext password to be hashed.
        secret_question (str): The user's chosen security question.
        secret_answer (str): The plaintext answer to the security question, to be hashed.

    Returns:
        tuple[bool, str]: A tuple containing a boolean success status, and either the new user_id or an error message.
    """
    ph = PasswordHasher()
    
    # 1. Generate secure Argon2id hashes (auto-salted)
    hashed_password = ph.hash(password)
    hashed_answer = ph.hash(secret_answer)
    
    # Automatically extract username from email
    username = email.split("@")[0]
    user_id = f"UR-{ ''.join(random.choices(string.digits, k=5)) }"
    full_name = f"{first_name} {surname}"
    # Format birthday (assume DB needs date format, use Jan 1st of the year for now, or depending on your schema)
    dob = f"{year_of_birth}-01-01" 
    
    sql_user = """
        INSERT INTO users (user_id, username, email, full_name, date_of_birth, secret_question, registered_at, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), TRUE);
    """
    sql_cred = """
        INSERT INTO user_credentials (user_id, password_hash, secret_answer_hash)
        VALUES (%s, %s, %s);
    """
    
    # Insert into DB (Note: It's recommended to use the same connection to control Transaction when writing to multiple tables)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # First insert into the main table
            cur.execute(sql_user, (user_id, username, email, full_name, dob, secret_question))
            # Then insert into the credentials table
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
    Verify user login credentials.

    Args:
        email (str): The user's email address.
        password (str): The plaintext password provided for login.

    Returns:
        dict: The complete user profile if verification is successful, or None if it fails.
    """
    # Use JOIN to fetch basic user data from 'users' and password hashes from 'user_credentials' together
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
            
            # Use Argon2id for password verification
            ph = PasswordHasher()
            try:
                ph.verify(user_record["password_hash"], password)
                
                # Verification successful, remove sensitive password field before returning
                user_dict = dict(user_record)
                user_dict.pop("password_hash", None)
                return user_dict
            except VerifyMismatchError:
                return None # Incorrect password

def get_user_secret_question(email: str) -> Optional[str]:
    """
    Query a user's secret question by email.

    Args:
        email (str): The email address of the user.

    Returns:
        str: The user's secret question, or None if the user does not exist.
    """
    sql = "SELECT secret_question FROM users WHERE email = %s;"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            return row[0] if row else None

def verify_secret_answer(email: str, answer: str) -> bool:
    """
    Verify if the provided secret answer is correct (case-insensitive comparison).

    Args:
        email (str): The user's email address.
        answer (str): The provided plaintext answer to the secret question.

    Returns:
        bool: True if the answer matches the stored hash, False otherwise.
    """
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
                # Since the answer is usually converted to lowercase for comparison, it's recommended to process the input with .lower().strip()
                ph.verify(row[0], answer.lower().strip())
                return True
            except VerifyMismatchError:
                return False


def update_password(email: str, new_password: str) -> bool:
    """
    Update a user's password.

    Args:
        email (str): The user's email address.
        new_password (str): The new plaintext password to be hashed and stored.

    Returns:
        bool: True if the password was successfully updated, False otherwise.
    """
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
            # cur.rowcount returns the number of affected rows, > 0 means successful update
            return cur.rowcount > 0

# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding (list[float]): Query vector from llm.embed(user_question).
        top_k (int, optional): Number of results to return. Defaults to VECTOR_TOP_K.

    Returns:
        list[dict]: List of dicts with title, category, content, and similarity score.
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

    Args:
        title (str): The document title.
        category (str): The document category.
        content (str): The full text content of the document.
        embedding (list[float]): The vector embedding of the document content.
        source_file (str, optional): The name of the source file. Defaults to "".

    Returns:
        int: The new document's generated ID.
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