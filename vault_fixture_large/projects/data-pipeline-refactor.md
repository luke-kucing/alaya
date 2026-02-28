---
title: data-pipeline-refactor
date: 2026-01-15
---
#project #python #data

## Goal
Replace fragile cron-based ETL with an event-driven pipeline.

## Stack
Kafka → Faust (Python stream processing) → PostgreSQL / S3.

## Status
Design complete. Implementation starting next sprint.

## Links
- [[postgresql-internals]]
- [[python-async]]
