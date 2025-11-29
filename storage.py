"""
Request storage module
Stores captured HTTP requests and responses
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
