# Section 6 — Reflection & Trade-offs

This section reflects on the key design decisions made during the development of the database infrastructure (including both Relational and Graph layers) and the UI integration layers, detailing the engineering rationales behind them and discussing production considerations.

---

## 1. Selected Design Decisions and Rationales

### Decision A: Dual Primary Key (PK) Selection Strategy — Balancing Security and Write Performance
* **Design Choice**: Rather than uniformly applying a single data type for all Primary Keys across the entire database system, we implemented a dual PK strategy based on the data's inherent nature. Core business tables (`users`, `bookings`, `payments`) utilize `VARCHAR(32)` to store non-sequential UUIDs/HashIDs, whereas telemetry log tables (`metro_access_logs`) utilize a fast auto-incrementing `BIGINT GENERATED ALWAYS AS IDENTITY` (Serial).
* **Rationale**:
  1. **Security & Privacy Orientation (`VARCHAR(32)` for UUIDs)**: For user profiles and financial booking records, utilizing standard serial integers exposes the system to **Insecure Direct Object Reference (IDOR)** vulnerability, where attackers can easily guess adjacent record IDs by simply incrementing URLs. Storing UUIDs as `VARCHAR(32)` guarantees unguessable, non-sequential references, providing security isolation and seamless support for distributed environments.
  2. **Performance & Throughput Orientation (`BIGINT IDENTITY`)**: For the turnstile gate logs (`metro_access_logs`), data ingestion is highly concurrent and append-only. Storing random `VARCHAR` keys here would severely bottleneck the database due to constant **B-Tree index page splits** and memory fragmentation during random inserts. Adhering to strict performance-driven database concepts, we explicitly avoided `VARCHAR` for logs and leveraged `BIGINT IDENTITY` to preserve native, chronological sorting and maximized insert speed.

### Decision B: Partitioning Node Labels by Transit Network (`:MetroStation` vs `:NationalRailStation`)
* **Design Choice**: Rather than using a generic label like `:Station` for every node in the graph, stations are explicitly partitioned into two distinct labels: `:MetroStation` and `:NationalRailStation`.
* **Rationale**:
  1. **Query Optimization**: Isolating the labels prevents the traversal engine from scanning irrelevant nodes. For example, if a query is searching for a path strictly within the city metro line (M1–M4), the engine restricts its search path to `:MetroStation` nodes, skipping national rail stations entirely.
  2. **Properties Separation & Polymorphic Resolution**: Metro stations contain specific interchange fields (such as `interchange_metro_lines`) that do not apply to rail stations. Explicit label partitioning keeps the graph schema clean and well-typed, allowing the polymorphic association defined in the relational table `station_adjacencies` to be cleanly resolved within the graph traversal space.

### Decision C: Pre-calculated Interchange Edges (`:INTERCHANGE_TO`)
* **Design Choice**: Instead of dynamically calculating whether a metro station and a rail station share a physical interchange during routing queries, these links are explicitly modeled as bidirectional `:INTERCHANGE_TO` relationships during the seeding phase.
* **Rationale**:
  1. **Latency Reduction**: Calculating geographic proximities or matching station names on the fly during a path traversal query adds runtime computational cost. Pre-seeding the interchange relationships trades a tiny amount of database disk space for sub-millisecond route-finding queries.
  2. **Encapsulating Transfer Logic**: Transfer times or walking penalties can be attached directly to the `:INTERCHANGE_TO` edges as properties, enabling routing algorithms to easily factor transfer overhead into their calculations.

---

## 2. Production System Considerations

To scale the graph database and UI for a production environment serving large-scale daily commuters, the following changes would be necessary:

### Causal Clustering for Neo4j Scaling
* **Current Implementation**: The system runs on a single, isolated Neo4j instance in a Docker container.
* **Production Requirement**: Transit routing queries are highly read-intensive. A single instance would quickly bottleneck under concurrent requests. A production deployment would implement a **Neo4j Causal Cluster** with one primary writer instance and multiple read replicas. This offloads routing and pathfinding calculations to read-only instances, ensuring horizontal scalability.

### Graph Data Syncing and Event-Driven Seeding
* **Current Implementation**: The seeder script clears the entire graph and recreates all nodes and edges from scratch from static JSON mock files.
* **Production Requirement**: In a live system, station statuses (closures, delays) and schedules change dynamically. The seeder must be replaced with an **event-driven syncing pipeline** (e.g., listening to database triggers or a Kafka message queue). This allows the graph to receive incremental updates (updating relationship weights or station availability) in real time without downtime.