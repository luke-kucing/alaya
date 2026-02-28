---
title: postgresql-internals
date: 2026-01-10
---
#database #postgresql #reference

## MVCC
PostgreSQL uses Multi-Version Concurrency Control. Each transaction sees a
snapshot. Old row versions are retained until VACUUM cleans them up.

## Indexing
- B-tree (default), Hash, GiST, GIN, BRIN.
- Partial indexes reduce index size for filtered queries.
- Expression indexes on computed values.

## Tuning
- `shared_buffers`: 25% of RAM.
- `effective_cache_size`: 75% of RAM.
- `work_mem`: per-sort/hash allocation.

## Links
- [[database-migrations]]
- [[redis-caching]]
