from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import logging
import os
import requests
import time
import threading
import hashlib
from openai import AzureOpenAI

# Configure logging - reduce verbosity for better performance
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set Azure OpenAI and httpx to WARNING level to reduce noise
logging.getLogger('openai').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

# Memory cache and request tracking
translation_cache = {}
active_requests = set()
active_modals = {}  # Store view_id for active translation requests
cache_lock = threading.Lock()

class SimpleTranslationService:
    def __init__(self):
        try:
            self.api_key = os.getenv('AZURE_OPENAI_API_KEY')
            self.endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
            self.api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview')
            self.deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
            
            if self.api_key and self.endpoint and self.deployment_name:
                self.client = AzureOpenAI(
                    api_version=self.api_version,
                    azure_endpoint=self.endpoint,
                    api_key=self.api_key
                )
                logger.info(f"Translation service configured with deployment: {self.deployment_name}")
                self.available = True
            else:
                self.client = None
                logger.warning(f"Translation service not configured - missing: api_key={bool(self.api_key)}, endpoint={bool(self.endpoint)}, deployment={bool(self.deployment_name)}")
                self.available = False
        except Exception as e:
            logger.error(f"Failed to initialize translation service: {e}")
            self.client = None
            self.available = False
    
    def detect_language(self, text: str) -> str:
        if any('\uAC00' <= char <= '\uD7A3' for char in text):
            return 'ko'
        return 'en'
    
    def translate(self, text: str) -> str:
        logger.debug(f"SimpleTranslationService.translate called with text: {text[:100]}...")
        
        if not text.strip():
            logger.debug("Empty text provided, returning as-is")
            return text
        
        # Disable cache for debugging
        # cache_key = get_cache_key(text)
        # with cache_lock:
        #     if cache_key in translation_cache:
        #         cached_result = translation_cache[cache_key]
        #         if time.time() - cached_result['timestamp'] < 3600:  # 1 hour cache
        #             logger.info("Using cached translation result")
        #             return cached_result['translation']
        #         else:
        #             # Remove expired cache
        #             del translation_cache[cache_key]
            
        # If service not available, provide mock translation for testing
        if not self.available:
            logger.warning("Translation service not available, using mock translation")
            source_lang = self.detect_language(text)
            if source_lang == 'ko':
                return f"[Mock] Hello (translation of: {text})"
            else:
                return f"[Mock] 안녕하세요 (번역: {text})"
        
        logger.info(f"Azure OpenAI client available, endpoint: {self.endpoint}")
        logger.info(f"Using deployment: {self.deployment_name}")
        
        source_lang = self.detect_language(text)
        logger.info(f"Detected source language: {source_lang}")
        
        try:
            if source_lang == 'ko':
                prompt = f"Translate to English:\n{text}"
            else:
                prompt = f"Translate to Korean:\n{text}"
            
            logger.info(f"Sending request to Azure OpenAI with prompt: {prompt[:100]}...")
            
            # Use the Azure OpenAI client's built-in timeout instead of signal
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional translator. Translate accurately and naturally. Only return the translation."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_completion_tokens=16384,
                model=self.deployment_name,
                timeout=3  # 3 second timeout
            )
            logger.info("Azure OpenAI request completed successfully")
            
            translated_text = response.choices[0].message.content.strip()
            logger.info(f"Translation result extracted, length: {len(translated_text)}")
            
            # Disable caching for debugging
            # with cache_lock:
            #     translation_cache[cache_key] = {
            #         'translation': translated_text,
            #         'timestamp': time.time()
            #     }
            #     # Keep only last 100 translations in cache
            #     if len(translation_cache) > 100:
            #         oldest_key = min(translation_cache.keys(), key=lambda k: translation_cache[k]['timestamp'])
            #         del translation_cache[oldest_key]
            
            logger.info(f"Successfully translated text from {source_lang}")
            return translated_text
            
        except TimeoutError as e:
            logger.error(f"Azure OpenAI request timeout: {e}")
            # Fallback to mock translation on timeout
            if source_lang == 'ko':
                return f"[Timeout] Hello (translation of: {text})"
            else:
                return f"[Timeout] 안녕하세요 (번역: {text})"
        except Exception as e:
            logger.error(f"Azure OpenAI translation error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            # Fallback to mock translation
            if source_lang == 'ko':
                return f"[Error] Hello (translation of: {text})"
            else:
                return f"[Error] 안녕하세요 (번역: {text})"

def get_request_id(user_id, text):
    """Generate unique request ID"""
    content = f"{user_id}:{text}"
    return hashlib.md5(content.encode()).hexdigest()[:12]

def get_cache_key(text):
    """Generate cache key for translation"""
    return hashlib.md5(text.encode()).hexdigest()

def send_delayed_response(response_url, message):
    """Send delayed response to Slack"""
    try:
        response = requests.post(
            response_url,
            json=message,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
        if response.status_code == 200:
            logger.info("Successfully sent delayed response")
        else:
            logger.error(f"Failed to send delayed response: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending delayed response: {e}")

# Removed fallback message functions - modal-only approach

# Global translation service
translation_service = SimpleTranslationService()

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
                            response_url = data.get('response_url')
                            
                            # Generate request ID for duplicate prevention
                            request_id = get_request_id(user_id, text)
                            
                            # Check for duplicate requests
                            if request_id in active_requests:
                                logger.info(f"Duplicate request detected: {request_id}")
                                self.send_response(200)
                                self.send_header('Content-type', 'text/plain')
                                self.end_headers()
                                self.wfile.write(b'')
                                return
                            
                            # Add to active requests
                            active_requests.add(request_id)
                            
                            if text.strip():
                                # NEW APPROACH: Immediate 200 OK + background translation + follow-up message
                                logger.info(f"=== Using delayed response pattern for request {request_id} ===")
                                
                                # Send immediate acknowledgment to avoid 3-second timeout
                                self.send_response(200)
                                self.send_header('Content-type', 'application/json')
                                self.end_headers()
                                immediate_response = {
                                    "response_type": "ephemeral", 
                                    "text": "🔄 번역 중입니다... 잠시만 기다려주세요."
                                }
                                self.wfile.write(json.dumps(immediate_response).encode())
                                
                                # Process translation in background and send follow-up message
                                def process_translation_and_respond():
                                    try:
                                        logger.info(f"=== Starting background translation for request {request_id} ===")
                                        source_lang = translation_service.detect_language(text.strip())
                                        logger.info(f"Processing translation for request {request_id}, source_lang: {source_lang}")
                                        
                                        # Try Azure OpenAI translation
                                        translated_text = translation_service.translate(text.strip())
                                        logger.info(f"Translation completed for request {request_id}, result length: {len(translated_text)}")
                                        logger.info(f"Translation result preview: {translated_text[:100]}...")
                                        
                                        if not translated_text or translated_text.strip() == "":
                                            logger.error("Translation returned empty result")
                                            translated_text = "번역 결과를 가져올 수 없습니다."
                                        
                                        # Create blocks for long content
                                        def create_text_blocks(text, max_chars=2800):
                                            if len(text) <= max_chars:
                                                return [{
                                                    "type": "section",
                                                    "text": {
                                                        "type": "mrkdwn",
                                                        "text": f"```{text}```"
                                                    }
                                                }]
                                            
                                            blocks = []
                                            start = 0
                                            while start < len(text):
                                                end = min(start + max_chars, len(text))
                                                if end < len(text):
                                                    last_space = text.rfind(' ', start, end)
                                                    last_newline = text.rfind('\n', start, end)
                                                    break_point = max(last_space, last_newline)
                                                    if break_point > start:
                                                        end = break_point
                                                
                                                chunk = text[start:end]
                                                blocks.append({
                                                    "type": "section",
                                                    "text": {
                                                        "type": "mrkdwn",
                                                        "text": f"```{chunk}```"
                                                    }
                                                })
                                                start = end
                                            
                                            return blocks
                                        
                                        # Create response blocks
                                        blocks = []
                                        blocks.append({
                                            "type": "section",
                                            "text": {
                                                "type": "mrkdwn",
                                                "text": "🌐 *번역 완료*"
                                            }
                                        })
                                        blocks.extend(create_text_blocks(text.strip()))
                                        blocks.append({"type": "divider"})
                                        blocks.extend(create_text_blocks(translated_text))
                                        blocks.append({
                                            "type": "context",
                                            "elements": [{
                                                "type": "mrkdwn",
                                                "text": "💡 텍스트를 선택하여 복사하세요."
                                            }]
                                        })
                                        
                                        # Send follow-up message with translation result
                                        follow_up_response = {
                                            "replace_original": True,
                                            "response_type": "ephemeral",
                                            "text": "🌐 번역 완료",
                                            "blocks": blocks
                                        }
                                        
                                        if response_url:
                                            send_delayed_response(response_url, follow_up_response)
                                            logger.info("Successfully sent translation result as follow-up message")
                                        else:
                                            logger.error("No response_url available for follow-up message")
                                        
                                    except Exception as e:
                                        logger.error(f"Background translation error: {e}")
                                        logger.error(f"Error traceback: ", exc_info=True)
                                        
                                        # Send error follow-up message
                                        error_response = {
                                            "replace_original": True,
                                            "response_type": "ephemeral",
                                            "text": f"❌ 번역 오류: {str(e)}"
                                        }
                                        
                                        if response_url:
                                            send_delayed_response(response_url, error_response)
                                            logger.info("Successfully sent error message as follow-up")
                                        
                                    finally:
                                        # Remove from active requests
                                        active_requests.discard(request_id)
                                
                                # Start background translation
                                thread = threading.Thread(target=process_translation_and_respond)
                                thread.daemon = True
                                thread.start()
                                return
                                
                            else:
                                # Handle empty commands with help message
                                self.send_response(200)
                                self.send_header('Content-type', 'application/json')
                                self.end_headers()
                                help_response = {
                                    "response_type": "ephemeral",
                                    "text": "🌐 사용법: `/translate 번역할 텍스트` 또는 `/translate text to translate`"
                                }
                                self.wfile.write(json.dumps(help_response).encode())
                                
                                # Remove from active requests
                                active_requests.discard(request_id)
                                return
                            
                except Exception as e:
                    logger.warning(f"Failed to parse form-encoded data: {e}")
            
            # Silent response for unhandled requests (no chat messages)
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'')
            
        except Exception as e:
            logger.error(f"POST handler error: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'')
    
    
# Removed all modal functions - using delayed response pattern with follow-up messages