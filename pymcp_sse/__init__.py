"""
PyMCP: Python Model Context Protocol Library
"""

__version__ = "0.1.0"

from .server import BaseMCPServer
from .client import BaseMCPClient, MultiMCPClient
from .utils.log_setup import configure_logging, get_logger

__all__ = ["BaseMCPServer", "BaseMCPClient", "MultiMCPClient", "configure_logging", "get_logger"]
