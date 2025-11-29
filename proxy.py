"""
Proxy server module using mitmproxy
Handles HTTP/HTTPS traffic interception
"""
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ProxyServer:
    """Manages the mitmproxy instance for traffic interception"""
    
    def __init__(self, port: int = 8080, on_request: Optional[Callable] = None, exclude_hosts: Optional[list] = None, cert_dir: str = "./certs"):
        """
        Initialize proxy server
        
        Args:
            port: Port to listen on for proxy traffic
            on_request: Callback function to handle captured requests (not used with CLI mode)
            exclude_hosts: List of hostnames to exclude from capture (not used with CLI mode)
            cert_dir: Directory to store mitmproxy certificates
        """
        self.port = port
        self.on_request = on_request
        self.exclude_hosts = exclude_hosts or []
        self.cert_dir = cert_dir
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        
        # Ensure certificate directory exists
        Path(self.cert_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Certificate directory: {os.path.abspath(self.cert_dir)}")
        
    def start(self):
        """Start the proxy server as a subprocess"""
        if self.is_running:
            logger.warning("Proxy server already running")
            return
            
        logger.info(f"Starting proxy server on port {self.port}")
        
        # Run mitmdump (command-line version of mitmproxy)
        # It will automatically load config from ~/.mitmproxy/config.yaml
        addon_path = os.path.join(os.path.dirname(__file__), 'capture_addon.py')
        cmd = [
            'mitmdump',
            '--listen-host', '0.0.0.0',
            '--listen-port', str(self.port),
            '--set', f'confdir={self.cert_dir}',
            '--set', 'block_global=false',  # Explicitly disable block_global
            '-s', addon_path,  # Load our capture addon
        ]
        
        try:
            # Start mitmdump as a subprocess
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,  # Suppress output
                stderr=subprocess.STDOUT,
                text=True
            )
            
            # Give it a moment to start
            time.sleep(1.5)
            
            # Check if process started successfully
            if self.process.poll() is None:
                self.is_running = True
                logger.info(f"Proxy started successfully on port {self.port}")
            else:
                # Process exited immediately
                exit_code = self.process.returncode
                logger.error(f"Proxy failed to start (exit code: {exit_code})")
                self.process = None
                
        except Exception as e:
            logger.error(f"Failed to start proxy: {e}")
            if self.process:
                self.process.kill()
                self.process = None
                
    def stop(self):
        """Stop the proxy server"""
        if not self.is_running:
            logger.warning("Proxy server not running")
            return
            
        logger.info("Stopping proxy server")
        self.is_running = False
        
        if self.process:
            try:
                # Terminate the process gracefully
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    self.process.kill()
                    self.process.wait()
            except Exception as e:
                logger.error(f"Error stopping proxy: {e}")
            finally:
                self.process = None
                
        logger.info("Proxy server stopped")
        
    def get_status(self) -> dict:
        """Get current proxy status"""
        return {
            'running': self.is_running,
            'port': self.port,
            'host': '0.0.0.0',
            'cert_dir': os.path.abspath(self.cert_dir)
        }
    
    def get_cert_path(self) -> Optional[str]:
        """Get the path to the CA certificate file"""
        cert_path = os.path.join(self.cert_dir, 'mitmproxy-ca-cert.pem')
        if os.path.exists(cert_path):
            return cert_path
        return None
