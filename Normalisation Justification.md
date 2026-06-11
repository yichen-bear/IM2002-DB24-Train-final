## Section 2 — Normalisation Justification

### 1. Relational Normalisation Decisions (3NF)

在 TransitFlow 系統的關聯式資料庫設計中，全面貫徹了 **Third Normal Form (3NF，第三正規化)** 的標準，旨在自底層消除資料冗餘（Data Redundancy）、根絕結構性的更新異常（Update Anomalies），並維護高併發運輸環境下的資料一致性。

本系統中一項展現 3NF 設計決策的具體實例，在於基礎車站主資料（Master Data）與動態營運路線排程（Operational Schedules）的解耦架構。在實作上，系統並未將車站屬性與路線費率混雜在單一表格中，而是將其嚴格拆分為 `metro_stations`（地鐵車站表）與 `metro_schedules`（地鐵班次排程表）兩張獨立的實體資料表。

* **Candidate Keys 與 Functional Dependencies（功能相依）之分析**：

  若在反正規化的單一巨型實體（Monolithic Entity）中進行設計，其潛在的 composite candidate key（複合候選鍵）可能包含 `station_id`。然而，在未經正規化的架構中，其 Functional Dependency（功能相依性）將呈現如下缺陷：

  $$
  \text{station\_id} \rightarrow \text{name}, \text{lines}, \text{metro\_schedule\_id}, \text{line}, \text{base\_fare\_usd}, \text{per\_stop\_rate\_usd}
  $$

  在此模型中，`base_fare_usd`（基本票價）與 `per_stop_rate_usd`（每站費率計價）在本質上是完全取決於特定的營運線路（由 `metro_schedule_id` 唯一識別），而非相依於物理上的車站實體。這首先違反了 **Second Normal Form (2NF)** 關於「非主屬性（Non-prime attributes）不得部分相依於候選鍵」的規範。同時，該結構亦引入了 **Transitive Dependency（遞移相依）**：

  $$
  \text{station\_id} \rightarrow \text{metro\_schedule\_id} \rightarrow \text{base\_fare\_usd}
  $$

  一旦某條捷運線路的計費標準發生變更，資料庫將被迫同步更新該線路旗下所有車站的元組（Tuples），進而引發嚴重的資料不一致與更新異常。

* **藉由綱要解耦（Schema Decoupling）達成 3NF 合規性**：

  為了解決上述缺陷，本專案的 `schema.sql` 實作了完全解耦的 3NF 架構。車站的物理特徵（如 `name`、`lines` 等陣列欄位）被隔離於 `metro_stations` 表中，並以 `station_id` 作為 Primary Key（主鍵）；而營運線路的計費標準則獨立收錄於 `metro_schedules` 表中，以 `metro_schedule_id` 作為 Primary Key。
  
  透過此項設計，所有非鍵屬性（Non-key attributes）皆嚴格相依於「主鍵、完整的主鍵，且僅有主鍵（the key, the whole key, and nothing but the key）」。當特定車站名稱變更或特定線路費率調整時，資料庫皆僅需針對相應資料表進行單一元組（Single Tuple）的局部更新，徹底在結構上杜絕了更新異常，保證了關聯查詢（Relation Joins）時的資料完整性。

---

### 2. Deliberate De-normalisation Trade-offs

在本系統的架構規劃中，針對核心的交易骨幹網路——特別是涉及票務分類帳的 `bookings`（訂單表）與財務審計軌跡的 `payments`（支付明細表）——**本專案明確拒絕了任何反正規化（De-normalisation）的設計，並判定 3NF 的完整正規化為此類高度併發金融系統的最佳解。**

* **一致性（Consistency）與效能（Performance）的權衡論證**：

  在分散式或高頻讀取的應用情境中，反正規化常見的作法是將交易金額或訂單狀態直接以冗餘欄位（Redundant Columns）的形式拷貝或快取至 `users`（用戶表）中，以期在執行高頻查詢時減少 SQL `JOIN` 語句的 CPU 開銷。然而，在大眾運輸系統的營運生態中，票務系統必須在高併發的 Race Conditions（競爭條件）下運作。
  
  若用戶同時觸發即時退票（Ticket Cancellation）與新訂單扣款，若採用反正規化結構，跨表之間的非同步資料同步延遲（Data Sync Lag），將導致用戶的可見錢包餘額與核心票務生命週期狀態（Lifecycle State）產生誠信度落差（Integrity Mismatch）。

* **結論**：

  為了確保底層金融與稽核數據具備絕對的防禦性與不可篡改性，系統在 `schema.sql` 中引入了嚴格的 Foreign Key（外鍵）約束（如 `REFERENCES users(user_id) ON DELETE CASCADE`），強制透過正規化鏈條進行狀態變更。
  
  在評估大眾運輸系統對於金流正確性的極端要求後，執行關聯式多表 `JOIN`（例如在 `queries.py` 實作的 `query_user_bookings` 中跨 `bookings` 與 `schedules` 撈取數據）所產生的微小運算開銷，是為了消弭金融資料異常（Financial Anomalies）而必須且完全合理的 Trade-off。

---

### 3. Cryptographic Password Hashing & Salt Management

為了保障用戶憑證（User Credentials）的隱私安全並防止潛在的資料庫外洩風險，本系統於用戶驗證層（Authentication Layer）導入了符合工業級標準的 **Argon2id** 密碼學雜湊演算法，在架構設計中全面禁止使用已被證實具備安全漏洞的傳統雜湊基元（Legacy Primitives）如 MD5 或 SHA-1。

* **選用 Argon2id 取代替代方案（MD5/SHA-1）之核心理由**：

  MD5 與 SHA-1 本質上屬於追求極致執行效率的通用型密碼學雜湊函數（General-purpose Hash Functions）。由於其缺乏內在的計算複雜度約束，一旦系統資料庫遭到惡意拖庫（Database Breach），外部攻擊者可輕易利用現代消費級 GPU 叢集或客製化 ASIC 晶片硬體，進行每秒高達數十億次的高速暴力破解（Brute-force Cracking）。
  
  作為密碼雜湊競賽（Password Hashing Competition）的優勝演算法，Argon2id 藉由 **Key Stretching（金鑰延伸）** 機制，將雜湊運算與不可忽略的硬體資源開銷進行強制綁定。其引入了三項可配置的數學成本參數（Cost Factors）：

  1. **Memory Cost（記憶體開銷）**：定義了計算單一雜湊所必須佔用的專用 RAM 區塊大小。此項設計具備 **Memory-hard（記憶體困難）** 特性，能有效使缺乏大容量快取的平行運算硬體（如 GPU/ASIC）因記憶體頻寬枯竭而陷入效能癱瘓。
  2. **Time Cost（時間開銷）**：嚴格控制演算法內部的順序迭代次數（Iterations），藉此拉長單次密碼驗證的執行時間。
  3. **Parallelism（並行度）**：指定運算時必須配置的底層 CPU 執行緒（Threads）數量。

  透過這些參數的交叉配置（在 Python 實作中自動呼叫符合工業級基線的預設參數值），Argon2id 在物理層面上對攻擊者課徵了極高的硬體算力成本，使得大規模的密碼破解在經濟與計算上均變得完全不可行。

* **Salt（鹽值）防禦 Rainbow-Table Attacks（彩虹表攻擊）之運作機制**：

  若資料庫僅儲存單純的密碼雜湊值，當兩位不同的用戶恰好設定了相同的常用密碼（例如 `"Transit2026"`）時，未加鹽的雜湊函數將在資料庫中寫入完全相同的十六進制字串。攻擊者便可利用預先計算好的大規模常用詞彙雜湊對照矩陣——即 **Rainbow Tables（彩虹表）**——來對外洩的資料庫進行瞬間的反向工程破解。
  
  Argon2id 的防禦機制是在雜湊運算啟動前，自動為每一個用戶帳號隨機生成一段由具備加密強度（Cryptographically Secure）的隨機位元組序列組成之 **Salt（鹽值）**，並將其與明文密碼進行拼接：

  $$
  \text{Hash} = \text{Argon2id}(\text{Plaintext Password} + \text{Unique Salt})
  $$

  由於系統中每一個用戶實體所獲配的鹽值皆是絕對獨立且隨機的，因此即使兩位用戶的明文密碼完全一致，最終寫入資料庫欄位的雜湊字串也會變得毫無關聯。此舉徹底瓦解了預先計算的彩虹表檢索機制，迫使攻擊者必須放棄批次對照的捷徑，轉而對個別帳戶進行代價高昂的單獨破譯，從而將系統的認證安全性提升至防禦級別。