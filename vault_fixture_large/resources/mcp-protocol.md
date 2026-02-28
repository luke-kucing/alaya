---
title: mcp-protocol
date: 2026-02-10
---
#mcp #ai #protocol

## Model Context Protocol
MCP is an open standard for connecting AI assistants to external tools and data.
Uses JSON-RPC 2.0 over stdio or HTTP/SSE.

## Tool registration
Tools have a name, description, and JSON Schema for input parameters.
The server returns a list of tools; the client (LLM) decides which to call.

## Resources and prompts
MCP also supports resources (file/URI access) and prompt templates.

## Links
- [[llm-engineering]]
- [[fastapi-patterns]]
