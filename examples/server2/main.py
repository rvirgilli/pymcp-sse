"""
Example MCP Server #2 using PyMCP
"""
import os
import sys
import asyncio
import random
import time
import math
from datetime import datetime
from typing import Dict, Any, Optional

# Add pymcp to path if running directly from examples
current_dir = os.path.dirname(os.path.abspath(__file__))
package_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from pymcp_sse.server import BaseMCPServer
from pymcp_sse.utils import get_logger
from pymcp_sse.common.constants import NOTIFICATION_INFO, NOTIFICATION_WARNING, NOTIFICATION_ERROR, NOTIFICATION_DATA

# Get logger
logger = get_logger("examples.server2")

# Create server
server = BaseMCPServer(server_name="Example Server 2", ping_interval=60)

# Store for sensor subscriptions
sensor_subscriptions = {}

# --- Define Tools ---

@server.register_tool(name="echo_s2")
async def echo_s2_tool(text: str):
    """Echoes the provided text back (Server 2)."""
    logger.info(f"[Server 2] Echoing: {text}")
    return {"response": f"Server 2 echoes: {text}"}

@server.register_tool(name="ping_s2")
async def ping_s2_tool():
    """Responds with a simple pong message (Server 2)."""
    logger.info("[Server 2] Responding to ping")
    return {"response": "pong_from_server2"}

@server.register_tool(name="calculate_s2")
async def calculate_s2_tool(operation: str, values: list):
    """
    Performs basic mathematical operations on a list of values.
    
    Args:
        operation: One of 'sum', 'average', 'min', 'max', 'median'
        values: List of numbers to operate on
    """
    logger.info(f"[Server 2] Calculating {operation} on {values}")
    
    if not values:
        return {"error": "No values provided"}
    
    try:
        # Convert all values to floats
        numbers = [float(v) for v in values]
        
        if operation == "sum":
            result = sum(numbers)
        elif operation == "average":
            result = sum(numbers) / len(numbers)
        elif operation == "min":
            result = min(numbers)
        elif operation == "max":
            result = max(numbers)
        elif operation == "median":
            sorted_nums = sorted(numbers)
            mid = len(sorted_nums) // 2
            if len(sorted_nums) % 2 == 0:
                result = (sorted_nums[mid-1] + sorted_nums[mid]) / 2
            else:
                result = sorted_nums[mid]
        else:
            return {"error": f"Unknown operation: {operation}"}
        
        return {
            "operation": operation,
            "values": values,
            "result": result
        }
    except Exception as e:
        return {"error": f"Calculation error: {str(e)}"}

@server.register_tool(name="search_database_s2")
async def search_database_s2_tool(query: str, limit: int = 3):
    """
    Simulates searching a database with the given query.
    This is a dummy implementation for demonstration.
    """
    logger.info(f"[Server 2] Searching database for: {query}")
    
    # Simulate database entries
    database = [
        {"id": 1, "title": "Introduction to AI", "content": "AI is transforming many industries..."},
        {"id": 2, "title": "Machine Learning Basics", "content": "ML is a subset of AI focused on..."},
        {"id": 3, "title": "Neural Networks Explained", "content": "Neural networks are inspired by..."},
        {"id": 4, "title": "Data Science Applications", "content": "Data science is applied in healthcare..."},
        {"id": 5, "title": "Python for AI Development", "content": "Python is widely used in AI due to..."},
        {"id": 6, "title": "LLM Applications", "content": "Large Language Models have many applications..."},
        {"id": 7, "title": "AI Ethics", "content": "Ethical considerations in AI include..."}
    ]
    
    # Simple search simulation
    results = []
    query_terms = query.lower().split()
    for entry in database:
        title = entry["title"].lower()
        content = entry["content"].lower()
        
        score = 0
        for term in query_terms:
            if term in title:
                score += 2
            if term in content:
                score += 1
        
        if score > 0:
            results.append({**entry, "relevance_score": score})
    
    # Sort by relevance and limit
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {
        "query": query,
        "results_count": len(results),
        "results": results[:limit]
    }

@server.register_tool(name="subscribe_sensor_s2")
async def subscribe_sensor_s2_tool(sensor_type: str, interval_seconds: int = 15, server_session_id: str = None):
    """
    Subscribes to a simulated sensor feed that sends updates via push notifications.
    
    Args:
        sensor_type: Type of sensor to subscribe to ('temperature', 'humidity', 'pressure', 'radiation')
        interval_seconds: How often to send updates (5-60 seconds)
        server_session_id: Session ID for push notifications (injected automatically)
    """
    if not server_session_id:
        raise ValueError("Session ID is required for sensor subscription")
    
    # Validate inputs
    valid_sensors = ["temperature", "humidity", "pressure", "radiation"]
    if sensor_type not in valid_sensors:
        return {"error": f"Invalid sensor type. Choose from: {', '.join(valid_sensors)}"}
    
    interval = max(5, min(60, interval_seconds))  # Clamp to 5-60 seconds
    
    logger.info(f"[Server 2] Client {server_session_id} subscribing to {sensor_type} sensor with {interval}s interval")
    
    subscription_id = f"{server_session_id}_{sensor_type}_{int(time.time())}"
    sensor_subscriptions[subscription_id] = {
        "sensor_type": sensor_type,
        "interval": interval,
        "session_id": server_session_id,
        "created_at": datetime.now().isoformat(),
        "last_reading": None
    }
    
    # Start subscription immediately with first reading
    asyncio.create_task(send_sensor_reading(subscription_id))
    
    return {
        "status": "subscribed",
        "subscription_id": subscription_id,
        "sensor_type": sensor_type,
        "interval_seconds": interval,
        "message": f"You are now subscribed to {sensor_type} sensor updates every {interval} seconds"
    }

@server.register_tool(name="unsubscribe_sensor_s2")
async def unsubscribe_sensor_s2_tool(subscription_id: str, server_session_id: str = None):
    """
    Unsubscribes from a sensor feed.
    
    Args:
        subscription_id: The ID returned from subscribe_sensor_s2
        server_session_id: Session ID (injected automatically)
    """
    if not server_session_id:
        raise ValueError("Session ID is required for sensor unsubscription")
    
    if not sensor_subscriptions:
        return {"error": "No subscriptions exist"}
    
    if subscription_id not in sensor_subscriptions:
        return {"error": f"Subscription ID {subscription_id} not found"}
    
    # Check that the session ID matches the subscription
    sub = sensor_subscriptions[subscription_id]
    if sub["session_id"] != server_session_id:
        return {"error": "You can only unsubscribe from your own subscriptions"}
    
    # Remove the subscription
    sensor_type = sub["sensor_type"]
    del sensor_subscriptions[subscription_id]
    logger.info(f"[Server 2] Client {server_session_id} unsubscribed from {sensor_type} sensor ({subscription_id})")
    
    return {
        "status": "unsubscribed",
        "subscription_id": subscription_id,
        "message": f"Successfully unsubscribed from {sensor_type} sensor updates"
    }

# --- Sensor Data Simulation ---

async def send_sensor_reading(subscription_id: str):
    """Sends a simulated sensor reading for a subscription."""
    if subscription_id not in sensor_subscriptions:
        logger.warning(f"[Server 2] Attempted to send reading for unknown subscription: {subscription_id}")
        return
    
    sub = sensor_subscriptions[subscription_id]
    session_id = sub["session_id"]
    sensor_type = sub["sensor_type"]
    interval = sub["interval"]
    
    # Check if client is still connected
    if session_id not in server.active_connections:
        logger.info(f"[Server 2] Removing subscription {subscription_id} because client disconnected")
        if subscription_id in sensor_subscriptions:
            del sensor_subscriptions[subscription_id]
        return
    
    try:
        # Generate sensor reading based on type
        reading = generate_sensor_reading(sensor_type, sub.get("last_reading"))
        
        # Store the last reading
        sensor_subscriptions[subscription_id]["last_reading"] = reading
        
        # Send the notification
        await server.push_notification(
            server_session_id=session_id,
            type_name=NOTIFICATION_DATA,
            message=f"New {sensor_type} reading",
            data={
                "subscription_id": subscription_id,
                "sensor_type": sensor_type,
                "reading": reading,
                "timestamp": datetime.now().isoformat(),
                "next_update_in_seconds": interval
            }
        )
        
        logger.info(f"[Server 2] Sent {sensor_type} sensor reading to client {session_id}")
        
        # Schedule the next reading after interval
        await asyncio.sleep(interval)
        asyncio.create_task(send_sensor_reading(subscription_id))
        
    except Exception as e:
        logger.error(f"[Server 2] Error sending sensor data: {e}")
        # Try again later
        await asyncio.sleep(interval)
        asyncio.create_task(send_sensor_reading(subscription_id))

def generate_sensor_reading(sensor_type: str, last_reading: dict = None):
    """Generates a somewhat realistic sensor reading with reasonable values."""
    now = time.time()
    
    if sensor_type == "temperature":
        # Base temperature around 22°C with reasonable fluctuation
        base = 22.0
        if last_reading:
            # Slight change from last reading (drift)
            last_value = last_reading["value"]
            # Move slightly toward base value plus some noise
            new_value = last_value + (base - last_value) * 0.1 + random.uniform(-0.3, 0.3)
        else:
            new_value = base + random.uniform(-2, 2)
            
        return {
            "value": round(new_value, 1),
            "unit": "°C",
            "status": "normal" if 18 <= new_value <= 26 else "warning"
        }
        
    elif sensor_type == "humidity":
        # Base humidity around 45% with fluctuation
        base = 45.0
        if last_reading:
            last_value = last_reading["value"]
            new_value = last_value + (base - last_value) * 0.1 + random.uniform(-1, 1)
        else:
            new_value = base + random.uniform(-10, 10)
            
        # Ensure within realistic bounds
        new_value = max(20, min(80, new_value))
        
        return {
            "value": round(new_value, 1),
            "unit": "%",
            "status": "normal" if 30 <= new_value <= 60 else "warning"
        }
        
    elif sensor_type == "pressure":
        # Base around 1013 hPa (standard atmospheric pressure)
        base = 1013.0
        if last_reading:
            last_value = last_reading["value"]
            # Pressure changes are typically small
            new_value = last_value + random.uniform(-0.5, 0.5)
        else:
            new_value = base + random.uniform(-10, 10)
            
        return {
            "value": round(new_value, 1),
            "unit": "hPa",
            "status": "normal" if 980 <= new_value <= 1040 else "warning", 
            "trend": "rising" if (last_reading and new_value > last_reading["value"]) else "falling"
        }
        
    elif sensor_type == "radiation":
        # Simulate some background radiation with occasional spikes
        base = 0.1  # µSv/h
        if last_reading:
            last_value = last_reading["value"]
            if random.random() < 0.05:  # 5% chance of spike
                new_value = last_value * random.uniform(1.5, 3.0)
            else:
                new_value = max(0.05, last_value * random.uniform(0.9, 1.1))
        else:
            new_value = base * random.uniform(0.8, 1.2)
            
        status = "normal"
        if new_value > 0.5:
            status = "elevated"
        if new_value > 1.0:
            status = "warning"
        if new_value > 5.0:
            status = "alert"
            
        return {
            "value": round(new_value, 3),
            "unit": "µSv/h",
            "status": status
        }
    
    # Fallback for unknown sensor type
    return {"value": random.random(), "unit": "unknown", "status": "unknown"}

# --- Run the server ---
if __name__ == "__main__":
    # Run the server
    server.run(
        host="0.0.0.0", 
        port=8002, 
        log_level="debug",
        timeout_keep_alive=65 # Set explicit keep-alive timeout
    ) 