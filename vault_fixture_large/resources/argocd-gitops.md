---
title: argocd-gitops
date: 2026-01-22
---
#kubernetes #gitops #argocd

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
