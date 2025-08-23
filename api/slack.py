from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import logging
import os
import requests
import time
from openai import AzureOpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"SimpleTranslationService.translate called with text: {text[:100]}...")
        
        if not text.strip():
            logger.info("Empty text provided, returning as-is")
            return text
            
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
            
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=16384,
                temperature=0
            )
            
            logger.info(f"Received response from Azure OpenAI: {response}")
            
            translated_text = response.choices[0].message.content.strip()
            logger.info(f"Extracted translated text: {translated_text}")
            logger.info(f"Successfully translated text from {source_lang}")
            return translated_text
            
        except Exception as e:
            logger.error(f"Azure OpenAI translation error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            # Fallback to mock translation
            if source_lang == 'ko':
                return f"[Fallback] Hello (translation of: {text})"
            else:
                return f"[Fallback] 안녕하세요 (번역: {text})"

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
                            
                            if text.strip():
                                # Translate immediately and show modal (must be within 3 seconds)
                                try:
                                    source_lang = translation_service.detect_language(text)
                                    logger.info(f"Detected language: {source_lang} for text: {text[:50]}...")
                                    
                                    translated_text = translation_service.translate(text.strip())
                                    logger.info(f"Translation result: {translated_text[:100]}...")
                                    logger.info(f"Translation result length: {len(translated_text)}")
                                    
                                    # Try to show modal with results
                                    modal_success = self._show_translation_modal(trigger_id, text.strip(), translated_text, source_lang)
                                    
                                    if modal_success:
                                        # Modal opened successfully - no Slack response needed
                                        self.send_response(200)
                                        self.send_header('Content-type', 'text/plain')
                                        self.end_headers()
                                        self.wfile.write(b'')
                                        return
                                    else:
                                        # Fallback: show inline response
                                        
                                        if source_lang == 'ko':
                                            original_label = "한국어"
                                            translated_label = "English"
                                        else:
                                            original_label = "English"
                                            translated_label = "한국어"
                                        
                                        translation_response = {
                                            "response_type": "ephemeral",
                                            "text": "🌐 Translation Result",
                                            "blocks": [
                                                {
                                                    "type": "section",
                                                    "text": {
                                                        "type": "mrkdwn",
                                                        "text": f"*{original_label}*\n{text.strip()}"
                                                    }
                                                },
                                                {
                                                    "type": "divider"
                                                },
                                                {
                                                    "type": "section",
                                                    "text": {
                                                        "type": "mrkdwn",
                                                        "text": f"*{translated_label}*\n{translated_text}"
                                                    }
                                                },
                                                {
                                                    "type": "context",
                                                    "elements": [
                                                        {
                                                            "type": "mrkdwn",
                                                            "text": "💡 Copy the text above to use it!"
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                        
                                except Exception as e:
                                    logger.error(f"Translation failed: {e}")
                                    translation_response = {
                                        "response_type": "ephemeral",
                                        "text": f"Translation error: {str(e)}"
                                    }
                                    
                            else:
                                # Try to show input modal for empty commands
                                modal_success = self._show_input_modal(trigger_id)
                                
                                if modal_success:
                                    # Modal opened successfully - no Slack response needed
                                    self.send_response(200)
                                    self.send_header('Content-type', 'text/plain')
                                    self.end_headers()
                                    self.wfile.write(b'')
                                    return
                                else:
                                    translation_response = {
                                        "response_type": "ephemeral",
                                        "text": "🌐 Please provide text to translate: `/translate your text here`"
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
    
    
    def _show_input_modal(self, trigger_id):
        """Show modal for text input when no text is provided"""
        try:
            modal_payload = {
                "trigger_id": trigger_id,
                "view": {
                    "type": "modal",
                    "callback_id": "translation_input_modal",
                    "title": {
                        "type": "plain_text",
                        "text": "번역하기"
                    },
                    "submit": {
                        "type": "plain_text",
                        "text": "번역"
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "취소"
                    },
                    "blocks": [
                        {
                            "type": "input",
                            "block_id": "text_input_block",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "text_input",
                                "multiline": True,
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "번역할 텍스트를 입력하세요..."
                                }
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "텍스트"
                            }
                        }
                    ]
                }
            }
            
            result = self._call_slack_api('views.open', modal_payload)
            return result and result.get('ok', False)
            
        except Exception as e:
            logger.error(f"Error showing input modal: {e}")
            return False
    
    def _show_translation_modal(self, trigger_id, original_text, translated_text, source_lang):
        """Show modal with original text and translation result"""
        try:
            # Split long text into multiple section blocks if needed
            def create_text_sections(text, max_chars=2800):
                if len(text) <= max_chars:
                    return [{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"```{text}```"
                        }
                    }]
                
                sections = []
                start = 0
                while start < len(text):
                    end = min(start + max_chars, len(text))
                    # Try to break at word boundary if not at end
                    if end < len(text):
                        last_space = text.rfind(' ', start, end)
                        last_newline = text.rfind('\n', start, end)
                        break_point = max(last_space, last_newline)
                        if break_point > start:
                            end = break_point
                    
                    chunk = text[start:end]
                    sections.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"```{chunk}```"
                        }
                    })
                    
                    start = end
                
                return sections
            
            # Create blocks with sections for original and translated text
            blocks = []
            
            # Add original text sections
            blocks.extend(create_text_sections(original_text))
            
            # Add divider
            blocks.append({
                "type": "divider"
            })
            
            # Add translated text sections
            blocks.extend(create_text_sections(translated_text))
            
            # Add context help
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 텍스트를 선택하여 복사하세요. 모달은 팝아웃하여 창 크기를 조정할 수 있습니다."
                    }
                ]
            })
            
            modal_payload = {
                "trigger_id": trigger_id,
                "view": {
                    "type": "modal",
                    "title": {
                        "type": "plain_text",
                        "text": "번역 결과"
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "닫기"
                    },
                    "blocks": blocks
                }
            }
            
            result = self._call_slack_api('views.open', modal_payload)
            success = result and result.get('ok', False)
            if success:
                logger.info(f"Successfully showed translation modal")
            return success
            
        except Exception as e:
            logger.error(f"Translation modal error: {e}")
            return False
    
    def _call_slack_api(self, method, payload):
        """Call Slack API method"""
        try:
            bot_token = os.getenv('SLACK_BOT_TOKEN')
            if not bot_token:
                logger.error("SLACK_BOT_TOKEN not configured - modal will not work")
                return {'ok': False, 'error': 'missing_token'}
            
            url = f'https://slack.com/api/{method}'
            headers = {
                'Authorization': f'Bearer {bot_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=2)
            response.raise_for_status()
            
            result = response.json()
            if not result.get('ok'):
                logger.error(f"Slack API error: {result.get('error', 'Unknown error')}")
            return result
                
        except Exception as e:
            logger.error(f"Slack API call error: {e}")
            return {'ok': False, 'error': str(e)}