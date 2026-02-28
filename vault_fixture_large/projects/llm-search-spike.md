---
title: llm-search-spike
date: 2026-02-18
---
#project #ai #search

## Goal
Evaluate LLM-powered search for the internal knowledge base.

## Findings
- Hybrid search (dense + sparse) beats pure keyword by ~30% MRR.
- nomic-embed-text-v1.5 provides good quality at low cost.
- Re-ranking with a cross-encoder adds latency but improves precision@3.

## Links
- [[llm-engineering]]
- [[vector-databases]]
- [[embedding-models]]
