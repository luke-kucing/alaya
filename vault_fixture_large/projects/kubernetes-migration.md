---
title: kubernetes-migration
date: 2026-02-10
---
#project #kubernetes #infrastructure

## Objective
Migrate all workloads from docker-compose to Kubernetes.

## Status
In progress. Core services migrated. Database migration pending.

## Risks
- Stateful services (PostgreSQL, Redis) need persistent volumes.
- Network policy migration from docker network to Kubernetes RBAC.

## Links
- [[kubernetes-notes]]
- [[platform-migration]]
- [[postgresql-internals]]
