# pymcp-sse Documentation Index

This directory contains documentation specific to the `pymcp_sse` library, focusing on usage patterns, implementation details, and integration guidelines.

## Key Documents

1.  [**General Usage & Best Practices**](./general_usage.md)
    *   Covers core concepts like server creation, tool registration, client connection, and push notification handling using `pymcp_sse`.
    *   Includes best practices adapted from general MCP guidelines, specific to this library.

2.  [**HTTP/SSE Implementation Notes**](./http_sse_notes.md)
    *   Details the library's robust handling of HTTP/SSE transport, including automatic session management and reconnection logic.
    *   Explains how `pymcp_sse` addresses common race conditions found in other implementations.

3.  [**LLM Integration Guide**](./llm_integration.md)
    *   Explains the `BaseLLMClient` abstraction layer.
    *   Shows how to use the provided `AnthropicLLMClient` example.
    *   Guides developers on creating custom LLM client implementations for other providers (e.g., OpenAI).

## Purpose

This documentation complements, rather than replaces, the official MCP specifications. It aims to help developers effectively use the `pymcp_sse` library to build MCP-compliant applications faster and with fewer pitfalls. 