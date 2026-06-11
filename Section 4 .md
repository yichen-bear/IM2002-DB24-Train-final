# Section 4 — Vector / RAG Design

## 1. Embedding and Cosine Similarity Rationale

在我們的 TransitFlow 系統中，要進行向量化（Embedding）的資料，是 `policy_documents` 資料表中的政策文件內容，其來源包含 `refund_policy.json`（退票政策）、`ticket_types.json`（票價類型）、`booking_rules.json`（訂票規則）以及 `travel_policies.json`（乘車與行為規範）。這些文件會被轉成向量後存入 PostgreSQL 的 `policy_documents.embedding` 欄位，供客服檢索增強生成（RAG）系統查詢使用。

### 為什麼做語意搜尋（Semantic Search）時，用餘弦相似度（Cosine Similarity）最適合？
最核心的原因就是餘弦相似度具備**大小無關性（Magnitude-Independent）**，它在向量空間中算的是**方向相似度（Directional Similarity）**，而不會單純被原始向量的長度大小給主導。

餘弦相似度非常適合語意搜尋，因為它比較的是兩個 embedding vectors 在語意空間中的方向，而不是原始向量長度。在實際的客服情境中，使用者輸入的問題通常較為簡短（例如：「怎麼退票」），而資料庫中儲存的官方規章條文篇幅較長（例如詳細的退票手續費與時間窗口梯隊）。

如果採用歐氏距離（Euclidean Distance），由於兩者文本長度差異導致的向量長度（Magnitude）差距，極易在距離計算上造成誤差。而餘弦相似度則能有效避開這點：即使使用者問題很短、政策文件較長，只要兩者語意主題接近（都在討論 refund rules），它們的向量方向在多維空間中仍會非常接近，因此系統能夠精準地將對應的官方政策政策檢索出來。

---

## 2. Full RAG Pipeline Workflow

我們實作的檢索增強生成（RAG）功能，從使用者輸入問題到最後看到答案，底層完整的 Pipeline 跑了以下四個階段：

1. **Query Embedding**
   使用者在客服介面送出問題後，後端程式會先呼叫嵌入模型（如 Ollama 的 `nomic-embed-text`），把這段問題文字轉換成一組固定長度的浮點數陣列（也就是問題向量）。
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
如果我們跑完 `seed_vectors.py` 把 768 維的 Ollama 向量塞進資料庫之後，沒重新 seed 就直接去 `.env` 把供應商改成 Gemini，系統會因為**維度不相容**而引發連鎖錯誤：

1. **維度不匹配（Dimension Mismatch）**：
   當使用者進來問問題，系統因為設定改成了 Gemini，會用 Gemini 產出一個 **3072 維** 的問題向量。但這時候系統拿著 3072 維的向量去資料庫下 SQL 進行餘弦相似度比對時，PostgreSQL 當初設定的欄位維度只能接收 **768 維**。
2. **索引失效與結構變更代價**：
   因為長度根本對不起來，PostgreSQL 會直接報錯 `ERROR: vector columns must have the same dimensions`。原本建立在 768 維欄位上的 HNSW index 無法用來查 3072 維向量。若要完成模型切換，必須進資料庫把欄位改成 `vector(3072)`，清空或重建資料，重新運行 `seed_vectors.py` 塞入新模型的 embeddings，並重新建構 HNSW 索引。
3. **實際運行的慘重後果（Practical Consequence）**：
   對實際使用者來說，這會導致**整個客服檢索功能完全癱瘓**。只要有人發問，後端就會在查資料庫時直接噴 `500 Error`。系統不僅完全撈不到任何政策參考，LLM 也因為拿不到 Context 而沒辦法回答。前端使用者只會看到客服視窗一直轉圈圈或跳系統錯誤，智慧客服專案在維度調整與重新 Seed 完成前將無法提供服務。