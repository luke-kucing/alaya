---
title: api-gateway-project
date: 2026-02-05
---
#project #api #active

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
