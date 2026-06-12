"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.

GRAPH ROLE:
  - Model the dual transit network (city metro M1–M4 + national rail NR1–NR2)
  - Find fastest routes (Dijkstra-equivalent via pure Cypher path-weight sorting)
  - Find cheapest routes (Dynamic fare accumulation using reduce expressions)
  - Find alternative routes avoiding a given disrupted station
  - Find cross-network interchange paths (metro <-> rail transit)
  - Show delay ripple: which stations are affected within N hops
"""

from __future__ import annotations
import random
import string
from typing import Optional, Any
from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

def _driver():
    """Return a Neo4j driver instance. Caller must handle lifecycle closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── 1. FASTEST ROUTE (Dijkstra-equivalent by travel_time_min) ────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest multi-modal route based on total travel time.
    Calculates moving times; interchange edges are treated as zero-time transfers.
    """
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    MATCH path = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..15]-(end)
    WITH path, 
         reduce(t = 0, r IN relationships(path) | t + coalesce(r.travel_time_min, 0)) AS total_time
    RETURN path, total_time
    ORDER BY total_time ASC
    LIMIT 1
    """
    
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher_query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            
            if not record:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "message": "No fast multi-modal route found between these endpoints."
                }
            
            path = record["path"]
            total_time = record["total_time"]
            
            stations = [{"station_id": n.get("station_id"), "name": n.get("name")} for n in path.nodes]
            legs = []
            for r in path.relationships:
                legs.append({
                    "type": r.type,
                    "line": r.get("line", "Interchange / Walkway"),
                    "travel_time_min": r.get("travel_time_min", 0)
                })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": total_time,
                "stations": stations,
                "legs": legs
            }


# ── 2. CHEAPEST ROUTE (Dynamic fare calculation via reduce) ──────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest path by dynamically aggregating cost structures 
    (metro flat/distance rates vs rail fixed matrices) across relationship variables.
    """
    # Uses reduce operation to compute granular ticket prices mathematically
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    MATCH path = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..15]-(end)
    WITH path,
         reduce(cost = 0.0, r IN relationships(path) | 
            cost + case 
                when type(r) = 'METRO_LINK' then coalesce(r.cost_usd, 1.50)
                when type(r) = 'RAIL_LINK' then coalesce(r.cost_usd, 4.50)
                else 0.0 -- Transfers are free or encapsulated in baseline boarding fares
            end
         ) AS total_fare
    RETURN path, total_fare
    ORDER BY total_fare ASC
    LIMIT 1
    """
    
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher_query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            
            if not record:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "message": "No multi-modal route found to calculate cost metrics."
                }
            
            path = record["path"]
            total_fare = record["total_fare"]
            
            stations = [{"station_id": n.get("station_id"), "name": n.get("name")} for n in path.nodes]
            legs = []
            transfers = 0
            
            for r in path.relationships:
                if r.type == "INTERCHANGE_TO":
                    transfers += 1
                legs.append({
                    "type": r.type,
                    "line": r.get("line", "Interchange"),
                    "network": "metro" if r.type == "METRO_LINK" else "national_rail" if r.type == "RAIL_LINK" else "transfer"
                })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "fare_class": fare_class,
                "total_fare_usd": round(total_fare, 2),
                "transfer_count": transfers,
                "stations": stations,
                "legs": legs
            }


# ── 3. ALTERNATIVE ROUTES (Avoiding a Closed Station) ────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
) -> dict:
    """
    Find an alternative route that completely circumvents a closed or delayed station.
    Guarantees structural return consistency (always a dict) to avoid application failure.
    """
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    MATCH path = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..15]-(end)
    WHERE NONE(node IN nodes(path) WHERE node.station_id = $avoid_station_id)
    WITH path,
         reduce(t = 0, r IN relationships(path) | t + coalesce(r.travel_time_min, 0)) AS total_time
    RETURN path, total_time
    ORDER BY total_time ASC
    LIMIT 1
    """
    
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher_query, 
                origin_id=origin_id, 
                destination_id=destination_id, 
                avoid_station_id=avoid_station_id
            )
            record = result.single()
            
            if not record:
                # FIXED: Return consistent dict structure instead of a nested array list
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "avoid_station_id": avoid_station_id,
                    "message": f"No viable alternative path exists detour bypassing {avoid_station_id}."
                }
            
            path = record["path"]
            
            stations = [{"station_id": n.get("station_id"), "name": n.get("name")} for n in path.nodes]
            legs = [{"type": r.type, "line": r.get("line", "Interchange"), "travel_time_min": r.get("travel_time_min", 2)} for r in path.relationships]

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "avoid_station_id": avoid_station_id,
                "total_time_min": record["total_time"],
                "stations": stations,
                "legs": legs
            }


# ── 4. CROSS-NETWORK INTERCHANGE PATH ────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a route connecting the city metro and national rail, enforcing 
    cross-network transfer topology mapping validation.
    """
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    MATCH path = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..15]-(end)
    WHERE ANY(rel IN relationships(path) WHERE type(rel) = 'INTERCHANGE_TO')
    WITH path,
         reduce(t = 0, r IN relationships(path) | t + coalesce(r.travel_time_min, 0)) AS total_time
    RETURN path, total_time
    ORDER BY total_time ASC
    LIMIT 1
    """
    
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher_query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            
            if not record:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "message": "No active cross-network interchange route found."
                }
            
            path = record["path"]
            stations = [{"station_id": n.get("station_id"), "name": n.get("name")} for n in path.nodes]
            legs = []
            interchange_points = []
            
            for r in path.relationships:
                legs.append({
                    "type": r.type,
                    "line": r.get("line", "Interchange"),
                    "travel_time_min": r.get("travel_time_min", 0)
                })
                if r.type == 'INTERCHANGE_TO':
                    interchange_points.append({
                        "from_station": r.start_node.get("station_id"),
                        "to_station": r.end_node.get("station_id")
                    })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time"],
                "interchange_points": interchange_points,
                "stations": stations,
                "legs": legs
            }


# ── 5. DELAY RIPPLE ANALYSIS ──────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Analyze and trace propagation ripple delays affecting nearby neighboring stations.
    """
    cypher_query = """
    MATCH (disrupted {station_id: $delayed_station_id})
    MATCH path = (disrupted)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..$hops]-(affected)
    WHERE disrupted <> affected
    RETURN DISTINCT affected.station_id AS station_id,
                    affected.name AS name,
                    length(path) AS hops_away,
                    [r IN relationships(path) | coalesce(r.line, 'Interchange')] AS lines_involved
    ORDER BY hops_away ASC
    """
    
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher_query, delayed_station_id=delayed_station_id, hops=hops)
            
            ripple_effects = []
            seen_stations = set()
            
            for record in result:
                st_id = record["station_id"]
                if st_id not in seen_stations:
                    seen_stations.add(st_id)
                    lines = list(set(record["lines_involved"]))
                    if "Interchange" in lines and len(lines) > 1:
                        lines.remove("Interchange")
                        
                    ripple_effects.append({
                        "station_id": st_id,
                        "name": record["name"],
                        "hops_away": record["hops_away"],
                        "lines_affected": lines
                    })
                    
            return ripple_effects


# ── 6. STATION CONNECTIONS ────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    Fetch direct, immediate next-stop station neighbors bordering the given station.
    """
    cypher_query = """
    MATCH (start {station_id: $station_id})-[r:METRO_LINK|RAIL_LINK]->(neighbor)
    RETURN neighbor.station_id AS station_id,
           neighbor.name AS name,
           r.line AS line,
           type(r) AS connection_type,
           r.travel_time_min AS travel_time_min
    ORDER BY line ASC, name ASC
    """
    
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher_query, station_id=station_id)
            connections = []
            for record in result:
                connections.append({
                    "station_id": record["station_id"],
                    "name": record["name"],
                    "line": record["line"],
                    "connection_type": "metro" if record["connection_type"] == "METRO_LINK" else "national_rail",
                    "travel_time_min": record["travel_time_min"]
                })
            return connections