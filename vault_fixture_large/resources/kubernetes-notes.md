---
title: kubernetes-notes
date: 2026-01-15
---
#kubernetes #reference

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
