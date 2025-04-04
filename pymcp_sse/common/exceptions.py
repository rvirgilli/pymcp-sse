"""
Custom exceptions for PyMCP.
"""

class MCPError(Exception):
    """Base class for PyMCP exceptions."""
    pass

class MCPConnectionError(MCPError):
    """Error establishing or maintaining connection to the server."""
    pass

class MCPInitializationError(MCPError):
    """Error during the MCP initialization handshake."""
    pass

class MCPToolError(MCPError):
    """Error during a tool call execution."""
    pass 