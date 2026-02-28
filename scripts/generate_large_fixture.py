#!/usr/bin/env python3
"""Generate vault_fixture_large/ — 100+ notes for integration / search benchmarks.

Run from the repo root:
    uv run python scripts/generate_large_fixture.py
"""
from __future__ import annotations

import shutil
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "vault_fixture_large"

# ---------------------------------------------------------------------------
# Note definitions
# ---------------------------------------------------------------------------

RESOURCES = [
    # kubernetes / platform
    ("kubernetes-notes", "2026-01-15", ["kubernetes", "reference"],
     dedent("""\
     ## Overview
     Kubernetes is a container orchestration platform. Key concepts: pods, deployments,
     services, ingress, namespaces, RBAC.

     ## Core objects
     - **Pod**: smallest deployable unit; one or more containers.
     - **Deployment**: desired-state spec for a set of pods; handles rollouts.
     - **Service**: stable DNS name and load-balancing for a pod set.
     - **ConfigMap / Secret**: externalise config and credentials.

     ## Links
     - [[helm-charts]]
     - [[argocd-gitops]]
     - [[zero-trust-research]]
     """)),

    ("helm-charts", "2026-01-20", ["kubernetes", "helm", "reference"],
     dedent("""\
     ## What is Helm
     Helm is the package manager for Kubernetes. Charts bundle manifests, templates,
     and default values.

     ## Key commands
     ```
     helm repo add bitnami https://charts.bitnami.com/bitnami
     helm install my-release bitnami/postgresql
     helm upgrade --install my-release ./mychart -f values.prod.yaml
     helm rollback my-release 1
     ```

     ## Links
     - [[kubernetes-notes]]
     - [[argocd-gitops]]
     """)),

    ("argocd-gitops", "2026-01-22", ["kubernetes", "gitops", "argocd"],
     dedent("""\
     ## ArgoCD overview
     ArgoCD is a declarative GitOps continuous delivery tool for Kubernetes.
     It reconciles a live cluster state against a Git repository.

     ## Setup
     - Install via Helm or raw manifests into the argocd namespace.
     - Create an Application CR pointing at a Git repo + path.
     - ArgoCD polls or receives webhooks and syncs automatically.

     ## Links
     - [[kubernetes-notes]]
     - [[helm-charts]]
     - [[platform-migration]]
     """)),

    ("zero-trust-research", "2026-01-25", ["security", "zero-trust", "reference"],
     dedent("""\
     ## Zero Trust principles
     Never trust, always verify. Assume breach. Apply least-privilege access.

     ## Components
     - **Identity**: strong MFA, short-lived certs, device attestation.
     - **Network**: micro-segmentation, mutual TLS, service mesh (Istio/Linkerd).
     - **Data**: encrypt at rest and in transit; DLP policies.

     ## Links
     - [[service-mesh-notes]]
     - [[kubernetes-notes]]
     """)),

    ("service-mesh-notes", "2026-01-28", ["kubernetes", "istio", "networking"],
     dedent("""\
     ## Service mesh overview
     A service mesh handles service-to-service communication: mTLS, retries,
     circuit breaking, observability.

     ## Istio
     - Sidecar injection (Envoy proxy).
     - VirtualService and DestinationRule CRDs.
     - Telemetry via Prometheus + Jaeger.

     ## Linkerd
     - Lighter weight than Istio; Rust-based data plane.
     - Good for low-overhead mTLS.

     ## Links
     - [[zero-trust-research]]
     - [[kubernetes-notes]]
     """)),

    ("postgresql-internals", "2026-01-10", ["database", "postgresql", "reference"],
     dedent("""\
     ## MVCC
     PostgreSQL uses Multi-Version Concurrency Control. Each transaction sees a
     snapshot. Old row versions are retained until VACUUM cleans them up.

     ## Indexing
     - B-tree (default), Hash, GiST, GIN, BRIN.
     - Partial indexes reduce index size for filtered queries.
     - Expression indexes on computed values.

     ## Tuning
     - `shared_buffers`: 25% of RAM.
     - `effective_cache_size`: 75% of RAM.
     - `work_mem`: per-sort/hash allocation.

     ## Links
     - [[database-migrations]]
     - [[redis-caching]]
     """)),

    ("database-migrations", "2026-01-12", ["database", "migrations", "python"],
     dedent("""\
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
     """)),

    ("redis-caching", "2026-01-18", ["database", "redis", "caching"],
     dedent("""\
     ## Redis data structures
     Strings, Lists, Sets, Sorted Sets, Hashes, Streams, HyperLogLog.

     ## Common patterns
     - **Cache-aside**: read from cache; miss → read DB → populate cache.
     - **Write-through**: write to cache and DB together.
     - **Pub/Sub**: lightweight message bus.
     - **Rate limiting**: INCR + EXPIRE per key.

     ## Links
     - [[postgresql-internals]]
     """)),

    ("python-async", "2026-01-05", ["python", "asyncio", "reference"],
     dedent("""\
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
     """)),

    ("python-packaging", "2026-01-08", ["python", "packaging", "uv"],
     dedent("""\
     ## uv
     uv is a fast Python package manager written in Rust (Astral). Replaces pip,
     pip-tools, virtualenv and pyenv in a single tool.

     ## Key commands
     ```
     uv init myproject
     uv add fastapi
     uv run pytest
     uv sync
     uv lock
     ```

     ## Links
     - [[python-async]]
     """)),

    ("fastapi-patterns", "2026-01-14", ["python", "fastapi", "web"],
     dedent("""\
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
     """)),

    ("observability-stack", "2026-01-30", ["observability", "prometheus", "grafana"],
     dedent("""\
     ## The three pillars
     Metrics (Prometheus), Logs (Loki / ELK), Traces (Tempo / Jaeger).

     ## Prometheus
     Pull-based metrics. PromQL for queries. Alertmanager for routing.

     ## Grafana
     Dashboards, alerting, and unified data source queries (Prometheus, Loki, Tempo).

     ## Links
     - [[kubernetes-notes]]
     - [[service-mesh-notes]]
     """)),

    ("terraform-patterns", "2026-02-01", ["iac", "terraform", "aws"],
     dedent("""\
     ## Module structure
     ```
     modules/
       vpc/
       eks/
       rds/
     environments/
       prod/
       staging/
     ```

     ## State management
     Remote state in S3 + DynamoDB locking. Workspaces for per-env isolation.

     ## Links
     - [[aws-networking]]
     - [[kubernetes-notes]]
     """)),

    ("aws-networking", "2026-02-03", ["aws", "networking", "vpc"],
     dedent("""\
     ## VPC fundamentals
     - CIDR block planning: avoid 10.0.0.0/8 overlap with on-prem.
     - Public subnets: internet gateway route. Private subnets: NAT gateway.
     - Security groups vs NACLs: SGs are stateful; NACLs are stateless.

     ## Transit Gateway
     Hub-and-spoke model for multi-VPC and hybrid connectivity.

     ## Links
     - [[terraform-patterns]]
     - [[zero-trust-research]]
     """)),

    ("git-workflows", "2026-01-02", ["git", "devops", "reference"],
     dedent("""\
     ## Trunk-based development
     Short-lived feature branches merged daily. Feature flags for incomplete work.
     Faster CI, less merge hell.

     ## Conventional commits
     `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`.
     Enables automated changelogs and semantic versioning.

     ## Links
     - [[ci-cd-patterns]]
     """)),

    ("ci-cd-patterns", "2026-01-04", ["devops", "ci", "github-actions"],
     dedent("""\
     ## GitHub Actions
     - Matrix builds for multiple Python versions / OSes.
     - Reusable workflows: `workflow_call` trigger.
     - OIDC for AWS credentials — no long-lived secrets.

     ## Pipeline stages
     lint → unit tests → build → integration tests → deploy to staging → smoke test → prod

     ## Links
     - [[git-workflows]]
     - [[argocd-gitops]]
     """)),

    ("llm-engineering", "2026-02-05", ["ai", "llm", "python"],
     dedent("""\
     ## Prompt engineering
     - System prompt: set role and constraints once.
     - Few-shot examples in the prompt for consistency.
     - Chain-of-thought: ask the model to reason step by step.

     ## RAG (Retrieval-Augmented Generation)
     Retrieve relevant context from a vector store, inject into prompt.
     Reduces hallucinations for knowledge-intensive tasks.

     ## Evaluation
     RAGAS, UpTrain, LangSmith for pipeline evaluation.

     ## Links
     - [[vector-databases]]
     - [[python-async]]
     """)),

    ("vector-databases", "2026-02-07", ["ai", "database", "embeddings"],
     dedent("""\
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
     """)),

    ("linux-performance", "2026-01-06", ["linux", "performance", "reference"],
     dedent("""\
     ## USE method
     For every resource: Utilisation, Saturation, Errors.

     ## Key tools
     - `perf`: CPU profiling, cache misses, branch mispredictions.
     - `bpftrace` / `eBPF`: kernel-level tracing without overhead.
     - `strace`: system call tracing.
     - `ss`, `netstat`: network socket state.

     ## Links
     - [[observability-stack]]
     """)),

    ("networking-fundamentals", "2025-12-20", ["networking", "reference", "tcp"],
     dedent("""\
     ## TCP/IP stack
     L1 Physical → L2 Data link → L3 Network (IP) → L4 Transport (TCP/UDP) → L7 Application.

     ## TCP
     Three-way handshake (SYN, SYN-ACK, ACK). Flow control via sliding window.
     Congestion control: CUBIC (Linux default), BBR.

     ## DNS
     Recursive vs authoritative resolvers. TTL caching. DNSSEC for integrity.

     ## Links
     - [[aws-networking]]
     - [[service-mesh-notes]]
     """)),

    ("security-hardening", "2026-01-26", ["security", "linux", "hardening"],
     dedent("""\
     ## OS hardening
     - Disable unused services. Minimal installed packages.
     - CIS benchmarks: automated compliance checks.
     - AppArmor / SELinux for mandatory access control.

     ## Secrets management
     HashiCorp Vault: dynamic secrets, PKI, encryption-as-a-service.
     AWS Secrets Manager for AWS-native workloads.

     ## Links
     - [[zero-trust-research]]
     - [[linux-performance]]
     """)),

    ("mcp-protocol", "2026-02-10", ["mcp", "ai", "protocol"],
     dedent("""\
     ## Model Context Protocol
     MCP is an open standard for connecting AI assistants to external tools and data.
     Uses JSON-RPC 2.0 over stdio or HTTP/SSE.

     ## Tool registration
     Tools have a name, description, and JSON Schema for input parameters.
     The server returns a list of tools; the client (LLM) decides which to call.

     ## Resources and prompts
     MCP also supports resources (file/URI access) and prompt templates.

     ## Links
     - [[llm-engineering]]
     - [[fastapi-patterns]]
     """)),

    ("embedding-models", "2026-02-12", ["ai", "embeddings", "nlp"],
     dedent("""\
     ## Sentence transformers
     Models that map sentences to dense vectors. Trained with contrastive
     objectives (SimCSE, MNRL).

     ## nomic-embed-text-v1.5
     768-dimensional embeddings. ONNX backend for fast CPU inference.
     Supports `search_query:` and `search_document:` prefixes for asymmetric search.

     ## Evaluation
     MTEB benchmark: retrieval, clustering, classification, reranking tasks.

     ## Links
     - [[vector-databases]]
     - [[llm-engineering]]
     """)),

    ("python-testing", "2026-01-16", ["python", "testing", "pytest"],
     dedent("""\
     ## pytest patterns
     - Fixtures for setup/teardown. `tmp_path` for temp files.
     - `monkeypatch` for env vars and function patching.
     - `pytest.mark.parametrize` for data-driven tests.

     ## Mocking
     `unittest.mock.patch` as decorator or context manager.
     `MagicMock` for auto-specced mocks.

     ## Property-based testing
     Hypothesis generates diverse inputs automatically.

     ## Links
     - [[python-packaging]]
     - [[ci-cd-patterns]]
     """)),

    ("api-design", "2026-01-24", ["api", "rest", "design"],
     dedent("""\
     ## REST conventions
     - Nouns not verbs in URLs: `/users/123` not `/getUser`.
     - HTTP verbs semantics: GET (safe), POST (create), PUT/PATCH (update), DELETE.
     - 2xx success, 4xx client error, 5xx server error.

     ## Versioning
     URL versioning (`/v1/`) vs header versioning. URL is simpler to test.

     ## OpenAPI
     Machine-readable spec. Auto-generate clients and docs.

     ## Links
     - [[fastapi-patterns]]
     """)),
]

PROJECTS = [
    ("second-brain", "2026-02-23", ["project", "python", "mcp"],
     dedent("""\
     ## Goal
     Build a FastMCP server that makes an AI assistant the primary interface for a zk-managed
     personal knowledge vault. Full read/write second brain.

     ## Tasks
     - [x] write requirements doc
     - [x] scaffold project structure
     - [x] M1: core read/write/navigate tools
     - [ ] M2: safety operations
     - [ ] M3: LanceDB hybrid search
     - [ ] M4: file watcher and ingestion
     - [ ] M5: GitLab integration

     ## Notes
     Stack: FastMCP, zk CLI, LanceDB, nomic-embed-text-v1.5 (ONNX), pymupdf4llm, trafilatura.

     ## Links
     - [[platform-migration]]
     - [[vector-databases]]
     - [[mcp-protocol]]
     """)),

    ("platform-migration", "2026-02-15", ["project", "kubernetes", "active"],
     dedent("""\
     ## Goal
     Migrate legacy monolith from bare metal to Kubernetes on AWS EKS.

     ## Phase 1: containerise (done)
     - Dockerfiles for all services.
     - docker-compose for local dev.

     ## Phase 2: EKS (in progress)
     - [ ] Set up EKS cluster with Terraform.
     - [ ] Migrate stateless services first.
     - [x] Set up ArgoCD.

     ## Links
     - [[kubernetes-notes]]
     - [[argocd-gitops]]
     - [[terraform-patterns]]
     """)),

    ("kubernetes-migration", "2026-02-10", ["project", "kubernetes", "infrastructure"],
     dedent("""\
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
     """)),

    ("alaya-project", "2026-02-20", ["project", "python", "ai"],
     dedent("""\
     ## Goal
     Personal AI assistant integrated into a zk vault.

     ## Stack
     FastMCP, LanceDB, nomic-embed-text-v1.5, zk CLI.

     ## Milestones
     - [x] M1: read/write/navigate
     - [ ] M2: safety
     - [ ] M3: semantic search
     - [ ] M4: file watcher

     ## Links
     - [[second-brain]]
     - [[mcp-protocol]]
     - [[embedding-models]]
     """)),

    ("zero-trust-rollout", "2026-02-01", ["project", "security", "active"],
     dedent("""\
     ## Goal
     Implement zero-trust network architecture across all internal services.

     ## Tasks
     - [x] Threat model workshop.
     - [x] Deploy service mesh (Istio).
     - [ ] Rotate all service credentials to short-lived certs.
     - [ ] Enable mTLS everywhere.
     - [ ] Implement device attestation for developer laptops.

     ## Links
     - [[zero-trust-research]]
     - [[service-mesh-notes]]
     - [[security-hardening]]
     """)),

    ("observability-overhaul", "2026-01-28", ["project", "observability", "stale"],
     dedent("""\
     ## Goal
     Replace ad-hoc logging with structured observability stack.

     ## Status
     Stalled. Prometheus deployed; Grafana dashboards incomplete.

     ## Blocked on
     - Engineering time.
     - Agreement on alert routing policies.

     ## Links
     - [[observability-stack]]
     - [[kubernetes-notes]]
     """)),

    ("llm-search-spike", "2026-02-18", ["project", "ai", "search"],
     dedent("""\
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
     """)),

    ("db-performance-project", "2026-01-20", ["project", "database", "completed"],
     dedent("""\
     ## Goal
     Reduce p99 query latency on the reporting database from 8s to under 1s.

     ## Completed
     - Added partial indexes on (user_id, created_at) for hot queries.
     - Moved heavy aggregations to materialized views, refreshed nightly.
     - Connection pooling with PgBouncer: reduced connection overhead by 60%.

     ## Result
     p99 down to 400ms. Closed.

     ## Links
     - [[postgresql-internals]]
     - [[redis-caching]]
     """)),

    ("api-gateway-project", "2026-02-05", ["project", "api", "active"],
     dedent("""\
     ## Goal
     Centralise external API traffic through a single gateway.

     ## Options evaluated
     - Kong: feature-rich but complex.
     - AWS API Gateway: easy but vendor lock-in.
     - Envoy + Contour: Kubernetes-native.

     ## Decision
     Envoy via Contour. Integrates with existing service mesh.

     ## Links
     - [[service-mesh-notes]]
     - [[api-design]]
     """)),

    ("data-pipeline-refactor", "2026-01-15", ["project", "python", "data"],
     dedent("""\
     ## Goal
     Replace fragile cron-based ETL with an event-driven pipeline.

     ## Stack
     Kafka → Faust (Python stream processing) → PostgreSQL / S3.

     ## Status
     Design complete. Implementation starting next sprint.

     ## Links
     - [[postgresql-internals]]
     - [[python-async]]
     """)),
]

PEOPLE = [
    ("alex-chen", "2026-02-20", ["people", "manager"],
     dedent("""\
     ## Role
     Engineering Manager, Platform team.

     ## 1:1 Notes

     ### 2026-02-20
     Discussed Q1 roadmap priorities. Platform migration is top priority.
     Alex wants weekly written updates on Kubernetes migration progress.

     ### 2026-02-06
     Reviewed career growth areas: system design depth and cross-team influence.
     Agreed to lead the observability overhaul project.

     ### 2026-01-23
     Onboarding check-in. Covered team norms and on-call rotation expectations.

     ## Links
     - [[platform-migration]]
     - [[observability-overhaul]]
     """)),

    ("maya-patel", "2026-02-18", ["people", "colleague"],
     dedent("""\
     ## Role
     Senior SRE.

     ## 1:1 Notes

     ### 2026-02-18
     Pair-programmed on the Prometheus alerting rules. Maya flagged that our
     alert-to-runbook coverage is under 40%.

     ### 2026-02-04
     Maya is leading the zero-trust rollout. Reviewed threat model together.

     ## Links
     - [[observability-stack]]
     - [[zero-trust-rollout]]
     - [[service-mesh-notes]]
     """)),

    ("sam-okonkwo", "2026-02-10", ["people", "report"],
     dedent("""\
     ## Role
     Software Engineer, Backend.

     ## 1:1 Notes

     ### 2026-02-10
     Sam is picking up the data pipeline refactor. Good progress on design doc.
     Flagged concern about Kafka operational complexity — suggest managed MSK.

     ### 2026-01-27
     Discussed scope of database performance project. Sam will own the indexing work.

     ## Links
     - [[data-pipeline-refactor]]
     - [[db-performance-project]]
     """)),

    ("priya-sharma", "2026-01-30", ["people", "colleague"],
     dedent("""\
     ## Role
     Product Manager, Developer Productivity.

     ## 1:1 Notes

     ### 2026-01-30
     Priya wants a developer portal to surface service ownership and runbooks.
     Suggested integrating with our internal wiki.

     ### 2026-01-16
     Reviewed Q1 OKRs. Agreed that DORA metrics (deploy freq, lead time, MTTR)
     are the right signals for developer productivity.

     ## Links
     - [[ci-cd-patterns]]
     - [[observability-stack]]
     """)),

    ("liam-foster", "2026-02-14", ["people", "report"],
     dedent("""\
     ## Role
     Junior SRE.

     ## 1:1 Notes

     ### 2026-02-14
     Liam completed the Kubernetes CKA certification. Assigned first on-call shift.

     ### 2026-01-31
     Pairing sessions on kubectl and Helm. Liam is progressing quickly.

     ## Links
     - [[kubernetes-notes]]
     - [[helm-charts]]
     """)),

    ("chen-wei", "2026-02-22", ["people", "colleague"],
     dedent("""\
     ## Role
     Staff Engineer, Data.

     ## 1:1 Notes

     ### 2026-02-22
     Discussed embedding model selection for semantic search project.
     Chen-Wei recommends nomic-embed-text-v1.5 for production; strong MTEB scores.

     ### 2026-02-08
     Reviewed data pipeline architecture. Chen-Wei flagged schema evolution risks.

     ## Links
     - [[embedding-models]]
     - [[vector-databases]]
     - [[data-pipeline-refactor]]
     """)),

    ("diana-ortiz", "2026-01-25", ["people", "stakeholder"],
     dedent("""\
     ## Role
     VP Engineering.

     ## Notes
     Diana wants quarterly tech radar updates and clear risk registers for all
     active projects. Prefers written briefings over slide decks.

     ## Links
     - [[platform-migration]]
     - [[zero-trust-rollout]]
     """)),

    ("james-nguyen", "2026-02-16", ["people", "report"],
     dedent("""\
     ## Role
     Software Engineer, API Platform.

     ## 1:1 Notes

     ### 2026-02-16
     James is leading the API gateway project. Evaluation of Kong vs Envoy complete.
     Recommendation: Envoy via Contour.

     ## Links
     - [[api-gateway-project]]
     - [[api-design]]
     - [[service-mesh-notes]]
     """)),

    ("fatima-al-zahra", "2026-01-20", ["people", "colleague"],
     dedent("""\
     ## Role
     Security Engineer.

     ## 1:1 Notes

     ### 2026-01-20
     Fatima reviewed our secrets management approach. Recommends migrating from
     env vars to HashiCorp Vault for all production services.

     ## Links
     - [[security-hardening]]
     - [[zero-trust-research]]
     """)),

    ("raj-krishnamurthy", "2026-02-25", ["people", "colleague"],
     dedent("""\
     ## Role
     Principal Engineer.

     ## 1:1 Notes

     ### 2026-02-25
     Raj reviewed the LLM search spike results. Agrees hybrid search is the right
     architecture. Wants to see re-ranking benchmarks before committing to cross-encoder.

     ## Links
     - [[llm-search-spike]]
     - [[vector-databases]]
     - [[embedding-models]]
     """)),
]

IDEAS = [
    ("voice-capture", "2026-01-10", ["idea", "productivity"],
     dedent("""\
     ## Concept
     Voice-to-inbox capture: record a voice memo on iPhone, transcribe with
     Whisper, push to inbox.md via the alaya MCP server.

     ## Status
     Idea stage. Requires iOS Shortcut + API endpoint.

     ## Links
     - [[second-brain]]
     """)),

    ("automated-standup", "2026-01-18", ["idea", "ai", "productivity"],
     dedent("""\
     ## Concept
     Auto-generate daily standup from yesterday's daily note and open tasks.
     Post to Slack via webhook.

     ## Status
     Prototype worked in a weekend spike. Needs polish.

     ## Links
     - [[llm-engineering]]
     - [[second-brain]]
     """)),

    ("knowledge-graph-viz", "2026-02-02", ["idea", "visualisation"],
     dedent("""\
     ## Concept
     Render the vault's wikilink graph as an interactive D3 force-directed graph.
     Colour by directory, size by backlink count.

     ## Status
     Idea. zk has a `--format json` output mode that could seed this.

     ## Links
     - [[second-brain]]
     """)),

    ("weekly-review-bot", "2026-02-08", ["idea", "ai", "productivity"],
     dedent("""\
     ## Concept
     Every Friday, run an LLM over the week's daily notes and produce a
     structured weekly review: wins, blockers, carry-overs, mood trend.

     ## Status
     Idea. Would require a scheduled trigger and prompt engineering.

     ## Links
     - [[llm-engineering]]
     - [[second-brain]]
     """)),

    ("context-aware-search", "2026-02-15", ["idea", "ai", "search"],
     dedent("""\
     ## Concept
     Search that understands the current project context: if I'm in a
     Kubernetes project note, boost k8s resources automatically.

     ## Status
     Idea stage. Would need session state in the MCP server.

     ## Links
     - [[llm-search-spike]]
     - [[vector-databases]]
     """)),
]

LEARNING = [
    ("distributed-systems", "2026-01-08", ["learning", "systems"],
     dedent("""\
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
     """)),

    ("rust-language", "2026-01-22", ["learning", "rust"],
     dedent("""\
     ## Progress
     Completed the Rust Book. Working through Rustlings exercises.

     ## Key concepts
     Ownership, borrowing, lifetimes. The borrow checker eliminates whole
     classes of bugs at compile time.

     ## Use cases
     Systems programming, WebAssembly, CLI tools, high-performance services.
     """)),

    ("machine-learning-ops", "2026-02-01", ["learning", "mlops", "ai"],
     dedent("""\
     ## Topics
     Model versioning, feature stores, model serving, monitoring, drift detection.

     ## Resources
     - Made With ML course
     - MLflow for experiment tracking
     - Seldon Core for Kubernetes model serving

     ## Links
     - [[llm-engineering]]
     - [[kubernetes-notes]]
     """)),
]

AREAS = [
    ("engineering-standards", "2026-01-15", ["area", "engineering"],
     dedent("""\
     ## Principles
     - Simple over clever.
     - Explicit over implicit.
     - Boring tech over shiny tech for production.
     - Test everything that could break.

     ## Code review guidelines
     - Review the design, not the style (automate style with linters).
     - One approval required; two for risky changes.
     - Respond within one business day.

     ## Links
     - [[python-testing]]
     - [[git-workflows]]
     """)),

    ("on-call-runbooks", "2026-01-20", ["area", "operations"],
     dedent("""\
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
     """)),
]

# Daily notes — span 5 weeks
DAILY_ENTRIES = [
    ("2026-01-19", ["daily"],
     dedent("""\
     ## Done
     - Reviewed PR for database indexing work.
     - 1:1 with Sam: data pipeline design discussion.

     ## Notes
     Good progress on PostgreSQL performance project. Sam's indexing changes
     look solid — need to run explain analyse on staging.

     ## Tomorrow
     - Merge indexing PR.
     - Start on Prometheus alerting rules.
     """)),
    ("2026-01-20", ["daily"],
     dedent("""\
     ## Done
     - Merged PostgreSQL indexing PR. p99 improved by 40% on staging.
     - 1:1 with Fatima: secrets management review.

     ## Notes
     Fatima's recommendation to move to HashiCorp Vault is solid. Need to
     plan migration away from env vars.

     ## Tomorrow
     - Write up Vault migration plan.
     - Review Kubernetes cluster sizing for platform migration.
     """)),
    ("2026-01-21", ["daily"],
     dedent("""\
     ## Done
     - Drafted HashiCorp Vault migration plan.
     - Kubernetes cluster sizing review: agreed on 3x m5.xlarge for node group.

     ## Notes
     Cluster sizing feels right for current workload. Leave room for 2x growth.
     """)),
    ("2026-01-22", ["daily"],
     dedent("""\
     ## Done
     - Started Rust Book exercises (ownership chapter).
     - Sprint planning: committed platform migration Phase 2 tickets.

     ## Notes
     Rust ownership model clicking. The borrow checker is strict but the
     errors are surprisingly helpful.
     """)),
    ("2026-01-23", ["daily"],
     dedent("""\
     ## Done
     - Onboarding 1:1 with Alex: team norms, on-call, career growth.
     - Reviewed ArgoCD ApplicationSet docs.

     ## Notes
     Alex wants weekly written updates. Will add a Friday review habit.
     """)),
    ("2026-01-26", ["daily"],
     dedent("""\
     ## Done
     - Set up ArgoCD ApplicationSet for multi-env deployments.
     - Reviewed service mesh options (Istio vs Linkerd).

     ## Notes
     Istio has more features but Linkerd is significantly lighter.
     For our scale, Linkerd is probably sufficient. Need to discuss with Maya.
     """)),
    ("2026-01-27", ["daily"],
     dedent("""\
     ## Done
     - 1:1 with Sam: database performance scope.
     - Reviewed PgBouncer config for connection pooling.

     ## Notes
     Connection pooling is low-hanging fruit. Sam will implement this week.
     """)),
    ("2026-01-28", ["daily"],
     dedent("""\
     ## Done
     - Deployed PgBouncer. Connection overhead down 60%.
     - Threat model workshop with Maya for zero-trust project.

     ## Notes
     Threat model surfaced 3 high-severity gaps: secret rotation, lateral
     movement paths, and developer laptop attestation.
     """)),
    ("2026-01-29", ["daily"],
     dedent("""\
     ## Done
     - Wrote up threat model findings.
     - Started Istio installation on staging EKS cluster.

     ## Notes
     Istio install more complex than expected. Sidecar injection needed careful
     namespace labelling.
     """)),
    ("2026-01-30", ["daily"],
     dedent("""\
     ## Done
     - Istio mTLS working on staging.
     - 1:1 with Priya: developer portal discussion.

     ## Notes
     Priya's portal idea is interesting. DORA metrics as the north star is right.
     Need to investigate Backstage as the platform.
     """)),
    ("2026-02-02", ["daily"],
     dedent("""\
     ## Done
     - Week review: zero-trust rollout ahead of schedule.
     - Started Kubernetes network policy migration.

     ## Notes
     Network policy syntax is verbose. Will write a small generator script.
     """)),
    ("2026-02-03", ["daily"],
     dedent("""\
     ## Done
     - Network policy generator script. Reduced boilerplate by 80%.
     - AWS Transit Gateway research for hybrid connectivity.

     ## Notes
     Transit Gateway pricing is reasonable for our scale.
     """)),
    ("2026-02-04", ["daily"],
     dedent("""\
     ## Done
     - 1:1 with Maya: pair on Prometheus alerting. Coverage gap identified.
     - Reviewed Liam's Kubernetes study plan.

     ## Notes
     Alert-to-runbook gap is a real risk. Need to prioritise runbook coverage
     before next on-call rotation.
     """)),
    ("2026-02-05", ["daily"],
     dedent("""\
     ## Done
     - Wrote 5 runbooks for most common alerts.
     - LLM engineering notes session: read about RAG architectures.

     ## Notes
     RAG is the right pattern for the alaya project. Need to evaluate
     chunking strategies.
     """)),
    ("2026-02-06", ["daily"],
     dedent("""\
     ## Done
     - 1:1 with Alex: career growth review.
     - Set up Prometheus alertmanager routing for P1/P2/P3.

     ## Notes
     Alex's feedback: focus on written communication for senior IC impact.
     This note-taking system is already helping.
     """)),
    ("2026-02-09", ["daily"],
     dedent("""\
     ## Done
     - LLM search spike: benchmarked hybrid vs keyword search.
     - Reviewed API gateway options with James.

     ## Notes
     Hybrid search 30% better MRR. The result is clear enough to proceed.
     """)),
    ("2026-02-10", ["daily"],
     dedent("""\
     ## Done
     - 1:1 with Sam: data pipeline progress check.
     - Kubernetes migration: migrated user-service to EKS.

     ## Notes
     User-service migration went smoothly. Stateless services are straightforward.
     Database services will be harder.
     """)),
    ("2026-02-11", ["daily"],
     dedent("""\
     ## Done
     - Reviewed Chen-Wei's schema evolution RFC for data pipeline.
     - Wrote up embedding model evaluation notes.

     ## Notes
     nomic-embed-text-v1.5 vs all-minilm: nomic wins on MTEB retrieval tasks.
     Decision made.
     """)),
    ("2026-02-12", ["daily"],
     dedent("""\
     ## Done
     - Integrated nomic-embed-text-v1.5 into alaya project.
     - Reviewed ONNX backend performance: 2x faster than PyTorch on CPU.

     ## Notes
     ONNX runtime is a solid choice for production inference.
     """)),
    ("2026-02-13", ["daily"],
     dedent("""\
     ## Done
     - Alaya M1 tools: get_note, list_notes, get_backlinks working.
     - Code review for API gateway spike.

     ## Notes
     Envoy via Contour is the cleanest Kubernetes-native option.
     James's recommendation is well-reasoned.
     """)),
    ("2026-02-16", ["daily"],
     dedent("""\
     ## Done
     - 1:1 with James: API gateway decision finalised.
     - Started alaya M2 safety operations.

     ## Notes
     archive-before-delete pattern is good for a personal vault. Low risk.
     """)),
    ("2026-02-17", ["daily"],
     dedent("""\
     ## Done
     - Alaya delete_note with frontmatter archive reason.
     - Renamed notes wikilink update working.

     ## Notes
     Wikilink updates via `zk edit --interactive` would be complex.
     Using `rglob + re.sub` is simpler and sufficient.
     """)),
    ("2026-02-18", ["daily"],
     dedent("""\
     ## Done
     - 1:1 with Maya: Prometheus pair programming session.
     - Alaya LanceDB integration: upsert_note, delete_note_from_index.

     ## Notes
     LanceDB columnar storage is efficient for the hybrid search use case.
     """)),
    ("2026-02-19", ["daily"],
     dedent("""\
     ## Done
     - Hybrid search working end-to-end on vault_fixture.
     - Wrote debounce logic for file watcher.

     ## Notes
     Threading.Timer works well for debounce. 2s interval is right for
     rapid-fire save events from editors.
     """)),
    ("2026-02-20", ["daily"],
     dedent("""\
     ## Done
     - 1:1 with Alex: Q1 progress review.
     - File watcher integrated with LanceDB upsert.

     ## Notes
     Alex happy with platform migration progress. Zero-trust is ahead of schedule.
     """)),
    ("2026-02-23", ["daily"],
     dedent("""\
     ## Done
     - Alaya project: structured error codes, server registration refactor.
     - Started issue backlog review.

     ## Notes
     The `errors.py` pattern is clean. Structured codes help the LLM distinguish
     error types without parsing free text.
     """)),
    ("2026-02-24", ["daily"],
     dedent("""\
     ## Done
     - Fixed watcher start in server.py main().
     - Added debounce tests.
     - Closed 8 issues.

     ## Notes
     TDD rhythm working well. Write test → fail → implement → green.
     """)),
    ("2026-02-25", ["daily"],
     dedent("""\
     ## Done
     - Implemented get_note title lookup and structured return.
     - Added since/until/recent/sort to list_notes.

     ## Notes
     The structured metadata header makes notes much more useful as LLM context.
     """)),
    ("2026-02-26", ["daily"],
     dedent("""\
     ## Done
     - Added tags/since filters to search_notes and hybrid_search.
     - Implemented section_header and dated params for append_to_note.

     ## Notes
     The dated+section_header combination is exactly what's needed for 1:1 notes.
     """)),
    ("2026-02-27", ["daily"],
     dedent("""\
     ## Done
     - Vault root caching at registration (issue #17).
     - VaultStore singleton (issue #18).
     - Pushed dev, closed 6 issues.

     ## Notes
     Architecture improvements land cleanly. No test changes needed for the
     core functions since they take vault directly.
     """)),
]


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_note(path: Path, title: str, date: str, tags: list[str], body: str) -> None:
    tag_line = " ".join(f"#{t}" for t in tags)
    content = f"---\ntitle: {title}\ndate: {date}\n---\n{tag_line}\n\n{body.strip()}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def build_fixture(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)

    # Copy .zk config from the small fixture
    small = ROOT / "vault_fixture"
    shutil.copytree(small / ".zk", dest / ".zk")

    # resources/
    for slug, date, tags, body in RESOURCES:
        write_note(dest / "resources" / f"{slug}.md", slug, date, tags, body)

    # projects/
    for slug, date, tags, body in PROJECTS:
        write_note(dest / "projects" / f"{slug}.md", slug, date, tags, body)

    # people/
    for slug, date, tags, body in PEOPLE:
        write_note(dest / "people" / f"{slug}.md", slug, date, tags, body)

    # ideas/
    for slug, date, tags, body in IDEAS:
        write_note(dest / "ideas" / f"{slug}.md", slug, date, tags, body)

    # learning/
    for slug, date, tags, body in LEARNING:
        write_note(dest / "learning" / f"{slug}.md", slug, date, tags, body)

    # areas/
    for slug, date, tags, body in AREAS:
        write_note(dest / "areas" / f"{slug}.md", slug, date, tags, body)

    # daily/
    for date, tags, body in DAILY_ENTRIES:
        write_note(dest / "daily" / f"{date}.md", date, date, tags, body)

    # inbox.md
    (dest / "inbox.md").write_text("# Inbox\n\nQuick capture. Process weekly.\n")

    # Count
    md_files = list(dest.rglob("*.md"))
    print(f"Generated {len(md_files)} notes in {dest}")


if __name__ == "__main__":
    build_fixture(ROOT / "vault_fixture_large")
