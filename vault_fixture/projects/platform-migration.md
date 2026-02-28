---
title: platform-migration
date: 2026-02-20
---
#project #kubernetes #platform

## Goal
Migrate the platform to a new deployment pipeline. Three umbrella charts.

## Tasks
- [x] audit current workloads
- [x] design target architecture
- [ ] migrate chart alpha
- [ ] migrate chart beta
- [ ] migrate chart gamma
- [ ] cut over DNS

## Notes
Umbrella charts supported natively. helm dependency update before packaging is mandatory.

## Links
- [[jordan]]
- [[kubernetes-notes]]
