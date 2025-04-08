"""
Notification utilities for MCP servers.

This module provides additional functionality for working with notifications,
including scheduled notifications and recurring notifications.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Awaitable

from ..common.constants import (
    NOTIFICATION_INFO,
    NOTIFICATION_WARNING,
    NOTIFICATION_ERROR,
    NOTIFICATION_DATA
)

# Get logger
logger = logging.getLogger("pymcp_sse.server.notifications")

class NotificationScheduler:
    """
    Utility class for scheduling and managing notifications.
    """
    
    def __init__(self, server):
        """
        Initialize the notification scheduler.
        
        Args:
            server: An instance of BaseMCPServer
        """
        self.server = server
        self.scheduled_tasks = {}
        self.periodic_tasks = {}
        
    async def schedule_notification(
        self, 
        delay_seconds: float, 
        type_name: str, 
        message: str, 
        data: Optional[Dict] = None,
        target_session_id: Optional[str] = None
    ) -> str:
        """
        Schedule a notification to be sent after a delay.
        
        Args:
            delay_seconds: Delay in seconds before sending the notification
            type_name: Notification type (info, warning, error, data)
            message: Notification message
            data: Optional additional data
            target_session_id: Optional session ID (if None, will broadcast to all)
            
        Returns:
            task_id: A unique ID for the scheduled task
        """
        task_id = f"notification_{datetime.now().timestamp()}_{id(message)}"
        
        async def _delayed_notification():
            await asyncio.sleep(delay_seconds)
            try:
                if target_session_id:
                    await self.server.push_notification(
                        server_session_id=target_session_id,
                        type_name=type_name,
                        message=message,
                        data=data
                    )
                else:
                    await self.server.broadcast_notification(
                        type_name=type_name,
                        message=message,
                        data=data
                    )
                # Clean up task reference
                if task_id in self.scheduled_tasks:
                    del self.scheduled_tasks[task_id]
            except Exception as e:
                logger.error(f"Error in scheduled notification {task_id}: {e}")
                
        # Create and store the task
        task = asyncio.create_task(_delayed_notification())
        self.scheduled_tasks[task_id] = task
        logger.info(f"Scheduled notification '{message}' (ID: {task_id}) in {delay_seconds}s")
        
        return task_id
        
    def cancel_scheduled_notification(self, task_id: str) -> bool:
        """
        Cancel a scheduled notification.
        
        Args:
            task_id: The ID of the task to cancel
            
        Returns:
            bool: True if the task was found and cancelled, False otherwise
        """
        if task_id in self.scheduled_tasks:
            task = self.scheduled_tasks[task_id]
            if not task.done():
                task.cancel()
            del self.scheduled_tasks[task_id]
            logger.info(f"Cancelled scheduled notification (ID: {task_id})")
            return True
        return False
        
    async def start_periodic_notification(
        self, 
        interval_seconds: float,
        type_name: str,
        message_or_callable: Any,
        data_or_callable: Any = None,
        target_session_id: Optional[str] = None
    ) -> str:
        """
        Start a periodic notification task.
        
        Args:
            interval_seconds: Interval between notifications
            type_name: Notification type (info, warning, error, data)
            message_or_callable: Static message or callable that returns a message
            data_or_callable: Static data or callable that returns data
            target_session_id: Optional specific client (None for broadcast)
            
        Returns:
            task_id: A unique ID for the periodic task
        """
        task_id = f"periodic_{datetime.now().timestamp()}_{id(message_or_callable)}"
        
        async def _periodic_notification():
            while True:
                try:
                    # Determine message and data values
                    if callable(message_or_callable):
                        message = message_or_callable()
                        # Handle async functions
                        if asyncio.iscoroutine(message):
                            message = await message
                    else:
                        message = message_or_callable
                        
                    if callable(data_or_callable):
                        data = data_or_callable()
                        # Handle async functions
                        if asyncio.iscoroutine(data):
                            data = await data
                    else:
                        data = data_or_callable
                    
                    # Send the notification
                    if target_session_id:
                        await self.server.push_notification(
                            server_session_id=target_session_id,
                            type_name=type_name,
                            message=message,
                            data=data
                        )
                    else:
                        await self.server.broadcast_notification(
                            type_name=type_name,
                            message=message,
                            data=data
                        )
                except asyncio.CancelledError:
                    logger.info(f"Periodic notification task {task_id} cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in periodic notification {task_id}: {e}")
                
                await asyncio.sleep(interval_seconds)
        
        # Create and store the task
        task = asyncio.create_task(_periodic_notification())
        self.periodic_tasks[task_id] = task
        logger.info(f"Started periodic notification (ID: {task_id}) with {interval_seconds}s interval")
        
        return task_id
        
    def stop_periodic_notification(self, task_id: str) -> bool:
        """
        Stop a periodic notification task.
        
        Args:
            task_id: The ID of the task to stop
            
        Returns:
            bool: True if the task was found and stopped, False otherwise
        """
        if task_id in self.periodic_tasks:
            task = self.periodic_tasks[task_id]
            if not task.done():
                task.cancel()
            del self.periodic_tasks[task_id]
            logger.info(f"Stopped periodic notification (ID: {task_id})")
            return True
        return False
        
    def stop_all_notifications(self):
        """Stop all scheduled and periodic notifications."""
        # Stop scheduled notifications
        for task_id in list(self.scheduled_tasks.keys()):
            self.cancel_scheduled_notification(task_id)
            
        # Stop periodic notifications
        for task_id in list(self.periodic_tasks.keys()):
            self.stop_periodic_notification(task_id)
            
        logger.info("Stopped all notifications")

# Export the class and constants
__all__ = [
    'NotificationScheduler',
    'NOTIFICATION_INFO', 
    'NOTIFICATION_WARNING', 
    'NOTIFICATION_ERROR',
    'NOTIFICATION_DATA'
] 