---
title: redis-caching
date: 2026-01-18
---
#database #redis #caching

## Redis data structures
Strings, Lists, Sets, Sorted Sets, Hashes, Streams, HyperLogLog.

## Common patterns
- **Cache-aside**: read from cache; miss → read DB → populate cache.
- **Write-through**: write to cache and DB together.
- **Pub/Sub**: lightweight message bus.
- **Rate limiting**: INCR + EXPIRE per key.

## Links
- [[postgresql-internals]]
