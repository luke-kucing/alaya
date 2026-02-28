---
title: platform-migration
date: 2026-02-15
---
#project #kubernetes #active

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
