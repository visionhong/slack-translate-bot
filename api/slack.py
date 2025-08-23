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
            
            # Initialize data variable to avoid scope issues
            data = None
            
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
                    logger.warning("Failed to parse JSON from Slack request")
                    data = None
            
            # Process with Slack Bolt if available
            if slack_app:
                try:
                    # Use proper Slack Bolt request handling
                    from slack_bolt.request.async_request import AsyncBoltRequest
                    from slack_bolt.response import BoltResponse
                    
                    # Convert to Slack request format
                    bolt_request = AsyncBoltRequest(
                        body=post_data,
                        headers=dict(self.headers)
                    )
                    
                    # Process with event loop
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Handle the request through Slack Bolt
                    async def process_slack_request():
                        try:
                            response = await slack_app.async_process(bolt_request)
                            return response
                        except Exception as e:
                            logger.error(f"Slack Bolt processing error: {e}")
                            return BoltResponse(status=200, body="OK")
                    
                    # Run the async processing
                    response = loop.run_until_complete(process_slack_request())
                    loop.close()
                    
                    # Send response
                    self.send_response(response.status)
                    for key, value in response.headers.items():
                        self.send_header(key, value)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    response_body = response.body if response.body else "OK"
                    self.wfile.write(response_body.encode())
                    
                    # Log event type if available
                    if data:
                        logger.info(f"Processed Slack event: {data.get('type', 'unknown')}")
                    
                except Exception as e:
                    logger.error(f"Slack processing error: {e}")
                    self._send_error_response(e)
            else:
                # Fallback response when Slack app is not available
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