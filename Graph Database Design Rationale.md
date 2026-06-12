# Section 3 — Graph Database Design Rationale

## 1. Data Modeling Decision (Nodes, Relationships, Properties)

我們在設計這個圖資料庫架構時，不是單純因為「車站是個東西」就把它放成節點，而是根據 `train-mock-data` 的結構，把資料拆成三個層級：

### Nodes（節點標籤設計）
我們在 `seed_neo4j.py` 裡建立了兩種標籤：`(:MetroStation)` 與 `(:NationalRailStation)`。
* **為什麼這樣做**：雖然它們都是車站，但在現實中地鐵和國鐵是兩個完全不同的交通網路。如果直接混在一起，之後寫 Cypher 查純地鐵線路時，圖形引擎就得去掃描所有的國鐵車站。把標籤分開，程式在第一步就能直接過濾掉不需要看的網路，能省下很多加載時間。

### Relationships（關係類型設計）
關係部分建立了三個種類：`-[:METRO_LINK]->`、`-[:RAIL_LINK]->` 以及雙向的 `-[:INTERCHANGE_TO]->`。
* **為什麼這樣做**：`METRO_LINK` 和 `RAIL_LINK` 用來代表各自系統內部的物理鐵軌連接。而 `-[:INTERCHANGE_TO]->` 是用來連通相鄰的地鐵站和國鐵站。這種設計可以讓尋路演算法在跑地鐵導航時，直接忽略 `RAIL_LINK`，不需要點進節點去看屬性才知道能不能走，在記憶體裡走訪的速度會快很多。

### Properties（屬性設計）
* **節點**：放 `station_id`、`name`、`lines` 等固定不變的靜態名稱與營運線路。
* **關係（邊）**：
  * 對於 **`METRO_LINK`** 與 **`RAIL_LINK`**：我們把 `travel_time_min`（行車時間）、`line`（營運線路名稱）及 `network_type` 直接塞在關係邊上。因為行車時間是拿來算路徑權重的核心指標，當演算法沿著邊找下一站時，可以直接在邊上讀到時間並累加，不用每次都點進目標節點裡面翻資料，能大幅減少記憶體讀取次數。
  * 對於 **`INTERCHANGE_TO`**：該關係純粹代表地鐵與國鐵之間的**站外/站內轉乘通道連通性**，在 seeder 中保持輕量化，**不帶任何屬性（無 `travel_time_min` 與 `line`）**，避免為無關的物理連動強加通用的路網屬性。

---

## 2. Graph vs. Relational Database Routing Argument

在處理路網尋路（例如找最短路徑或分析延遲連鎖反應）時，用圖資料庫（Neo4j）和傳統關聯式資料庫（PostgreSQL）做，兩者的演算法邏輯有很大的差別。

### 如果用關聯式資料庫（SQL 遞迴 CTE）
在 SQL 裡面，如果要算 A 站到 B 站中間轉乘好幾站的路徑，必須要用 `WITH RECURSIVE` 寫遞迴查詢。
* **背後代價**：SQL 只要多走一站（搜尋深度加深），系統就必須把 `station_adjacencies` 這張表跟自己做一次 `Join`。當你要計算所有可能路徑的集合時，時間複雜度會隨深度變成指數型成長 $O(R^d)$。這會在記憶體裡產生一堆暫存表跟排序開銷，只要路網稍微複雜一點，查詢就會直接超時卡死。

### 如果用圖資料庫（Neo4j 免索引鄰接）
Neo4j 底層用的是 **免索引鄰接（Index-Free Adjacency）** 的技術。
* **背後優勢**：在 `seed_neo4j.py` 把節點和關係建立好之後，每個車站節點內部就已經記錄了指向旁邊車站的記憶體指標。當我們跑權重路徑展開或廣度優先搜尋（BFS）時，引擎只要跟著這些指針在記憶體裡直接「跳轉」到下一站就好。它的時間複雜度只跟走過的節點和邊的數量有關，不管資料庫總共有幾百萬筆資料，查起來速度都一樣快，完全避開了 SQL 做 Join 的高昂代價。

---

## 3. Query Types Analysis

透過我們設計的圖架構與實際在 `queries.py` 中的實作，可以很輕鬆地寫出下面兩種不同情境的 Cypher 查詢：

### 查詢一：動態跨網路最省時路徑（Pure Cypher Weighted Path Expansion & Sorting）
* **情境**：用戶想從某個特定起點站出發，找出轉乘至特定終點站最省時的路線。
* **Cypher 語法**：
    ```cypher
    MATCH p = (src {station_id: "METRO_001"})-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..15]->(dest {station_id: "RAIL_099"})
    RETURN p, 
           reduce(total = 0, r IN relationships(p) | total + coalesce(r.travel_time_min, 0)) AS total_time
    ORDER BY total_time ASC
    LIMIT 1
    ```
* **架構如何支持**：為了避免內建 `shortestPath()` 只計算「最少站數（Min Hops）」而非「最短時間（Min Travel Time）」的缺陷，我們的 `queries.py` 實作採用了**定長權重路徑展開（1 到 15 hops）**的策略。
* 由於轉乘關係 `INTERCHANGE_TO` 上沒有 `travel_time_min` 屬性，我們在 Cypher 中利用 `coalesce(r.travel_time_min, 0)` 進行動態防空值處理。圖形引擎能夠極速沿著指標拉出所有候選路徑 `p`，並在記憶體內直接將各邊的權重累加，最後透過 `ORDER BY total_time` 篩選出真正最省時的跨網路路線。

### 查詢二：轉乘樞紐核心度分析（Hub and Dependency Analysis）
* **情境**：找出有哪些車站是核心轉乘點（連接著最多的營運線路），用來做人流管制或系統脆弱性評估。
* **Cypher 語法**：
    ```cypher
    MATCH (s)-[r]->()
    WHERE s:MetroStation OR s:NationalRailStation
    RETURN s.station_id AS ID, s.name AS Name, count(DISTINCT r.line) AS LineCount
    ORDER BY LineCount DESC
    LIMIT 5
    ```
* **架構如何支持**：這類查詢看重的是路網的「拓撲結構」。因為每個系統內部關係（`METRO_LINK` 與 `RAIL_LINK`）上都有帶線路名稱（`r.line`），Neo4j 只要直接數一下節點伸出去的邊（Degree）並做去重計數，在非常低的複雜度下就能抓出前五名的核心樞紐站。在關聯式資料庫裡這得拿基礎設施變動表做好幾層 `GROUP BY` 才算得出來。

---

## 4. Node Identity Strategy

### 唯一識別屬性
我們選擇 **`station_id`**（例如 `"METRO_001"` 或 `"RAIL_045"`）作為每個節點的唯一識別屬性。

### 為什麼選擇它
1. **防止名稱重複**：車站名稱（`name`）在現實中很容易重名（例如地鐵有台北車站，國鐵也有台北車站），而且站名未來規模擴大後可能會改。用全域唯一的 `station_id` 可以保證圖形結構絕對不會認錯站。
2. **跟 PostgreSQL 連動（Polyglot Persistence）**：這個 `station_id` 跟我們在關聯式資料庫（PostgreSQL）裡地鐵表、國鐵表設計的 **Primary Key（主鍵）** 是一模一樣的。
3. **架構分流職責**：有了這個共通的 ID，我們就能做雙軌資料庫分流。那些需要強大交易安全（ACID）、商務邏輯複雜的商業資料（像是 `bookings` 訂單狀態、`payments` 金流明細、使用者帳密雜湊），乖乖留在 **PostgreSQL** 處理；而高頻率的路徑規劃、導航、轉乘時間計算，就直接拿著同一個 `station_id` 來 **Neo4j** 跑圖遍歷。兩邊互相配合，是最合理的系統架構。