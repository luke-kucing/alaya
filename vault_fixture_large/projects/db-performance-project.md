---
title: db-performance-project
date: 2026-01-20
---
#project #database #completed

## Goal
Reduce p99 query latency on the reporting database from 8s to under 1s.

## Completed
- Added partial indexes on (user_id, created_at) for hot queries.
- Moved heavy aggregations to materialized views, refreshed nightly.
- Connection pooling with PgBouncer: reduced connection overhead by 60%.

## Result
p99 down to 400ms. Closed.

## Links
- [[postgresql-internals]]
- [[redis-caching]]
