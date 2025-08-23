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
            parsed_data = None
            content_type = self.headers.get('Content-Type', '')
            
            # Parse request based on content type
            if post_data:
                if 'application/json' in content_type:
                    try:
                        data = json.loads(post_data)
                        parsed_data = data
                        # Handle Slack URL verification for JSON requests
                        if data.get('type') == 'url_verification':
                            challenge = data.get('challenge', '')
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain')
                            self.end_headers()
                            self.wfile.write(challenge.encode())
                            return
                        logger.info(f"Parsed JSON request: {data.get('type', 'unknown')}")
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse JSON from Slack request")
                        data = None
                elif 'application/x-www-form-urlencoded' in content_type:
                    try:
                        # Parse form-encoded data (used by slash commands, interactions)
                        parsed_data = urllib.parse.parse_qs(post_data)
                        # Convert single-item lists to strings for easier access
                        parsed_data = {k: v[0] if len(v) == 1 else v for k, v in parsed_data.items()}
                        
                        # Check if this is an interaction payload (JSON embedded in form data)
                        if 'payload' in parsed_data:
                            try:
                                data = json.loads(parsed_data['payload'])
                                logger.info(f"Parsed Slack interaction: {data.get('type', 'unknown')}")
                            except json.JSONDecodeError:
                                logger.warning("Failed to parse payload JSON from form data")
                        else:
                            # This is likely a slash command
                            data = parsed_data
                            logger.info(f"Parsed Slack command: {data.get('command', 'unknown')}")
                            
                    except Exception as e:
                        logger.warning(f"Failed to parse form-encoded data: {e}")
                        parsed_data = None
                else:
                    logger.info(f"Processing request with content type: {content_type}")
                    # Try JSON first as fallback
                    try:
                        data = json.loads(post_data)
                        parsed_data = data
                    except json.JSONDecodeError:
                        # If not JSON, treat as raw data
                        parsed_data = {"raw_body": post_data}
            
            # Process with Slack Bolt if available
            if slack_app:
                try:
                    # Use Slack Bolt's built-in adapter for serverless
                    from slack_bolt.adapter.aws_lambda import SlackRequestHandler
                    
                    # Create handler for serverless environment
                    handler = SlackRequestHandler(slack_app)
                    
                    # Convert to Lambda-style event format for Slack Bolt
                    event = {
                        "httpMethod": "POST",
                        "headers": dict(self.headers),
                        "body": post_data,
                        "isBase64Encoded": False
                    }
                    
                    # Process with Slack Bolt handler
                    lambda_response = handler.handle(event, None)
                    
                    # Send response
                    status_code = lambda_response.get("statusCode", 200)
                    headers = lambda_response.get("headers", {})
                    body = lambda_response.get("body", "OK")
                    
                    self.send_response(status_code)
                    for key, value in headers.items():
                        self.send_header(key, value)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    self.wfile.write(body.encode())
                    
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