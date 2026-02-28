---
title: ci-cd-patterns
date: 2026-01-04
---
#devops #ci #github-actions

## GitHub Actions
- Matrix builds for multiple Python versions / OSes.
- Reusable workflows: `workflow_call` trigger.
- OIDC for AWS credentials — no long-lived secrets.

## Pipeline stages
lint → unit tests → build → integration tests → deploy to staging → smoke test → prod

## Links
- [[git-workflows]]
- [[argocd-gitops]]
