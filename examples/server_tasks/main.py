import os
import sys
import asyncio
import argparse
import random
from datetime import datetime
from typing import Optional

# Add project root to path if running directly
current_dir = os.path.dirname(os.path.abspath(__file__))
package_dir = os.path.abspath(os.path.join(current_dir, '../..'))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from pymcp_sse.server import (
    BaseMCPServer, 
    NotificationScheduler,
    NOTIFICATION_INFO, 
    NOTIFICATION_WARNING, 
    NOTIFICATION_ERROR,
    NOTIFICATION_DATA
)
from pymcp_sse.utils import configure_logging, get_logger

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
configure_logging(level=log_level)
logger = get_logger("example.server_tasks")

# Create server instance
server = BaseMCPServer(server_name="Async Tasks Server")

# Create the notification scheduler
scheduler = NotificationScheduler(server)

# --- Tools --- 

# Tool to send an immediate notification
@server.register_tool(name="send_immediate_notification")
async def send_immediate_notification(message: str, type_name: str = NOTIFICATION_INFO):
    """Sends an immediate notification to all connected clients."""
    await server.broadcast_notification(type_name=type_name, message=message)
    logger.info(f"Sent immediate notification: {message}")
    return {"success": True, "message_sent": message}

# Tool to schedule a notification
@server.register_tool(name="schedule_notification")
async def schedule_notification(delay_seconds: int, message: str, type_name: str = NOTIFICATION_INFO):
    """Schedules a notification to be sent after a delay."""
    task_id = await scheduler.schedule_notification(
        delay_seconds=delay_seconds,
        type_name=type_name,
        message=message,
        data={"scheduled": True}
    )
    logger.info(f"Scheduled notification in {delay_seconds}s with ID: {task_id}")
    return {"success": True, "scheduled_for_seconds": delay_seconds, "task_id": task_id}

# Tool to start periodic notifications
@server.register_tool(name="start_periodic_pings")
async def start_periodic_pings(interval_seconds: int = 15):
    """Starts sending periodic ping notifications with a counter."""
    counter = {"value": 0}
    def get_ping_data():
        counter["value"] += 1
        return {"count": counter["value"], "periodic": True}

    task_id = await scheduler.start_periodic_notification(
        interval_seconds=interval_seconds,
        type_name=NOTIFICATION_DATA,
        message_or_callable="Periodic Server Ping",
        data_or_callable=get_ping_data
    )
    logger.info(f"Started periodic pings every {interval_seconds}s with ID: {task_id}")
    return {"success": True, "interval_seconds": interval_seconds, "task_id": task_id}

# Tool to stop periodic notifications
@server.register_tool(name="stop_periodic_task")
async def stop_periodic_task(task_id: str):
    """Stops a periodic notification task using its ID."""
    success = scheduler.stop_periodic_notification(task_id)
    if success:
        logger.info(f"Stopped periodic task with ID: {task_id}")
        return {"success": True, "message": f"Stopped task {task_id}"}
    else:
        logger.warning(f"Failed to stop periodic task with ID: {task_id}")
        return {"success": False, "message": f"No task found with ID {task_id}"}

# --- Background Task & Shutdown Callback --- 

# No explicit background task needed for the scheduler itself,
# as it creates tasks internally when its methods are called.

async def stop_scheduler_tasks(): # Renamed for clarity
    """Gracefully shuts down all tasks managed by the scheduler."""
    logger.info("Executing shutdown callback: stopping all scheduler notifications...")
    # Call the scheduler's cleanup method
    scheduler.stop_all_notifications() 
    logger.info("Scheduler notifications stopped.")

# --- Main Execution --- 

async def main(host: Optional[str], port: Optional[int]):
    # Define tasks and callbacks
    concurrent_tasks = None # No extra tasks to run alongside the server for this example
    shutdown_callbacks = [stop_scheduler_tasks] # Callback to stop the scheduler's tasks

    logger.info("Starting Async Tasks Server...")
    try:
        await server.run_with_tasks(
            host=host, 
            port=port or 8102, # Default port 8102 for this server
            log_level=log_level.lower(),
            concurrent_tasks=concurrent_tasks,
            shutdown_callbacks=shutdown_callbacks
        )
    except Exception as e:
        logger.critical(f"Server execution failed: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Server has shut down gracefully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Async Tasks Example MCP Server.")
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind the server to (overrides MCP_HOST env var, defaults to 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None, # Let run_with_tasks handle default and MCP_PORT
        help="Port to bind the server to (overrides MCP_PORT env var, defaults to 8000)"
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(host=args.host, port=args.port))
    except KeyboardInterrupt:
        logger.info("Runner received KeyboardInterrupt, exiting.")
    except Exception as e:
        logger.error(f"Critical error in runner: {e}", exc_info=True)
        sys.exit(1) 