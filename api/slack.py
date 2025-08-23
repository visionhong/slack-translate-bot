import json
import logging
import urllib.parse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(request, context=None):
    """Simple Vercel handler function for testing"""
    try:
        logger.info("Handler called")
        
        # Get basic request info
        method = getattr(request, 'method', 'GET')
        logger.info(f"Method: {method}")
        
        if method == 'GET':
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    "status": "ok",
                    "service": "slack-translate-bot",
                    "endpoint": "slack-events",
                    "method": method
                })
            }
        
        # Handle POST requests
        if method == 'POST':
            # Get request body
            body = ""
            if hasattr(request, 'body'):
                body = request.body
                if hasattr(body, 'decode'):
                    body = body.decode('utf-8')
                elif isinstance(body, bytes):
                    body = body.decode('utf-8')
                else:
                    body = str(body)
            
            # Get headers
            headers = {}
            if hasattr(request, 'headers'):
                headers = dict(request.headers)
            
            content_type = headers.get('content-type', headers.get('Content-Type', ''))
            logger.info(f"Content-Type: {content_type}")
            logger.info(f"Body length: {len(body)}")
            
            # Parse form data if needed
            parsed_data = {}
            if 'application/x-www-form-urlencoded' in content_type and body:
                try:
                    parsed_data = urllib.parse.parse_qs(body)
                    parsed_data = {k: v[0] if len(v) == 1 else v for k, v in parsed_data.items()}
                    logger.info(f"Parsed command: {parsed_data.get('command', 'none')}")
                except Exception as e:
                    logger.error(f"Parse error: {e}")
            
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    "status": "received",
                    "method": method,
                    "content_type": content_type,
                    "body_length": len(body),
                    "parsed_command": parsed_data.get('command', 'none'),
                    "message": "Request processed successfully"
                })
            }
        
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'})
        }
        
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'Internal server error', 
                'message': str(e),
                'type': type(e).__name__
            })
        }