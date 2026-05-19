import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)

def load_json(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return {station["station_id"]: station for station in json.load(f)}

def verify_data():
    # 1. 讀取原始 JSON 檔案
    print("📋 正在讀取原始 JSON 檔案...")
    json_metro = load_json("metro_stations.json")
    json_rail = load_json("national_rail_stations.json")
    
    # 2. 連線到 Neo4j 資料庫
    print("🌐 正在連線至 Neo4j 資料庫...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    error_count = 0
    
    with driver.session() as session:
        # ---- 檢查 A：比對地鐵車站 (MetroStation) ----
        print("\n🔍 開始比對地鐵車站節點 (MetroStation)...")
        result = session.run("MATCH (m:MetroStation) RETURN m")
        db_metro_count = 0
        
        for record in result:
            db_metro_count += 1
            node = record["m"]
            s_id = node["station_id"]
            
            if s_id not in json_metro:
                print(f"❌ 錯誤：資料庫中存在地鐵站 ID {s_id}，但 JSON 檔案裡找不到！")
                error_count += 1
                continue
                
            json_node = json_metro[s_id]
            # 比對基本屬性
            if node["name"] != json_node["name"]:
                print(f"❌ 欄位不符 [{s_id}]：資料庫名稱 '{node['name']}' != JSON名稱 '{json_node['name']}'")
                error_count += 1
                
        if db_metro_count != len(json_metro):
            print(f"❌ 數量不符：JSON 有 {len(json_metro)} 個地鐵站，但資料庫只有 {db_metro_count} 個！")
            error_count += 1
        else:
            print(f"✅ 地鐵車站基本資料比對完成（共 {db_metro_count} 筆成功對齊）")

        # ---- 檢查 B：比對國鐵車站 (NationalRailStation) ----
        print("\n🔍 開始比對國鐵車站節點 (NationalRailStation)...")
        result = session.run("MATCH (r:NationalRailStation) RETURN r")
        db_rail_count = 0
        
        for record in result:
            db_rail_count += 1
            node = record["r"]
            s_id = node["station_id"]
            
            if s_id not in json_rail:
                print(f"❌ 錯誤：資料庫中存在國鐵站 ID {s_id}，但 JSON 檔案裡找不到！")
                error_count += 1
                continue
                
            json_node = json_rail[s_id]
            if node["name"] != json_node["name"]:
                print(f"❌ 欄位不符 [{s_id}]：資料庫名稱 '{node['name']}' != JSON名稱 '{json_node['name']}'")
                error_count += 1
                
        if db_rail_count != len(json_rail):
            print(f"❌ 數量不符：JSON 有 {len(json_rail)} 個國鐵站，但資料庫只有 {db_rail_count} 個！")
            error_count += 1
        else:
            print(f"✅ 國鐵車站基本資料比對完成（共 {db_rail_count} 筆成功對齊）")

        # ---- 檢查 C：比對相鄰關係連通性 ----
        print("\n🔍 開始驗證資料庫中的路線連線 (METRO_LINK / RAIL_LINK)...")
        # 拿一筆地鐵連線測試
        metro_links = session.run("MATCH ()-[r:METRO_LINK]->() RETURN count(r) AS c").single()["c"]
        rail_links = session.run("MATCH ()-[r:RAIL_LINK]->() RETURN count(r) AS c").single()["c"]
        
        # 計算 JSON 裡面預期應該要有幾條線
        expected_metro_links = sum(len(s["adjacent_stations"]) for s in json_metro.values())
        expected_rail_links = sum(len(s["adjacent_stations"]) for s in json_rail.values())
        
        if metro_links != expected_metro_links:
            print(f"❌ 地鐵連線數不符：JSON 預期 {expected_metro_links} 條，資料庫實際建立 {metro_links} 條")
            error_count += 1
        else:
            print(f"✅ 地鐵相鄰路線數量正確（共 {metro_links} 條連線）")
            
        if rail_links != expected_rail_links:
            print(f"❌ 國鐵連線數不符：JSON 預期 {expected_rail_links} 條，資料庫實際建立 {rail_links} 條")
            error_count += 1
        else:
            print(f"✅ 國鐵相鄰路線數量正確（共 {rail_links} 條連線）")

    driver.close()
    
    print("\n========================================")
    if error_count == 0:
        print("🎉 恭喜！Neo4j 圖形資料庫的資料與您的 JSON 檔案 100% 完全一致！")
    else:
        print(f"⚠️ 檢查結束，共發現 {error_count} 處資料不一致，請檢查 seed_neo4j.py 是否有漏掉欄位。")
    print("========================================")

if __name__ == "__main__":
    verify_data()