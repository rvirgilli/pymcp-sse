"""
Pydantic models for MCP protocol messages.
"""
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field
from datetime import datetime

class ClientInfo(BaseModel):
    """Client information sent during initialization."""
    name: str
    version: str = "1.0.0"

class InitializeParams(BaseModel):
    """Parameters for the initialize method."""
    protocol_version: str = Field(..., alias="protocolVersion")
    capabilities: Dict[str, Any] = {}
    client_info: ClientInfo = Field(..., alias="clientInfo")

class InitializeRequest(BaseModel):
    """JSON-RPC initialize request."""
    jsonrpc: str = "2.0"
    method: str = "initialize"
    params: InitializeParams
    id: str

class ToolCallParams(BaseModel):
    """Parameters for the tools/call method."""
    name: str
    kwargs: Dict[str, Any] = {}

class ToolCallRequest(BaseModel):
    """JSON-RPC tool call request."""
    jsonrpc: str = "2.0"
    method: str = "tools/call"
    params: ToolCallParams
    id: str

class JsonRpcResponse(BaseModel):
    """JSON-RPC response."""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[str] = None

class JsonRpcError(BaseModel):
    """JSON-RPC error."""
    code: int
    message: str
    data: Optional[Any] = None

class JsonRpcErrorResponse(BaseModel):
    """JSON-RPC error response."""
    jsonrpc: str = "2.0"
    error: JsonRpcError
    id: Optional[str] = None

class NotificationParams(BaseModel):
    """Parameters for a notification."""
    type: str
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    data: Optional[Dict[str, Any]] = None

class Notification(BaseModel):
    """JSON-RPC notification."""
    jsonrpc: str = "2.0"
    method: str = "notification"
    params: NotificationParams

class Tool(BaseModel):
    """Tool definition."""
    name: str
    description: str = ""
    parameters: Dict[str, Any] = {}
    returns: Dict[str, Any] = {} 