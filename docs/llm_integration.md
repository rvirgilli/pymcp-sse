# pymcp-sse LLM Integration Guide

The `pymcp_sse` library provides a flexible way to integrate Large Language Models (LLMs) to act as agents controlling MCP clients.

## The `BaseLLMClient` Abstraction

At the core of the integration is the `pymcp_sse.client.llm.BaseLLMClient` abstract base class. This class defines a standard interface for interacting with different LLM providers.

**Key Abstract Methods:**

- `async initialize()`: Sets up the connection to the LLM service (e.g., initializing API client with keys).
- `async process_message(message: str, context: Dict[str, Any]) -> str`: Sends a message (typically the user's query) and context (like tool lists and conversation history) to the LLM and returns the LLM's response string.
- `async shutdown()`: Cleans up any resources used by the LLM client.
- `system_instructions` (property): Gets or sets the main system prompt/instructions given to the LLM.

**Helper Methods:**

- `get_default_tool_instructions() -> str`: Provides the standard `TOOL_CALL:` format instructions that should typically be included in the system prompt.

## Using the `LLMAgent`

The `pymcp_sse.examples.client.llm_agent.LLMAgent` class orchestrates the interaction between the `MultiMCPClient` and a `BaseLLMClient` implementation.

**Initialization:**

```python
from pymcp_sse.client import MultiMCPClient
from pymcp_sse.examples.client.llm_agent import LLMAgent, AnthropicLLMClient

# Assuming 'mcp_client' is an initialized MultiMCPClient instance

# Use the default Anthropic client
llm_agent = LLMAgent(mcp_client)

# Or provide your own implementation
# from your_llm_module import YourCustomLLMClient
# llm_agent = LLMAgent(mcp_client, llm_client=YourCustomLLMClient())

# NOTE: Ensure mcp_client (MultiMCPClient) was created with appropriate timeouts
# Example:
# servers = {...}
# mcp_client = MultiMCPClient(servers, http_read_timeout=65, http_connect_timeout=10)

# Start the agent (initializes LLM client, discovers tools, sets prompt)
await llm_agent.start()
```

**Processing Queries:**

```python
user_query = "What is the weather in London?"
response = await llm_agent.process_query(user_query)
print(response)
```

The `LLMAgent.process_query` method handles:
1. Adding the query to the conversation history.
2. Calling the `BaseLLMClient.process_message` method with the query and context.
3. Parsing the LLM's response to look for the `TOOL_CALL:` line.
4. If `TOOL_CALL:` is found:
    - Extracting the server, tool, and parameters.
    - Calling the tool using `MultiMCPClient.call_tool()`.
    - Formatting the response including the tool result.
5. If no `TOOL_CALL:` is found, returning the LLM's response directly.
6. Updating the conversation history.

## Creating a Custom LLM Client

To use a different LLM provider (e.g., OpenAI, Gemini), create a new class that inherits from `BaseLLMClient` and implement the abstract methods.

```python
import aiohttp # Example dependency
from pymcp_sse.client.llm import BaseLLMClient
from typing import Dict, Any
import os

class MyGeminiClient(BaseLLMClient):
    def __init__(self):
        self._api_key = None
        self._session = None
        self._system_instructions = ""

    async def initialize(self) -> bool:
        self._api_key = os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            print("Error: GEMINI_API_KEY not found")
            return False
        self._session = aiohttp.ClientSession()
        print("MyGeminiClient initialized")
        return True

    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        if not self._session:
            return "Error: Client not initialized"
        
        # 1. Format history and message for Gemini API
        gemini_payload = self._format_payload(message, context)
        
        # 2. Make API call using self._session and self._api_key
        gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self._api_key}"
        try:
            async with self._session.post(gemini_api_url, json=gemini_payload) as response:
                response.raise_for_status()
                result = await response.json()
                # 3. Extract and return the text response from Gemini's result structure
                # (This depends on the specific Gemini API response format)
                return result['candidates'][0]['content']['parts'][0]['text'] # Example structure
        except Exception as e:
            print(f"Error calling Gemini: {e}")
            return f"Error communicating with LLM: {e}"

    async def shutdown(self) -> None:
        if self._session:
            await self._session.close()
        print("MyGeminiClient shut down")

    @property
    def system_instructions(self) -> str:
        return self._system_instructions

    @system_instructions.setter
    def system_instructions(self, instructions: str) -> None:
        # Gemini might handle system instructions differently (e.g., within the 'contents')
        self._system_instructions = instructions

    def _format_payload(self, message: str, context: Dict[str, Any]) -> Dict:
        # Implement logic to convert pymcp_sse history/context + system prompt
        # into the format expected by the Gemini API's generateContent endpoint.
        # This will involve creating the 'contents' list with appropriate roles.
        contents = []
        # Add system instructions (may need specific formatting for Gemini)
        # Add history from context['history']
        # Add current user message
        return {"contents": contents}

```

**Key Considerations for Custom Implementations:**

- **API Key Management:** Securely retrieve API keys (environment variables, `.env` files, etc.).
- **Payload Formatting:** Correctly format the conversation history, system prompt, and current message according to the specific LLM provider's API requirements.
- **Response Parsing:** Extract the relevant text response from the LLM API's result structure.
- **Error Handling:** Implement robust error handling for API calls.
- **System Prompt:** Understand how the chosen LLM handles system-level instructions (some use a dedicated parameter, others expect it as part of the message history). 