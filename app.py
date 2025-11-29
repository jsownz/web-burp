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
