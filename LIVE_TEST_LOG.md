# LIVE_TEST_LOG

## Environment
- Date: 2026-06-12
- Tester: AI Assistant
- Branch: 
- Commit hash: 
- Docker reset? yes

## Seeding Status
- PostgreSQL: OK (All tables seeded)
- Neo4j: OK (Graph seeded and verify_neo4j.py passed)
- pgvector: OK (13 policy documents embedded)

## PostgreSQL Query Tests
- B1: PASS (Works perfectly)
- B2: PASS
- B3: PASS (Fixed `seed_postgres.py` JSON fare mapping logic which previously seeded $0 fares)
- B4: PASS
- B5: PASS
- B6: PASS
- B7: PASS
- B8: PASS
- B9: PASS (Fixed missing `user_id` and `schedule_id` return keys)
- B10: PASS (Fixed missing `refund_amount` return key)

## Vector / RAG Tests
- D1: PASS (Modified `query_policy_vector_search` to map `id AS policy_id` to match expected dictionary shape)

## Neo4j Query Tests
- C1: PASS (Fixed return shape from dict to list of dicts)
- C2: PASS (Fixed return shape from dict to list of dicts, ignored missing `cost_usd` warning by removing the reference)
- C3: PASS (Fixed return shape from nested dict to list of list of dicts)
- C4: PASS (Fixed `name` key to `station_name` to match spec)
- C5: PASS
- C6: PASS

## UI Tests
- Policy / RAG:
- Route:
- Schedule:
- Booking:
- Cancellation:

## Known Issues
1. FK Integrity Check for payments returned 20 orphan payments (because the `payments` seed data includes 20 payments for metro trips, but the query strictly checks `bookings` table which only has 20 national rail bookings).
2.
3.

## Handoff Notes
