"""
Example MCP Server #1 using PyMCP
"""
import os
import sys
import asyncio
import random
import time
from datetime import datetime

# Add pymcp to path if running directly from examples
current_dir = os.path.dirname(os.path.abspath(__file__))
package_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from pymcp_sse.server import BaseMCPServer
from pymcp_sse.utils import get_logger
from pymcp_sse.common.constants import NOTIFICATION_INFO, NOTIFICATION_WARNING, NOTIFICATION_ERROR, NOTIFICATION_DATA

# Get logger
logger = get_logger("examples.server1")

# Create server
server = BaseMCPServer(server_name="Example Server 1", ping_interval=30)

# --- Define Tools ---

@server.register_tool(name="echo_s1")
async def echo_s1_tool(text: str):
    """Echoes the provided text back (Server 1)."""
    logger.info(f"[Server 1] Echoing: {text}")
    return {"response": f"Server 1 echoes: {text}"}

@server.register_tool(name="schedule_notification_s1")
async def schedule_notification_s1_tool(message: str, delay_seconds: int = 5, server_session_id: str = None):
    """
    Schedules a push notification to be sent back to the client after a delay.
    Requires server_session_id injection.
    """
    if not server_session_id:
        raise ValueError("server_session_id is required for notifications but was not provided.")

    logger.info(f"[{server_session_id}] Scheduling notification: '{message}' in {delay_seconds}s")

    async def sender_task():
        await asyncio.sleep(delay_seconds)
        logger.info(f"[{server_session_id}] Sending delayed notification: '{message}'")
        await server.push_notification(
            server_session_id=server_session_id,
            type_name=NOTIFICATION_INFO,
            message=f"Delayed message from Server 1: {message}",
            data={"original_delay": delay_seconds}
        )

    # Run the sender in the background
    asyncio.create_task(sender_task())

    # Return immediate success confirmation
    return {"status": f"Notification '{message}' scheduled from Server 1 in {delay_seconds}s"}

@server.register_tool(name="get_weather_s1")
async def get_weather_s1_tool(location: str = "New York"):
    """
    Simulates retrieving weather information for a location.
    This is a dummy tool for demonstration.
    """
    logger.info(f"[Server 1] Getting weather for: {location}")
    
    # Simulate API call with random weather data
    weather_conditions = ["Sunny", "Rainy", "Cloudy", "Partly Cloudy", "Stormy", "Snowy", "Windy"]
    temperature = random.randint(5, 35)  # Celsius
    condition = random.choice(weather_conditions)
    humidity = random.randint(30, 90)
    
    return {
        "location": location,
        "temperature": temperature,
        "condition": condition,
        "humidity": f"{humidity}%",
        "timestamp": datetime.now().isoformat(),
        "source": "Server 1 Weather Service (Simulated)"
    }

@server.register_tool(name="translate_text_s1")
async def translate_text_s1_tool(text: str, target_language: str = "Spanish"):
    """
    Simulates text translation.
    This is a dummy tool for demonstration.
    """
    logger.info(f"[Server 1] Translating text to {target_language}: {text}")
    
    # Very simple "translation" simulation
    translations = {
        "Spanish": {"hello": "hola", "goodbye": "adiós", "thanks": "gracias"},
        "French": {"hello": "bonjour", "goodbye": "au revoir", "thanks": "merci"},
        "German": {"hello": "hallo", "goodbye": "auf wiedersehen", "thanks": "danke"}
    }
    
    # Default response
    result = f"[Translation to {target_language}] {text}"
    
    # Check if target language is supported
    if target_language in translations:
        # Very simple word replacement (just for demonstration)
        translated = text.lower()
        for eng, trans in translations[target_language].items():
            translated = translated.replace(eng, trans)
        result = translated
    
    return {
        "original_text": text,
        "translated_text": result,
        "target_language": target_language,
        "source": "Server 1 Translation Service (Simulated)"
    }

# --- Periodic Notification System ---

async def send_periodic_notifications():
    """Background task that sends various notifications to all connected clients."""
    logger.info("[Server 1] Starting periodic notification service")
    
    # Different types of notifications to send periodically
    notification_types = [
        {
            "type": NOTIFICATION_INFO,
            "topics": [
                "System running normally",
                "Weather update available",
                "Resources within normal limits",
                "Monitoring active"
            ]
        },
        {
            "type": NOTIFICATION_WARNING,
            "topics": [
                "System load increasing",
                "Service response time elevated",
                "Resource usage high",
                "Consider optimization"
            ]
        },
        {
            "type": NOTIFICATION_ERROR,
            "topics": [
                "External API integration status changed",
                "Configuration update recommended",
                "System maintenance scheduled",
                "New feature available"
            ]
        }
    ]
    
    while True:
        # Wait for a random interval (20-40 seconds)
        interval = random.randint(20, 40)
        await asyncio.sleep(interval)
        
        # Only proceed if we have connected clients
        if not server.active_connections:
            logger.debug("[Server 1] No active connections for notifications")
            continue
            
        # Select a random notification type and topic
        notif_type_data = random.choice(notification_types)
        notif_type = notif_type_data["type"]
        notif_message = random.choice(notif_type_data["topics"])
        
        # Add some dynamic content
        timestamp = datetime.now().isoformat()
        data = {
            "server": "Server 1",
            "timestamp": timestamp,
            "interval": interval,
            "active_connections": len(server.active_connections)
        }
        
        # Broadcast to all clients
        logger.info(f"[Server 1] Broadcasting {notif_type} notification: {notif_message}")
        await server.broadcast_notification(
            type_name=notif_type,
            message=notif_message,
            data=data
        )

# --- Run the server ---
if __name__ == "__main__":
    # Start the periodic notification task in a different way
    # First, create an event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Schedule the notification task
    loop.create_task(send_periodic_notifications())
    
    # Run the server - this will run in the same event loop
    server.run(
        host="0.0.0.0", 
        port=8101, 
        log_level="debug",
        timeout_keep_alive=65 # Set explicit keep-alive timeout
    ) 