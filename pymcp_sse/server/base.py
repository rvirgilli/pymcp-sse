"""
Base implementation of an MCP server using FastAPI and SSE.
"""
import asyncio
import inspect
import json
import uuid
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional, Callable, Awaitable, List

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from ..utils.log_setup import get_logger
from ..common.constants import *
from ..common.utils import (
    format_jsonrpc_response,
    format_jsonrpc_error,
    format_jsonrpc_notification
)

# Get logger
logger = get_logger("server.base")

class ClientConnection:
    """Represents a single client SSE connection and its associated state."""
    def __init__(self, client_id: str, server_session_id: str):
        self.client_id = client_id
        self.server_session_id = server_session_id
        self.message_queue = asyncio.Queue()
        self.initialized = False
        self.connected_at = datetime.now()
        self.last_heartbeat = self.connected_at
        self.protocol_version: Optional[str] = None
        self.client_info: Optional[Dict] = None
        self.ping_task: Optional[asyncio.Task] = None
        logger.info(f"[{self.server_session_id}] Connection created for client {client_id}")

    async def send(self, event: str, data: Any):
        """Put an event onto the client's SSE queue."""
        try:
            # Ensure data is serializable before queuing
            if not isinstance(data, (str, bytes)):
                payload = json.dumps(data)
            else:
                payload = data

            logger.debug(f"[{self.server_session_id}] Queuing event: {event}, Data: {str(payload)[:200]}...")
            await self.message_queue.put(ServerSentEvent(
                event=event,
                data=payload,
                comment=None # Default comment to None
            ))
        except TypeError as e:
            logger.error(f"[{self.server_session_id}] Failed to serialize message for event '{event}': {e}")
        except Exception as e:
            logger.error(f"[{self.server_session_id}] Failed to queue message for event '{event}': {e}", exc_info=True)

    def mark_initialized(self, protocol_version: str, client_info: Dict):
        """Mark the session as initialized."""
        self.initialized = True
        self.protocol_version = protocol_version
        self.client_info = client_info
        logger.info(f"[{self.server_session_id}] Session initialized. Protocol: {protocol_version}, Client: {client_info}")
        
    async def start_ping(self, ping_interval: int = DEFAULT_PING_INTERVAL):
        """Start the ping task for this connection."""
        if self.ping_task is None or self.ping_task.done():
            logger.info(f"[{self.server_session_id}] Starting SSE ping task...")
            try:
                self.ping_task = asyncio.create_task(self._send_sse_ping(ping_interval))
                # Add callback to log if task finishes unexpectedly
                self.ping_task.add_done_callback(self._ping_task_done_callback)
                logger.info(f"[{self.server_session_id}] Successfully created SSE ping task.")
            except Exception as e:
                logger.error(f"[{self.server_session_id}] Failed to create SSE ping task: {e}", exc_info=True)
        else:
            logger.warning(f"[{self.server_session_id}] Ping task already running.")
            
    def _ping_task_done_callback(self, task: asyncio.Task):
        """Callback function to log when the ping task finishes."""
        try:
            # Check if the task finished with an exception
            exception = task.exception()
            if exception:
                logger.error(f"[{self.server_session_id}] Ping task finished with error: {exception}", exc_info=exception)
            else:
                logger.info(f"[{self.server_session_id}] Ping task finished normally.")
        except asyncio.CancelledError:
            logger.info(f"[{self.server_session_id}] Ping task cancelled.")
        except Exception as e:
            logger.error(f"[{self.server_session_id}] Error in ping_task_done_callback: {e}", exc_info=True)

    async def stop_ping(self):
        """Stop the ping task for this connection."""
        if self.ping_task and not self.ping_task.done():
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass
            logger.info(f"[{self.server_session_id}] Stopped SSE ping task.")
        self.ping_task = None
        
    async def _send_sse_ping(self, interval: int):
        """Periodically sends a keep-alive ping event via the queue."""
        logger.info(f"[{self.server_session_id}] Ping task started with {interval}s interval.")
        ping_count = 0
        while True:
            try:
                await asyncio.sleep(interval)
                ping_count += 1
                
                # Send ping as a standard event
                try:
                    await self.send(event=EVENT_PING, data=str(ping_count))
                    logger.debug(f"[{self.server_session_id}] Sent SSE ping event #{ping_count}.")
                except Exception as send_err:
                    logger.error(f"[{self.server_session_id}] Error sending ping event #{ping_count}: {send_err}", exc_info=True)
                    
            except asyncio.CancelledError:
                logger.debug(f"[{self.server_session_id}] SSE ping task cancelled.")
                break
            except Exception as e:
                logger.error(f"[{self.server_session_id}] Error in SSE ping task: {e}", exc_info=True)
                break  # Stop task on unexpected error

class BaseMCPServer:
    """Base MCP Server implementation using FastAPI and SSE for transport."""
    
    def __init__(self, server_name: str = "MCP Server", ping_interval: int = DEFAULT_PING_INTERVAL):
        """
        Initialize the MCP server.
        
        Args:
            server_name: Name of the server (shown in logs and health endpoint)
            ping_interval: Interval in seconds for sending ping events to clients
        """
        self.server_name = server_name
        self.ping_interval = ping_interval
        self.active_connections: Dict[str, ClientConnection] = {}
        self.tool_registry: Dict[str, Callable] = {}
        
        # Create FastAPI app
        self.app = self._create_app()
        
        # Register the describe_tools tool by default
        self.register_tool(name="describe_tools")(self._describe_tools)
        
        logger.info(f"Initialized BaseMCPServer '{server_name}'")
        
    def _create_app(self) -> FastAPI:
        """Create and configure the FastAPI application with MCP endpoints."""
        
        @asynccontextmanager
        async def lifespan_manager(app: FastAPI):
            """Manage server lifecycle."""
            logger.info(f"Server '{self.server_name}' starting up...")
            yield
            logger.info(f"Server '{self.server_name}' shutting down...")
            # Gracefully stop pings for any remaining connections
            for conn in list(self.active_connections.values()):
                await conn.stop_ping()
            self.active_connections.clear()
            
        app = FastAPI(title=self.server_name, lifespan=lifespan_manager)
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"], 
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @app.get("/health", name="health_endpoint")
        async def health():
            """Health check endpoint."""
            return {
                "status": "ok",
                "service": self.server_name,
                "active_sessions": len(self.active_connections),
                "available_tools": list(self.tool_registry.keys())
            }
            
        @app.get("/sse")
        async def sse_endpoint(request: Request):
            """Handles client SSE connections."""
            client_id = request.query_params.get("client_id")
            if not client_id:
                client_id = str(uuid.uuid4())
                logger.info(f"Client connected without client_id, generated: {client_id}")
                
            server_session_id = str(uuid.uuid4())
            connection = ClientConnection(client_id, server_session_id)
            self.active_connections[server_session_id] = connection
            
            logger.info(f"[{server_session_id}] Client {client_id} connected. Total clients: {len(self.active_connections)}")
            
            # Define the message endpoint URL for this session
            base_url = str(request.url_for('message_endpoint'))
            # Ensure scheme matches the incoming request
            if request.url.scheme == "https":
                message_url = base_url.replace("http://", "https://", 1)
            else:
                message_url = base_url
                
            # Append session ID
            message_url_with_session = f"{message_url}?session_id={server_session_id}"
            
            # Initial event with endpoint info
            initial_event = ServerSentEvent(
                event=EVENT_ENDPOINT,
                data=json.dumps({
                    "endpoint": message_url_with_session,
                    "server_session_id": server_session_id
                })
            )
            
            # Start ping task for this connection
            await connection.start_ping(self.ping_interval)
            
            async def event_generator():
                """Yields events: endpoint info, messages from queue."""
                yield initial_event
                try:
                    while True:
                        # Wait for message from the queue
                        message = await connection.message_queue.get()
                        logger.debug(f"[{server_session_id}] Yielding SSE event: {message.event}")
                        yield message
                        connection.message_queue.task_done()
                except asyncio.CancelledError:
                    logger.info(f"[{server_session_id}] Event generator cancelled.")
                finally:
                    logger.info(f"[{server_session_id}] Cleaning up SSE connection.")
                    await connection.stop_ping()
                    if server_session_id in self.active_connections:
                        del self.active_connections[server_session_id]
                    logger.info(f"[{self.server_name} / {server_session_id}] Client {client_id} disconnected. Total clients: {len(self.active_connections)}")
            
            return EventSourceResponse(event_generator(), ping=self.ping_interval)
            
        @app.post("/messages", name="message_endpoint")
        async def message_endpoint(request: Request):
            """Handles incoming JSON-RPC requests."""
            server_session_id = request.query_params.get("session_id")
            request_id = None
            connection: Optional[ClientConnection] = None
            
            # Get connection if possible
            if server_session_id and server_session_id in self.active_connections:
                connection = self.active_connections[server_session_id]
                
            try:
                body = await request.json()
                log_session = server_session_id or 'NO_SESSION'
                logger.debug(f"[{log_session}] Received request: {body}")
                
                # Basic JSON-RPC validation
                if not isinstance(body, dict) or body.get("jsonrpc") != JSONRPC_VERSION or "method" not in body:
                    err = format_jsonrpc_error(ERROR_INVALID_REQUEST, "Invalid request structure", body.get("id"))
                    raise HTTPException(status_code=400, detail=err)
                    
                method = body["method"]
                params = body.get("params", {})
                request_id = body.get("id")
                
                # --- Initialization ---
                if method == METHOD_INITIALIZE:
                    if not connection:
                        logger.error(f"Initialize received for unknown session ID: {server_session_id}")
                        err = format_jsonrpc_error(ERROR_INVALID_SESSION, "Invalid session ID", request_id)
                        raise HTTPException(status_code=400, detail=err)
                        
                    if connection.initialized:
                        logger.warning(f"[{server_session_id}] Session already initialized.")
                    else:
                        protocol_version = params.get("protocolVersion", "unknown")
                        client_info = params.get("clientInfo", {})
                        connection.mark_initialized(protocol_version, client_info)
                        
                    # Send success response with available tools
                    response_data = {"capabilities": {"tools": list(self.tool_registry.keys())}}
                    response = format_jsonrpc_response(response_data, request_id)
                    await connection.send(EVENT_MESSAGE, response)
                    return Response(status_code=202)  # Accepted, response via SSE
                    
                # --- Validate session for other requests ---
                if not connection:
                    logger.warning(f"Request '{method}' received without valid session: {server_session_id}")
                    err = format_jsonrpc_error(ERROR_INVALID_SESSION, "Missing or invalid session ID", request_id)
                    raise HTTPException(status_code=400, detail=err)
                    
                if not connection.initialized:
                    logger.warning(f"[{server_session_id}] Received '{method}' before initialization.")
                    error_response = format_jsonrpc_error(ERROR_SERVER_NOT_INITIALIZED, "Session not initialized", request_id)
                    await connection.send(EVENT_MESSAGE, error_response)
                    return Response(status_code=202)
                    
                # --- Tool Call ---
                if method == METHOD_TOOL_CALL:
                    tool_name = params.get("name")
                    tool_kwargs = params.get("kwargs", {})
                    logger.info(f"[{server_session_id}] Processing tool call '{tool_name}' with args: {tool_kwargs}")
                    
                    if not tool_name or tool_name not in self.tool_registry:
                        error_response = format_jsonrpc_error(
                            ERROR_TOOL_NOT_FOUND, 
                            f"Tool not found: {tool_name}", 
                            request_id
                        )
                        await connection.send(EVENT_MESSAGE, error_response)
                        return Response(status_code=202)
                        
                    try:
                        tool_func = self.tool_registry[tool_name]
                        # Inject session ID if tool accepts it
                        if "server_session_id" in inspect.signature(tool_func).parameters:
                            tool_kwargs["server_session_id"] = server_session_id
                            
                        result = await tool_func(**tool_kwargs)
                        success_response = format_jsonrpc_response(result, request_id)
                        await connection.send(EVENT_MESSAGE, success_response)
                    except Exception as e:
                        logger.error(f"[{server_session_id}] Error executing tool '{tool_name}': {e}", exc_info=True)
                        error_response = format_jsonrpc_error(
                            ERROR_TOOL_EXECUTION_ERROR,
                            f"Tool execution error: {str(e)}",
                            request_id
                        )
                        await connection.send(EVENT_MESSAGE, error_response)
                        
                    return Response(status_code=202)
                    
                # --- Unknown Method ---
                logger.warning(f"[{server_session_id}] Unknown method: {method}")
                error_response = format_jsonrpc_error(
                    ERROR_METHOD_NOT_FOUND,
                    f"Method not found: {method}",
                    request_id
                )
                await connection.send(EVENT_MESSAGE, error_response)
                return Response(status_code=202)
                
            except HTTPException:
                # Re-raise HTTP exceptions
                raise
            except Exception as e:
                # General error handling
                log_session = server_session_id or 'UNKNOWN'
                logger.error(f"[{log_session}] Error processing request: {e}", exc_info=True)
                
                # Try to send error via SSE if possible
                if connection and request_id:
                    try:
                        error_response = format_jsonrpc_error(ERROR_INTERNAL_ERROR, f"Internal error: {str(e)}", request_id)
                        await connection.send(EVENT_MESSAGE, error_response)
                        return Response(status_code=202)
                    except Exception as send_err:
                        logger.error(f"[{log_session}] Failed to send error via SSE: {send_err}")
                        
                # Fallback to HTTP error
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
        
        # Hook for custom routes
        self._add_custom_routes(app)
                
        return app
    
    def _add_custom_routes(self, app: FastAPI):
        """
        Hook for adding custom routes to the FastAPI app.
        
        Override this method in subclasses to add custom endpoints.
        
        Args:
            app: The FastAPI application
        """
        pass
    
    def register_tool(self, name: str = None):
        """
        Decorator to register a tool function.
        
        Args:
            name: Tool name (uses function name if None)
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable[..., Awaitable[Any]]):
            tool_name = name or func.__name__
            logger.info(f"[{self.server_name}] Registering tool: {tool_name}")
            
            if tool_name in self.tool_registry:
                logger.warning(f"[{self.server_name}] Tool '{tool_name}' is being overwritten.")
                
            self.tool_registry[tool_name] = func
            return func
        return decorator
        
    async def push_notification(self, server_session_id: str, type_name: str, message: str, data: Optional[Dict] = None):
        """
        Send a notification to a specific client.
        
        Args:
            server_session_id: Target client's session ID
            type_name: Notification type (info, warning, error, data)
            message: Notification message
            data: Optional additional data
        """
        connection = self.active_connections.get(server_session_id)
        if connection:
            notification_params = {
                "type": type_name,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            if data:
                notification_params["data"] = data
                
            notification = format_jsonrpc_notification(METHOD_NOTIFICATION, notification_params)
            await connection.send(EVENT_MESSAGE, notification)
            logger.info(f"[{server_session_id}] Sent {type_name} notification: {message}")
        else:
            logger.warning(f"Notification attempted for non-existent session: {server_session_id}")
    
    async def broadcast_notification(self, type_name: str, message: str, data: Optional[Dict] = None):
        """
        Send a notification to all connected clients.
        
        Args:
            type_name: Notification type (info, warning, error, data)
            message: Notification message
            data: Optional additional data
        """
        if not self.active_connections:
            logger.info(f"No active connections for broadcast notification: {message}")
            return
            
        logger.info(f"Broadcasting {type_name} notification to {len(self.active_connections)} clients: {message}")
        
        for session_id in list(self.active_connections.keys()):
            try:
                await self.push_notification(session_id, type_name, message, data)
            except Exception as e:
                logger.error(f"Error sending notification to {session_id}: {e}")
    
    def run(self, host: Optional[str] = None, port: Optional[int] = None, **kwargs):
        """
        Run the server using uvicorn.

        Args:
            host: Host to listen on. If None, checks the MCP_HOST environment
                  variable, otherwise defaults to "0.0.0.0".
            port: Port to listen on. If None, checks the MCP_PORT environment
                  variable, otherwise defaults to 8000.
            **kwargs: Additional arguments passed to uvicorn.run
        """
        # Determine host and port
        final_host = host or os.environ.get("MCP_HOST") or "0.0.0.0"
        final_port = 8000 # Default port
        if port is not None:
            final_port = port
        else:
            env_port_str = os.environ.get("MCP_PORT")
            if env_port_str:
                try:
                    final_port = int(env_port_str)
                except ValueError:
                    logger.warning(f"Invalid MCP_PORT environment variable '{env_port_str}'. Using default port {final_port}.")

        # Use determined host/port in log message and uvicorn.run
        logger.info(f"Starting {self.server_name} on {final_host}:{final_port}")
        uvicorn.run(self.app, host=final_host, port=final_port, **kwargs)

    async def _describe_tools(self) -> Dict[str, Dict[str, Any]]:
        """
        Return detailed information about all available tools, including parameters and docstrings.
        
        Returns:
            Dict: A dictionary mapping tool names to their details (description, parameters)
        """
        tools_info = {}
        
        # Add describe_tools information first
        tools_info["describe_tools"] = {
            "description": "Returns detailed information about all available tools, including parameters and docstrings",
            "parameters": {},
            "return_type": "Dict[str, Dict[str, Any]]"
        }
        
        for tool_name, tool_func in self.tool_registry.items():
            # Skip the describe_tools function itself to avoid recursion in display
            if tool_name == "describe_tools":
                continue
                
            # Get docstring
            docstring = inspect.getdoc(tool_func) or "No description available"
            
            # Get signature information
            try:
                sig = inspect.signature(tool_func)
                parameters = {}
                
                for param_name, param in sig.parameters.items():
                    # Skip 'self' for class methods
                    if param_name == "self":
                        continue
                        
                    param_info = {
                        "required": param.default is inspect.Parameter.empty,
                        "type": str(param.annotation).replace("typing.", "").replace("<class '", "").replace("'>", ""),
                    }
                    
                    # Add default value if available
                    if param.default is not inspect.Parameter.empty and param.default is not None:
                        param_info["default"] = param.default
                        
                    parameters[param_name] = param_info
                
                # Get return type if annotated
                return_type = "Any"
                if sig.return_annotation is not inspect.Signature.empty:
                    return_type = str(sig.return_annotation).replace("typing.", "").replace("<class '", "").replace("'>", "")
                
                # Add tool info to result
                tools_info[tool_name] = {
                    "description": docstring,
                    "parameters": parameters,
                    "return_type": return_type
                }
            except Exception as e:
                logger.error(f"Error getting details for tool '{tool_name}': {e}")
                tools_info[tool_name] = {
                    "description": docstring,
                    "parameters": {},
                    "error": str(e)
                }
                
        return tools_info

    async def run_with_tasks(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        log_level: str = "info",
        concurrent_tasks: Optional[List[Callable[[], Awaitable[Any]]]] = None,
        shutdown_callbacks: Optional[List[Callable[[], Awaitable[Any]]]] = None,
        **uvicorn_kwargs
    ):
        """
        Run the MCP server along with additional concurrent asynchronous tasks.

        This method manages the Uvicorn server and user-provided tasks,
        handling graceful shutdown on KeyboardInterrupt.

        Args:
            host: The host address to bind the server to. If None, checks
                  the MCP_HOST environment variable, otherwise defaults to "0.0.0.0".
            port: The port to bind the server to. If None, checks the
                  MCP_PORT environment variable, otherwise defaults to 8000.
            log_level: The logging level for Uvicorn.
            concurrent_tasks: A list of callable functions that return awaitables
                              (coroutines) to run concurrently with the server.
            shutdown_callbacks: A list of callable functions that return awaitables
                                (coroutines) to execute before shutting down tasks.
            **uvicorn_kwargs: Additional keyword arguments passed directly to
                              uvicorn.Config.
        """
        # Determine host and port
        final_host = host or os.environ.get("MCP_HOST") or "0.0.0.0"
        final_port = 8000 # Default port
        if port is not None:
            final_port = port
        else:
            env_port_str = os.environ.get("MCP_PORT")
            if env_port_str:
                try:
                    final_port = int(env_port_str)
                except ValueError:
                    logger.warning(f"Invalid MCP_PORT environment variable '{env_port_str}'. Using default port {final_port}.")

        config = uvicorn.Config(
            self.app,
            host=final_host, # Use determined host
            port=final_port, # Use determined port
            log_level=log_level,
            lifespan="off", # Manage lifecycle manually in this method
            **uvicorn_kwargs
        )
        server = uvicorn.Server(config)

        server_task = None
        user_task_futures = []
        all_tasks = []

        try:
            # Create task for the uvicorn server
            server_task = asyncio.create_task(server.serve(), name="uvicorn_server")
            all_tasks.append(server_task)

            # Create asyncio tasks for concurrent user functions
            checked_tasks_coroutines = []
            if concurrent_tasks:
                for task_item_func in concurrent_tasks:
                    if callable(task_item_func):
                        try:
                            coro = task_item_func()
                            if inspect.isawaitable(coro):
                                checked_tasks_coroutines.append(coro)
                                logger.debug(f"Scheduled concurrent task: {getattr(task_item_func, '__name__', repr(task_item_func))}")
                            else:
                                logger.warning(f"Callable {getattr(task_item_func, '__name__', repr(task_item_func))} in concurrent_tasks did not return an awaitable, skipping.")
                        except Exception as e:
                            logger.error(f"Error calling concurrent task function {getattr(task_item_func, '__name__', repr(task_item_func))}: {e}", exc_info=True)
                    else:
                        logger.warning(f"Item {task_item_func} in concurrent_tasks is not callable, skipping.")

                user_task_futures = [asyncio.create_task(ct, name=f"concurrent_task_{i}") for i, ct in enumerate(checked_tasks_coroutines)]
                all_tasks.extend(user_task_futures)

            if not all_tasks:
                logger.warning("No server or concurrent tasks to run.")
                return # Nothing to run

            # Use determined host/port in log message
            logger.info(f"Running Uvicorn server on {final_host}:{final_port} and {len(user_task_futures)} concurrent task(s)...")
            # Wait for all tasks to complete or an exception to occur
            await asyncio.gather(*all_tasks)
            # This point is reached if all tasks complete successfully without interruption

        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt, initiating graceful shutdown...")
        except asyncio.CancelledError:
            logger.info("run_with_tasks task was cancelled.")
            # Propagate cancellation if needed, or just proceed to finally for cleanup
        except Exception as e:
            logger.error(f"An unexpected error occurred in run_with_tasks gather: {e}", exc_info=True)
            # Ensure cleanup happens in finally block

        finally:
            logger.info("Starting shutdown process...")

            # 1. Run shutdown callbacks
            if shutdown_callbacks:
                logger.info(f"Executing {len(shutdown_callbacks)} shutdown callback(s)...")
                callback_tasks = []
                for callback_func in shutdown_callbacks:
                    if callable(callback_func):
                        try:
                            callback_coro = callback_func()
                            if inspect.isawaitable(callback_coro):
                                callback_tasks.append(asyncio.create_task(callback_coro, name=f"shutdown_callback_{getattr(callback_func, '__name__', 'unknown')}"))
                                logger.debug(f"Scheduled shutdown callback: {getattr(callback_func, '__name__', repr(callback_func))}")
                            else:
                                logger.warning(f"Shutdown callback {getattr(callback_func, '__name__', repr(callback_func))} did not return an awaitable, skipping.")
                        except Exception as cb_e:
                            logger.error(f"Error calling shutdown callback function {getattr(callback_func, '__name__', repr(callback_func))}: {cb_e}", exc_info=True)

                    else:
                        logger.warning(f"Shutdown callback {callback_func} is not callable, skipping.")

                if callback_tasks:
                    try:
                        results = await asyncio.gather(*callback_tasks, return_exceptions=True)
                        for i, res in enumerate(results):
                            if isinstance(res, Exception):
                                logger.error(f"Shutdown callback {callback_tasks[i].get_name()} failed: {res}", exc_info=res)
                        logger.info("Shutdown callbacks finished.")
                    except Exception as e_cb_gather:
                         logger.error(f"Error gathering shutdown callbacks: {e_cb_gather}", exc_info=True)


            # 2. Cancel all running tasks (server + user tasks)
            tasks_to_cancel = []
            if server_task and not server_task.done():
                tasks_to_cancel.append(server_task)
                # Uvicorn specific shutdown signal
                if hasattr(server, 'should_exit'):
                     server.should_exit = True
                     logger.debug("Set server.should_exit = True")
            for task in user_task_futures:
                if not task.done():
                    tasks_to_cancel.append(task)

            if tasks_to_cancel:
                logger.info(f"Cancelling {len(tasks_to_cancel)} running task(s)...")
                for task in tasks_to_cancel:
                    task.cancel()

                # Wait for tasks to finish cancellation
                cancelled_wait_results = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                logger.info("Running tasks cancellation complete.")

                # Log any errors during cancellation (other than CancelledError)
                for i, result in enumerate(cancelled_wait_results):
                    task = tasks_to_cancel[i]
                    task_name = task.get_name() if hasattr(task, 'get_name') else f"task_{i}"
                    if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                        logger.error(f"Error during cancellation of task {task_name}: {result}", exc_info=result)
                    elif not isinstance(result, asyncio.CancelledError):
                         logger.debug(f"Task {task_name} finished during cancellation with result: {result}")

            logger.info("Shutdown process complete.")

            logger.info(f"Server '{self.server_name}' has shut down.")

    def run(self, host: Optional[str] = None, port: Optional[int] = None, **kwargs):
        """
        Run the server using uvicorn.

        Args:
            host: Host to listen on. If None, checks the MCP_HOST environment
                  variable, otherwise defaults to "0.0.0.0".
            port: Port to listen on. If None, checks the MCP_PORT environment
                  variable, otherwise defaults to 8000.
            **kwargs: Additional arguments passed to uvicorn.run
        """
        # Determine host and port
        final_host = host or os.environ.get("MCP_HOST") or "0.0.0.0"
        final_port = 8000 # Default port
        if port is not None:
            final_port = port
        else:
            env_port_str = os.environ.get("MCP_PORT")
            if env_port_str:
                try:
                    final_port = int(env_port_str)
                except ValueError:
                    logger.warning(f"Invalid MCP_PORT environment variable '{env_port_str}'. Using default port {final_port}.")

        # Use determined host/port in log message and uvicorn.run
        logger.info(f"Starting {self.server_name} on {final_host}:{final_port}")
        uvicorn.run(self.app, host=final_host, port=final_port, **kwargs) 