"""
TransitFlow — Neo4j Seeder
=========================
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

# Append the current directory to path to ensure proper module resolution
sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Locate the target data directory dynamically relative to this script path
_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    """Helper function to load and parse mock transit JSON raw payloads."""
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    """
    Core graph database seeder. Parses relational transit components into 
    property graphs with standard indexing properties for optimized path-finding.
    """
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        # Clear existing graph data before each run to ensure transaction idempotency
        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # 0. Create Constraints
        print("  Creating constraints and indexes...")
        session.run("CREATE CONSTRAINT metro_station_id_unique IF NOT EXISTS FOR (s:MetroStation) REQUIRE s.station_id IS UNIQUE")
        session.run("CREATE CONSTRAINT nr_station_id_unique IF NOT EXISTS FOR (s:NationalRailStation) REQUIRE s.station_id IS UNIQUE")

        # 1. Create City Metro Station Nodes (MetroStation)
        print("  Creating MetroStation nodes...")
        for station in metro_stations:
            session.run(
                """
                MERGE (s:MetroStation {station_id: $station_id})
                ON CREATE SET
                    s.name = $name,
                    s.lines = $lines,
                    s.is_interchange_metro = $is_interchange_metro,
                    s.interchange_metro_lines = $interchange_metro_lines,
                    s.is_interchange_national_rail = $is_interchange_national_rail,
                    s.interchange_national_rail_station_id = $interchange_national_rail_station_id
                ON MATCH SET
                    s.name = $name,
                    s.lines = $lines,
                    s.is_interchange_metro = $is_interchange_metro,
                    s.interchange_metro_lines = $interchange_metro_lines,
                    s.is_interchange_national_rail = $is_interchange_national_rail,
                    s.interchange_national_rail_station_id = $interchange_national_rail_station_id
                """,
                station_id=station["station_id"],
                name=station["name"],
                lines=station["lines"],
                is_interchange_metro=station["is_interchange_metro"],
                interchange_metro_lines=station["interchange_metro_lines"],
                is_interchange_national_rail=station["is_interchange_national_rail"],
                interchange_national_rail_station_id=station["interchange_national_rail_station_id"]
            )

        # 2. Create National Rail Station Nodes (NationalRailStation)
        print("  Creating NationalRailStation nodes...")
        for station in rail_stations:
            session.run(
                """
                MERGE (s:NationalRailStation {station_id: $station_id})
                ON CREATE SET
                    s.name = $name,
                    s.lines = $lines,
                    s.is_interchange_national_rail = $is_interchange_national_rail,
                    s.interchange_rail_lines = $interchange_national_rail_lines,
                    s.is_interchange_metro = $is_interchange_metro,
                    s.interchange_metro_station_id = $interchange_metro_station_id
                ON MATCH SET
                    s.name = $name,
                    s.lines = $lines,
                    s.is_interchange_national_rail = $is_interchange_national_rail,
                    s.interchange_rail_lines = $interchange_national_rail_lines,
                    s.is_interchange_metro = $is_interchange_metro,
                    s.interchange_metro_station_id = $interchange_metro_station_id
                """,
                station_id=station["station_id"],
                name=station["name"],
                lines=station["lines"],
                is_interchange_national_rail=station["is_interchange_national_rail"],
                interchange_national_rail_lines=station["interchange_national_rail_lines"],
                is_interchange_metro=station["is_interchange_metro"],
                interchange_metro_station_id=station["interchange_metro_station_id"]
            )

        # 3. Establish Metro Adjacent Relationships (METRO_LINK)
        # Why: MERGE includes the line attribute to gracefully support multi-line parallel tracks.
        print("  Creating Metro adjacent links...")
        for station in metro_stations:
            for adj in station["adjacent_stations"]:
                session.run(
                    """
                    MATCH (source:MetroStation {station_id: $source_id})
                    MATCH (target:MetroStation {station_id: $target_id})
                    MERGE (source)-[r:METRO_LINK {line: $line}]->(target)
                    ON CREATE SET 
                        r.network_type = "metro",
                        r.travel_time_min = $travel_time_min
                    ON MATCH SET 
                        r.network_type = "metro",
                        r.travel_time_min = $travel_time_min
                    """,
                    source_id=station["station_id"],
                    target_id=adj["station_id"],
                    line=adj["line"],
                    travel_time_min=int(adj["travel_time_min"])
                )

        # 4. Establish National Rail Adjacent Relationships (RAIL_LINK)
        # Design Choice: Enforces direct integer conversion for travel_time_min 
        # to support clean mathematical summation during execution-time Cypher reduce loops.
        print("  Creating National Rail adjacent links...")
        for station in rail_stations:
            for adj in station["adjacent_stations"]:
                session.run(
                    """
                    MATCH (source:NationalRailStation {station_id: $source_id})
                    MATCH (target:NationalRailStation {station_id: $target_id})
                    MERGE (source)-[r:RAIL_LINK {line: $line}]->(target)
                    ON CREATE SET 
                        r.network_type = "national_rail",
                        r.travel_time_min = $travel_time_min
                    ON MATCH SET 
                        r.network_type = "national_rail",
                        r.travel_time_min = $travel_time_min
                    """,
                    source_id=station["station_id"],
                    target_id=adj["station_id"],
                    line=adj["line"],
                    travel_time_min=int(adj["travel_time_min"])
                )

        # 5. Build Bidirectional Interchanges Between Distinct Networks (INTERCHANGE_TO)
        # Why: Binds isolated graphs together to allow seamless multi-modal cross-routing queries.
        print("  Creating interchange relationships between metro and rail stations...")
        for station in metro_stations:
            if station["is_interchange_national_rail"] and station["interchange_national_rail_station_id"]:
                session.run(
                    """
                    MATCH (m:MetroStation {station_id: $metro_id})
                    MATCH (r:NationalRailStation {station_id: $rail_id})
                    MERGE (m)-[:INTERCHANGE_TO]->(r)
                    MERGE (r)-[:INTERCHANGE_TO]->(m)
                    """,
                    metro_id=station["station_id"],
                    rail_id=station["interchange_national_rail_station_id"]
                )

    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()