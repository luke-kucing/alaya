---
title: python-testing
date: 2026-01-16
---
#python #testing #pytest

## pytest patterns
- Fixtures for setup/teardown. `tmp_path` for temp files.
- `monkeypatch` for env vars and function patching.
- `pytest.mark.parametrize` for data-driven tests.

## Mocking
`unittest.mock.patch` as decorator or context manager.
`MagicMock` for auto-specced mocks.

## Property-based testing
Hypothesis generates diverse inputs automatically.

## Links
- [[python-packaging]]
- [[ci-cd-patterns]]
