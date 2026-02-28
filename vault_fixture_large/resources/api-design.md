---
title: api-design
date: 2026-01-24
---
#api #rest #design

## REST conventions
- Nouns not verbs in URLs: `/users/123` not `/getUser`.
- HTTP verbs semantics: GET (safe), POST (create), PUT/PATCH (update), DELETE.
- 2xx success, 4xx client error, 5xx server error.

## Versioning
URL versioning (`/v1/`) vs header versioning. URL is simpler to test.

## OpenAPI
Machine-readable spec. Auto-generate clients and docs.

## Links
- [[fastapi-patterns]]
