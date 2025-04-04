"""
Constants for the MCP protocol.
"""

# Protocol version
PROTOCOL_VERSION = "0.3.0"

# JSON-RPC
JSONRPC_VERSION = "2.0"

# Methods
METHOD_INITIALIZE = "initialize"
METHOD_SHUTDOWN = "shutdown"
METHOD_TOOL_CALL = "tools/call"
METHOD_NOTIFICATION = "notification"

# Error codes (Standard JSON-RPC + MCP specific)
ERROR_PARSE_ERROR = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL_ERROR = -32603

# MCP specific error codes
ERROR_SERVER_NOT_INITIALIZED = -32002
ERROR_SERVER_ALREADY_INITIALIZED = -32003
ERROR_INVALID_SESSION = -32004
ERROR_TOOL_EXECUTION_ERROR = -32050
ERROR_TOOL_NOT_FOUND = -32051
ERROR_SESSION_EXPIRED = -32060

# Event types
EVENT_MESSAGE = "message"
EVENT_ENDPOINT = "endpoint"
EVENT_PING = "ping"

# Notification types
NOTIFICATION_INFO = "info"
NOTIFICATION_WARNING = "warning"
NOTIFICATION_ERROR = "error"
NOTIFICATION_DATA = "data"

# Default values
DEFAULT_PING_INTERVAL = 30  # seconds
DEFAULT_RECONNECT_INTERVAL = 1  # seconds
DEFAULT_MAX_RECONNECT_ATTEMPTS = 5 