---
title: database-migrations
date: 2026-01-12
---
#database #migrations #python

## Alembic
Python migration framework for SQLAlchemy. Auto-generates migration scripts
from model diffs.

## Best practices
- Never edit an existing migration once deployed.
- Keep migrations small and reversible.
- Test `upgrade` and `downgrade` in CI.
- Use `batch_alter_table` for SQLite compatibility.

## Links
- [[postgresql-internals]]
