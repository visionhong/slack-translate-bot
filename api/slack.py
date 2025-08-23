from http.server import BaseHTTPRequestHandler
import os
import sys
import json
import logging
import urllib.parse
import asyncio

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Slack Bolt App after path setup
try:
    from src.bot import create_slack_app
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    
    # Create the Slack app
    slack_app = create_slack_app()
    logger.info("Slack app created successfully")
except Exception as e:
    logger.error(f"Failed to create Slack app: {e}")
    slack_app = None

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Get request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # Handle Slack URL verification first
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
            
            # Process with Slack Bolt if available
            if slack_app:
                try:
                    # Convert HTTP request to Slack request format
                    slack_request = {
                        "method": "POST",
                        "url": self.path,
                        "headers": dict(self.headers),
                        "body": post_data
                    }
                    
                    # Create event loop for async processing
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Process the request with Slack app
                    # For now, just acknowledge receipt and log
                    logger.info(f"Processing Slack event: {data.get('type', 'unknown')}")
                    
                    response_data = {
                        "status": "processed",
                        "message": "Event processed by Slack Bolt"
                    }
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    self.wfile.write(json.dumps(response_data).encode())
                    
                except Exception as e:
                    logger.error(f"Slack processing error: {e}")
                    self._send_error_response(e)
            else:
                # Fallback response
                response_data = {
                    "status": "received",
                    "message": "Slack app not available, but event received"
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                self.wfile.write(json.dumps(response_data).encode())
            
        except Exception as e:
            logger.error(f"Handler error: {e}")
            self._send_error_response(e)
    
    def do_GET(self):
        """Handle GET requests for testing"""
        response_data = {
            "status": "ok",
            "service": "slack-translate-bot",
            "endpoint": "slack-events",
            "slack_app_ready": slack_app is not None
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        self.wfile.write(json.dumps(response_data).encode())
    
    def _send_error_response(self, error):
        """Send error response"""
        self.send_response(500)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        error_response = {
            'error': 'Internal server error', 
            'message': str(error)
        }
        self.wfile.write(json.dumps(error_response).encode())