erDiagram
    %% ============================================================
    %% Volume 1: Security & Users
    %% ============================================================
    users ||--|| user_credentials : "has security hash (1:1)"
    users {
        varchar32 user_id PK
        varchar50 username UK
        varchar100 email UK
        varchar100 full_name
        date date_of_birth
        varchar20 phone
        varchar255 secret_question
        timestamp registered_at
        boolean is_active
    }
    user_credentials {
        varchar32 user_id PK, FK
        text password_hash
        text secret_answer_hash
    }

    %% ============================================================
    %% Volume 5: Stations & Topology
    %% ============================================================
    metro_stations ||--o{ station_adjacencies : "acts as source/adjacent"
    national_rail_stations ||--o{ station_adjacencies : "acts as source/adjacent"
    
    metro_stations {
        varchar32 station_id PK
        varchar100 name
        varchar255 lines
        boolean is_interchange_metro
        varchar255 interchange_metro_lines
        boolean is_interchange_national_rail
        varchar32 interchange_national_rail_station_id
    }
    national_rail_stations {
        varchar32 station_id PK
        varchar100 name
        varchar255 lines
        boolean is_interchange_national_rail
        varchar255 interchange_national_rail_lines
        boolean is_interchange_metro
        varchar32 interchange_metro_station_id
    }
    station_adjacencies {
        varchar32 source_station_id PK
        varchar32 adjacent_station_id PK
        varchar20 network_type PK
        varchar50 line
        int travel_time_min
    }

    %% ============================================================
    %% Volume 7: Refund Policies
    %% ============================================================
    refund_policies ||--o{ refund_cancellation_windows : "defines tiers"
    refund_policies ||--o{ refund_compensation_rules : "defines triggers"
    refund_policies ||--o{ schedules : "applies to"

    refund_policies {
        varchar32 policy_id PK
        varchar20 service_type
        varchar100 policy_name
        int no_refund_before_departure_min
        date effective_from
        date effective_until
        timestamp created_at
    }
    refund_cancellation_windows {
        varchar32 window_id PK
        varchar32 policy_id FK
        varchar100 window_label
        decimal hours_before_departure_min
        decimal hours_before_departure_max
        decimal refund_percent
        decimal processing_fee_usd
        int sort_order
    }
    refund_compensation_rules {
        varchar32 compensation_id PK
        varchar32 policy_id FK
        varchar30 trigger_type
        int delay_minutes_threshold
        decimal compensation_percent
        varchar20 compensation_type
        text description
    }

    %% ============================================================
    %% Volume 2: Networks & Assets (Normalized with Stop Tables)
    %% ============================================================
    national_rail_stations ||--o{ schedules : "origin"
    national_rail_stations ||--o{ schedules : "destination"
    schedules ||--o{ rail_coaches : "has"
    rail_coaches ||--o{ rail_seats : "contains"

    schedules {
        varchar32 schedule_id PK
        varchar32 route_id
        varchar50 line
        varchar32 policy_id FK
        varchar20 service_type
        varchar20 direction
        time departure_time
        time arrival_time
        varchar32 origin_station_id FK
        varchar32 destination_station_id FK
        decimal base_fare_standard_usd
        decimal per_stop_standard_usd
        decimal base_fare_first_usd
        decimal per_stop_first_usd
        int frequency_min
        varchar100 operates_on
        boolean overnight_flag
    }

    %% 正規化新增：火車班次停靠細節（解構多值欄位）
    schedules ||--o{ national_rail_schedule_stops : "has stop details"
    national_rail_stations ||--o{ national_rail_schedule_stops : "is stopping at"

    national_rail_schedule_stops {
        varchar32 schedule_id PK, FK
        varchar32 station_id PK, FK
        int stop_sequence
        int travel_time_offset_min
    }
    
    metro_stations ||--o{ metro_schedules : "origin"
    metro_stations ||--o{ metro_schedules : "destination"
    
    metro_schedules {
        varchar32 metro_schedule_id PK
        varchar50 line
        varchar20 direction
        varchar32 origin_station_id FK
        varchar32 destination_station_id FK
        time first_train_time
        time last_train_time
        int frequency_min
        decimal base_fare_usd
        decimal per_stop_rate_usd
        varchar100 operates_on
    }

    %% 正規化新增：捷運班次停靠細節（解構多值欄位）
    metro_schedules ||--o{ metro_schedule_stops : "has stop details"
    metro_stations ||--o{ metro_schedule_stops : "is stopping at"

    metro_schedule_stops {
        varchar32 metro_schedule_id PK, FK
        varchar32 station_id PK, FK
        int stop_sequence
        int travel_time_offset_min
    }

    rail_coaches {
        varchar32 coach_id PK
        varchar32 schedule_id FK
        int coach_number
        varchar20 fare_class
    }
    rail_seats {
        varchar64 seat_real_id PK
        varchar32 coach_id FK
        varchar10 seat_id
        int seat_row
        varchar5 seat_column
        boolean is_booked
    }

    %% ============================================================
    %% Volume 6: History, Bookings & Feedback
    %% ============================================================
    users ||--o{ bookings : "places"
    schedules ||--o{ bookings : "reserved for"
    national_rail_stations ||--o{ bookings : "origin"
    national_rail_stations ||--o{ bookings : "destination"
    rail_seats ||--o{ bookings : "assigned"
    bookings ||--o{ feedback : "receives"
    users ||--o{ feedback : "writes"

    bookings {
        varchar32 booking_id PK
        varchar32 user_id FK
        varchar32 schedule_id FK
        varchar32 origin_station_id FK
        varchar32 destination_station_id FK
        date travel_date
        time departure_time
        varchar20 ticket_type
        varchar20 fare_class
        varchar64 seat_real_id FK
        int stops_travelled
        decimal amount_usd
        varchar20 status
        timestamp booked_at
        timestamp travelled_at
    }
    feedback {
        varchar32 feedback_id PK
        varchar32 booking_id FK
        varchar32 user_id FK
        int rating
        text comment
        timestamp submitted_at
    }

    users ||--o{ metro_travel_history : "undertakes"
    metro_schedules ||--o{ metro_travel_history : "referenced in"
    metro_stations ||--o{ metro_travel_history : "origin"
    metro_stations ||--o{ metro_travel_history : "destination"

    metro_travel_history {
        varchar32 trip_id PK
        varchar32 user_id FK
        varchar32 metro_schedule_id FK
        varchar32 origin_station_id FK
        varchar32 destination_station_id FK
        date travel_date
        varchar20 ticket_type
        varchar32 day_pass_ref
        int stops_travelled
        decimal amount_usd
        varchar20 status
        timestamp purchased_at
        timestamp travelled_at
    }

    %% ============================================================
    %% Volume 3 & 4: Payments & Telemetry Logs
    %% ============================================================
    bookings ||--o{ payments : "settles"
    payments ||--o{ payments : "refund parent link (1:N)"

    payments {
        varchar32 payment_id PK
        varchar32 booking_id FK
        decimal amount_usd
        varchar20 payment_type
        varchar30 method
        varchar20 status
        timestamp paid_at
        varchar32 parent_payment_id FK
        decimal refunded_amount
    }

    users ||--o{ metro_access_logs : "generates"
    metro_stations ||--o{ metro_access_logs : "located at"

    metro_access_logs {
        bigint log_id PK
        varchar32 user_id FK
        varchar32 station_id FK
        varchar10 action_type
        timestamp timestamp
        varchar32 day_pass_trip_id
    }

    %% ============================================================
    %% Volume 8 & 9: Business & Legal Rules
    %% ============================================================
    booking_rule_sets ||--o{ booking_rule_params : "contains"
    booking_rule_sets {
        varchar32 rule_set_id PK
        varchar20 network_type
        int version
        boolean is_active
        date effective_from
        date effective_until
        timestamp created_at
    }
    booking_rule_params {
        bigserial param_id PK
        varchar32 rule_set_id FK
        varchar20 ticket_type
        varchar20 fare_class
        varchar100 rule_key
        decimal rule_value_numeric
        varchar255 rule_value_text
        varchar20 unit
        text description
    }

    policy_categories ||--o{ policy_rules : "categorizes"
    policy_categories {
        varchar32 category_id PK
        varchar20 network_type
        text rule_key
        varchar100 display_name_zh
        varchar100 display_name_en
        int sort_order
    }
    policy_rules {
        varchar32 rule_id PK
        varchar32 category_id FK
        varchar100 rule_key
        boolean is_permitted
        varchar500 rule_value_text
        text description_zh
        text description_en
        varchar20 applies_to_ticket_type
        varchar20 applies_to_fare_class
        date effective_from
        date effective_until
        int version
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    %% Unconnected Vector Segment (RAG Component)
    policy_documents {
        int id PK
        varchar200 title
        varchar50 category
        text content
        vector embedding
        varchar200 source_file
        timestamptz created_at
    }