---
title: aws-networking
date: 2026-02-03
---
#aws #networking #vpc

## VPC fundamentals
- CIDR block planning: avoid 10.0.0.0/8 overlap with on-prem.
- Public subnets: internet gateway route. Private subnets: NAT gateway.
- Security groups vs NACLs: SGs are stateful; NACLs are stateless.

## Transit Gateway
Hub-and-spoke model for multi-VPC and hybrid connectivity.

## Links
- [[terraform-patterns]]
- [[zero-trust-research]]
