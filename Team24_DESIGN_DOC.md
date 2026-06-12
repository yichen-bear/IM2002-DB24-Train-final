## Section 1 — ERD

```mermaid
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

    %% Normalized stop sequence table for National Rail schedules
    schedules ||--o{ national_rail_schedule_stops : "has ordered stops"
    national_rail_stations ||--o{ national_rail_schedule_stops : "appears in"

    national_rail_schedule_stops { 
        varchar32 schedule_id PK, FK
        int stop_order PK 
        varchar32 station_id FK 
        int travel_time_offset 
        boolean is_pass_through 
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

    %% Normalized stop sequence table for Metro schedules
    metro_schedules ||--o{ metro_schedule_stops : "has ordered stops" 
    metro_stations ||--o{ metro_schedule_stops : "appears in" 

    metro_schedule_stops { 
        varchar32 metro_schedule_id PK, FK 
        int stop_order PK 
        varchar32 station_id FK 
        int travel_time_offset 
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
        varchar100 category_key
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
```

---

## Section 2 — Normalisation Justification

### 1. Relational Normalisation Decisions (3NF)

In the core relational database design of the TransitFlow system, especially in the design of schedules, stations, stop ordering, and transaction data, this project mainly follows **Third Normal Form (3NF)** as its design principle. The goal is to reduce data redundancy, avoid structural update anomalies, and maintain data consistency.

A key example that demonstrates both 2NF and 3NF design decisions is the handling of the complex many-to-many (M:N) relationship between stations and operating schedules. This project introduces the junction tables `metro_schedule_stops` and `national_rail_schedule_stops` to achieve clear schema decomposition.

* **Analysis of Candidate Keys and Functional Dependencies**:  
  In an unnormalised design, a developer might attempt to store schedule and stopping-station information directly in the same table. In that case, if `{schedule_id, station_id}` were used as the primary key, non-key attributes such as the schedule’s `line`, fare columns, or stop-specific attributes such as `travel_time_offset` would create confused dependency relationships.

  Specifically, `line` depends only on `schedule_id`, while `station_name` depends only on `station_id`. These are partial dependencies and therefore violate 2NF. At the same time, stop-specific attributes such as `travel_time_offset` should depend strictly on the full `{schedule_id, stop_order}` combination. If all of these fields were forced into a single table, the design would create repeated data and would cause update anomalies whenever a station name or schedule-level attribute changes.

* **Achieving 3NF Compliance Through Junction Tables**:  
  To solve these problems, the schema implements a decomposed 3NF structure:

  1. Entity attributes are separated: basic station attributes are stored in `metro_stations`, while schedule-level attributes are stored in `metro_schedules`.
  2. A junction table is introduced: `metro_schedule_stops` uses the composite primary key `{metro_schedule_id, stop_order}` to record which station (`station_id`) appears at a specific stop order within a specific schedule, together with the relative travel time (`travel_time_offset`).

  With this design, all non-key attributes depend on “the key, the whole key, and nothing but the key.” This design removes partial dependencies and transitive dependencies, and it preserves structural integrity during relational queries.

---

### 2. Deliberate De-normalisation Trade-offs

Although the base data in this system is maintained under a strict 3NF-oriented design, the core transaction table `bookings` intentionally uses a **transaction snapshot** pattern. This is a deliberate denormalisation trade-off.

* **Trade-off Between Audit Accuracy and Historical Immutability**:  
  Under a strictly normalised design, booking amounts and origin/destination station information could be dynamically recalculated by joining back to `schedules`, `national_rail_schedule_stops`, and station tables, using fare columns such as `base_fare_standard_usd`, `per_stop_standard_usd`, and `base_fare_first_usd`. However, in public transport and e-commerce systems, base fares and station operating conditions may change over time.

  If the system increases fares tomorrow, dynamically recalculating historical bookings through joins would change the apparent amount of past transactions. This would create serious financial inconsistency and would fail audit requirements.

* **Conclusion**:  
  To solve this problem, the `bookings` table intentionally stores selected current-state values directly, including `amount_usd`, `departure_time`, and `origin_station_id`.

  This denormalised design freezes the operational state at the time of booking as a historical snapshot. At the same time, strict foreign key constraints are used. For example, `bookings.user_id` uses `ON DELETE RESTRICT`, preventing users with transaction records from being deleted casually, rather than using a dangerous `CASCADE` behaviour. This preserves the immutability and historical correctness of financial audit data. The design is therefore a necessary and reasonable trade-off for the business and payment logic of the system.

---

### 3. Cryptographic Password Hashing and Salt Management

To protect user credentials and reduce the risk of database leakage, the application layer of this system uses the industry-standard **Argon2id** password hashing algorithm. The `user_credentials.password_hash` field is designed to store the complex hash output produced by the application. This approach replaces insecure legacy primitives such as MD5 and SHA-1.

* **Why Argon2id Is Used Instead of MD5 or SHA-1**:  
  MD5 and SHA-1 are general-purpose cryptographic hash functions designed for high execution speed. Because they do not include built-in computational cost controls, if a database breach occurs, attackers can use modern GPUs or ASIC hardware to perform extremely fast brute-force cracking.

  Argon2id, the winner of the Password Hashing Competition, uses **key stretching** to bind the hashing process to hardware resource costs. It introduces three major cost parameters:

  1. **Memory Cost**: Controls how much RAM is required to compute a single hash. This memory-hard property makes large-scale parallel cracking on GPUs much more expensive because the attack becomes constrained by memory bandwidth.
  2. **Time Cost**: Controls the number of sequential iterations, increasing the time required for a single password verification.
  3. **Parallelism**: Specifies the number of CPU threads used during computation.

  These design choices impose a high computational cost on attackers and make large-scale password cracking economically impractical.

* **How Salt Defends Against Rainbow-Table Attacks**:  
  If a database stores only unsalted password hashes, then two users who choose the same common password, such as `"Transit2026"`, will produce the same hash string. Attackers can then use precomputed lookup tables of common password hashes, known as rainbow tables, to reverse those hashes quickly.

  Before hashing, Argon2id generates a cryptographically secure random byte sequence known as a **salt** for each account, and combines it with the plaintext password:

  $$
  \text{Hash} = \text{Argon2id}(\text{Plaintext Password}, \text{Unique Salt}, \text{Cost Parameters})
  $$

  Because every user has an independent and random salt, two users with the same plaintext password will still have unrelated stored hash strings. This defeats rainbow-table lookup and forces attackers to crack each account individually with a high computational cost.

---

## Section 3 — Graph Database Design Rationale

### 1. Data Modeling Decision: Nodes, Relationships, and Properties

The TransitFlow graph database is mainly used to support route planning, cross-network interchange routing, and delay ripple analysis. These problems are fundamentally about how stations are connected to one another, so a graph model is a better fit for representing transit network topology than relying only on relational joins.

#### Nodes

Neo4j creates two main station node labels:

- `(:MetroStation)`
- `(:NationalRailStation)`

This design is used because metro stations and national rail stations belong to different transit networks, come from different data sources, and have some different properties. Separating them into different labels keeps the graph schema clearer and also makes it possible to write network-specific queries, such as analysing only metro stations or only national rail stations.

Each node mainly contains:

- `station_id`
- `name`
- `lines`
- interchange-related fields

The `station_id` is the main identifier used to connect the graph database with the relational database.

#### Relationships

The graph mainly creates three relationship types:

- `-[:METRO_LINK]->`
- `-[:RAIL_LINK]->`
- `-[:INTERCHANGE_TO]->`

`METRO_LINK` represents adjacent station connections within the metro network.  
`RAIL_LINK` represents adjacent station connections within the national rail network.  
`INTERCHANGE_TO` connects metro stations and national rail stations where passengers can transfer between the two networks.

During the seeding phase, `INTERCHANGE_TO` relationships are created bidirectionally. This allows users to transfer from metro to national rail and also from national rail back to metro. As a result, cross-network routing can be completed in a single graph traversal, without manually combining two separate route segments in the application layer.

#### Properties

Node properties mainly describe the station itself, such as `station_id`, `name`, and `lines`. These attributes belong to the station entity and are therefore stored on the node.

Relationship properties describe the connection between two stations. For `METRO_LINK` and `RAIL_LINK`, the relationship stores:

- `line`
- `network_type`
- `travel_time_min`

This design is used because route planning needs to accumulate the travel time of each edge in a path. Storing `travel_time_min` on the relationship allows a Cypher query to directly read each edge’s travel time from `relationships(path)` and sum the values.

In the current project, `INTERCHANGE_TO` represents a zero-time transfer edge, so it does not store `travel_time_min` or `line`. In the fastest route query, this type of edge is treated as a 0-minute transfer through `coalesce(r.travel_time_min, 0)`.

---

### 2. Why Graph Database Is Suitable for Routing

Route planning and delay propagation are naturally graph traversal problems. In a transit network, stations can be represented as nodes, and physical or logical connections between stations can be represented as relationships. This allows the database to traverse directly from one station to its connected stations.

If the same routing task were implemented purely in PostgreSQL, the system would need to repeatedly join an adjacency table, such as `station_adjacencies`, to explore paths with increasing depth. This is possible with recursive CTEs, but it becomes harder to write, debug, and optimise as the number of hops and path constraints increases.

In Neo4j, relationships are first-class data objects. The query can directly expand from a station through `METRO_LINK`, `RAIL_LINK`, and `INTERCHANGE_TO` relationships. This makes multi-hop route search, cross-network interchange routing, and delay ripple analysis more natural to express than repeated SQL self-joins.

This does not mean that graph queries are always faster in every situation. Rather, for this project’s routing-related use cases, the graph model is a better conceptual and practical fit because the main operations are path expansion, edge-weight accumulation, and neighbourhood traversal.

---

### 3. Query Types Analysis

The implemented graph schema supports multiple routing-related query types. Two representative examples are fastest path routing and delay ripple analysis.

#### Query 1: Fastest Multi-modal Route

**Use case:**  
A user wants to find the fastest route between two stations. The origin and destination may both be metro stations, both be national rail stations, or belong to different networks.

**Cypher structure:**

```cypher
MATCH (start {station_id: $origin_id})
MATCH (end {station_id: $destination_id})
MATCH path = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..15]-(end)
WITH path,
     reduce(t = 0, r IN relationships(path) | t + coalesce(r.travel_time_min, 0)) AS total_time
RETURN path, total_time
ORDER BY total_time ASC
LIMIT 1
```

This query expands candidate paths between the start and end station through `METRO_LINK`, `RAIL_LINK`, and `INTERCHANGE_TO` relationships. It then uses `reduce()` to sum the `travel_time_min` value of each relationship in the path.

Because `INTERCHANGE_TO` does not store `travel_time_min`, `coalesce(r.travel_time_min, 0)` treats interchange edges as zero-time transfer edges. Finally, the query orders candidate paths by total travel time and returns the lowest-time route.

This is not Neo4j’s built-in `shortestPath()` function. Instead, the implementation uses pure Cypher weighted path expansion and sorting, which is more appropriate here because the shortest route should be based on travel time, not simply the fewest number of hops.

#### Query 2: Delay Ripple Analysis

**Use case:**  
When a station is delayed or disrupted, the system needs to identify nearby stations that may be affected within a specified number of hops.

**Cypher structure:**

```cypher
MATCH (disrupted {station_id: $delayed_station_id})
MATCH path = (disrupted)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..$hops]-(affected)
WHERE disrupted <> affected
RETURN DISTINCT affected.station_id AS station_id,
                affected.name AS name,
                length(path) AS hops_away,
                [r IN relationships(path) | coalesce(r.line, 'Interchange')] AS lines_involved
ORDER BY hops_away ASC
```

This query starts from the disrupted station and traverses outward through the transit network up to the specified hop count. Each returned station includes its `station_id`, `name`, how many hops away it is from the disrupted station, and which lines or interchange relationships are involved.

This query is well-suited to a graph database because delay ripple is naturally a neighbourhood traversal problem. In a relational database, this would require recursive joins over an adjacency table, whereas Neo4j can express the same logic directly as relationship expansion.

---

### 4. Node Identity Strategy

The graph uses `station_id` as the main station identifier, together with the node label. For example:

- `(:MetroStation {station_id: "MS01"})`
- `(:NationalRailStation {station_id: "NR01"})`

This is safer than relying on station names because names may be duplicated or changed in the future. The `station_id` also matches the identifiers used in the relational database, which allows PostgreSQL and Neo4j to refer to the same real-world station consistently.

This shared identifier supports the project’s polyglot persistence design. Transactional data such as users, bookings, payments, and credentials remain in PostgreSQL, while route traversal and network topology queries are handled in Neo4j. The common `station_id` allows the two database systems to stay connected without duplicating all business data inside the graph.

---

## Section 4 — Vector / RAG Design

### 1. Embedding and Cosine Similarity Rationale

In the TransitFlow system, the data to be embedded consists of the policy document content stored in the `policy_documents` table. The source files include `refund_policy.json` for refund policies, `ticket_types.json` for ticket type information, `booking_rules.json` for booking rules, and `travel_policies.json` for travel and conduct policies. These documents are converted into vectors and stored in the `policy_documents.embedding` column in PostgreSQL, where they support the customer service Retrieval-Augmented Generation (RAG) system.

#### Why Cosine Similarity Is Suitable for Semantic Search

The key reason is that cosine similarity is **magnitude-independent**. It measures **directional similarity** in vector space instead of being dominated by the raw length or magnitude of the vectors.

Cosine similarity is suitable for semantic search because it compares the direction of two embedding vectors in semantic space rather than their original vector lengths. In a customer service scenario, user questions are usually short, such as “How can I get a refund?”, while official policy documents are often much longer, such as detailed refund fee rules and time-window tiers.

If Euclidean distance were used, differences in text length and vector magnitude could affect the distance calculation. Cosine similarity reduces this issue: even if the user question is short and the policy document is long, as long as both discuss a similar semantic topic, such as refund rules, their vector directions will still be close in high-dimensional space. Therefore, the system can retrieve the corresponding official policy documents more accurately.

---

### 2. Full RAG Pipeline Workflow

The implemented Retrieval-Augmented Generation (RAG) function follows four main stages from the user’s question to the final answer:

1. **Query Embedding**  
   After the user submits a question in the customer service interface, the backend first calls an embedding model, such as Ollama’s `nomic-embed-text`, to convert the question text into a fixed-length array of floating-point numbers.

2. **Similarity Search**  
   After obtaining the query vector, the system searches the PostgreSQL `policy_documents` table. The database has an HNSW index on the embedding column using `vector_cosine_ops`, so PostgreSQL can perform efficient cosine similarity comparisons.

3. **Retrieved Documents**  
   Based on cosine similarity scores, the database returns the most relevant official policy documents as context for the language model.

4. **LLM Prompt → Answer**  
   The Python backend combines the user’s question with the retrieved official reference documents into a prompt template. The prompt instructs the language model to answer based only on the official policy context. The completed prompt is then sent to the LLM, and the generated customer-service response is returned to the frontend.

---

### 3. Embedding Dimension Choice and Provider Switch Impact

#### Dimension Choice

According to the setting in `schema.sql`, the vector column is created as `embedding vector(768)`. This means the current implementation uses Ollama’s `nomic-embed-text`, which produces 768-dimensional embeddings. If the provider is switched to Gemini in the future, Gemini’s embedding model produces 3072-dimensional vectors.

#### What Happens If the Provider Is Changed After Seeding

If `seed_vectors.py` has already inserted 768-dimensional Ollama embeddings into the database, and the provider is changed to Gemini in `.env` without reseeding, the system will fail because the vector dimensions are incompatible.

1. **Dimension Mismatch**  
   When a user asks a question, the system will generate a 3072-dimensional query embedding through Gemini. PostgreSQL, however, has an embedding column defined as `vector(768)`, so the 3072-dimensional query vector cannot be compared against the stored 768-dimensional document vectors.

2. **Index Incompatibility and Schema Change Cost**  
   PostgreSQL will raise an error such as `ERROR: vector columns must have the same dimensions`. The HNSW index originally built on the 768-dimensional column cannot be used for 3072-dimensional vectors. To complete the provider switch, the database schema must be changed to `vector(3072)`, existing vector data must be cleared or regenerated, `seed_vectors.py` must be rerun using the new embedding provider, and the HNSW index must be rebuilt.

3. **Practical Consequence**  
   From the user’s perspective, this would cause the entire customer service retrieval function to fail. When a user asks a question, the backend would fail during database retrieval and may return a server error. The system would not be able to retrieve policy context, and the LLM would not have the required reference documents to answer correctly. Until the vector dimension is adjusted and the documents are reseeded, the smart customer service component would not function properly.

---

## Section 5 — AI Tool Usage Evidence

This section documents the structured collaboration with AI tools during the graph database design, seeding development, verification scripting, and UI integration phases of the TransitFlow system. Below are three distinct examples illustrating how AI assistance was utilised, focusing on the specific responsibilities of this role.

---

### Example 1: Graph Modeling and Label Partitioning Decision

* **Context**: Designing the Neo4j graph database schema in `seed_neo4j.py` to support multi-modal transit routing. The challenge was deciding whether to represent all stations under a single generic label or partition them into distinct networks, which directly impacts how polymorphic station associations from the relational schema (`station_adjacencies`) are mapped.

* **Prompt**:
  ```text
  We are seeding a Neo4j database from two JSON files containing station records: metro stations and national rail stations. Should we label all stations with a single (:Station) label, or separate labels like (:MetroStation) and (:NationalRailStation)? How should we model the connection edges between them to enable efficient routing search?
  ```

* **Outcome**: The AI suggested using partitioned labels (`MetroStation` and `NationalRailStation`) to isolate the two transit systems in memory, avoiding scanning rail station nodes during metro-only traversals. For connectivity, it recommended establishing separate edge types (`METRO_LINK` and `RAIL_LINK`) and bridging them via bidirectional `INTERCHANGE_TO` edges at interchange hubs. This graph model was implemented in `seed_neo4j.py`.

---

### Example 2: Edge Property Data Type Enforcement (AI Error and Correction)

* **Context**: Resolving a Cypher runtime error where the pathfinding query failed to calculate total trip durations because travel times were imported as string variables rather than numbers.

* **Prompt**:
  ```text
  In my Neo4j database, when I run a Cypher query using `reduce(t = 0, r IN relationships(path) | t + r.travel_time_min)`, it fails with a type mismatch error because some relationships store `travel_time_min` as strings. Show me how to fix my Python seeder script where I retrieve properties from the parsed JSON data.
  ```

* **Outcome (Incorrect AI Suggestion)**: The AI suggested modifying the Cypher query to perform dynamic type casting during traversal, for example by using `toInteger(r.travel_time_min)`.

* **Why It Was Incorrect**: Executing `toInteger()` dynamically inside the Cypher traversal engine introduces runtime CPU overhead for every edge visited. In a production routing system with deep paths, this would degrade performance. The correct place to solve the issue is during the data ingestion phase.

* **Correction**: The suggestion was rejected. Instead, the seeder script `seed_neo4j.py` was corrected by explicitly casting the JSON values using `int(adj["travel_time_min"])` when parameterising the `session.run` parameters. This ensures that only pure integer values are stored on edges, allowing the Neo4j engine to execute the `reduce` summation natively.

---

### Example 3: Automated Parity Check Scripting for Graph Integrity

* **Context**: Creating an automated verification script (`skeleton/verify_neo4j.py`) to guarantee that the seeded graph nodes and relationships match the source JSON mock files.

* **Prompt**:
  ```text
  Write a Python script that connects to Neo4j and validates that the number of MetroStation and NationalRailStation nodes matches the count of items in metro_stations.json and national_rail_stations.json, and counts the relationship edges to make sure they correspond to the number of adjacencies.
  ```

* **Outcome**: The AI generated a script template using the Neo4j Python driver. It loads the JSON payloads into memory, queries node labels, computes expected edge counts mathematically, and compares them against the database. This was refined into the final `verify_neo4j.py` tool to quickly audit database parity.

---

## Section 6 — Reflection & Trade-offs

This section reflects on the key design decisions made during the development of the database infrastructure, including both the relational and graph layers, as well as the UI integration layer. It explains the engineering rationale behind these decisions and discusses production considerations.

---

### 1. Selected Design Decisions and Rationales

#### Decision A: Dual Primary Key Selection Strategy — Balancing Security and Write Performance

* **Design Choice**: Rather than applying a single primary key data type across the entire database system, the project uses a dual primary key strategy based on the nature of the data. Core business tables such as `users`, `bookings`, and `payments` use `VARCHAR(32)` to store non-sequential UUIDs or hash IDs, whereas the telemetry log table `metro_access_logs` uses a fast auto-incrementing `BIGINT GENERATED ALWAYS AS IDENTITY`.

* **Rationale**:
  1. **Security and Privacy Orientation (`VARCHAR(32)` for UUIDs)**: For user profiles and financial booking records, using standard serial integers could expose the system to Insecure Direct Object Reference (IDOR) risks, because attackers might guess adjacent record IDs by incrementing URL parameters. Storing UUID-style values as `VARCHAR(32)` provides non-sequential and difficult-to-guess references, improving security isolation and supporting distributed environments.
  2. **Performance and Throughput Orientation (`BIGINT IDENTITY`)**: For turnstile gate logs such as `metro_access_logs`, data ingestion is highly concurrent and append-only. Random `VARCHAR` keys would increase B-tree index page splits and memory fragmentation during random inserts. Using `BIGINT IDENTITY` preserves chronological ordering and improves insert performance for log-style data.

#### Decision B: Partitioning Node Labels by Transit Network (`:MetroStation` vs `:NationalRailStation`)

* **Design Choice**: Rather than using a generic label such as `:Station` for every node in the graph, stations are explicitly partitioned into two distinct labels: `:MetroStation` and `:NationalRailStation`.

* **Rationale**:
  1. **Query Optimisation**: Separate labels make it possible to write network-specific Cypher queries, such as matching only `:MetroStation` nodes for metro-only analysis. Even when a multi-modal query uses both labels, label partitioning keeps the graph model semantically clear and avoids relying on a single overloaded `:Station` label with many conditional properties.
  2. **Property Separation and Polymorphic Resolution**: Metro stations contain specific interchange fields, such as `interchange_metro_lines`, that do not apply to rail stations. Explicit label partitioning keeps the graph schema cleaner and better typed, allowing the polymorphic association defined in the relational table `station_adjacencies` to be represented clearly within the graph traversal space.

#### Decision C: Pre-calculated Interchange Edges (`:INTERCHANGE_TO`)

* **Design Choice**: Instead of dynamically calculating whether a metro station and a rail station share a physical interchange during routing queries, these links are explicitly modelled as bidirectional `:INTERCHANGE_TO` relationships during the seeding phase.

* **Rationale**:
  1. **Latency Reduction**: Calculating geographic proximity or matching station names during a path traversal query would add runtime computation cost. Pre-seeding interchange relationships trades a small amount of database storage for faster route-finding queries.
  2. **Encapsulating Transfer Logic**: In the current project, `INTERCHANGE_TO` is modelled as a zero-time transfer edge, matching the project assumption that interchange time is not included in route estimates. In a future extension, transfer penalties could be added as relationship properties if the routing model needs to account for walking time.

---

### 2. Production System Considerations

To scale the graph database and UI for a production environment serving large numbers of daily commuters, the following changes would be necessary.

#### Causal Clustering for Neo4j Scaling

* **Current Implementation**: The system runs on a single isolated Neo4j instance in a Docker container.

* **Production Requirement**: Transit routing queries are read-intensive. A single instance could become a bottleneck under many concurrent requests. A production deployment would use a Neo4j causal cluster with one primary writer instance and multiple read replicas. This would offload routing and pathfinding calculations to read-only instances and support horizontal scalability.

#### Graph Data Syncing and Event-Driven Seeding

* **Current Implementation**: The seeder script clears the entire graph and recreates all nodes and edges from static JSON mock files.

* **Production Requirement**: In a live system, station statuses, closures, delays, and schedules may change dynamically. The seeder should be replaced with an event-driven syncing pipeline, such as database triggers or a Kafka message queue. This would allow the graph to receive incremental updates, such as updated relationship weights or station availability, in real time without downtime.
