---
title: networking-fundamentals
date: 2025-12-20
---
#networking #reference #tcp

## TCP/IP stack
L1 Physical → L2 Data link → L3 Network (IP) → L4 Transport (TCP/UDP) → L7 Application.

## TCP
Three-way handshake (SYN, SYN-ACK, ACK). Flow control via sliding window.
Congestion control: CUBIC (Linux default), BBR.

## DNS
Recursive vs authoritative resolvers. TTL caching. DNSSEC for integrity.

## Links
- [[aws-networking]]
- [[service-mesh-notes]]
