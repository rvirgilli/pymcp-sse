"""
Abstract LLM Client interface for PyMCP.
This module provides a base class for LLM implementations that can be used with PyMCP.
"""

from abc import ABC, abstractmethod
import asyncio
import os
import logging
from typing import Dict, List, Any, Optional, Tuple

from ..utils import get_logger

logger = get_logger("client.llm")

class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients in PyMCP.
    Provides a common interface for different LLM implementations.
    """
    
    @property
    @abstractmethod
    def tool_call_prefix(self) -> str:
        """The prefix string that indicates a tool call in the LLM's output."""
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the LLM client.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        """
        Process a user message and generate a response.
        
        Args:
            message: The user's message
            context: Additional context information (e.g., available tools, conversation history)
            
        Returns:
            str: The LLM's response
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean up any resources used by the LLM client.
        """
        pass
    
    @property
    @abstractmethod
    def system_instructions(self) -> str:
        """
        Get the system instructions for the LLM.
        
        Returns:
            str: The system instructions/prompt
        """
        pass
    
    @system_instructions.setter
    @abstractmethod
    def system_instructions(self, instructions: str) -> None:
        """
        Set the system instructions for the LLM.
        
        Args:
            instructions: The system instructions/prompt
        """
        pass
    
    @abstractmethod
    def parse_tool_call(self, response: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """
        Parse the LLM's response text to find a tool call instruction.
        
        Args:
            response: The raw text response from the LLM.
            
        Returns:
            A tuple (server_name, tool_name, parameters) if a tool call is found,
            otherwise None.
        """
        pass

    @abstractmethod
    def get_default_tool_instructions(self) -> str:
        """
        Get the default instructions for how the LLM should format tool calls.
        This can be appended to the system instructions.
        
        Returns:
            str: Default tool usage instructions
        """
        return """
When you need to call a tool, include a line in your response formatted exactly like this:
TOOL_CALL: server=<server_name> tool=<tool_name> [param1=value1] [param2="value with spaces"] ...

Replace <server_name> and <tool_name> with the actual server and tool names, and include any necessary parameters.
Parameter values containing spaces must be enclosed in double quotes.

Example:
TOOL_CALL: server=weather_server tool=get_forecast location="New York" days=5

Only include the TOOL_CALL line if you are actually invoking a tool. Be helpful and conversational in the rest of your response.
""" 