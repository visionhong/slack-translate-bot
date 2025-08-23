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
    from slack_bolt.adapter.aws_lambda import SlackRequestHandler
    
    # Create the Slack app
    slack_app = create_slack_app()
    slack_handler = SlackRequestHandler(slack_app)
    logger.info("Slack app created successfully")
except Exception as e:
    logger.error(f"Failed to create Slack app: {e}")
    slack_app = None
    slack_handler = None

def handler(request, context=None):
    """Main Vercel handler function"""
    try:
        method = getattr(request, 'method', 'POST')
        
        if method == 'GET':
            # Handle GET requests for testing
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    "status": "ok",
                    "service": "slack-translate-bot",
                    "endpoint": "slack-events",
                    "slack_app_ready": slack_app is not None
                })
            }
        
        if method != 'POST':
            return {
                'statusCode': 405,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Method not allowed'})
            }
        
        # Get request data
        if hasattr(request, 'body'):
            body = request.body.decode('utf-8') if hasattr(request.body, 'decode') else str(request.body)
        else:
            body = ""
            
        headers = dict(getattr(request, 'headers', {}))
        content_type = headers.get('content-type', '')
        
        # Initialize data variables
        data = None
        parsed_data = None
        
        # Parse request based on content type
        if body:
            if 'application/json' in content_type:
                try:
                    data = json.loads(body)
                    parsed_data = data
                    # Handle Slack URL verification for JSON requests
                    if data.get('type') == 'url_verification':
                        challenge = data.get('challenge', '')
                        return {
                            'statusCode': 200,
                            'headers': {'Content-Type': 'text/plain'},
                            'body': challenge
                        }
                    logger.info(f"Parsed JSON request: {data.get('type', 'unknown')}")
                except json.JSONDecodeError:
                    logger.warning("Failed to parse JSON from Slack request")
                    data = None
            elif 'application/x-www-form-urlencoded' in content_type:
                try:
                    # Parse form-encoded data (used by slash commands, interactions)
                    parsed_data = urllib.parse.parse_qs(body)
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
                    data = json.loads(body)
                    parsed_data = data
                except json.JSONDecodeError:
                    # If not JSON, treat as raw data
                    parsed_data = {"raw_body": body}
        
        # Process with Slack Bolt if available
        if slack_handler:
            try:
                # Convert to Lambda-style event format for Slack Bolt
                event = {
                    "httpMethod": "POST",
                    "headers": headers,
                    "body": body,
                    "isBase64Encoded": False
                }
                
                # Process with Slack Bolt handler
                lambda_response = slack_handler.handle(event, None)
                
                # Log event type if available
                if data:
                    event_type = data.get('type') if isinstance(data, dict) else 'unknown'
                    command = data.get('command') if isinstance(data, dict) else 'unknown'
                    logger.info(f"Processed Slack event: {event_type}, command: {command}")
                
                return lambda_response
                
            except Exception as e:
                logger.error(f"Slack processing error: {e}")
                return {
                    'statusCode': 500,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Internal server error', 'message': str(e)})
                }
        else:
            # Fallback response when Slack app is not available
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    "status": "received",
                    "message": "Slack app not available, but event received"
                })
            }
        
    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Internal server error', 'message': str(e)})
        }