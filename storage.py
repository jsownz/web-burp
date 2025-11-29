"""
Request storage module
Stores captured HTTP requests and responses
Manages intercept queue for request modification
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class RequestStore:
    """In-memory storage for captured requests"""
    
    def __init__(self):
        self.requests: List[Dict] = []
        self._lock = Lock()
        self._id_counter = 0
        self.intercept_enabled = False
        self.intercept_queue: List[Dict] = []
        self.intercept_decisions: Dict[int, Dict] = {}  # request_id -> decision
        
    def add_request(self, request_data: Dict) -> int:
        """
        Add a captured request to storage
        
        Args:
            request_data: Dictionary containing request information
            
        Returns:
            ID of the stored request
        """
        with self._lock:
            self._id_counter += 1
            request_data['id'] = self._id_counter
            request_data['captured_at'] = datetime.utcnow().isoformat()
            
            # Store request
            self.requests.append(request_data)
            
            logger.debug(f"Stored request {self._id_counter}: {request_data.get('method')} {request_data.get('url')}")
            
            return self._id_counter
            
    def get_all_requests(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get all captured requests
        
        Args:
            limit: Maximum number of requests to return (most recent first)
            
        Returns:
            List of request dictionaries
        """
        with self._lock:
            if limit:
                return list(reversed(self.requests[-limit:]))
            return list(reversed(self.requests))
            
    def get_request(self, request_id: int) -> Optional[Dict]:
        """
        Get a specific request by ID
        
        Args:
            request_id: ID of the request to retrieve
            
        Returns:
            Request dictionary or None if not found
        """
        with self._lock:
            for req in self.requests:
                if req['id'] == request_id:
                    return req
            return None
            
    def clear(self):
        """Clear all stored requests"""
        with self._lock:
            self.requests.clear()
            self._id_counter = 0
            logger.info("Request storage cleared")
            
    def get_stats(self) -> Dict:
        """Get statistics about stored requests"""
        with self._lock:
            total = len(self.requests)
            
            methods = {}
            hosts = {}
            
            for req in self.requests:
                # Count by method
                method = req.get('method', 'UNKNOWN')
                methods[method] = methods.get(method, 0) + 1
                
                # Count by host
                host = req.get('host', 'unknown')
                hosts[host] = hosts.get(host, 0) + 1
                
            return {
                'total': total,
                'by_method': methods,
                'by_host': hosts,
                'most_recent': self.requests[-1] if self.requests else None
            }
    
    def enable_intercept(self):
        """Enable request interception"""
        with self._lock:
            self.intercept_enabled = True
            logger.info("Intercept mode enabled")
    
    def disable_intercept(self):
        """Disable request interception"""
        with self._lock:
            self.intercept_enabled = False
            # Clear any pending decisions
            self.intercept_decisions.clear()
            logger.info("Intercept mode disabled")
    
    def is_intercept_enabled(self) -> bool:
        """Check if intercept mode is enabled"""
        with self._lock:
            return self.intercept_enabled
    
    def add_to_intercept_queue(self, request_data: Dict):
        """Add a request to the intercept queue"""
        with self._lock:
            if request_data not in self.intercept_queue:
                self.intercept_queue.append(request_data)
                logger.debug(f"Added request {request_data.get('id')} to intercept queue")
    
    def get_intercept_queue(self) -> List[Dict]:
        """Get all requests in the intercept queue"""
        with self._lock:
            return list(self.intercept_queue)
    
    def get_next_intercepted_request(self) -> Optional[Dict]:
        """Get the next request waiting for interception"""
        with self._lock:
            if self.intercept_queue:
                return self.intercept_queue[0]
            return None
    
    def set_intercept_decision(self, request_id: int, action: str, modifications: Optional[Dict] = None):
        """
        Set the decision for an intercepted request
        
        Args:
            request_id: ID of the request
            action: 'forward' or 'drop'
            modifications: Optional dict of modifications to apply
        """
        with self._lock:
            self.intercept_decisions[request_id] = {
                'action': action,
                'modifications': modifications or {},
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Remove from intercept queue
            self.intercept_queue = [req for req in self.intercept_queue if req.get('id') != request_id]
            
            logger.info(f"Set decision for request {request_id}: {action}")
    
    def get_intercept_decision(self, request_id: int) -> Optional[Dict]:
        """Get the decision for a request"""
        with self._lock:
            return self.intercept_decisions.get(request_id)
    
    def clear_intercept_decision(self, request_id: int):
        """Clear the decision for a request after it's been processed"""
        with self._lock:
            if request_id in self.intercept_decisions:
                del self.intercept_decisions[request_id]
