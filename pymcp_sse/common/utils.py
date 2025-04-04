"""
Utility functions for MCP protocol.
"""
from typing import Any, Dict, Optional
import json
import uuid
from datetime import datetime

from .constants import (
    JSONRPC_VERSION,
    METHOD_NOTIFICATION,
    METHOD_TOOL_CALL,
    METHOD_INITIALIZE
)

def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())

def format_jsonrpc_request(method: str, params: Dict[str, Any], request_id: Optional[str] = None) -> Dict:
    """
    Format a JSON-RPC request.
    
    Args:
        method: Method name
        params: Parameters
        request_id: Request ID (generated if None)
        
    Returns:
        JSON-RPC request dictionary
    """
    if not request_id:
        request_id = generate_request_id()
        
    return {
        "jsonrpc": JSONRPC_VERSION,
        "method": method,
        "params": params,
        "id": request_id
    }

def format_jsonrpc_response(result: Any, request_id: Any) -> Dict:
    """
    Format a JSON-RPC success response.
    
    Args:
        result: Response result
        request_id: Request ID
        
    Returns:
        JSON-RPC response dictionary
    """
    return {
        "jsonrpc": JSONRPC_VERSION,
        "result": result,
        "id": request_id
    }

def format_jsonrpc_error(code: int, message: str, request_id: Any, data: Optional[Any] = None) -> Dict:
    """
    Format a JSON-RPC error response.
    
    Args:
        code: Error code
        message: Error message
        request_id: Request ID
        data: Additional error data
        
    Returns:
        JSON-RPC error response dictionary
    """
    error_obj = {"code": code, "message": message}
    if data:
        try:
            # Test if data is JSON serializable
            json.dumps(data)
            error_obj["data"] = data
        except (TypeError, OverflowError):
            error_obj["data"] = str(data)
            
    return {
        "jsonrpc": JSONRPC_VERSION,
        "error": error_obj,
        "id": request_id
    }

def format_jsonrpc_notification(method: str, params: Dict) -> Dict:
    """
    Format a JSON-RPC notification.
    
    Args:
        method: Method name
        params: Parameters
        
    Returns:
        JSON-RPC notification dictionary
    """
    return {
        "jsonrpc": JSONRPC_VERSION,
        "method": method,
        "params": params
    }

def format_initialize_request(client_name: str, client_version: str = "1.0.0", protocol_version: str = "0.3.0") -> Dict:
    """
    Format an initialize request.
    
    Args:
        client_name: Client name
        client_version: Client version
        protocol_version: Protocol version
        
    Returns:
        Initialize request dictionary
    """
    return format_jsonrpc_request(
        method=METHOD_INITIALIZE,
        params={
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {
                "name": client_name,
                "version": client_version
            }
        },
        request_id=f"init-{generate_request_id()}"
    )

def format_tool_call_request(tool_name: str, kwargs: Dict[str, Any]) -> Dict:
    """
    Format a tool call request.
    
    Args:
        tool_name: Tool name
        kwargs: Tool parameters
        
    Returns:
        Tool call request dictionary
    """
    return format_jsonrpc_request(
        method=METHOD_TOOL_CALL,
        params={
            "name": tool_name,
            "kwargs": kwargs
        },
        request_id=f"call-{generate_request_id()}"
    )

def format_notification(type_name: str, message: str, data: Optional[Dict[str, Any]] = None) -> Dict:
    """
    Format a notification for a client.
    
    Args:
        type_name: Notification type (info, warning, error, etc.)
        message: Notification message
        data: Additional data
        
    Returns:
        Notification dictionary
    """
    params = {
        "type": type_name,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    
    if data:
        params["data"] = data
        
    return format_jsonrpc_request(
        method=METHOD_NOTIFICATION,
        params=params,
        request_id=None
    ) 