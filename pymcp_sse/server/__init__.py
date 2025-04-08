"""
MCP Server implementation
"""

from .base import BaseMCPServer
from .notifications import NotificationScheduler

# For backward compatibility or direct imports
async def push_notification(server, server_session_id, type_name, message, data=None):
    """
    Helper function to push a notification to a specific client via a server instance.
    
    Args:
        server: Instance of BaseMCPServer
        server_session_id: Target client session ID
        type_name: Type of notification (info, warning, error, etc.)
        message: Notification message
        data: Optional data payload
    """
    return await server.push_notification(
        server_session_id=server_session_id,
        type_name=type_name,
        message=message,
        data=data
    )

async def broadcast_notification(server, type_name, message, data=None):
    """
    Helper function to broadcast a notification to all connected clients via a server instance.
    
    Args:
        server: Instance of BaseMCPServer
        type_name: Type of notification (info, warning, error, etc.)
        message: Notification message
        data: Optional data payload
    """
    return await server.broadcast_notification(
        type_name=type_name,
        message=message,
        data=data
    )

# Import notification types for convenience
from ..common.constants import (
    NOTIFICATION_INFO,
    NOTIFICATION_WARNING,
    NOTIFICATION_ERROR,
    NOTIFICATION_DATA
)
