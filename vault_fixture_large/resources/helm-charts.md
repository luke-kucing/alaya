---
title: helm-charts
date: 2026-01-20
---
#kubernetes #helm #reference

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
