"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.

GRAPH ROLE:
  - Model the dual transit network (city metro M1–M4 + national rail NR1–NR2)
  - Find fastest routes (Dijkstra by travel_time_min via APOC)
  - Find cheapest routes (Dijkstra by fare via APOC)
  - Find alternative routes avoiding a given station
  - Find cross-network interchange paths (metro → rail or rail → metro)
  - Show delay ripple: which stations are affected within N hops

STUDENT TASK
------------
Design your graph schema (node labels, relationship types, properties)
based on the data in train-mock-data/, seed it with skeleton/seed_neo4j.py,
then implement the query_ functions below.

Functions prefixed with `query_` are called by the agent (skeleton/agent.py).
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]

# TODO: Implement the query_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    找出從起點到終點的最快路徑 (最短旅行時間)。
    """
    # 我們允許路徑走 METRO_LINK、RAIL_LINK 或是 INTERCHANGE 轉乘
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    CALL apoc.algo.dijkstra(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE', 'travel_time_min')
    YIELD path, weight
    RETURN path, weight AS total_time_min
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
                    "message": "No route found between these stations."
                }
            
            path = record["path"]
            total_time = record["total_time_min"]
            
            stations = []
            legs = []
            
            for node in path.nodes:
                stations.append({
                    "station_id": node.get("station_id"),
                    "name": node.get("name")
                })
                
            for rel in path.relationships:
                legs.append({
                    "type": rel.type,
                    "line": rel.get("line", "Interchange"), # 如果是轉乘可能沒有line屬性
                    "travel_time_min": rel.get("travel_time_min", 0) # 轉乘時間若沒設預設為0
                })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": total_time,
                "stations": stations,
                "legs": legs
            }
            

# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest path between two stations, minimising total estimated fare.
    (Since explicit fare weights aren't in Neo4j, we estimate by finding the fewest stops/hops).
    """
    # 使用 Neo4j 內建的 shortestPath，它會預設尋找「經過節點最少 (最少站)」的路徑
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    MATCH path = shortestPath((start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE*]-(end))
    RETURN path, length(path) AS total_hops
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
                    "message": "No route found between these stations."
                }
            
            path = record["path"]
            total_hops = record["total_hops"]
            
            stations = []
            legs = []
            
            # 解析途經車站
            for node in path.nodes:
                stations.append({
                    "station_id": node.get("station_id"),
                    "name": node.get("name")
                })
                
            # 解析搭乘區段
            for rel in path.relationships:
                legs.append({
                    "type": rel.type,
                    "line": rel.get("line", "Interchange"),
                    "network": rel.get("network_type", "transfer")
                })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "fare_class": fare_class,
                "estimated_fare_strategy": "fewest_stops", # 告知 AI 這是用最少站數估算的
                "total_hops": total_hops,                  # 總共搭了幾站
                "stations": stations,
                "legs": legs
            }
            

# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
) -> dict:
    """
    Finds the shortest path avoiding a specific station (e.g., due to closure or delay).
    """
    # 關鍵語法：WHERE ALL(node IN nodes(path) WHERE node.station_id <> $avoid_station_id)
    # 這行會強制 Neo4j 在找路時，只要碰到避開的車站就回頭找別條路。
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    MATCH path = shortestPath((start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE*]-(end))
    WHERE ALL(node IN nodes(path) WHERE node.station_id <> $avoid_station_id)
    RETURN path, length(path) AS total_hops
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
                return [{
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "avoid_station_id": avoid_station_id,
                    "message": f"No alternative route found avoiding {avoid_station_id}."
                }]
            
            path = record["path"]
            total_hops = record["total_hops"]
            
            stations = []
            legs = []
            
            for node in path.nodes:
                stations.append({
                    "station_id": node.get("station_id"),
                    "name": node.get("name")
                })
                
            for rel in path.relationships:
                legs.append({
                    "type": rel.type,
                    "line": rel.get("line", "Interchange"),
                    "network": rel.get("network_type", "transfer")
                })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "avoid_station_id": avoid_station_id,
                "total_hops": total_hops,
                "stations": stations,
                "legs": legs
            }


# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a path between a metro station and a national rail station (or vice versa)
    crossing the network boundary via interchange relationships.
    """
    # 強制路徑中必須包含至少一段 INTERCHANGE 連線
    cypher_query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    MATCH path = shortestPath((start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE*]-(end))
    WHERE any(rel IN relationships(path) WHERE type(rel) = 'INTERCHANGE')
    RETURN path, 
           length(path) AS total_hops,
           reduce(s = 0, r IN relationships(path) | s + coalesce(r.travel_time_min, 0)) AS total_time_min
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
                    "message": "No interchange route found between these stations."
                }
            
            path = record["path"]
            
            stations = []
            legs = []
            interchange_points = []
            
            for node in path.nodes:
                stations.append({
                    "station_id": node.get("station_id"),
                    "name": node.get("name")
                })
                
            for rel in path.relationships:
                rel_type = rel.type
                legs.append({
                    "type": rel_type,
                    "line": rel.get("line", "Interchange"),
                    "travel_time_min": rel.get("travel_time_min", 0)
                })
                # 紀錄在哪裡發生了轉乘
                if rel_type == 'INTERCHANGE':
                    interchange_points.append({
                        "from_station": rel.start_node.get("station_id"),
                        "to_station": rel.end_node.get("station_id")
                    })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "total_hops": record["total_hops"],
                "interchange_points": interchange_points,
                "stations": stations,
                "legs": legs
            }
            

# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    找出受故障車站波及的周圍車站（N 步之內的所有車站）。
    """
    # 透過 *1..$hops 語法，找出從故障站出發，在指定步數內可以走到的所有相鄰站
    cypher_query = """
    MATCH (disrupted {station_id: $delayed_station_id})
    MATCH path = (disrupted)-[:METRO_LINK|RAIL_LINK|INTERCHANGE*1..$hops]-(affected)
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
            seen_stations = set() # 用來避免同一個車站在不同路徑被重複算到
            
            for record in result:
                st_id = record["station_id"]
                # 確保同一個車站只保留最短的那次步數
                if st_id not in seen_stations:
                    seen_stations.add(st_id)
                    
                    # 整理受影響的路線清單（去除重複的轉乘標籤）
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
        

# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    列出指定車站所有直接相連（直達）的相鄰車站與路線資訊。
    """
    # 這裡我們不限節點 Label，只要關係是 METRO_LINK 或 RAIL_LINK 就找出來
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
        
        