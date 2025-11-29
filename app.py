"""
Web-Burp: Flask-based intercepting proxy
Main application entry point
"""
from flask import Flask, render_template, jsonify, request, send_file
from flask_socketio import SocketIO, emit
import logging
import os
import sys

from proxy import ProxyServer
from storage import RequestStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global instances (will be initialized in create_app)
proxy_server: ProxyServer = None
request_store: RequestStore = None
socketio: SocketIO = None


def create_app():
    """Application factory pattern for Flask"""
    global proxy_server, request_store, socketio
    
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    app.config['DEBUG'] = False  # Set via environment in Docker
    
    # Initialize SocketIO with threading mode (compatible with mitmproxy)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    
    # Initialize storage
    request_store = RequestStore()
    
    # Initialize proxy server with callback
    def on_request_captured(request_data):
        """Callback when proxy captures a request"""
        req_id = request_store.add_request(request_data)
        # Emit WebSocket event for new request
        socketio.emit('new_request', request_data, namespace='/')
        # Emit updated stats
        stats = request_store.get_stats()
        socketio.emit('stats_update', stats, namespace='/')
    
    # Exclude localhost and web-burp UI from capture
    # This prevents capturing the web-burp interface's own traffic
    exclude_hosts = [
        'localhost',
        '127.0.0.1',
        '::1',
        '0.0.0.0',
        # Add any other domains you want to exclude here
    ]
    
    proxy_server = ProxyServer(port=8080, on_request=on_request_captured, exclude_hosts=exclude_hosts)
    
    # Register routes
    @app.route('/')
    def index():
        """Main dashboard"""
        return render_template('index.html')
    
    @app.route('/health')
    def health():
        """Health check endpoint for Docker"""
        return {'status': 'healthy', 'service': 'web-burp'}, 200
    
    # Proxy control endpoints
    @app.route('/api/proxy/start', methods=['POST'])
    def start_proxy():
        """Start the proxy server"""
        try:
            if proxy_server.is_running:
                return {'error': 'Proxy already running'}, 400
            
            proxy_server.start()
            # Emit proxy status change via WebSocket
            socketio.emit('proxy_status', {'running': True, 'port': proxy_server.port}, namespace='/')
            return {'status': 'started', 'port': proxy_server.port}, 200
        except Exception as e:
            logger.error(f"Failed to start proxy: {e}")
            return {'error': str(e)}, 500
    
    @app.route('/api/proxy/stop', methods=['POST'])
    def stop_proxy():
        """Stop the proxy server"""
        try:
            if not proxy_server.is_running:
                return {'error': 'Proxy not running'}, 400
            
            proxy_server.stop()
            # Emit proxy status change via WebSocket
            socketio.emit('proxy_status', {'running': False}, namespace='/')
            return {'status': 'stopped'}, 200
        except Exception as e:
            logger.error(f"Failed to stop proxy: {e}")
            return {'error': str(e)}, 500
    
    @app.route('/api/proxy/status')
    def proxy_status():
        """Get proxy server status"""
        status = proxy_server.get_status()
        stats = request_store.get_stats()
        return {
            'proxy': status,
            'stats': stats
        }, 200
    
    # Request history endpoints
    @app.route('/api/requests')
    def get_requests():
        """Get all captured requests"""
        limit = request.args.get('limit', type=int, default=100)
        requests = request_store.get_all_requests(limit=limit)
        return {'requests': requests, 'total': len(requests)}, 200
    
    @app.route('/api/requests/capture', methods=['POST'])
    def capture_request():
        """Receive captured request from mitmproxy addon"""
        request_data = request.get_json()
        if request_data:
            req_id = request_store.add_request(request_data)
            
            # Update request_data with the assigned ID
            request_data['id'] = req_id
            
            # If intercepted, add to intercept queue
            if request_data.get('intercepted'):
                request_store.add_to_intercept_queue(request_data)
                socketio.emit('intercepted_request', request_data, namespace='/')
                logger.info(f"Request {req_id} intercepted and added to queue")
            else:
                # Emit WebSocket event for new request
                socketio.emit('new_request', request_data, namespace='/')
            
            # Emit updated stats
            stats = request_store.get_stats()
            socketio.emit('stats_update', stats, namespace='/')
            return {'status': 'ok', 'id': req_id}, 200
        return {'error': 'No data'}, 400
    
    @app.route('/api/requests/<int:request_id>')
    def get_request(request_id):
        """Get a specific request by ID"""
        req = request_store.get_request(request_id)
        if req:
            return req, 200
        return {'error': 'Request not found'}, 404
    
    @app.route('/api/requests/clear', methods=['POST'])
    def clear_requests():
        """Clear all captured requests"""
        request_store.clear()
        # Emit clear event via WebSocket
        socketio.emit('requests_cleared', {}, namespace='/')
        socketio.emit('stats_update', request_store.get_stats(), namespace='/')
        return {'status': 'cleared'}, 200
    
    @app.route('/api/proxy/exclusions')
    def get_exclusions():
        """Get list of excluded hosts"""
        return {'exclusions': proxy_server.exclude_hosts}, 200
    
    @app.route('/api/proxy/exclusions', methods=['POST'])
    def add_exclusion():
        """Add a host to exclusion list"""
        data = request.get_json()
        host = data.get('host')
        if not host:
            return {'error': 'Host is required'}, 400
        
        if host not in proxy_server.exclude_hosts:
            proxy_server.exclude_hosts.append(host)
            logger.info(f"Added {host} to exclusion list")
        
        return {'exclusions': proxy_server.exclude_hosts}, 200
    
    @app.route('/api/proxy/exclusions/<host>', methods=['DELETE'])
    def remove_exclusion(host):
        """Remove a host from exclusion list"""
        # Don't allow removing localhost variants
        protected = ['localhost', '127.0.0.1', '::1', '0.0.0.0']
        if host in protected:
            return {'error': 'Cannot remove protected host'}, 400
        
        if host in proxy_server.exclude_hosts:
            proxy_server.exclude_hosts.remove(host)
            logger.info(f"Removed {host} from exclusion list")
        
        return {'exclusions': proxy_server.exclude_hosts}, 200
    
    # Intercept control endpoints
    @app.route('/api/intercept/status')
    def get_intercept_status():
        """Get intercept status"""
        return {
            'enabled': request_store.is_intercept_enabled(),
            'queue_length': len(request_store.get_intercept_queue())
        }, 200
    
    @app.route('/api/intercept/enable', methods=['POST'])
    def enable_intercept():
        """Enable request interception"""
        request_store.enable_intercept()
        socketio.emit('intercept_status', {'enabled': True}, namespace='/')
        return {'status': 'enabled'}, 200
    
    @app.route('/api/intercept/disable', methods=['POST'])
    def disable_intercept():
        """Disable request interception"""
        request_store.disable_intercept()
        socketio.emit('intercept_status', {'enabled': False}, namespace='/')
        return {'status': 'disabled'}, 200
    
    @app.route('/api/intercept/check')
    def check_intercept():
        """Check if intercept is enabled (called by mitmproxy addon)"""
        return {'enabled': request_store.is_intercept_enabled()}, 200
    
    @app.route('/api/intercept/queue')
    def get_intercept_queue():
        """Get all intercepted requests waiting for decision"""
        queue = request_store.get_intercept_queue()
        return {'queue': queue, 'length': len(queue)}, 200
    
    @app.route('/api/intercept/next')
    def get_next_intercepted():
        """Get the next intercepted request"""
        next_req = request_store.get_next_intercepted_request()
        if next_req:
            return next_req, 200
        return {'error': 'No intercepted requests'}, 404
    
    @app.route('/api/intercept/forward/<int:request_id>', methods=['POST'])
    def forward_request(request_id):
        """Forward an intercepted request (optionally with modifications)"""
        data = request.get_json() or {}
        modifications = data.get('modifications', {})
        
        request_store.set_intercept_decision(request_id, 'forward', modifications)
        socketio.emit('request_forwarded', {'id': request_id}, namespace='/')
        
        return {'status': 'forwarded', 'id': request_id}, 200
    
    @app.route('/api/intercept/drop/<int:request_id>', methods=['POST'])
    def drop_request(request_id):
        """Drop an intercepted request"""
        request_store.set_intercept_decision(request_id, 'drop')
        socketio.emit('request_dropped', {'id': request_id}, namespace='/')
        
        return {'status': 'dropped', 'id': request_id}, 200
    
    @app.route('/api/intercept/decision/<int:request_id>')
    def get_decision(request_id):
        """Get the decision for a request (called by mitmproxy addon)"""
        decision = request_store.get_intercept_decision(request_id)
        if decision:
            # Clear the decision after retrieving it
            request_store.clear_intercept_decision(request_id)
            return decision, 200
        return {'action': 'pending'}, 200
    
    # Repeater endpoints
    @app.route('/api/repeater/send', methods=['POST'])
    def send_repeater_request():
        """Send a custom HTTP request from repeater"""
        import requests
        
        data = request.get_json()
        if not data:
            return {'error': 'No data provided'}, 400
        
        method = data.get('method', 'GET')
        url = data.get('url')
        headers = data.get('headers', {})
        body = data.get('body', '')
        
        if not url:
            return {'error': 'URL is required'}, 400
        
        try:
            # Send the request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body.encode('utf-8') if body else None,
                allow_redirects=False,
                verify=False,  # Allow self-signed certs for testing
                timeout=30
            )
            
            # Prepare response data
            response_data = {
                'status_code': response.status_code,
                'status_text': response.reason,
                'headers': dict(response.headers),
                'body': response.text,
                'elapsed_ms': int(response.elapsed.total_seconds() * 1000)
            }
            
            # Store in repeater history
            entry_id = request_store.add_repeater_request(data, response_data)
            
            # Emit WebSocket event
            socketio.emit('repeater_response', {
                'id': entry_id,
                'request': data,
                'response': response_data
            }, namespace='/')
            
            return {
                'id': entry_id,
                'response': response_data
            }, 200
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Repeater request failed: {e}")
            error_response = {
                'error': str(e),
                'error_type': type(e).__name__
            }
            
            # Store failed request in history
            entry_id = request_store.add_repeater_request(data, error_response)
            
            return {
                'id': entry_id,
                'error': str(e)
            }, 500
    
    @app.route('/api/repeater/history')
    def get_repeater_history():
        """Get repeater request/response history"""
        limit = request.args.get('limit', type=int, default=50)
        history = request_store.get_repeater_history(limit=limit)
        return {'history': history, 'total': len(history)}, 200
    
    @app.route('/api/repeater/history/<int:entry_id>')
    def get_repeater_entry(entry_id):
        """Get a specific repeater entry"""
        entry = request_store.get_repeater_entry(entry_id)
        if entry:
            return entry, 200
        return {'error': 'Entry not found'}, 404
    
    @app.route('/api/repeater/history/clear', methods=['POST'])
    def clear_repeater_history():
        """Clear repeater history"""
        request_store.clear_repeater_history()
        socketio.emit('repeater_history_cleared', {}, namespace='/')
        return {'status': 'cleared'}, 200
    
    # Certificate management endpoints
    @app.route('/api/proxy/certificate')
    def get_certificate_info():
        """Get certificate information"""
        cert_path = proxy_server.get_cert_path()
        if cert_path and os.path.exists(cert_path):
            return {
                'available': True,
                'path': cert_path,
                'download_url': '/api/proxy/certificate/download'
            }, 200
        return {
            'available': False,
            'message': 'Certificate not yet generated. Start the proxy to generate it.'
        }, 200
    
    @app.route('/api/proxy/certificate/download')
    def download_certificate():
        """Download the CA certificate for installation"""
        cert_path = proxy_server.get_cert_path()
        if cert_path and os.path.exists(cert_path):
            return send_file(
                cert_path,
                as_attachment=True,
                download_name='mitmproxy-ca-cert.pem',
                mimetype='application/x-pem-file'
            )
        return {'error': 'Certificate not available. Start the proxy first.'}, 404
    
    # WebSocket event handlers
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        logger.info("Client connected to WebSocket")
        # Send initial status
        status = proxy_server.get_status()
        stats = request_store.get_stats()
        emit('proxy_status', status)
        emit('stats_update', stats)
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        logger.info("Client disconnected from WebSocket")
    
    @socketio.on('request_history')
    def handle_request_history(data):
        """Client requesting history"""
        limit = data.get('limit', 50)
        requests = request_store.get_all_requests(limit=limit)
        emit('history_update', {'requests': requests, 'total': len(requests)})
    
    logger.info("Web-Burp application initialized")
    return app


if __name__ == '__main__':
    app = create_app()
    # Run with SocketIO support
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
