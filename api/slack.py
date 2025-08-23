from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import logging
import os
import requests
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleTranslationService:
    def __init__(self):
        try:
            self.api_key = os.getenv('AZURE_OPENAI_API_KEY')
            self.endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
            self.api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-01')
            self.deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
            
            if self.api_key and self.endpoint:
                logger.info("Translation service configured")
                self.available = True
            else:
                logger.warning("Translation service not configured - missing environment variables")
                self.available = False
        except Exception as e:
            logger.error(f"Failed to initialize translation service: {e}")
            self.available = False
    
    def detect_language(self, text: str) -> str:
        if any('\uAC00' <= char <= '\uD7A3' for char in text):
            return 'ko'
        return 'en'
    
    def translate(self, text: str) -> str:
        if not text.strip() or not self.available:
            return text
        
        source_lang = self.detect_language(text)
        
        try:
            if source_lang == 'ko':
                prompt = f"Translate the following Korean text to natural English:\n\n{text}"
            else:
                prompt = f"Translate the following English text to natural Korean:\n\n{text}"
            
            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
            headers = {
                'api-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {
                "messages": [
                    {"role": "system", "content": "You are a professional translator. Translate accurately and naturally. Only return the translation."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1000,
                "temperature": 0.1
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            translated_text = result['choices'][0]['message']['content'].strip()
            logger.info(f"Successfully translated text from {source_lang}")
            return translated_text
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return f"Translation error: {str(e)}"

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
                                # Attempt translation
                                try:
                                    translated_text = translation_service.translate(text.strip())
                                    source_lang = translation_service.detect_language(text)
                                    
                                    # Show translation modal
                                    self._show_translation_modal(trigger_id, text.strip(), translated_text, source_lang)
                                    
                                    # Return acknowledgment
                                    response_text = "🌐 Opening translation modal..."
                                    
                                except Exception as e:
                                    logger.error(f"Translation failed: {e}")
                                    response_text = f"Translation error: {str(e)}"
                                    
                            else:
                                # Show input modal for empty commands
                                self._show_input_modal(trigger_id)
                                response_text = "🌐 Opening input modal..."
                            
                            translation_response = {
                                "response_type": "ephemeral",
                                "text": response_text
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
            
            self._call_slack_api('views.open', modal_payload)
            
        except Exception as e:
            logger.error(f"Error showing input modal: {e}")
    
    def _show_translation_modal(self, trigger_id, original_text, translated_text, source_lang):
        """Show modal with original text and translation result"""
        try:
            # Set language labels
            if source_lang == 'ko':
                original_label = "한국어"
                translated_label = "English"
            else:
                original_label = "English"
                translated_label = "한국어"
            
            modal_payload = {
                "trigger_id": trigger_id,
                "view": {
                    "type": "modal",
                    "callback_id": "translation_result_modal",
                    "title": {
                        "type": "plain_text",
                        "text": "번역 결과"
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "닫기"
                    },
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{original_label}*"
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "original_text_block",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "original_text",
                                "multiline": True,
                                "initial_value": original_text
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "원문"
                            }
                        },
                        {
                            "type": "divider"
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{translated_label}*"
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "translated_text_block",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "translated_text",
                                "multiline": True,
                                "initial_value": translated_text
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "번역문"
                            }
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": "💡 텍스트를 편집하고 복사해서 사용하세요!"
                                }
                            ]
                        }
                    ]
                }
            }
            
            self._call_slack_api('views.open', modal_payload)
            logger.info(f"Successfully showed translation modal")
            
        except Exception as e:
            logger.error(f"Translation modal error: {e}")
    
    def _call_slack_api(self, method, payload):
        """Call Slack API method"""
        try:
            bot_token = os.getenv('SLACK_BOT_TOKEN')
            if not bot_token:
                logger.error("SLACK_BOT_TOKEN not configured")
                return None
            
            url = f'https://slack.com/api/{method}'
            headers = {
                'Authorization': f'Bearer {bot_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            
            result = response.json()
            if not result.get('ok'):
                logger.error(f"Slack API error: {result.get('error', 'Unknown error')}")
            return result
                
        except Exception as e:
            logger.error(f"Slack API call error: {e}")
            return None