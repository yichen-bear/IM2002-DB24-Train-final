"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design your graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        # 每次執行前清空現有圖資料 (安全重播)
        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # 1. 建立地鐵車站節點 (MetroStation)
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

        # 2. 建立國鐵車站節點 (NationalRailStation)
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

        # 3. 建立地鐵相鄰站點關係 (METRO_LINK) - 最佳化 MERGE 屬性賦值
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

        # 4. 建立國鐵相鄰站點關係 (RAIL_LINK) - 最佳化 MERGE 屬性賦值
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

        # 5. 建立城市地鐵與系統國鐵之間的轉乘關係 (INTERCHANGE)
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