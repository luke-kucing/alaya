---
title: service-mesh-notes
date: 2026-01-28
---
#kubernetes #istio #networking

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
