import os
import sys
import json
import logging
from typing import Dict, Any

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from slack_bolt import App
from slack_bolt.adapter.aws_lambda.serverless_handler import SlackRequestHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Slack app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    process_before_response=True
)

# Import handlers
try:
    from src.handlers.command import handle_translate_command, handle_help_command, handle_stats_command
    from src.handlers.events import handle_app_mention, handle_direct_message, handle_reaction_added
    
    # Register handlers
    app.command("/translate")(handle_translate_command)
    app.command("/translate-help")(handle_help_command) 
    app.command("/translate-stats")(handle_stats_command)
    app.event("app_mention")(handle_app_mention)
    app.event("message")(handle_direct_message)
    app.event("reaction_added")(handle_reaction_added)
    
except ImportError as e:
    logger.warning(f"Could not import handlers: {e}")

# Create handler
handler = SlackRequestHandler(app)


def handler_func(request) -> Dict[str, Any]:
    """Main handler function for Vercel"""
    try:
        # Convert Vercel request to format expected by Slack handler
        if hasattr(request, 'method'):
            method = request.method
        else:
            method = request.get('httpMethod', 'POST')
            
        if hasattr(request, 'body'):
            body = request.body
        else:
            body = request.get('body', '')
            
        if hasattr(request, 'headers'):
            headers = dict(request.headers)
        else:
            headers = request.get('headers', {})
            
        # Handle the request
        response = handler.handle({
            'httpMethod': method,
            'body': body,
            'headers': headers,
            'isBase64Encoded': False
        }, None)
        
        return {
            'statusCode': response.get('statusCode', 200),
            'headers': response.get('headers', {}),
            'body': response.get('body', '{"status": "ok"}')
        }
        
    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Internal server error'})
        }