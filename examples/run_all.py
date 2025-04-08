#!/usr/bin/env python3
"""
Launcher script for running all PyMCP example components.
"""
import os
import sys
import time
import subprocess
import signal
import argparse
from typing import List, Dict, Any
import asyncio
import httpx
import platform # Import platform module
import logging

# Add pymcp to path if running directly from examples
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
package_dir = os.path.join(parent_dir, 'pymcp_sse')
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import logging
from pymcp_sse.utils import configure_logging, get_logger

# Configure logging
configure_logging(level="INFO")
logger = get_logger("examples.launcher")

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# --- Prepare file paths ---
CLIENT_PATH = os.path.join(script_dir, "client", "main.py")
SERVER_BASIC_PATH = os.path.join(script_dir, "server_basic", "main.py")
SERVER_TASKS_PATH = os.path.join(script_dir, "server_tasks", "main.py")

# Define Server URLs (match default ports in server files)
SERVER_BASIC_URL = "http://localhost:8101"
SERVER_TASKS_URL = "http://localhost:8102"

# --- Global Process Management ---
# List of started processes
processes: List[subprocess.Popen] = []

# Server configurations used for health checks
server_configs = [
    {"path": SERVER_BASIC_PATH, "port": 8101, "name": "Server Basic", "url": SERVER_BASIC_URL},
    {"path": SERVER_TASKS_PATH, "port": 8102, "name": "Server Tasks", "url": SERVER_TASKS_URL}
]

def get_logger(name: str):
    # Basic logger for run_all
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

logger = get_logger("run_all")

def start_component(script_path: str, args: List[str] = None) -> subprocess.Popen:
    """
    Start a component as a subprocess.
    
    Args:
        script_path: Path to the script
        args: Additional arguments
        
    Returns:
        Process object
    """
    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)
        
    logger.info(f"Starting: {' '.join(cmd)}")
    
    # Start process in its own process group to handle Ctrl+C properly
    popen_kwargs = {
        "text": True,
        "env": os.environ.copy(),
    }
    if platform.system() == "Windows":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
        
    return subprocess.Popen(cmd, **popen_kwargs)

def stop_all():
    """Stop all started processes."""
    logger.info("Stopping all components...")
    
    for process in processes:
        try:
            # Send SIGTERM
            process.terminate()
            # Wait a bit
            time.sleep(0.2)
            # If still running, kill
            if process.poll() is None:
                process.kill()
        except Exception as e:
            logger.error(f"Error stopping process: {e}")
            
    # Wait for all to terminate
    for process in processes:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            logger.warning(f"Process {process.pid} did not terminate in time")
            
    logger.info("All components stopped")

def signal_handler(sig, frame):
    """Handle keyboard interrupt."""
    logger.info("Received interrupt, stopping components...")
    stop_all()
    sys.exit(0)

async def check_servers_ready(servers: List[tuple[str, subprocess.Popen]], timeout: int = 10) -> bool:
    """Check if servers are ready by polling their /health endpoint."""
    start_time = time.monotonic()
    
    async with httpx.AsyncClient() as client:
        while time.monotonic() - start_time < timeout:
            ready_count = 0
            all_processes_running = True
            
            check_tasks = []
            server_map = {}
            for url, process in servers:
                if process.poll() is not None:
                    logger.warning(f"Server process for {url} terminated unexpectedly.")
                    all_processes_running = False
                    break # No point checking health if process is dead
                
                # Create task for health check
                health_url = f"{url.rstrip('/')}/health"
                check_tasks.append(client.get(health_url))
                server_map[len(check_tasks) - 1] = url # Map task index to URL
                
            if not all_processes_running:
                return False # A server process died
                
            if not check_tasks:
                return True # No servers to check?

            results = await asyncio.gather(*check_tasks, return_exceptions=True)
            
            for i, res in enumerate(results):
                url = server_map[i]
                if isinstance(res, httpx.Response) and res.status_code == 200:
                    try:
                        json_body = res.json()
                        if json_body.get("status") == "ok":
                            ready_count += 1
                            logger.debug(f"Server {url} is ready (status ok).")
                        else:
                            logger.warning(f"Server {url} health status not 'ok'. Body: {json_body}")
                    except Exception as json_err:
                        logger.warning(f"Server {url} health check returned 200 OK but failed JSON parsing: {json_err}. Body: {res.text[:100]}")
                elif isinstance(res, Exception):
                    logger.warning(f"Health check for {url} failed with exception: {res}")
                else: # Should be httpx.Response but not 200
                    logger.warning(f"Health check for {url} returned non-200 status: {res.status_code}")

            if ready_count == len(servers):
                logger.info(f"All {len(servers)} servers are ready.")
                return True
            
            await asyncio.sleep(0.5) # Wait before retrying
            
    logger.error(f"Timeout waiting for servers to become ready after {timeout} seconds.")
    return False

async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run PyMCP example components")
    args = parser.parse_args()
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Add httpx for health checks
    try:
        import httpx
    except ImportError:
        logger.error("httpx is required for health checks. Please install it: pip install httpx")
        sys.exit(1)
        
    try:
        # Start servers
        server_processes = []
        for config in server_configs:
            process = start_component(config["path"])
            processes.append(process)
            server_processes.append((config["url"], process))
        
        # Wait for servers to become ready
        logger.info("Waiting for servers to start...")
        if not await check_servers_ready(server_processes):
            logger.error("One or more servers failed to become ready")
            stop_all()
            return 1
            
        # Start client
        client_process = start_component(CLIENT_PATH)
        processes.append(client_process)
        
        # Wait for client to exit
        client_process.wait()
        
        # Stop servers
        stop_all()
        
        return 0
        
    except Exception as e:
        logger.error(f"Error running components: {e}")
        stop_all()
        return 1
        
    finally:
        # Make sure we stop all processes on exit
        stop_all()

if __name__ == "__main__":
    # Use asyncio.run for the main function if using async checks
    sys.exit(asyncio.run(main())) 