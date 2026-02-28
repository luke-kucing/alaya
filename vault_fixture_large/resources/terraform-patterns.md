---
title: terraform-patterns
date: 2026-02-01
---
#iac #terraform #aws

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
