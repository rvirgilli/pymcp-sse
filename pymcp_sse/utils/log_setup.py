"""
Logging utilities for PyMCP.

This module provides consistent, configurable logging across the PyMCP package.
"""
import logging
import os
import sys
from typing import Optional, Dict, Union, Any

# Define standard log levels with descriptions
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,      # Detailed debugging info
    "INFO": logging.INFO,        # Confirmation that things are working as expected
    "WARNING": logging.WARNING,  # Indication that something unexpected happened
    "ERROR": logging.ERROR,      # Due to a more serious problem, the software couldn't perform a function
    "CRITICAL": logging.CRITICAL # A serious error, indicating the program may be unable to continue running
}

# Default log format
DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name, configured according to environment variables.
    
    Environment variables:
    - PYMCP_LOG_LEVEL: Set the log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - PYMCP_LOG_FORMAT: Set the log format
    - PYMCP_LOG_FILE: Set a file to log to (in addition to console)
    
    Args:
        name: Logger name, typically __name__ or a component name like 'pymcp.server'
        
    Returns:
        A configured logger
    """
    # Add pymcp prefix if not already there
    if not name.startswith('pymcp.'):
        name = f'pymcp.{name}'
    
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers and not logging.getLogger().handlers:
        configure_logging()
        
    return logger

def configure_logging(
    level: Optional[Union[str, int]] = None,
    format_str: Optional[str] = None,
    log_file: Optional[str] = None,
    handlers: Optional[Dict[str, Any]] = None
) -> None:
    """
    Configure the logging system for PyMCP.
    
    Args:
        level: Log level (name or value)
        format_str: Log format string
        log_file: File to log to
        handlers: Custom handlers to add
    """
    # Get level from environment or parameter
    if level is None:
        level = os.environ.get('PYMCP_LOG_LEVEL', 'INFO')
    
    # Convert level name to value if needed
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.upper(), logging.INFO)
    
    # Get format from environment or parameter
    if format_str is None:
        format_str = os.environ.get('PYMCP_LOG_FORMAT', DEFAULT_FORMAT)
    
    # Get log file from environment or parameter
    if log_file is None:
        log_file = os.environ.get('PYMCP_LOG_FILE', None)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(format_str)
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Add file handler if specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            # Don't fail if logging to file fails
            logging.getLogger('pymcp.utils.logging').error(f"Failed to set up log file {log_file}: {e}")
    
    # Add custom handlers if provided
    if handlers:
        for handler in handlers.values():
            if handler and hasattr(handler, 'setFormatter'):
                handler.setFormatter(formatter)
                root_logger.addHandler(handler)
                
    # Set library dependency loggers to WARNING level unless explicitly configured
    for logger_name in ['uvicorn', 'httpx', 'fastapi']:
        if not os.environ.get(f'PYMCP_LOG_LEVEL_{logger_name.upper()}'):
            logging.getLogger(logger_name).setLevel(logging.WARNING) 