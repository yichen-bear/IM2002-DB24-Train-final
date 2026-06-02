# Work Allocation Report — [24]

> **Instructions:** Complete this document as a team before or alongside your final submission.
> Submit one copy per team via EEClass. This document is shared with all markers.
> Be specific — vague entries ("we all helped") will prevent individual contribution adjustments from being applied in your favour.

---

## 1. Team Members

| Full Name | Student ID | GitHub Username | Email |
|-----------|-----------|----------------|-------|
| 熊浥辰 | 113403047 | yichen-bear | sophie20060705@gmail.com |
| 邱鈺婷 | 113403034 | yuting0308 | tephanie71206@gmail.com |
| 呂怡柔 | 113101507 | catherinenoriy-arch | catherine.noriy@gmail.com |

---

## 2. Task Ownership

For each task, name the **primary owner** (the person most responsible for delivering it)
and any **supporting members** (who assisted but were not the lead). Leave the Notes column
for anything that deviates from the standard expectation (e.g., task was pair-programmed,
or reassigned mid-project).

### Code Repository

| Task | Primary Owner | Supporting Member(s) | Notes |
|------|--------------|---------------------|-------|
| **Task 1** — Relational schema design (`schema.sql`) | 熊浥辰、呂怡柔 | |熊浥辰負責設計文字版schema，呂怡柔負責將文字轉為實際程式|
| **Task 2a** — Core availability & fare queries (`query_national_rail_availability`, `query_metro_schedules`, `query_national_rail_fare`, `query_metro_fare`) |呂怡柔|邱鈺婷、熊浥辰|primary owner負責建立基本架構 supporting members負責debug|
| **Task 2b** — Seat & user queries (`query_available_seats`, `query_user_profile`, `query_user_bookings`, `query_payment_info`) |呂怡柔|邱鈺婷|primary owner負責建立基本架構 supporting members負責debug|
| **Task 2c** — Write operations (`execute_booking`, `execute_cancellation`) |呂怡柔|邱鈺婷|primary owner負責建立基本架構，supporting members負責debug|
| **Task 2d** — Authentication queries (`login_user`, `register_user`, `get_user_secret_question`, `verify_secret_answer`, `update_password`) |呂怡柔|邱鈺婷|primary owner 負責建立基本架構 supporting members 負責debug|
| **Task 3** — PostgreSQL seeding (`seed_postgres.py`) |邱鈺婷| | |
| **Task 4** — Neo4j graph design & seeding (`seed_neo4j.py`, `seed.cypher`) |熊浥辰| | |
| **Task 5** — Neo4j query functions (`graph/queries.py`) |邱鈺婷| | |
| **Task 6** *(if attempted)* — Optional extension | | | |

### Design Document

| Section | Primary Author | Supporting Member(s) | Notes |
|---------|--------------|---------------------|-------|
| Section 1 — ER Diagram | | | |
| Section 2 — Normalisation Justification | | | |
| Section 3 — Graph Database Design Rationale | | | |
| Section 4 — Vector / RAG Design | | | |
| Section 5 — AI Tool Usage Evidence | | | |
| Section 6 — Reflection & Trade-offs | | | |
| Section 7 — Optional Extension *(if applicable)* | | | |

---

## 3. Estimated Contribution Percentages

Based on the task allocation above, what percentage of total team effort do you estimate each member contributed?
All members must sum to 100%.

| Member | Estimated % | Brief justification |
|--------|-----------|---------------------|
| 熊浥辰 | 33.3% | 主要負責`skeleton/seed_neo4j.py`、`skeleton/verify_neo4j.py`(輔助驗證`skeleton/seed_neo4j.py`)、`skeleton/ui.py`，協助`skeleton/agent.py`、`relational/queries.py`|
| 邱鈺婷 | 33.3% | 主要負責`skeleton/seed_postgres.py`、`graph/queries.py`，協助`skeleton/agent.py`、`relational/queries.py`|
| 呂怡柔 | 33.3% | 主要負責`relational/schema.sql`、`relational/queries.py`，協助agent測試，畫ERD|
| **Total** | **100%** | |

---

## 4. Mid-Project Changes

If any tasks were reassigned or the original plan changed significantly, document it here.
If nothing changed, write "No changes."

| Change | Original plan | Revised plan | Reason |
|--------|--------------|-------------|--------|
| | | | |

---

## 5. Team Declaration

We confirm that this work allocation accurately reflects how responsibilities were divided within our team.

| Name | Signature / Typed name | Date |
|------|----------------------|------|
| | | |
| 邱鈺婷 | 邱鈺婷 | 2026/6/2 |
| 呂怡柔 | 呂怡柔 | 2026/6/2 |

