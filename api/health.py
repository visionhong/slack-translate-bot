from http.server import BaseHTTPRequestHandler
import json
import time

start_time = time.time()

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            uptime = int(time.time() - start_time)
            
            response_data = {
                "status": "healthy",
                "service": "slack-translation-bot",
                "uptime_seconds": uptime,
                "version": "1.0.0",
                "environment": "production"
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            self.wfile.write(json.dumps(response_data).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            error_response = {'error': 'Internal server error', 'message': str(e)}
            self.wfile.write(json.dumps(error_response).encode())