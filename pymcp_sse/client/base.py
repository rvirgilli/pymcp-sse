"""
Base implementation of an MCP client using httpx and SSE.
"""
import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union

import httpx
from httpx_sse import aconnect_sse

from ..utils.log_setup import get_logger
from ..common.constants import *
from ..common.utils import (
    format_jsonrpc_request,
    format_initialize_request,
    format_tool_call_request,
    generate_request_id
)
from ..common.exceptions import (
    MCPError,
    MCPConnectionError,
    MCPInitializationError,
    MCPToolError
)

# Get logger
logger = get_logger("client.base")

class BaseMCPClient:
    """Base MCP Client implementation with HTTP/SSE transport."""
    
    def __init__(
        self,
        server_url: str,
        client_id: Optional[str] = None,
        client_name: str = "PyMCP Client",
        client_version: str = "0.1.0",
        reconnect_interval: int = DEFAULT_RECONNECT_INTERVAL, # Initial delay
        max_reconnect_attempts: int = DEFAULT_MAX_RECONNECT_ATTEMPTS,
        max_reconnect_delay: int = 60, # Maximum delay in seconds
        connect_timeout: int = 10, # Timeout for initial SSE connection/endpoint info
        init_timeout: int = 10,    # Timeout for initialize() response
        tool_call_timeout: int = 30, # Timeout for call_tool() response
        http_read_timeout: int = 30,  # HTTP read timeout
        http_connect_timeout: int = 10 # HTTP connect timeout
    ):
        """
        Initialize the MCP client.
        
        Args:
            server_url: Base URL of the MCP server
            client_id: Client ID (generated if None)
            client_name: Client name sent during initialization
            client_version: Client version sent during initialization
            reconnect_interval: Seconds for the *initial* wait between reconnection attempts
            max_reconnect_attempts: Maximum number of reconnection attempts (-1 for infinite)
            max_reconnect_delay: Maximum seconds to wait between reconnection attempts
            connect_timeout: Seconds to wait for initial connection and endpoint info
            init_timeout: Seconds to wait for the initialize response
            tool_call_timeout: Seconds to wait for a tool call response
            http_read_timeout: Seconds to wait for reading data from the server (applies to SSE stream)
            http_connect_timeout: Seconds to wait for establishing the initial HTTP connection
        """
        self.server_url = server_url.rstrip('/')
        self.client_id = client_id or str(uuid.uuid4())
        self.client_name = client_name
        self.client_version = client_version
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.max_reconnect_delay = max_reconnect_delay
        self.connect_timeout = connect_timeout
        self.init_timeout = init_timeout
        self.tool_call_timeout = tool_call_timeout
        self.http_read_timeout = http_read_timeout
        self.http_connect_timeout = http_connect_timeout
        
        # State
        self.connected = False
        self.initialized = False
        self.server_session_id: Optional[str] = None
        self.message_endpoint: Optional[str] = None
        self.available_tools: List[str] = []
        self.protocol_version: Optional[str] = None
        self.tool_details: Dict[str, Any] = {}
        
        # Transport
        self.http_client: Optional[httpx.AsyncClient] = None
        self.sse_task: Optional[asyncio.Task] = None
        
        # Response handling
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.notification_callbacks: List[Callable[[Dict], Awaitable[None]]] = []
        
        logger.info(f"Initialized BaseMCPClient {self.client_id} for server {server_url}")
        
    async def connect(self) -> bool:
        """
        Connect to the MCP server.
        
        Returns:
            True if connection was successful, False otherwise
        """
        # Clean up any existing connection
        if self.connected:
            await self.close()
            
        # Create HTTP client with configured timeouts
        timeouts = httpx.Timeout(self.http_connect_timeout, read=self.http_read_timeout)
        self.http_client = httpx.AsyncClient(timeout=timeouts)
        
        # Check server health first
        try:
            health_url = f"{self.server_url}/health"
            logger.info(f"Checking server health at {health_url}")
            response = await self.http_client.get(health_url)
            
            if response.status_code != 200:
                logger.error(f"Server health check failed: {response.status_code} {response.text}")
                return False
                
            logger.info(f"Server health check successful: {response.json()}")
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            await self.close()
            return False
            
        # Connect to SSE endpoint
        try:
            sse_url = f"{self.server_url}/sse?client_id={self.client_id}"
            logger.info(f"Connecting to SSE endpoint: {sse_url}")
            
            # Start SSE listener task
            endpoint_future = asyncio.get_event_loop().create_future()
            self.sse_task = asyncio.create_task(self._listen_sse(sse_url, endpoint_future))
            
            # Wait for endpoint info
            try:
                endpoint_info = await asyncio.wait_for(endpoint_future, timeout=self.connect_timeout)
                self.message_endpoint = endpoint_info["endpoint"]
                self.server_session_id = endpoint_info["server_session_id"]
                logger.info(f"Received message endpoint: {self.message_endpoint}")
                logger.info(f"Received server session ID: {self.server_session_id}")
            except asyncio.TimeoutError:
                logger.error("Timed out waiting for endpoint info from SSE connection")
                await self.close()
                return False
                
            # Mark as connected
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to SSE endpoint: {e}")
            await self.close()
            return False
            
    async def initialize(self) -> bool:
        """
        Initialize the session with the server.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        if not self.connected:
            logger.error("Cannot initialize: not connected")
            # Raise custom exception
            raise MCPConnectionError("Cannot initialize: client is not connected to the server")
            
        if self.initialized:
            logger.warning("Session already initialized")
            return True
            
        try:
            # Create initialize request
            request = format_initialize_request(
                client_name=self.client_name,
                client_version=self.client_version,
                protocol_version=PROTOCOL_VERSION
            )
            request_id = request["id"]
            
            # Create a future for the response
            response_future = asyncio.get_event_loop().create_future()
            self.pending_requests[request_id] = response_future
            
            # Send the request
            logger.info(f"Sending initialize request: {request}")
            response = await self.http_client.post(
                self.message_endpoint,
                json=request
            )
            
            if response.status_code != 202:
                logger.error(f"Unexpected response to initialize: {response.status_code} {response.text}")
                del self.pending_requests[request_id]
                return False
                
            # Wait for response via SSE
            try:
                result = await asyncio.wait_for(response_future, timeout=self.init_timeout)
                
                if "error" in result:
                    logger.error(f"Initialize failed: {result['error']}")
                    return False
                    
                # Store capabilities
                if "capabilities" in result.get("result", {}):
                    capabilities = result["result"]["capabilities"]
                    if "tools" in capabilities:
                        self.available_tools = capabilities["tools"]
                        logger.info(f"Available tools: {self.available_tools}")
                        
                # Mark as initialized
                self.initialized = True
                return True
                
            except asyncio.TimeoutError:
                logger.error("Timed out waiting for initialize response")
                del self.pending_requests[request_id]
                # Raise custom exception
                raise MCPInitializationError("Timed out waiting for initialize response from server")
                
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            # Raise custom exception
            raise MCPInitializationError(f"Initialization failed: {e}")
            
    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Call a tool on the server.
        
        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool parameters
            
        Returns:
            Tool result
            
        Raises:
            RuntimeError: If not connected or initialized
            ValueError: If the tool call fails
        """
        if not self.connected:
            # Raise custom exception
            raise MCPConnectionError("Cannot call tool: client is not connected to the server")
            
        if not self.initialized:
            # Raise custom exception
            raise MCPInitializationError("Cannot call tool: client session is not initialized")
            
        # Create tool call request
        request = format_tool_call_request(tool_name, kwargs)
        request_id = request["id"]
        
        # Create a future for the response
        response_future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = response_future
        
        try:
            # Send the request
            logger.info(f"Calling tool {tool_name} with params: {kwargs}")
            response = await self.http_client.post(
                self.message_endpoint,
                json=request
            )
            
            if response.status_code != 202:
                del self.pending_requests[request_id]
                # Raise custom exception
                raise MCPToolError(f"Unexpected server response to tool call: {response.status_code} {response.text}")
                
            # Wait for response via SSE
            try:
                result = await asyncio.wait_for(response_future, timeout=self.tool_call_timeout)
                
                if "error" in result:
                    error = result["error"]
                    # Raise custom exception
                    raise MCPToolError(f"Tool call failed: {error['message']} (code: {error['code']})")
                    
                return result.get("result")
                
            except asyncio.TimeoutError:
                # Raise custom exception
                raise MCPToolError(f"Timed out waiting for tool call response for '{tool_name}'")
                
        except MCPError: # Re-raise specific MCP errors
            raise
        except Exception as e:
            # Wrap other exceptions
            raise MCPToolError(f"Error during tool call '{tool_name}': {e}")
            
    async def _listen_sse(self, sse_url: str, endpoint_future: asyncio.Future):
        """
        Listen for SSE events from the server.
        
        Args:
            sse_url: SSE endpoint URL
            endpoint_future: Future to complete with endpoint info
        """
        retry_count = 0
        endpoint_received = False
        
        while retry_count < self.max_reconnect_attempts and self.http_client is not None:
            try:
                logger.info(f"Connecting to SSE endpoint: {sse_url}")
                
                # Connect to SSE endpoint
                async with aconnect_sse(self.http_client, "GET", sse_url) as event_source:
                    logger.info("SSE connection established")
                    retry_count = 0  # Reset retry count on successful connection
                    
                    # Process events
                    async for event in event_source.aiter_sse():
                        # Check if client is shutting down
                        if self.http_client is None:
                            logger.info("HTTP client closed, exiting SSE listener")
                            break
                            
                        try:
                            # Handle the event based on type
                            if event.event == EVENT_ENDPOINT:
                                # Endpoint info - first event after connection or reconnection
                                data = json.loads(event.data)
                                new_endpoint = data["endpoint"]
                                new_session_id = data["server_session_id"]
                                
                                # Check if this is a new session (reconnection case)
                                if endpoint_received and (new_session_id != self.server_session_id):
                                    logger.info(f"Received new session ID after reconnection: {new_session_id} (old: {self.server_session_id})")
                                    # Update session info
                                    self.message_endpoint = new_endpoint
                                    self.server_session_id = new_session_id
                                    self.initialized = False  # Mark as not initialized
                                    
                                    # Cancel any pending requests as they're for the old session
                                    for request_id, future in list(self.pending_requests.items()):
                                        if not future.done():
                                            future.set_exception(
                                                # Use custom exception
                                                MCPConnectionError("Session reinitialized after reconnection")
                                            )
                                    self.pending_requests.clear()
                                    
                                    # Re-initialize the session
                                    asyncio.create_task(self._reinitialize_after_reconnect())
                                elif not endpoint_received:
                                    # First connection
                                    self.message_endpoint = new_endpoint
                                    self.server_session_id = new_session_id
                                    endpoint_received = True
                                    
                                    # Set the endpoint future if it's not done
                                    if not endpoint_future.done():
                                        endpoint_future.set_result(data)
                                
                            elif event.event == EVENT_MESSAGE:
                                # JSON-RPC message
                                message = json.loads(event.data)
                                await self._handle_jsonrpc_message(message)
                                
                            elif event.event == EVENT_PING:
                                # Ping event - can ignore, just keeps connection alive
                                logger.debug(f"Received ping: {event.data}")
                                
                            else:
                                # Unknown event type
                                logger.warning(f"Received unknown event type: {event.event}")
                                
                        except Exception as e:
                            logger.error(f"Error processing SSE event: {e}", exc_info=True)
                    
                    logger.info("SSE connection closed normally")
                    
            except asyncio.CancelledError:
                logger.info("SSE listener cancelled")
                break
                
            except Exception as e:
                if self.http_client is None:
                    logger.info("HTTP client closed, exiting SSE listener")
                    break
                    
                retry_count += 1
                logger.error(f"SSE connection error (attempt {retry_count}/{self.max_reconnect_attempts if self.max_reconnect_attempts > 0 else 'infinite'}): {e}")
                
                if self.max_reconnect_attempts == -1 or retry_count < self.max_reconnect_attempts:
                    # Calculate backoff delay
                    delay = min(self.reconnect_interval * (2 ** (retry_count - 1)), self.max_reconnect_delay)
                    logger.info(f"Reconnecting in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error("Max reconnection attempts reached, giving up")
                    # Mark as disconnected
                    self.connected = False
                    
                    # Complete the endpoint future with an error if it's not done
                    if not endpoint_future.done():
                        endpoint_future.set_exception(
                            # Use custom exception
                            MCPConnectionError("Failed to connect to SSE endpoint after multiple retries")
                        )
                    break
        
        # Clean up if we exit the loop
        logger.info("SSE listener exiting")
        
    async def _reinitialize_after_reconnect(self):
        """
        Reinitialize the session after reconnection with a new session ID.
        """
        logger.info("Reinitializing session after reconnection")
        success = await self.initialize()
        
        if success:
            logger.info("Session successfully reinitialized")
        else:
            logger.error("Failed to reinitialize session after reconnection")
            # Mark as disconnected if we can't reinitialize
            self.connected = False
        
    async def _handle_jsonrpc_message(self, message: Dict):
        """
        Handle a JSON-RPC message from the server.
        
        Args:
            message: JSON-RPC message
        """
        logger.debug(f"Received JSON-RPC message: {message}")
        
        # Handle responses to pending requests
        if "id" in message and message["id"] in self.pending_requests:
            request_id = message["id"]
            future = self.pending_requests[request_id]
            
            if not future.done():
                future.set_result(message)
                
            del self.pending_requests[request_id]
            return
            
        # Handle notifications
        if "method" in message and message["method"] == METHOD_NOTIFICATION:
            logger.info(f"Received notification: {message['params']}")
            
            # Call all notification callbacks
            for callback in self.notification_callbacks:
                try:
                    await callback(message["params"])
                except Exception as e:
                    logger.error(f"Error in notification callback: {e}")
            return
            
        # Unknown message
        logger.warning(f"Received unknown message: {message}")
        
    def add_notification_callback(self, callback: Callable[[Dict], Awaitable[None]]):
        """
        Add a callback for notifications.
        
        Args:
            callback: Callback function that takes notification params
        """
        self.notification_callbacks.append(callback)
        logger.debug(f"Added notification callback: {callback}")
        
    def remove_notification_callback(self, callback: Callable[[Dict], Awaitable[None]]):
        """
        Remove a notification callback.
        
        Args:
            callback: Callback function to remove
        """
        if callback in self.notification_callbacks:
            self.notification_callbacks.remove(callback)
            logger.debug(f"Removed notification callback: {callback}")
            
    async def close(self):
        """Close the client connection."""
        logger.info("Closing client connection")
        
        # Cancel SSE listener task
        if self.sse_task and not self.sse_task.done():
            logger.debug("Cancelling SSE listener task")
            self.sse_task.cancel()
            try:
                await self.sse_task
            except asyncio.CancelledError:
                pass
            
        # Close HTTP client
        if self.http_client:
            logger.debug("Closing HTTP client")
            http_client = self.http_client
            self.http_client = None
            await http_client.aclose()
            
        # Clear state
        self.connected = False
        self.initialized = False
        self.server_session_id = None
        self.message_endpoint = None
        
        # Clear any pending requests
        for request_id, future in list(self.pending_requests.items()):
            if not future.done():
                future.set_exception(
                    # Use custom exception
                    MCPConnectionError("Client connection closed")
                )
        self.pending_requests.clear()
        
        logger.info("Client connection closed") 