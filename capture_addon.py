"""
Mitmproxy addon to capture requests and send them to the Flask API
Supports request interception for modification before forwarding
"""
import urllib.request
import json
import time
from datetime import datetime
from mitmproxy import http


class RequestCapture:
    """Captures HTTP/HTTPS requests and sends them to Flask API"""
    
    def __init__(self):
        self.request_count = 0
        self.flask_url = "http://localhost:5000/api/requests/capture"
        self.intercept_url = "http://localhost:5000/api/intercept/check"
        self.decision_url = "http://localhost:5000/api/intercept/decision"
        
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
        
        # Check if intercept mode is enabled
        intercept_enabled = False
        try:
            req = urllib.request.Request(self.intercept_url)
            response = urllib.request.urlopen(req, timeout=1)
            data = json.loads(response.read().decode('utf-8'))
            intercept_enabled = data.get('enabled', False)
        except Exception:
            # If Flask isn't available or request fails, continue without intercept
            pass
        
        # Mark as intercepted if intercept mode is enabled
        if intercept_enabled:
            request_data['intercepted'] = True
        
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
        
        # If intercept is enabled, hold the request and wait for user decision
        if intercept_enabled:
            
            # Poll for user decision
            max_wait = 300  # 5 minutes max wait
            poll_interval = 0.5  # Poll every 500ms
            elapsed = 0
            
            while elapsed < max_wait:
                try:
                    decision_req = urllib.request.Request(
                        f"{self.decision_url}/{self.request_count}"
                    )
                    response = urllib.request.urlopen(decision_req, timeout=1)
                    decision = json.loads(response.read().decode('utf-8'))
                    
                    action = decision.get('action')
                    
                    if action == 'forward':
                        # Apply modifications if present
                        modifications = decision.get('modifications', {})
                        
                        if 'method' in modifications:
                            flow.request.method = modifications['method']
                        if 'path' in modifications:
                            flow.request.path = modifications['path']
                        if 'headers' in modifications:
                            flow.request.headers.clear()
                            for key, value in modifications['headers'].items():
                                flow.request.headers[key] = value
                        if 'content' in modifications:
                            flow.request.content = modifications['content'].encode('utf-8')
                        
                        # Continue with the request
                        break
                    elif action == 'drop':
                        # Kill the connection
                        flow.kill()
                        break
                    
                except Exception:
                    # No decision yet, continue waiting
                    pass
                
                time.sleep(poll_interval)
                elapsed += poll_interval


addons = [RequestCapture()]
