# Section 4 — Vector / RAG Design

## 1. Embedding and Cosine Similarity Rationale

在我們這個火車客服系統裡，要丟去算 Embedding（向量化）的對象，就是放在資料庫 `policy_documents` 資料表裡面的官方規章與退票政策文字檔。

### 為什麼做語意搜尋（Semantic Search）時，用餘弦相似度（Cosine Similarity）最適合？
最核心的原因就是餘弦相似度具備**大小無關性（Magnitude-Independent）**，它在向量空間中算的是**方向相似度（Directional Similarity）**，而不會被向量的長度大小給影響。

這在我們的客服系統中非常重要。因為一般使用者進來問問題時，通常都打得很短（例如：「怎麼退票」），但我們資料庫裡存的官方退票政策，往往是一大串好幾百字的法條。如果把這兩段文字拿去轉成向量，它們的長度（Magnitude）會差非常多。
* **如果用歐氏距離（Euclidean Distance）**：系統去算距離時，會因為這兩個向量長度差太多，誤判定這兩個句子不相似，結果就撈不到答案。
* **如果用餘弦相似度（Cosine Similarity）**：系統只會看它們在空間中的夾角方向。只要兩邊的話題都是在講退票，它們的方向就會很接近，系統就能準確把這條政策撈出來。

---

## 2. Full RAG Pipeline Workflow

我們實作的檢索增強生成（RAG）功能，從使用者輸入問題到最後看到答案，底層完整的 Pipeline 跑了以下四個階段：

1. **Query Embedding**
   使用者在客服介面送出問題後，後端程式會先呼叫 Ollama 的 `nomic-embed-text` 模型，把這段問題文字轉換成一組固定長度的浮點數陣列（也就是問題向量）。
2. **Similarity Search**
   拿到問題向量後，系統會直接去 PostgreSQL 的 `policy_documents` 表下 SQL 查詢。我們在資料庫有針對 embedding 欄位建立 `USING hnsw (embedding vector_cosine_ops)` 索引，所以資料庫可以用餘弦相似度在裡面進行高速的比對。
3. **Retrieved Documents**
   資料庫會根據餘弦相似度算出來的分數，把最相關的幾筆官方政策原始文字（Context）撈出來，做為大模型回答時的依據。
4. **LLM Prompt $\rightarrow$ Answer**
   Python 後端會把「使用者的問題」跟剛才撈出來的「官方參考文件」包進我們寫好的 Prompt 模板裡，限制大模型一定要根據官方規定回答。最後把這個組裝好的 Prompt 丟給大語言模型（LLM），等模型生成出正確且口吻親切的客服答案後，再回傳給前端使用者。

---

## 3. Embedding Dimension Choice and Provider Switch Impact

### 維度選擇
看我們 `schema.sql` 裡的設定，當初建立向量欄位是寫 `embedding vector(768)`。這代表我們目前實作是用 **Ollama 的 `nomic-embed-text`**，產生的向量維度固定是 **768 維**。如果以後我們把模型廠商切換到 **Gemini** 的話，它預設產生的向量維度則會是 **3072 維**。

### 如果在 Seed 完資料後強行「更換模型供應商」會怎樣？
如果我們跑完 `seed_vectors.py` 把 768 維的 Ollama 向量塞進資料庫之後，沒重新 seed 就直接去 `.env` 把供應商改成 Gemini，系統會因為以下原因直接掛掉：

1. **維度不匹配（Dimension Mismatch）**：
   當使用者進來問問題，系統因為設定改成了 Gemini，會用 Gemini 產出一個 **3072 維** 的問題向量。但這時候系統拿著 3072 維的向量去資料庫下 SQL 時，PostgreSQL 當初設定的欄位只能接收 **768 維**。
2. **索引失效無法使用（Index Unusable）**：
   因為長度根本對不起來，PostgreSQL 會直接報錯 `ERROR: vector columns must have the same dimensions`。這會導致搜尋的 SQL 查詢直接壞掉，原本針對 768 維建立的 HNSW 相似度索引也因為維度錯亂，導致**整張索引直接報廢、無法使用（Unusable）**。
3. **實際運行的慘重後果（Practical Consequence）**：
   對實際使用者來說，這會導致**整個客服檢索功能完全癱瘓**。只要有人發問，後端就會在查資料庫時直接噴 `500 Error`。系統不僅完全撈不到任何政策參考，LLM 也因為拿不到 Context 而沒辦法回答。前端使用者只會看到客服視窗一直轉圈圈、跳系統錯誤或直接斷線，整個智慧客服專案直接報銷。
