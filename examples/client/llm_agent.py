import re
import json
import asyncio
import logging
import os
import anthropic
from typing import Dict, List, Any, Callable, Optional
import shlex
import traceback

# Import from the pymcp_sse package
from pymcp_sse.client import MultiMCPClient
from pymcp_sse.utils import get_logger
from pymcp_sse.client.llm import BaseLLMClient

# Use the new logging utility
logger = get_logger("examples.client.llm_agent")

class AnthropicLLMClient(BaseLLMClient):
    """
    Anthropic Claude implementation of the BaseLLMClient interface.
    """
    
    def __init__(self):
        """Initialize the Anthropic Claude client."""
        self._api_key = None
        self._anthropic_client = None
        self._system_instructions = ""
        
    async def initialize(self) -> bool:
        """
        Initialize the LLM client with Anthropic API key.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        # Get API key from environment or .env file
        self._api_key = os.environ.get("ANTHROPIC_API_KEY")
        
        if not self._api_key:
            # Try to load from .env file
            try:
                env_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
                with open(env_file_path) as f:
                    for line in f:
                        if line.strip().startswith("ANTHROPIC_API_KEY="):
                            self._api_key = line.strip().split("=", 1)[1].strip()
                            break
            except FileNotFoundError:
                logger.warning("No .env file found. Please provide ANTHROPIC_API_KEY in environment.")
        
        if not self._api_key:
            logger.error("No Anthropic API key found. LLM functionality will be disabled.")
            return False
        
        # Initialize the Anthropic client
        try:
            self._anthropic_client = anthropic.Anthropic(api_key=self._api_key)
            logger.info("Anthropic client initialized.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            return False
    
    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        """
        Process a user message using Claude.
        
        Args:
            message: The user's message
            context: Additional context (tools, conversation history, etc.)
            
        Returns:
            str: The LLM's response
        """
        if not self._anthropic_client:
            return "LLM is not initialized. Please check your API key configuration."
            
        # Get conversation history from context
        history = context.get("history", [])
        
        # Build message history - Claude requires "user" and "assistant" roles
        messages = []
        
        # Add the last few conversation turns
        relevant_history = [entry for entry in history[-6:] 
                          if entry["role"] in ("user", "assistant")]
        
        for entry in relevant_history:
            messages.append({"role": entry["role"], "content": entry["message"]})
        
        # Add the current query if not already added
        if not any(m["role"] == "user" and m["content"] == message for m in messages):
            messages.append({"role": "user", "content": message})
        
        try:
            # Send to Claude - use system as a top-level parameter
            response = await asyncio.to_thread(
                self._anthropic_client.messages.create,
                model="claude-3-5-haiku-20241022",  # Faster, more efficient model
                # model="claude-3-7-sonnet-20250219",  # Higher capability model (uncomment to use)
                max_tokens=1000,
                system=self._system_instructions,
                messages=messages
            )
            
            llm_response = response.content[0].text
            logger.info(f"Received response from Claude: {llm_response[:100]}...")
            
            return llm_response
            
        except Exception as e:
            logger.error(f"Error processing message with Claude: {e}")
            return f"Sorry, I encountered an error when processing your request: {str(e)}"
    
    async def shutdown(self) -> None:
        """Clean up resources used by the LLM client."""
        # No specific cleanup needed for Anthropic client
        self._anthropic_client = None
    
    @property
    def system_instructions(self) -> str:
        """Get the system instructions."""
        return self._system_instructions
    
    @system_instructions.setter
    def system_instructions(self, instructions: str) -> None:
        """Set the system instructions."""
        self._system_instructions = instructions


class LLMAgent:
    """
    An LLM agent that uses a BaseLLMClient implementation to interact with MCP servers.
    """
    
    def __init__(self, client: MultiMCPClient, llm_client: Optional[BaseLLMClient] = None):
        """
        Initialize the LLM agent with a reference to the MultiMCPClient.
        
        Args:
            client: An instance of MultiMCPClient
            llm_client: An optional LLM client; if None, AnthropicLLMClient will be used
        """
        self.client = client
        self.available_tools = {}
        self.conversation_history = []
        self.running = False
        
        # Use the provided LLM client or create an Anthropic client by default
        self.llm_client = llm_client or AnthropicLLMClient()
        
    async def start(self):
        """
        Start the LLM agent and discover available tools.
        """
        logger.info("Starting LLM Agent")
        
        # Initialize the LLM client
        if not await self.llm_client.initialize():
            logger.error("Failed to initialize LLM client. LLM functionality will be limited.")
        
        # Set the system instructions
        await self.discover_tools()
        tools_info = self._format_tools_for_system_prompt()
        
        # Add specific instructions for sensor subscription tool
        sensor_tool_instructions = """
For the 'subscribe_sensor_s2' tool on server2, use the 'sensor_type' parameter (e.g., 'temperature', 'humidity', 'pressure', 'radiation') and optionally 'interval_seconds'. Do not use 'sensor_id'.
Example: TOOL_CALL: server=server2 tool=subscribe_sensor_s2 sensor_type="temperature" interval_seconds=30
"""

        system_prompt = f"""You are an AI assistant that helps users by calling tools available on connected MCP servers.

{tools_info}

You should:
1. Analyze the user's request and determine the best way to help them.
2. If you need to use a tool, select the appropriate one based on the user's request.
3. Provide helpful, accurate responses to the user's questions.

{sensor_tool_instructions}
{self.llm_client.get_default_tool_instructions()}
"""
        self.llm_client.system_instructions = system_prompt
        
        self.running = True
    
    async def stop(self):
        """Stop the LLM agent"""
        logger.info("Stopping LLM Agent")
        self.running = False
        
        # Shutdown the LLM client
        if self.llm_client:
            await self.llm_client.shutdown()
    
    async def discover_tools(self):
        """Discover available tools from all connected servers"""
        logger.info("Discovering available tools from all servers")
        
        # Clear current tools
        self.available_tools = {}
        
        # Get server information
        server_info = self.client.get_server_info()
        
        for server_name, info in server_info.items():
            if info.get("available_tools"):
                self.available_tools[server_name] = info["available_tools"]
        
        total_tools = sum(len(tools) for tools in self.available_tools.values())
        logger.info(f"Discovered {total_tools} tools across {len(self.available_tools)} servers")
        
        # Add to conversation history
        self._add_to_history("system", f"I found {total_tools} tools across {len(self.available_tools)} servers")
        
        return self.available_tools
    
    def _format_tools_for_system_prompt(self) -> str:
        """Format available tools into a string for the system prompt."""
        tools_info = "Available tools:\n"
        for server_name, tools in self.available_tools.items():
            tools_info += f"\nServer: {server_name}\n"
            for tool in tools:
                tools_info += f"- {tool}\n"
        return tools_info
    
    async def process_query(self, query: str) -> str:
        """
        Process a user query using the LLM client to determine action.
        
        Args:
            query: User's natural language query
            
        Returns:
            Response message
        """
        if not self.running:
            return "LLM Agent is not running. Please start it first."
        
        if not self.available_tools:
            await self.discover_tools()
        
        # Add query to conversation history
        self._add_to_history("user", query)
        
        # Process the message with the LLM client
        context = {
            "history": self.conversation_history,
            "tools": self.available_tools
        }
        
        llm_response = await self.llm_client.process_message(query, context)
        
        # Extract tool call if present
        tool_server, tool_name, params = self._extract_tool_call(llm_response)
        
        if tool_server and tool_name:
            # Tool call detected
            logger.info(f"Tool call detected: Server={tool_server}, Tool={tool_name}, Params={params}")
            
            # Remove the TOOL_CALL line from the response for cleaner output
            cleaned_response = re.sub(r"^TOOL_CALL:.*$", "", llm_response, flags=re.MULTILINE).strip()
            
            # Call the tool
            try:
                result = await self.client.call_tool(tool_server, tool_name, **params)
                result_str = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)
                
                # Add response to history
                self._add_to_history("assistant", cleaned_response)
                self._add_to_history("system", f"Tool result: {result_str}")
                
                # Return the response and tool result
                return f"{cleaned_response}\n\n--- Tool Result ---\n{result_str}"
            except Exception as e:
                error_msg = f"Error calling tool: {str(e)}"
                logger.error(error_msg)
                self._add_to_history("system", error_msg)
                return f"{cleaned_response}\n\n{error_msg}"
        else:
            # No tool call, just return the response
            self._add_to_history("assistant", llm_response)
            return llm_response
    
    def _extract_tool_call(self, response: str):
        """
        Extract tool call information from the LLM response.
        
        Returns:
            tuple: (server_name, tool_name, parameters)
        """
        # Look for the TOOL_CALL pattern
        tool_call_match = re.search(r'^TOOL_CALL:\s*(.*?)$', response, re.MULTILINE)
        
        if not tool_call_match:
            logger.info("No TOOL_CALL line detected in response")
            return None, None, {}
            
        tool_call_line = tool_call_match.group(1).strip()
        
        # Extract server and tool names
        server_match = re.search(r'server\s*=\s*([^\s]+)', tool_call_line)
        tool_match = re.search(r'tool\s*=\s*([^\s]+)', tool_call_line)
        
        if not server_match or not tool_match:
            logger.warning(f"Invalid TOOL_CALL format: {tool_call_line}")
            return None, None, {}
            
        server_name = server_match.group(1)
        tool_name = tool_match.group(1)
        
        # Extract parameters - handle quoted values
        params = {}
        param_pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s"]*))'
        
        for match in re.finditer(param_pattern, tool_call_line):
            param_name = match.group(1)
            if param_name in ('server', 'tool'):
                continue  # Skip server and tool parameters
                
            # Use quoted value if available, otherwise use unquoted value
            param_value = match.group(2) if match.group(2) is not None else match.group(3)
            
            # Try to convert numeric and boolean values
            if param_value.lower() == 'true':
                param_value = True
            elif param_value.lower() == 'false':
                param_value = False
            elif param_value.isdigit():
                param_value = int(param_value)
            elif param_value.replace('.', '', 1).isdigit() and param_value.count('.') == 1:
                param_value = float(param_value)
                
            params[param_name] = param_value
            
        return server_name, tool_name, params
    
    def _add_to_history(self, role: str, message: str):
        """Add a message to the conversation history."""
        self.conversation_history.append({
            "role": role,
            "message": message,
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # Keep history reasonably sized
        if len(self.conversation_history) > 100:
            self.conversation_history = self.conversation_history[-100:] 