# pymcp-sse HTTP/SSE Implementation Notes

This document details how the `pymcp_sse` library handles HTTP/SSE transport, particularly focusing on addressing common challenges like session initialization and reconnection.

## Session Management

The `pymcp_sse` library is designed to handle the complexities of HTTP/SSE transport, specifically avoiding the race condition described in `mcp_examples/docs/http_sse_initialization_issue.md`.

**Key Features:**

1.  **Clear State Management:** The `BaseMCPClient` maintains distinct `connected` and `initialized` states.
2.  **Endpoint Synchronization:** The client waits for the `endpoint` event via SSE *before* sending the `initialize` request, ensuring the correct message endpoint and server session ID are used.
3.  **Reconnection Logic:**
    *   The `_listen_sse` method includes automatic reconnection attempts with exponential backoff.
    *   **Session ID Handling:** Upon successful reconnection, the client checks if the server assigned a *new* `server_session_id` (which typically happens).
    *   **Automatic Reinitialization:** If a new session ID is detected, the client automatically:
        *   Marks the session as `initialized = False`.
        *   Cancels any pending requests associated with the old session.
        *   Triggers the `initialize` sequence again using the new session ID.
    *   **Error Handling:** If reconnection or reinitialization fails after multiple attempts, the connection is marked as permanently failed.

**How it Avoids the Race Condition:**

By explicitly tracking the `initialized` state and automatically re-initializing after a reconnect assigns a new session ID, `pymcp_sse` ensures that tool calls are only sent *after* the server session is confirmed ready. The client won't attempt to use an old, potentially invalid session ID after a network disruption.

## Usage Notes

- The reconnection and reinitialization logic is handled automatically by `BaseMCPClient` and `MultiMCPClient`.
- Developers using the library generally don't need to manually manage session state during reconnections.
- Monitor client logs (DEBUG level for more detail) to observe reconnection and reinitialization events.

## Comparison to Other Implementations

Unlike some libraries that might struggle with state synchronization between the HTTP request channel and the SSE event channel, `pymcp_sse`'s explicit state management and re-initialization protocol on the client-side ensures consistency even when network interruptions occur.

## Timeout Configuration for Stability

Maintaining stable, long-lived HTTP/SSE connections often requires careful configuration of timeouts at multiple layers to prevent premature disconnections:

1.  **Client-Side Read Timeout (`http_read_timeout`):**
    - Configured via the `BaseMCPClient` or `MultiMCPClient` constructor (e.g., `http_read_timeout=65`).
    - This sets the `httpx` client's read timeout.
    - **Crucial:** Must be set longer than the server's effective ping interval to prevent the client from closing the connection while waiting for a ping or data.
    - The default `httpx` read timeout is 5 seconds, which is often too short for SSE connections relying on pings.

2.  **Server-Side Keep-Alive Timeout (`timeout_keep_alive`):**
    - Configured by passing it as a keyword argument to `server.run()` (e.g., `timeout_keep_alive=65`).
    - This is passed to `uvicorn` and controls how long the ASGI server waits before closing an idle connection.
    - **Crucial:** Must be set longer than the effective ping interval.
    - The default `uvicorn` keep-alive timeout is 5 seconds.

3.  **SSE Ping Interval (`ping` in `EventSourceResponse`):**
    - `pymcp_sse` automatically sets this interval within `BaseMCPServer` to match the `ping_interval` configured for the server (`BaseMCPServer(ping_interval=...)`).
    - This ensures the `sse-starlette` library sends its own keep-alive pings at the same rate as the server's application-level ping task.
    - **Recommendation:** Ensure `ping_interval` is less than both the client's read timeout and the server's keep-alive timeout (e.g., 30 seconds is often reasonable).

By correctly configuring these three timeouts, you ensure that both the client and server expect the connection to stay open long enough for ping events to maintain it, preventing the common ~5-second disconnection issue caused by default ASGI/HTTP client timeouts. 