---
title: distributed-systems
date: 2026-01-08
---
#learning #systems

## Topics
Consensus (Raft, Paxos), replication, partitioning, CAP theorem,
eventual consistency, CRDT.

## Resources
- Designing Data-Intensive Applications (Kleppmann)
- MIT 6.824 Distributed Systems lectures
- The morning paper blog

## Notes
CAP: in a network partition you must choose consistency or availability.
Most systems prefer AP (with tunable consistency) — e.g. Cassandra, DynamoDB.
