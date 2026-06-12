import sys
import json
from datetime import datetime

sys.path.insert(0, ".")

def print_result(name, res):
    print(f"=== {name} ===")
    try:
        if isinstance(res, list) and len(res) > 3:
            print(json.dumps(res[:3], default=str, indent=2))
            print(f"... (and {len(res) - 3} more items)")
        else:
            print(json.dumps(res, default=str, indent=2))
    except Exception as e:
        print(f"Result: {res}")
    print("\n")

try:
    print("Loading Relational Queries...")
    from databases.relational.queries import (
        query_national_rail_availability,
        query_metro_schedules,
        query_national_rail_fare,
        query_metro_fare,
        query_available_seats,
        query_user_profile,
        query_user_bookings,
        query_payment_info,
        execute_booking,
        execute_cancellation
    )

    print_result("B1: National Rail Availability (NR01->NR05)", query_national_rail_availability(origin_id="NR01", destination_id="NR05", travel_date="2026-06-01"))
    print_result("B2: Metro Schedules (MS01->MS09)", query_metro_schedules(origin_id="MS01", destination_id="MS09"))
    
    print_result("B3: National Rail Fare (NR_SCH01, standard, 4 stops)", query_national_rail_fare(schedule_id="NR_SCH01", fare_class="standard", stops_travelled=4))
    print_result("B4: Metro Fare (M1_N, 4 stops)", query_metro_fare(schedule_id="M1_N", stops_travelled=4))
    
    print_result("B5: Available Seats (NR_SCH01, 2026-06-01)", query_available_seats(schedule_id="NR_SCH01", travel_date="2026-06-01", fare_class="standard"))
    
    # We will test an unknown email to ensure it returns None without crashing
    print_result("B6: User Profile (Unknown)", query_user_profile("unknown@test.com"))
    print_result("B7: User Bookings (Unknown)", query_user_bookings("unknown@test.com"))
    
    print("Testing Booking (B9)...")
    success, result = execute_booking(
        user_id="RU01",
        schedule_id="NR_SCH01",
        origin_station_id="NR01",
        destination_station_id="NR05",
        travel_date="2026-06-01",
        fare_class="standard",
        seat_id="any",
    )
    print_result("B9: Execute Booking", {"success": success, "result": result})

    if success:
        b_id = result.get("booking_id")
        print("Testing Cancellation (B10)...")
        c_success, c_result = execute_cancellation(booking_id=b_id, user_id="RU01")
        print_result("B10: Execute Cancellation", {"success": c_success, "result": c_result})
    
    print("Loading Graph Queries...")
    from databases.graph.queries import (
        query_shortest_route,
        query_cheapest_route,
        query_alternative_routes,
        query_interchange_path,
        query_delay_ripple,
        query_station_connections
    )

    print_result("C1: Shortest Route (MS01->MS14)", query_shortest_route("MS01", "MS14"))
    print_result("C2: Cheapest Route (MS01->MS14)", query_cheapest_route("MS01", "MS14"))
    print_result("C3: Alternative Routes (NR01->NR05 avoiding NR03)", query_alternative_routes("NR01", "NR05", avoid_station_id="NR03"))
    print_result("C4: Interchange Path (MS01->NR05)", query_interchange_path("MS01", "NR05"))
    print_result("C5: Delay Ripple (MS01, 2 hops)", query_delay_ripple("MS01", 2))
    print_result("C6: Station Connections (MS01)", query_station_connections("MS01"))

except Exception as e:
    import traceback
    traceback.print_exc()
