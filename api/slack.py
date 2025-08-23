from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import logging
import re
import asyncio
import aiohttp
import os
from openai import AsyncAzureOpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleTranslationService:
    def __init__(self):
        try:
            api_key = os.getenv('AZURE_OPENAI_API_KEY')
            endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
            api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-01')
            deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
            
            if api_key and endpoint:
                self.client = AsyncAzureOpenAI(
                    api_key=api_key,
                    api_version=api_version,
                    azure_endpoint=endpoint
                )
                self.deployment_name = deployment
                logger.info("Translation service initialized")
            else:
                self.client = None
                logger.warning("Translation service not configured")
        except Exception as e:
            logger.error(f"Failed to initialize translation service: {e}")
            self.client = None
    
    def detect_language(self, text: str) -> str:
        if any('\uAC00' <= char <= '\uD7A3' for char in text):
            return 'ko'
        return 'en'
    
    async def translate(self, text: str) -> str:
        if not text.strip() or self.client is None:
            return text
        
        source_lang = self.detect_language(text)
        
        try:
            if source_lang == 'ko':
                prompt = f"Translate the following Korean text to natural English:\n\n{text}"
            else:
                prompt = f"Translate the following English text to natural Korean:\n\n{text}"
            
            response = await self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a professional translator. Translate accurately and naturally. Only return the translation."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            return response.choices[0].message.content.strip()
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
                                # Show modal with translation result
                                asyncio.run(self._show_translation_modal(trigger_id, text.strip(), user_id))
                            else:
                                # Show input modal if no text provided
                                asyncio.run(self._show_input_modal(trigger_id))
                            
                            # Return acknowledgment
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({"response_type": "ephemeral", "text": "Opening translation modal..."}).encode())
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
    
    async def _show_input_modal(self, trigger_id):
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
            
            await self._call_slack_api('views.open', modal_payload)
            
        except Exception as e:
            logger.error(f"Error showing input modal: {e}")
    
    async def _show_translation_modal(self, trigger_id, original_text, user_id):
        """Show modal with original text and translation result"""
        try:
            # Translate text
            translated_text = await translation_service.translate(original_text)
            
            # Detect source language for proper labeling
            source_lang = translation_service.detect_language(original_text)
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
            
            await self._call_slack_api('views.open', modal_payload)
            logger.info(f"Successfully showed translation modal for user {user_id}")
            
        except Exception as e:
            logger.error(f"Translation modal error: {e}")
    
    async def _call_slack_api(self, method, payload):
        """Call Slack API method"""
        try:
            bot_token = os.getenv('SLACK_BOT_TOKEN')
            if not bot_token:
                logger.error("SLACK_BOT_TOKEN not configured")
                return
            
            url = f'https://slack.com/api/{method}'
            headers = {
                'Authorization': f'Bearer {bot_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    result = await response.json()
                    if not result.get('ok'):
                        logger.error(f"Slack API error: {result.get('error', 'Unknown error')}")
                    return result
                    
        except Exception as e:
            logger.error(f"Slack API call error: {e}")
            return None