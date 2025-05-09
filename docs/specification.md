# PyMCP-SSE Protocol Specification

This document outlines the specific implementation details and conventions used in the `pymcp-sse` library for the Model Context Protocol (MCP).

## 1. Overview

The primary goal of this protocol implementation is to enable robust communication between clients (often driven by Large Language Models - LLMs) and one or more servers that provide tools or capabilities. The protocol facilitates:

-   Client connection and session management.
-   Discovery of server capabilities (tools).
-   Execution of tools on servers by clients.
-   Server-initiated push notifications to clients.
-   Context sharing between client and server via request/response parameters.

## 2. Transport: HTTP/SSE

`pymcp-sse` uses standard HTTP for request/response and Server-Sent Events (SSE) for server-to-client push notifications and connection management.

### 2.1. Endpoints

Servers implementing `BaseMCPServer` expose the following standard HTTP endpoints relative to their base URL:

-   **`GET /health`**: A simple health check endpoint.
    -   **Success Response (200 OK):**
        ```json
        {
          "status": "ok",
          "service": "Server Name",
          "active_sessions": 0,
          "available_tools": ["tool1", "tool2", "..."]
        }
        ```
    -   Provides basic server status, name, number of active client connections, and a simple list of registered tool names.
-   **`GET /sse`**: The Server-Sent Events endpoint for establishing a persistent connection.
    -   **Query Parameter:** `client_id` (Optional): If provided by the client, it's used for logging. If omitted, the server generates a UUID.
    -   Establishes the SSE connection and sends the initial `endpoint` event (see Section 6).
-   **`POST /messages`**: The endpoint for sending client requests (JSON-RPC messages) to the server.
    -   **Query Parameter:** `session_id` (Required): The `server_session_id` provided by the server in the initial `endpoint` SSE event. This associates the request with an active SSE connection.
    -   **Request Body:** A standard JSON-RPC 2.0 Request object (see Section 4).
    -   **Success Response (202 Accepted):** Indicates the server accepted the request. The actual result or error will be sent asynchronously via the SSE connection.
    -   **Error Responses (e.g., 400 Bad Request):** Used for immediate errors like missing/invalid `session_id` or malformed JSON-RPC requests before processing. The response body contains a JSON-RPC Error object.

## 3. Session Management

-   **Client ID:** A unique identifier for a client instance (e.g., UUID). Provided by the client or generated by the server if missing on SSE connection. Used primarily for logging.
-   **Server Session ID:** A unique identifier (UUID) generated by the *server* for each established SSE connection.
-   **Initialization:** After connecting via SSE and receiving the `/messages` endpoint URL with the `server_session_id`, the client *must* send an `initialize` request to the `/messages` endpoint (including the `session_id` query parameter) before sending any other requests like `tools/call`.

## 4. Message Format: JSON-RPC 2.0

All communication via the `/messages` endpoint (client requests) and the `message` SSE event (server responses/notifications) adheres to the JSON-RPC 2.0 specification.

-   **Request Object:**
    ```json
    {
      "jsonrpc": "2.0",
      "method": "method_name",
      "params": { /* parameters object or array */ },
      "id": "request_id" /* Required for calls expecting a response */
    }
    ```
-   **Response Object (Success):**
    ```json
    {
      "jsonrpc": "2.0",
      "result": { /* result object or value */ },
      "id": "request_id"
    }
    ```
-   **Response Object (Error):**
    ```json
    {
      "jsonrpc": "2.0",
      "error": {
        "code": -32xxx,
        "message": "Error description",
        "data": { /* optional additional info */ }
      },
      "id": "request_id" /* or null for some errors */
    }
    ```
-   **Notification Object (No ID):**
    ```json
    {
      "jsonrpc": "2.0",
      "method": "notification_method_name",
      "params": { /* parameters object or array */ }
    }
    ```

## 5. Core Methods (JSON-RPC `method` field)

### 5.1. Client -> Server (`/messages` endpoint)

-   **`initialize`**:
    -   **Purpose:** Establishes the logical session after SSE connection. Must be the first request sent.
    -   **Params:**
        ```json
        {
          "protocolVersion": "0.3.0", // Current version supported by pymcp-sse
          "clientInfo": {
            "name": "Client Name",
            "version": "Client Version"
          },
          "capabilities": {} // Reserved for future use
        }
        ```
    -   **Response (via SSE `message` event):**
        -   **Success:** Result object contains server capabilities.
            ```json
            {
              "capabilities": {
                "tools": ["tool1", "tool2", ...] // List of available tool names
              }
            }
            ```
        -   **Error:** e.g., `ERROR_SERVER_ALREADY_INITIALIZED`.
-   **`tools/call`**:
    -   **Purpose:** Executes a registered tool on the server.
    -   **Params:**
        ```json
        {
          "name": "tool_name_to_call",
          "kwargs": { // Keyword arguments for the tool function
            "param1": "value1",
            "param2": 123
          }
        }
        ```
    -   **Response (via SSE `message` event):**
        -   **Success:** Result object contains the return value of the tool function. Structure is tool-dependent.
        -   **Error:** e.g., `ERROR_TOOL_NOT_FOUND`, `ERROR_INVALID_PARAMS`, `ERROR_TOOL_EXECUTION_ERROR`.
-   **`describe_tools`** (Standard Tool implemented by `BaseMCPServer`):
    -   **Purpose:** Allows clients to query detailed information about all available tools.
    -   **Params:** `{}` (No parameters needed).
    -   **Response (via SSE `message` event):**
        -   **Success:** Result is a dictionary where keys are tool names and values are objects containing details:
            ```json
            {
              "tool_name_1": {
                "description": "Docstring of the tool.",
                "parameters": {
                  "param_name": {
                    "required": true,
                    "type": "str", // Type hint string
                    "default": null // or default value if present
                  }, ...
                },
                "return_type": "str" // Return type hint string or "Any"
              },
              "tool_name_2": { ... }
            }
            ```
        -   **Error:** Should generally succeed if the tool exists.

### 5.2. Server -> Client (via SSE `message` event)

-   **`notification`**:
    -   **Purpose:** Sends unsolicited information from the server to the client.
    -   **Params:**
        ```json
        {
          "type": "info" | "warning" | "error" | "data", // Predefined types
          "message": "Human-readable notification message",
          "timestamp": "ISO 8601 timestamp string",
          "data": { /* Optional structured data payload */ }
        }
        ```
    -   **Response:** None (it's a notification).

## 6. SSE Events

The `GET /sse` endpoint streams the following event types:

-   **`endpoint`**:
    -   **Purpose:** Sent immediately upon successful SSE connection. Provides the client with the necessary information to interact further.
    -   **Data (JSON string):**
        ```json
        {
          "endpoint": "http(s)://server/messages?session_id=SERVER_SESSION_ID",
          "server_session_id": "SERVER_SESSION_ID" // The unique UUID for this connection
        }
        ```
-   **`message`**:
    -   **Purpose:** Carries JSON-RPC Response objects (results or errors for client requests) or Notification objects (server-initiated pushes).
    -   **Data (JSON string):** A complete JSON-RPC Response or Notification object (see Section 4).
-   **`ping`**:
    -   **Purpose:** Keep-alive message sent periodically by the server (`ping_interval`) to prevent connection timeouts. Can also be used by clients to detect connection health.
    -   **Data (String):** A simple counter or timestamp (implementation detail, can be ignored by client if only used for keep-alive).

## 7. Error Handling

Errors are communicated using standard JSON-RPC Error objects.

### 7.1. Standard JSON-RPC Codes

-   `-32700 Parse error`
-   `-32600 Invalid Request`
-   `-32601 Method not found`
-   `-32602 Invalid params`
-   `-32603 Internal error`

### 7.2. `pymcp-sse` Specific Error Codes

-   `-32002 Server not initialized`: Request (e.g., `tools/call`) sent before successful `initialize`.
-   `-32003 Server already initialized`: `initialize` sent on an already initialized session.
-   `-32004 Invalid session`: Request sent to `/messages` with a missing, invalid, or expired `session_id`.
-   `-32050 Tool execution error`: The tool function raised an unhandled exception during execution. `data` may contain traceback info.
-   `-32051 Tool not found`: The requested tool name in `tools/call` is not registered.
-   `-32060 Session expired`: Reserved for future potential session timeout implementation beyond SSE connection loss. 