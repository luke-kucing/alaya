---
title: on-call-runbooks
date: 2026-01-20
---
#area #operations

## Alert response SLAs
- P1 (service down): respond in 5 min, resolve in 30 min.
- P2 (degraded): respond in 30 min, resolve in 4 hours.
- P3 (warning): acknowledge in 4 hours, next business day resolve.

## Common incidents
- High memory: check for memory leaks, OOM killer logs.
- Pod crash loop: check logs, resource limits, liveness probe config.
- Slow queries: check pg_stat_activity, look for missing indexes.

## Links
- [[observability-stack]]
- [[kubernetes-notes]]
