# Section 5 — AI Tool Usage Evidence

This section documents the structured collaboration with AI tools during the graph database design, seeding development, verification scripting, and UI integration phases of the TransitFlow system. Below are four distinct examples illustrating how AI assistance was utilized, focusing on the specific responsibilities of this role.

---

### Example 1: Graph Modeling and Label Partitioning Decision
* **Context**: Designing the Neo4j graph database schema in `seed_neo4j.py` to support multi-modal transit routing. The challenge was deciding whether to represent all stations under a single generic label or partition them into distinct networks.
* **Prompt**:
  ```text
  We are seeding a Neo4j database from two JSON files containing station records: metro stations and national rail stations. Should we label all stations with a single (:Station) label, or separate labels like (:MetroStation) and (:NationalRailStation)? How should we model the connection edges between them to enable efficient routing search?
  ```
* **Outcome**: The AI suggested using partitioned labels (`MetroStation` and `NationalRailStation`) to isolate the two transit systems in memory, avoiding scanning rail station nodes during metro-only traversals. For connectivity, it recommended establishing separate edge types (`METRO_LINK` and `RAIL_LINK`) and bridging them via bidirectional `INTERCHANGE_TO` edges at interchange hubs. This graph model was implemented in `seed_neo4j.py`.

---

### Example 2: Edge Property Data Type Enforcement (AI Error & Correction)
* **Context**: Resolving a Cypher runtime error where the pathfinding query failed to calculate total trip durations because travel times were imported as string variables rather than numbers.
* **Prompt**:
  ```text
  In my Neo4j database, when I run a Cypher query using `reduce(t = 0, r IN relationships(path) | t + r.travel_time_min)`, it fails with a type mismatch error because some relationships store `travel_time_min` as strings. Show me how to fix my Python seeder script where I retrieve properties from the parsed JSON data.
  ```
* **Outcome (Incorrect AI Suggestion)**: The AI suggested modifying the Cypher query to perform dynamic type casting during traversal, e.g., `toInteger(r.travel_time_min)`.
* **Why it was incorrect**: Executing `toInteger()` dynamically inside the Cypher traversal engine introduces substantial runtime CPU overhead for every edge visited. In a production routing system with deep paths, this degrades performance. The correct place to solve this is during the data ingest phase.
* **Correction**: The suggestion was rejected. Instead, the seeder script `seed_neo4j.py` was corrected by explicitly casting the JSON values using `int(adj["travel_time_min"])` when parameterizing the `session.run` parameters. This ensures that only pure integer types are stored on edges, allowing the Neo4j engine to execute the `reduce` summation natively at maximum speed.

---

### Example 3: Automated Parity Check Scripting for Graph Integrity
* **Context**: Creating an automated verification script (`skeleton/verify_neo4j.py`) to guarantee that the seeded graph nodes and relationships match the source JSON mock files perfectly.
* **Prompt**:
  ```text
  Write a Python script that connects to Neo4j and validates that the number of MetroStation and NationalRailStation nodes matches the count of items in metro_stations.json and national_rail_stations.json, and counts the relationship edges to make sure they correspond to the number of adjacencies.
  ```
* **Outcome**: The AI generated a script template using the Neo4j Python driver. It loads the JSON payloads into memory, queries node labels, computes expected edge counts mathematically, and compares them against the database. This was refined into the final `verify_neo4j.py` tool to quickly audit database parity.

---

### Example 4: Tabbed Layout Architecture in Gradio UI
* **Context**: Constructing the web user interface (`skeleton/ui.py`) using Gradio. The goal was to build a clean tabbed layout that separates the main AI chat assistant from auxiliary diagnostic tools.
* **Prompt**:
  ```text
  How can I set up a Gradio tabbed layout that contains a chat interface in the first tab, and a route-finding tester in the second tab where users can select origin and destination stations from a dropdown?
  ```
* **Outcome**: The AI provided a block-based structure using `with gr.Blocks():` containing `with gr.Tab("Transit Chatbot"):` and `with gr.Tab("Multi-Modal Route Finder"):`. This structure was integrated into `skeleton/ui.py`, allowing users to test graph queries and LLM capabilities in separate, clean tabs.
