---
title: vector-databases
date: 2026-02-07
---
#ai #database #embeddings

## Options
- **LanceDB**: embedded, Rust-based, columnar. Good for local/serverless.
- **Qdrant**: self-hosted or cloud. Rich filtering, Rust client.
- **Chroma**: simple Python-native. Good for prototyping.
- **Pinecone**: managed cloud. No ops overhead.

## Hybrid search
Combine dense (vector ANN) and sparse (BM25 / keyword) retrieval.
Reciprocal Rank Fusion or linear interpolation for merging.

## Links
- [[llm-engineering]]
- [[postgresql-internals]]
