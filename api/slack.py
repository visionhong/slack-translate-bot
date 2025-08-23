from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            "status": "ok",
            "service": "slack-translate-bot",
            "endpoint": "slack-events",
            "slack_app_ready": True
        }
        
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            content_type = self.headers.get('Content-Type', '')
            
            logger.info(f"Received POST request, Content-Type: {content_type}")
            
            # Initialize response data
            parsed_data = {}
            data = None
            
            # Parse request based on content type
            if 'application/json' in content_type:
                try:
                    data = json.loads(post_data)
                    # Handle Slack URL verification
                    if data.get('type') == 'url_verification':
                        challenge = data.get('challenge', '')
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(challenge.encode())
                        return
                    logger.info(f"Parsed JSON request: {data.get('type', 'unknown')}")
                except json.JSONDecodeError:
                    logger.warning("Failed to parse JSON data")
                    
            elif 'application/x-www-form-urlencoded' in content_type:
                try:
                    # Parse form-encoded data (slash commands, interactions)
                    parsed_data = urllib.parse.parse_qs(post_data)
                    parsed_data = {k: v[0] if len(v) == 1 else v for k, v in parsed_data.items()}
                    
                    # Check for interaction payload
                    if 'payload' in parsed_data:
                        try:
                            data = json.loads(parsed_data['payload'])
                            logger.info(f"Parsed Slack interaction: {data.get('type', 'unknown')}")
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse payload JSON")
                    else:
                        # Slash command
                        data = parsed_data
                        command = data.get('command', 'unknown')
                        text = data.get('text', '')
                        logger.info(f"Parsed Slack command: {command} with text: {text[:50]}...")
                        
                        # Handle /translate command specifically
                        if command == '/translate':
                            trigger_id = data.get('trigger_id')
                            user_id = data.get('user_id')
                            
                            # Simple response for now - will add modal functionality back after deployment works
                            if text.strip():
                                response_text = f"🌐 Translation request received for: {text[:50]}..."
                                translated_text = f"Mock translation of: {text}"  # Mock for now
                            else:
                                response_text = "🌐 Please provide text to translate: `/translate your text here`"
                                translated_text = ""
                            
                            translation_response = {
                                "response_type": "ephemeral",
                                "text": response_text,
                                "blocks": [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f"*Original:* {text}\n*Translation:* {translated_text}\n\n_Modal functionality coming soon!_"
                                        }
                                    }
                                ]
                            }
                            
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps(translation_response).encode())
                            return
                            
                except Exception as e:
                    logger.warning(f"Failed to parse form-encoded data: {e}")
            
            # Default response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                "status": "received",
                "message": "Request processed successfully",
                "content_type": content_type,
                "data_length": len(post_data),
                "parsed_command": parsed_data.get('command', 'none') if parsed_data else 'none'
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            logger.error(f"POST handler error: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            error_response = {
                "error": "Internal server error",
                "message": str(e)
            }
            
            self.wfile.write(json.dumps(error_response).encode())