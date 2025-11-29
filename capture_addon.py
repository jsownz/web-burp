"""
Mitmproxy addon to capture requests and send them to the Flask API
"""
import urllib.request
import json
from datetime import datetime
from mitmproxy import http


class RequestCapture:
    """Captures HTTP/HTTPS requests and sends them to Flask API"""
    
    def __init__(self):
        self.request_count = 0
        self.flask_url = "http://localhost:5000/api/requests/capture"
        
    def request(self, flow: http.HTTPFlow):
        """Called when a request is received"""
        self.request_count += 1
        
        request_data = {
            'id': self.request_count,
            'timestamp': datetime.utcnow().isoformat(),
            'method': flow.request.method,
            'url': flow.request.pretty_url,
            'host': flow.request.host,
            'port': flow.request.port,
            'scheme': flow.request.scheme,
            'path': flow.request.path,
            'headers': dict(flow.request.headers),
            'content': flow.request.content.decode('utf-8', errors='ignore') if flow.request.content else None,
            'status': 'pending'
        }
        
        # Send to Flask API using urllib (thread-safe)
        try:
            data = json.dumps(request_data).encode('utf-8')
            req = urllib.request.Request(
                self.flask_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=1)
        except Exception as e:
            # Silently fail if Flask isn't available
            pass


addons = [RequestCapture()]
