---
title: fastapi-patterns
date: 2026-01-14
---
#python #fastapi #web

## Dependency injection
FastAPI's `Depends()` system provides clean DI without a framework.
Use it for DB sessions, auth, config, and request validation.

## Background tasks
`BackgroundTasks` for fire-and-forget work within a request.
For heavy lifting use Celery or ARQ.

## Testing
Use `TestClient` for synchronous tests; `httpx.AsyncClient` for async.

## Links
- [[python-async]]
- [[postgresql-internals]]
