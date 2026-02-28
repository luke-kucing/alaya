---
title: kubernetes-notes
date: 2026-02-01
---
#kubernetes #reference

## Overview
Reference notes on Kubernetes concepts relevant to the platform work.

## Key concepts
- Pods, Deployments, StatefulSets
- Helm charts and umbrella charts
- Helm dependency update before packaging
- ArgoCD multi-source pattern for value files

## Helm umbrella chart pattern
Parent chart declares sub-charts as dependencies in Chart.yaml.
Sub-charts bundled into the tgz via helm dependency update.
Apollo treats the whole tgz as a single product.

## Links
- [[platform-migration]]
