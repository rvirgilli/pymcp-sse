import re
import json
import asyncio
import logging
import os
import anthropic
from typing import Dict, List, Any, Callable, Optional, Tuple, Union
import shlex
import traceback
from dotenv import load_dotenv

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
        self._tool_call_prefix = "TOOL_CALL:"
        
    async def initialize(self) -> bool:
        """
        Initialize the LLM client with Anthropic API key.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        # Try to load from .env file
        try:
            # Load environment variables from .env file in the project root
            dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
            load_dotenv(dotenv_path=dotenv_path)
            self._api_key = os.environ.get("ANTHROPIC_API_KEY") # Reload after loading .env
        except Exception as e:
            logger.warning(f"Could not load .env file: {e}")
            
        if not self._api_key:
            # If still not found, check environment again (maybe it was set directly)
            self._api_key = os.environ.get("ANTHROPIC_API_KEY")
        
        if not self._api_key:
            logger.error("No Anthropic API key found (checked environment and .env). LLM functionality will be disabled.")
            return False
        
        # Initialize the Anthropic client
        try:
            self._anthropic_client = anthropic.Anthropic(api_key=self._api_key)
            logger.info("Anthropic client initialized.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            return False
    
    async def process_message(self, message_or_history: Union[str, List[Dict[str, str]]], context: Optional[Dict[str, Any]] = None) -> str:
        """
        Process a user message or conversation history using Claude.
        
        Args:
            message_or_history: Either a single user message string or the full conversation history
            context: Additional context (tools, conversation history, etc.)
            
        Returns:
            str: The LLM's response
        """
        if not self._anthropic_client:
            return "LLM is not initialized. Please check your API key configuration."
        
        # Build message history - Claude requires "user" and "assistant" roles
        messages = []
        
        # Handle different input formats
        if isinstance(message_or_history, str):
            # Single message input
            user_message = message_or_history
            
            # Get conversation history from context if available
            history = context.get("history", []) if context else []
            
            # Add the last few conversation turns from history
            relevant_history = [entry for entry in history[-6:] 
                            if entry["role"] in ("user", "assistant")]
            
            for entry in relevant_history:
                messages.append({"role": entry["role"], "content": entry["message"]})
            
            # Add the current message if not already in the history
            if not any(m["role"] == "user" and m["content"] == user_message for m in messages):
                messages.append({"role": "user", "content": user_message})
        else:
            # Full conversation history
            for entry in message_or_history[-6:]:  # Use last 6 turns at most
                if entry["role"] in ("user", "assistant"):
                    messages.append({"role": entry["role"], "content": entry["message"]})
        
        try:
            # Send to Claude - use system as a top-level parameter
            response = await asyncio.to_thread(
                self._anthropic_client.messages.create,
                # model="claude-3-5-haiku-20241022",  # Faster, more efficient model
                model="claude-3-opus-20240229",  # Higher capability model (using opus as sonnet is not available)
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
    
    @property
    def tool_call_prefix(self) -> str:
        """The prefix string that indicates a tool call in the LLM's output."""
        return self._tool_call_prefix
    
    def parse_tool_call(self, response: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """
        Parse the LLM's response text to find an Anthropic-style tool call instruction.
        Expected format: TOOL_CALL: server=X tool=Y param1="value1" param2=123 ...
        """
        # Look for the TOOL_CALL pattern
        tool_call_match = re.search(rf"^{re.escape(self.tool_call_prefix)}\s*(.*?)$", response, re.MULTILINE)
        
        if not tool_call_match:
            logger.debug("No TOOL_CALL prefix detected in response")
            return None
            
        tool_call_line = tool_call_match.group(1).strip()
        logger.debug(f"Found potential tool call line: {tool_call_line}")
        
        # Extract server and tool names
        server_match = re.search(r'server\s*=\s*([^\s]+)', tool_call_line)
        tool_match = re.search(r'tool\s*=\s*([^\s]+)', tool_call_line)
        
        if not server_match or not tool_match:
            logger.warning(f"Invalid TOOL_CALL format (missing server or tool): {tool_call_line}")
            return None
            
        server_name = server_match.group(1)
        tool_name = tool_match.group(1)
        logger.debug(f"Extracted server='{server_name}', tool='{tool_name}'")
        
        # Extract parameters - handle quoted values carefully
        params = {}
        # Regex to find key=value pairs, handling quotes correctly
        param_pattern = r'(\b\w+\b)\s*=\s*(?:"((?:\\"|[^"\\])*)"|([^\s"]+))'
        
        for match in re.finditer(param_pattern, tool_call_line):
            param_name = match.group(1)
            
            # Skip server and tool parameters themselves
            if param_name in ('server', 'tool'):
                continue
                
            # group(2) is the content inside quotes, group(3) is the unquoted value
            if match.group(2) is not None:
                # Value was quoted
                param_value_str = match.group(2).replace('\\"', '"')
            else:
                # Value was not quoted
                param_value_str = match.group(3)
                
            # Attempt to interpret the value
            try:
                # Try JSON decoding first for complex types
                param_value = json.loads(param_value_str)
            except json.JSONDecodeError:
                # If JSON fails, apply simple type conversion heuristics
                if param_value_str.lower() == 'true':
                    param_value = True
                elif param_value_str.lower() == 'false':
                    param_value = False
                elif param_value_str.isdigit():
                    param_value = int(param_value_str)
                elif param_value_str.replace('.', '', 1).isdigit() and param_value_str.count('.') <= 1:
                    try:
                        param_value = float(param_value_str)
                    except ValueError:
                        param_value = param_value_str
                else:
                    # Keep as string
                    param_value = param_value_str
                    
            params[param_name] = param_value
            logger.debug(f"Extracted param: {param_name}={param_value} (type: {type(param_value)})")
            
        return server_name, tool_name, params
    
    def get_default_tool_instructions(self) -> str:
        """
        Provide specific instructions for how Claude should format tool calls.
        """
        return (
            f"When you need to call a tool, output the following line **exactly**, replacing the placeholders:\n"
            f"{self.tool_call_prefix} server=<server_name> tool=<tool_name> [param1=\"value1\"] [param2=value2] ...\n"
            f"- Replace <server_name> with the target server (e.g., server1, server2).\n"
            f"- Replace <tool_name> with the exact tool name.\n"
            f"- Include required parameters (param=value).\n"
            f"- **Use quotes (\"\") around string values, especially if they contain spaces.**\n"
            f"- For boolean or numeric values, quotes are optional (e.g., count=5, active=true).\n"
            f"- Do not include any other text on the {self.tool_call_prefix} line.\n"
            f"- IMPORTANT: Before calling a tool like 'stop_periodic_task' that requires an ID from a previous step, check the conversation history for that ID. If you cannot find it, ask the user for the ID. Do not guess or call the starting tool again."
        )


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
        
        # Instructions for specific tools can still be useful
        sensor_tool_instructions = """
For the 'subscribe_sensor_s2' tool on server2, use the 'sensor_type' parameter (e.g., 'temperature', 'humidity', 'pressure', 'radiation') and optionally 'interval_seconds'. Do not use 'sensor_id'.
Example: TOOL_CALL: server=server2 tool=subscribe_sensor_s2 sensor_type="temperature" interval_seconds=30
"""

        server3_tool_instructions = """
For tools on server3 (send_notification_now_s3, schedule_notification_s3, start_periodic_notification_s3):
- Always include the 'type_name' parameter (e.g., "info", "warning", "error", "data").
- For schedule_notification_s3, include 'delay_seconds'.
- For start_periodic_notification_s3, include 'interval_seconds'.
Example: TOOL_CALL: server=server3 tool=send_notification_now_s3 type_name="info" message="Hello there!"
Example: TOOL_CALL: server=server3 tool=schedule_notification_s3 type_name="warning" message="Maintenance soon" delay_seconds=300
Example: TOOL_CALL: server=server3 tool=start_periodic_notification_s3 type_name="data" interval_seconds=60 message_prefix="System Load"
"""

        # Combine instructions
        system_prompt = f"""You are an AI assistant that helps users by calling tools available on connected MCP servers.

{tools_info}

**Important:** The list above contains all currently available tools and their detailed descriptions and parameters. When asked about available tools, please summarize the information provided above rather than calling the 'describe_tools' tool, as you already have the complete details.

You should:
1. Analyze the user's request.
2. If a tool is needed, select the appropriate one from the list above and call it using the specified format.
3. Provide helpful, accurate responses.

{sensor_tool_instructions}
{server3_tool_instructions}
{self.llm_client.get_default_tool_instructions()}
"""
        self.llm_client.system_instructions = system_prompt
        logger.debug(f"LLM System Prompt set: \n{system_prompt}") # Log the full prompt at debug level
        
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
        self.tool_details = {}
        
        # Get server information
        server_info = self.client.get_server_info()
        
        for server_name, info in server_info.items():
            if info.get("available_tools"):
                self.available_tools[server_name] = info["available_tools"]
                
                # Get detailed tool descriptions if available
                if info.get("tool_details"):
                    self.tool_details[server_name] = info["tool_details"]
                    logger.info(f"Retrieved detailed information for {len(info['tool_details'])} tools from {server_name}")
        
        total_tools = sum(len(tools) for tools in self.available_tools.values())
        logger.info(f"Discovered {total_tools} tools across {len(self.available_tools)} servers")
        
        # Add to conversation history
        self._add_to_history("system", f"I found {total_tools} tools across {len(self.available_tools)} servers")
        
        return self.available_tools
    
    def _format_tools_for_system_prompt(self) -> str:
        """
        Format the available tool information for inclusion in the system prompt.
        """
        # Use self.tool_details which contains the detailed info fetched
        # from describe_tools, not self.available_tools (which might just be names).
        if not self.tool_details: 
            return "No detailed tool information available."

        prompt_text = "You have access to the following tools:\n\n"
        
        # Iterate through the servers for which we have detailed tool info
        for server_name, tools_dict in self.tool_details.items():
            if not tools_dict:
                continue
            
            prompt_text += f"--- Server: {server_name} ---\n"
            # Iterate through the tool details dictionary for the server
            for tool_name, tool_info in tools_dict.items(): 
                if not isinstance(tool_info, dict): continue # Skip if info is not a dict
                
                # Skip describe_tools itself in the prompt
                if tool_name == "describe_tools":
                    continue
                    
                prompt_text += f"- Tool: {tool_name}\n"
                description = tool_info.get("description", "No description.").split('\n')[0]
                prompt_text += f"  Description: {description}\n"
                
                parameters = tool_info.get("parameters", {})
                if parameters:
                    prompt_text += "  Parameters:\n"
                    for param_name, param_info in parameters.items():
                        type_str = param_info.get('type', 'any')
                        required_str = "(required)" if param_info.get('required') else "(optional)"
                        default_str = f", default={param_info['default']}" if 'default' in param_info else ""
                        prompt_text += f"    - {param_name}: {type_str} {required_str}{default_str}\n"
                else:
                    prompt_text += "  Parameters: None\n"
                
                # Add specific instructions for stop_periodic_task
                if tool_name == "stop_periodic_task":
                    prompt_text += "    *Note: Requires the 'task_id' returned by 'start_periodic_pings'. Check history or ask user if ID is unknown.*\n"
                    
            prompt_text += "\n"
            
        prompt_text += self.llm_client.get_default_tool_instructions()
        
        return prompt_text
    
    async def generate_opening_statement(self) -> str:
        """Generates an opening statement from the LLM summarizing its capabilities."""
        logger.info("Generating opening statement from LLM...")
        if not self.llm_client or not self.llm_client.system_instructions:
            logger.warning("Cannot generate opening statement: LLM client not ready or system prompt not set.")
            return "Hello! I'm ready to help. Ask me anything or tell me what you'd like to do."
            
        try:
            # Use a simple prompt asking the LLM to introduce itself based on its system prompt
            # We send this as a one-off request, not using the main conversation history
            opening_prompt = "Based on your system instructions (which include available tools), please provide a brief opening statement to the user introducing yourself and summarizing your main capabilities."
            
            # Note: We call process_message with the prompt directly, not history
            response = await self.llm_client.process_message(opening_prompt, context=None) 
            logger.info("Received opening statement from LLM.")
            return response
        except Exception as e:
            logger.error(f"Error generating opening statement: {e}", exc_info=True)
            return "Hello! I encountered an issue generating my opening statement, but I'm ready to help."
    
    async def handle_message(self, user_message: str):
        """Handle a user message, interact with LLM, and execute tools if needed."""
        logger.info(f"User Message: {user_message}")
        self._add_to_history("user", user_message)
        
        print("Processing...")
        
        try:
            # Get response from LLM
            logger.debug("Sending conversation history to LLM")
            llm_response_text = await self.llm_client.process_message(user_message, {"history": self.conversation_history})
            logger.debug(f"Raw LLM Response: {llm_response_text}")
            
            # Process the LLM response (check for tool calls)
            await self._process_llm_response(llm_response_text)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            print(f"An error occurred: {e}")

    async def _process_llm_response(self, response_text: str):
        """Process the LLM response, handling potential tool calls."""
        tool_call_info = self.llm_client.parse_tool_call(response_text)
        
        if tool_call_info:
            server_name, tool_name, params = tool_call_info
            logger.info(f"Tool call detected: Server={server_name}, Tool={tool_name}, Params={params}")
            
            # --- Safeguard for stop_periodic_task --- 
            if tool_name == "stop_periodic_task":
                if "task_id" not in params or not params.get("task_id"):
                    missing_id_msg = "I need the task_id to stop the periodic task. Could you please provide it?"
                    logger.warning("LLM tried to call stop_periodic_task without a task_id. Asking user.")
                    self._add_to_history("assistant", missing_id_msg)
                    print(f"Assistant: {missing_id_msg}")
                    return # Stop processing, wait for user to provide ID
            # --- End Safeguard --- 

            try:
                # Add assistant's thought process before tool call to history
                # Extract the part of the response before the tool call
                thought_process = response_text.split(self.llm_client.tool_call_prefix)[0].strip()
                if thought_process:
                     self._add_to_history("assistant", thought_process)
                     print(f"Assistant: {thought_process}") # Print the thought process
                     
                # Execute the tool call
                tool_result = await self.client.call_tool(server_name, tool_name, **params)
                logger.info(f"Tool call result: {tool_result}")
                
                # Format the result for history and user display
                result_message = f"--- Tool Result ({server_name}.{tool_name}) ---\n{json.dumps(tool_result, indent=2)}"
                self._add_to_history("assistant", result_message) # Use assistant role for tool results
                print(f"\n{result_message}") # Print the formatted result
                
                # (Optional) Send result back to LLM for summary/next step?
                # For now, we just display the result.
                
            except Exception as e:
                error_message = f"Error executing tool {server_name}.{tool_name}: {e}"
                logger.error(error_message, exc_info=True)
                detailed_error = traceback.format_exc()
                self._add_to_history("assistant", f"Error: {error_message}\nDetails: {detailed_error}")
                print(f"\nError executing tool: {e}")
        else:
            # No tool call, just add the LLM's response to history and print
            self._add_to_history("assistant", response_text)
            print(f"Assistant: {response_text}")
    
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