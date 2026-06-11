## Section 2 — Normalisation Justification

### 1. Relational Normalisation Decisions (3NF)

在 TransitFlow 系統的核心關聯式資料庫設計中，特別是班次、車站、停靠順序與交易資料的設計上，本專案以 **Third Normal Form (3NF，第三正規化)** 為主要設計原則，旨在降低資料冗餘（Data Redundancy）、避免結構性的更新異常（Update Anomalies），並維護資料的一致性。

本系統中一項展現 2NF 與 3NF 設計決策的核心實例，在於解決「車站（Stations）」與「營運班次（Schedules）」之間複雜的多對多（M:N）關係，我們藉由導入聯合表（Junction Table）`metro_schedule_stops` 與 `national_rail_schedule_stops` 來進行完美的綱要解耦。

* **Candidate Keys 與 Functional Dependencies（功能相依）之分析**：
  若在未經正規化的不良設計中，開發者可能會試圖將班次與停靠站資訊硬塞在同一張表中。在這種情況下，若以複合鍵 `{schedule_id, station_id}` 作為 Primary Key，非主屬性（如班次所屬的 `line`、票價欄位，或停靠關係中的 `travel_time_offset`）將產生混亂的相依關係。
  
  具體而言：`line` 僅相依於 `schedule_id`，而 `station_name` 僅相依於 `station_id`（這兩者皆為部分相依，違反 2NF）；同時，停靠關係本身的屬性如 `travel_time_offset` 則應嚴格相依於完整的 `{schedule_id, stop_order}` 組合。若強行合併，不僅引發資料重複，一旦車站改名更會造成全表多處的 Update Anomalies。

* **藉由 Junction Table 達成 3NF 合規性**：
  為了解決上述缺陷，本專案的 Schema 實作了完全解耦的 3NF 架構：
  1. 將實體分離：車站基礎屬性存放於 `metro_stations`，班次通用屬性存放於 `metro_schedules`。
  2. 建立中介表：透過 `metro_schedule_stops` 作為聯合表，使用複合主鍵 `{metro_schedule_id, stop_order}` 來記錄特定班次在特定停靠順序上的車站（`station_id`）與相對行車時間（`travel_time_offset`）。

  透過此項設計，所有非鍵屬性（Non-key attributes）皆嚴格相依於「主鍵、完整的主鍵，且僅有主鍵（the key, the whole key, and nothing but the key）」。此決策徹底根絕了 Partial Dependency（部分相依）與 Transitive Dependency（遞移相依），保證了關聯查詢時的結構完整性。

---

### 2. Deliberate De-normalisation Trade-offs

在本系統的架構規劃中，雖然基礎資料維持嚴格的 3NF，但針對核心交易表 `bookings`（訂單），**本專案刻意採用了「歷史快照（Transaction Snapshot）」的設計模式，這是一項經過深思熟慮的有意反正規化（Deliberate De-normalisation）權衡。**

* **審計正確性（Audit Accuracy）與歷史不可變性之權衡論證**：
  在嚴格正規化的設計下，訂單金額與起訖站資訊可以透過 `JOIN` 回 `schedules`、`national_rail_schedule_stops` 與站點資料表，並依照票價欄位（如 `base_fare_standard_usd`、`per_stop_standard_usd`、`base_fare_first_usd` 等）動態重新計算。然而，在大眾運輸與電子商務系統中，票價基準（Base Fare）與車站營運狀態是會隨時間變更的。
  
  如果明天系統調漲了票價，嚴格 3NF 下動態 `JOIN` 算出來的歷史訂單金額將會跟著改變，這將導致災難性的財務帳目不一致與稽核失敗。

* **結論**：
  為了解決此問題，我們在 `bookings` 資料表中，刻意將 `amount_usd`（交易金額）、`departure_time`（出發時間）、`origin_station_id` 等當下狀態，直接作為冗餘欄位存儲下來。
  
  此種反正規化設計將當下的營運狀態「凍結」為歷史快照。同時，我們搭配嚴格的 Foreign Key 約束（例如在訂單關聯 `bookings.user_id` 中採用 `ON DELETE RESTRICT`，嚴禁輕易刪除帶有交易紀錄的使用者，而非危險的 `CASCADE`），確保了金融稽核數據具備絕對的不可篡改性與歷史正確性。這是為了滿足商業金流邏輯而必須且完全合理的 Trade-off。

---

### 3. Cryptographic Password Hashing & Salt Management

為了保障用戶憑證（User Credentials）的隱私安全並防止潛在的資料庫外洩風險，本系統的應用程式層（Application Layer）導入了符合工業級標準的 **Argon2id** 密碼學雜湊演算法，且資料庫的 `user_credentials.password_hash` 欄位結構亦專門設計用於存儲其生成的複雜雜湊值，全面淘汰已被證實具備安全漏洞的傳統基元如 MD5 或 SHA-1。

* **選用 Argon2id 取代替代方案（MD5/SHA-1）之核心理由**：
  MD5 與 SHA-1 本質上屬於追求極致執行效率的通用型密碼學雜湊函數。由於其缺乏內在的計算複雜度約束，一旦系統資料庫遭到惡意拖庫（Database Breach），外部攻擊者可輕易利用現代消費級 GPU 叢集或 ASIC 晶片，進行每秒高達數十億次的高速暴力破解（Brute-force Cracking）。
  
  作為密碼雜湊競賽（Password Hashing Competition）的優勝演算法，Argon2id 藉由 **Key Stretching（金鑰延伸）** 機制，將雜湊運算與硬體資源開銷進行強制綁定。其引入了三項數學成本參數（Cost Factors）：

  1. **Memory Cost（記憶體開銷）**：設定計算單一雜湊所必須佔用的 RAM 區塊大小。此 **Memory-hard（記憶體困難）** 特性，能有效使平行運算硬體（如 GPU）因記憶體頻寬枯竭而陷入效能癱瘓。
  2. **Time Cost（時間開銷）**：控制順序迭代次數（Iterations），拉長單次密碼驗證的執行時間。
  3. **Parallelism（並行度）**：指定運算時的 CPU 執行緒（Threads）數量。

  這些設計在物理層面上對攻擊者課徵了極高的算力成本，使得大規模密碼破解在經濟上完全不可行。

* **Salt（鹽值）防禦 Rainbow-Table Attacks（彩虹表攻擊）之運作機制**：
  若資料庫僅儲存單純的密碼雜湊值，當兩位用戶設定了相同的常用密碼（例如 `"Transit2026"`）時，未加鹽的函數會產生完全相同的十六進制字串。攻擊者便可利用預先計算好的大規模常用詞彙雜湊對照矩陣——即 **Rainbow Tables（彩虹表）**——來瞬間進行反向破解。
  
  Argon2id 在雜湊運算啟動前，會自動為每個帳號生成一段具備加密強度（Cryptographically Secure）的隨機位元組序列（**Salt 鹽值**），並將其與明文密碼拼接：

  $$
  \text{Hash} = \text{Argon2id}(\text{Plaintext Password} + \text{Unique Salt})
  $$

  由於每個用戶的鹽值皆絕對獨立且隨機，即使兩位用戶明文密碼完全一致，寫入資料庫 `password_hash` 欄位的字串也會變得毫無關聯。此舉徹底瓦解了彩虹表檢索機制，迫使攻擊者必須逐一對個別帳戶進行代價高昂的單獨破譯。