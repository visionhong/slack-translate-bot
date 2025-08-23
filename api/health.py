import time
import json
from typing import Dict, Any

start_time = time.time()


def handler_func(request) -> Dict[str, Any]:
    """Health check endpoint for the translation bot"""
    try:
        uptime = int(time.time() - start_time)
        
        response_data = {
            "status": "healthy",
            "service": "slack-translation-bot",
            "uptime_seconds": uptime,
            "version": "1.0.0",
            "environment": "production"
        }
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(response_data)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Internal server error', 'message': str(e)})
        }