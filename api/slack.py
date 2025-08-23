from http.server import BaseHTTPRequestHandler
import os
import sys
import json
import logging
import urllib.parse

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Get request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # For now, just return a basic response
            # TODO: Implement actual Slack event handling
            response_data = {
                "status": "received",
                "message": "Slack event received successfully",
                "debug": {
                    "content_length": content_length,
                    "headers": dict(self.headers),
                    "data_preview": post_data[:100] if post_data else "No data"
                }
            }
            
            # Handle Slack URL verification
            if post_data:
                try:
                    data = json.loads(post_data)
                    if data.get('type') == 'url_verification':
                        challenge = data.get('challenge', '')
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(challenge.encode())
                        return
                except json.JSONDecodeError:
                    pass
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            self.wfile.write(json.dumps(response_data).encode())
            
        except Exception as e:
            logger.error(f"Handler error: {e}")
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            error_response = {
                'error': 'Internal server error', 
                'message': str(e)
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_GET(self):
        """Handle GET requests for testing"""
        response_data = {
            "status": "ok",
            "service": "slack-translate-bot",
            "endpoint": "slack-events"
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        self.wfile.write(json.dumps(response_data).encode())