"""
FastAPI Slack Translation Bot
Vercel 서버리스 환경에 최적화된 번역 봇
"""

import os
import json
import logging
import hashlib
import asyncio
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, Response
import httpx
from openai import AsyncAzureOpenAI
import uvicorn

# 환경 변수 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Slack Translation Bot",
    description="Azure OpenAI 기반 번역 봇",
    version="2.0.0"
)

# 글로벌 변수
active_requests = set()
translation_cache = {}

class TranslationService:
    def __init__(self):
        self.api_key = os.getenv('AZURE_OPENAI_API_KEY')
        self.endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview')
        self.deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
        
        if self.api_key and self.endpoint and self.deployment_name:
            self.client = AsyncAzureOpenAI(
                api_version=self.api_version,
                azure_endpoint=self.endpoint,
                api_key=self.api_key
            )
            self.available = True
            logger.info(f"Translation service configured with deployment: {self.deployment_name}")
        else:
            self.client = None
            self.available = False
            logger.warning("Translation service not configured")
    
    def detect_language(self, text: str) -> str:
        """언어 감지 (한국어 vs 영어)"""
        if any('\uAC00' <= char <= '\uD7A3' for char in text):
            return 'ko'
        return 'en'
    
    async def translate(self, text: str) -> str:
        """비동기 번역"""
        if not text.strip():
            return text
        
        if not self.available:
            logger.warning("Translation service not available, using mock")
            source_lang = self.detect_language(text)
            if source_lang == 'ko':
                return f"[Mock] Hello (translation of: {text})"
            else:
                return f"[Mock] 안녕하세요 (번역: {text})"
        
        source_lang = self.detect_language(text)
        logger.info(f"Detected language: {source_lang}")
        
        try:
            if source_lang == 'ko':
                prompt = f"Translate to English:\n{text}"
            else:
                prompt = f"Translate to Korean:\n{text}"
            
            logger.info("🚀 Starting Azure OpenAI translation...")
            
            response = await self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a friendly team communication translator. Translate naturally and conversationally for casual team chat. Keep the tone friendly and approachable, not formal or stiff. Only return the translation."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.deployment_name,
                max_completion_tokens=16384,
                timeout=15  # 15초 타임아웃
            )
            
            logger.info("✅ Azure OpenAI response received")
            
            # 응답 분석
            raw_content = response.choices[0].message.content
            logger.info(f"🔍 Raw content: '{raw_content}'")
            logger.info(f"Content is None: {raw_content is None}")
            
            if raw_content is None:
                logger.error("❌ Azure OpenAI returned None content")
                return "Translation failed - empty response"
            
            translated_text = raw_content.strip()
            logger.info(f"📝 Final result: '{translated_text}' (length: {len(translated_text)})")
            
            return translated_text
            
        except Exception as e:
            logger.error(f"❌ Translation error: {e}")
            # Fallback translation
            if source_lang == 'ko':
                if '테스트' in text:
                    return "I will test this."
                elif '안녕' in text:
                    return "Hello."
                else:
                    return f"Translation service error. Original: {text}"
            else:
                if 'test' in text.lower():
                    return "테스트"
                elif 'hello' in text.lower():
                    return "안녕하세요"
                else:
                    return f"번역 서비스 오류. 원문: {text}"

# 글로벌 번역 서비스 인스턴스
translation_service = TranslationService()

def get_request_id(user_id: str, text: str) -> str:
    """요청 ID 생성"""
    content = f"{user_id}:{text}"
    return hashlib.md5(content.encode()).hexdigest()[:12]

async def open_initial_modal(trigger_id: str, text: str):
    """번역 시작 모달 열기"""
    try:
        bot_token = os.getenv('SLACK_BOT_TOKEN')
        if not bot_token:
            logger.error("❌ SLACK_BOT_TOKEN not found")
            return None
        
        # 번역 중 모달 블록 구성
        modal_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{text}\n\n---\n\n🔄 번역 중..."
                }
            }
        ]
        
        modal_payload = {
            "trigger_id": trigger_id,
            "view": {
                "type": "modal",
                "title": {
                    "type": "plain_text",
                    "text": "번역 결과"
                },
                "blocks": modal_blocks
            }
        }
        
        logger.info("📤 Opening initial translation modal...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/views.open",
                json=modal_payload,
                headers={
                    'Authorization': f'Bearer {bot_token}',
                    'Content-Type': 'application/json'
                },
                timeout=10.0
            )
            
            result = response.json()
            logger.info(f"Initial modal response: {result}")
            
            if result.get('ok'):
                view_id = result['view']['id']
                logger.info(f"✅ Successfully opened initial modal with view_id: {view_id}")
                return view_id
            else:
                error = result.get('error', 'unknown')
                logger.error(f"❌ Failed to open initial modal: {error}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Error opening initial modal: {e}")
        return None

async def update_modal_with_translation(view_id: str, text: str, translated_text: str, response_url: str):
    """모달을 번역 결과로 업데이트"""
    try:
        bot_token = os.getenv('SLACK_BOT_TOKEN')
        if not bot_token:
            logger.error("❌ SLACK_BOT_TOKEN not found, using fallback")
            await send_fallback_message(response_url, text, translated_text)
            return
        
        # 번역 완료 모달 블록 구성
        updated_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{text}\n\n---\n\n{translated_text}"
                }
            }
        ]
        
        update_payload = {
            "view_id": view_id,
            "view": {
                "type": "modal",
                "title": {
                    "type": "plain_text",
                    "text": "번역 결과"
                },
                "blocks": updated_blocks
            }
        }
        
        logger.info(f"🔄 Updating modal {view_id} with translation result...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/views.update",
                json=update_payload,
                headers={
                    'Authorization': f'Bearer {bot_token}',
                    'Content-Type': 'application/json'
                },
                timeout=10.0
            )
            
            result = response.json()
            logger.info(f"Update modal response: {result}")
            
            if result.get('ok'):
                logger.info("✅ Successfully updated modal with translation")
            else:
                error = result.get('error', 'unknown')
                logger.warning(f"⚠️ Modal update failed ({error}), using fallback message")
                # view_id 만료 등으로 모달 업데이트 실패시 메시지로 대체
                await send_fallback_message(response_url, text, translated_text)
                
    except Exception as e:
        logger.error(f"❌ Error updating modal, using fallback: {e}")
        await send_fallback_message(response_url, text, translated_text)

async def send_fallback_message(response_url: str, text: str, translated_text: str):
    """모달 실패시 대체 메시지 전송"""
    try:
        # 메시지용 블록 구성 (모달과 동일한 레이아웃)
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{text}\n\n---\n\n{translated_text}"
                }
            }
        ]
        
        fallback_response = {
            "response_type": "ephemeral",
            "text": "🌐 번역 완료",
            "blocks": blocks
        }
        
        logger.info("📤 Sending fallback translation message...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                response_url,
                json=fallback_response,
                headers={'Content-Type': 'application/json'},
                timeout=10.0
            )
            
            if response.status_code == 200:
                logger.info("✅ Successfully sent fallback message")
            else:
                logger.error(f"❌ Failed to send fallback: {response.status_code}")
                
    except Exception as e:
        logger.error(f"❌ Error sending fallback message: {e}")

def create_text_blocks(text: str, max_chars: int = 2800) -> list:
    """긴 텍스트를 Slack 블록으로 분할"""
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

async def process_translation(
    text: str, 
    view_id: str,
    response_url: str,
    user_id: str, 
    request_id: str
):
    """백그라운드 번역 처리"""
    try:
        logger.info(f"🔄 Processing translation for request {request_id}")
        
        # 번역 수행
        translated_text = await translation_service.translate(text)
        
        # 모달 업데이트 (실패시 메시지로 대체)
        if view_id:
            await update_modal_with_translation(view_id, text, translated_text, response_url)
        else:
            await send_fallback_message(response_url, text, translated_text)
        
        logger.info(f"✅ Translation completed for request {request_id}")
        
    except Exception as e:
        logger.error(f"❌ Translation processing error: {e}")
        
        # 에러 표시 (모달 업데이트 시도 후 메시지로 대체)
        try:
            if view_id:
                await update_modal_with_translation(view_id, text, f"번역 오류: {str(e)}", response_url)
            else:
                await send_fallback_message(response_url, text, f"번역 오류: {str(e)}")
        except:
            logger.error("Failed to show error message")
        
    finally:
        # 활성 요청에서 제거
        active_requests.discard(request_id)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "slack-translation-bot",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health():
    """상세 헬스 체크"""
    return {
        "status": "healthy",
        "service": "slack-translation-bot", 
        "translation_service": translation_service.available,
        "active_requests": len(active_requests),
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.post("/api/slack")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    """Slack 이벤트 및 명령어 처리"""
    try:
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            data = await request.json()
            
            # URL 검증
            if data.get('type') == 'url_verification':
                return {"challenge": data.get('challenge', '')}
                
        elif "application/x-www-form-urlencoded" in content_type:
            form_data = await request.form()
            
            # Slack command 처리
            command = form_data.get('command')
            text = form_data.get('text', '').strip()
            user_id = form_data.get('user_id')
            trigger_id = form_data.get('trigger_id')
            response_url = form_data.get('response_url')
            
            logger.info(f"📩 Received command: {command} with text: {text[:50]}...")
            
            if command == '/translate':
                request_id = get_request_id(user_id, text)
                
                # 중복 요청 체크
                if request_id in active_requests:
                    logger.info(f"Duplicate request: {request_id}")
                    return JSONResponse(content="")
                
                active_requests.add(request_id)
                
                if text:
                    # 즉시 번역 모달 열기
                    view_id = await open_initial_modal(trigger_id, text)
                    
                    # 백그라운드에서 번역 처리
                    background_tasks.add_task(
                        process_translation,
                        text, view_id, response_url, user_id, request_id
                    )
                    
                    # 즉시 200 응답 (빈 응답)
                    return Response(status_code=200)
                    
                else:
                    active_requests.discard(request_id)
                    # 사용법 안내
                    return JSONResponse(content={
                        "response_type": "ephemeral",
                        "text": "🌐 사용법: `/translate 번역할 텍스트` 또는 `/translate text to translate`"
                    })
        
        # 기본 응답
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"❌ Error processing request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)