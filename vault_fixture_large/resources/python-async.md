---
title: python-async
date: 2026-01-05
---
#python #asyncio #reference

## asyncio basics
`async def` defines a coroutine. `await` suspends execution until the
awaitable completes. The event loop runs coroutines cooperatively.

## Key primitives
- `asyncio.gather`: run multiple coroutines concurrently.
- `asyncio.TaskGroup`: structured concurrency (Python 3.11+).
- `asyncio.Queue`: producer/consumer patterns.
- `asyncio.Lock / Semaphore`: coordination.

## Links
- [[python-packaging]]
- [[fastapi-patterns]]
