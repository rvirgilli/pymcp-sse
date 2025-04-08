"""
Multi-server client implementation for MCP.
"""
import asyncio
from typing import Dict, Any, Optional, List, Union, Callable, Awaitable

from ..utils.log_setup import get_logger
from .base import BaseMCPClient
from ..common.exceptions import MCPError # Import base exception

# Get logger
logger = get_logger("client.multi")

class MultiMCPClient:
    """Client for connecting to multiple MCP servers."""
    
    def __init__(self, servers: Dict[str, str], **kwargs):
        """
        Initialize the multi-server client.
        
        Args:
            servers: Dictionary mapping server aliases to URLs
            **kwargs: Additional arguments to pass to BaseMCPClient constructor
                      (e.g., http_read_timeout, http_connect_timeout)
        """
        self.server_urls = servers
        self.clients: Dict[str, BaseMCPClient] = {}
        self.client_kwargs = kwargs
        logger.info(f"Initialized MultiMCPClient with {len(servers)} servers")
        
    async def _connect_and_init_single(self, alias: str, url: str) -> Dict[str, Any]:
        """Connect and initialize a single client."""
        logger.info(f"Attempting connection to server '{alias}' at {url}")
        # Pass stored kwargs to BaseMCPClient
        client = BaseMCPClient(url, client_name=f"MultiMCPClient_{alias}", **self.client_kwargs)
        
        try:
            connected = await client.connect()
            if not connected:
                # Connection failed before initialization
                await client.close() # Ensure cleanup
                return {"success": False, "error": "Connection refused or health check failed", "client": None}
                
            initialized = await client.initialize()
            if not initialized:
                # If initialization failed after successful connection
                await client.close() # Ensure cleanup
                return {"success": False, "error": "Initialization failed after connection", "client": None}
                
            logger.info(f"Successfully connected and initialized server '{alias}'")
            return {"success": True, "error": None, "client": client}
        except MCPError as e:
            logger.error(f"MCPError connecting to server '{alias}': {e}")
            await client.close() # Ensure cleanup
            return {"success": False, "error": str(e), "client": None}
        except Exception as e:
            logger.error(f"Unexpected error connecting to server '{alias}': {e}")
            await client.close() # Ensure cleanup
            return {"success": False, "error": f"Unexpected error: {e}", "client": None}

    async def connect_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Connect concurrently to all configured servers.
        
        Returns:
            Dictionary mapping server aliases to connection results.
            Each result is a dict: {'success': bool, 'error': Optional[str]}
        """
        tasks = [
            self._connect_and_init_single(alias, url) 
            for alias, url in self.server_urls.items()
        ]
        
        logger.info(f"Starting concurrent connection attempts to {len(tasks)} servers...")
        connection_results = await asyncio.gather(*tasks)
        
        final_results = {}
        successful_connections = 0
        
        # Process results and populate self.clients
        for i, alias in enumerate(self.server_urls.keys()):
            result = connection_results[i]
            final_results[alias] = {
                "success": result["success"],
                "error": result["error"]
            }
            if result["success"] and result["client"]:
                self.clients[alias] = result["client"]
                successful_connections += 1
            else:
                # Ensure failed clients are not stored
                if alias in self.clients:
                    del self.clients[alias]
                
        logger.info(f"Finished connection attempts. Successfully connected to {successful_connections}/{len(self.server_urls)} servers")
        
        # Try to fetch tool details from each server that has the describe_tools endpoint
        await self._fetch_tool_details()
        
        return final_results
        
    async def _fetch_tool_details(self):
        """
        Attempt to fetch detailed tool information from servers that support the describe_tools endpoint.
        """
        for alias, client in self.clients.items():
            if "describe_tools" in client.available_tools:
                try:
                    logger.info(f"Fetching detailed tool information from server '{alias}'")
                    # Call the describe_tools endpoint
                    client.tool_details = await client.call_tool("describe_tools")
                    logger.info(f"Retrieved detailed information for {len(client.tool_details)} tools from '{alias}'")
                except Exception as e:
                    logger.warning(f"Failed to fetch tool details from server '{alias}': {e}")
                    client.tool_details = {}
            else:
                client.tool_details = {}
        
    async def call_tool(self, server_alias: str, tool_name: str, **kwargs) -> Any:
        """
        Call a tool on a specific server.
        
        Args:
            server_alias: Server alias
            tool_name: Tool name
            **kwargs: Tool parameters
            
        Returns:
            Tool result
            
        Raises:
            KeyError: If the server alias is unknown
            ValueError: If the tool call fails
        """
        if server_alias not in self.clients:
            raise KeyError(f"Unknown server alias: {server_alias}")
            
        client = self.clients[server_alias]
        logger.info(f"Calling tool '{tool_name}' on server '{server_alias}'")
        return await client.call_tool(tool_name, **kwargs)
        
    def get_server_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all connected servers.
        
        Returns:
            Dictionary mapping server aliases to server info
        """
        info = {}
        
        for alias, client in self.clients.items():
            status = "connected" if client.connected else "disconnected"
            initialized = client.initialized
            
            info[alias] = {
                "status": status,
                "initialized": initialized,
                "available_tools": client.available_tools if initialized else [],
                "tool_details": client.tool_details if initialized and hasattr(client, "tool_details") else {}
            }
            
        return info
        
    def add_notification_callback(self, server_alias: Optional[str], callback: Callable[[str, Dict], Awaitable[None]]):
        """
        Add a notification callback for one or all servers.
        
        Args:
            server_alias: Server alias, or None for all servers
            callback: Callback function that takes server alias and notification params
        """
        if server_alias is None:
            # Add to all servers
            for alias, client in self.clients.items():
                self._add_wrapped_callback(alias, client, callback)
        elif server_alias in self.clients:
            # Add to specific server
            self._add_wrapped_callback(server_alias, self.clients[server_alias], callback)
        else:
            logger.warning(f"Cannot add callback: unknown server alias '{server_alias}'")
            
    def _add_wrapped_callback(self, alias: str, client: BaseMCPClient, callback: Callable[[str, Dict], Awaitable[None]]):
        """
        Add a wrapped callback to a client.
        
        Args:
            alias: Server alias
            client: Client instance
            callback: Callback function
        """
        async def wrapped_callback(params: Dict):
            await callback(alias, params)
            
        client.add_notification_callback(wrapped_callback)
        
    async def close(self):
        """Close all client connections."""
        logger.info("Closing all client connections")
        
        close_tasks = []
        for alias, client in self.clients.items():
            logger.debug(f"Closing connection to server '{alias}'")
            close_tasks.append(client.close())
            
        if close_tasks:
            await asyncio.gather(*close_tasks)
            
        self.clients.clear()
        logger.info("All client connections closed") 