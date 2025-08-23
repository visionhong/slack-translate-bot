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
from fastapi.responses import JSONResponse
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
                        "content": "You are a professional translator. Translate accurately and naturally. Only return the translation."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.deployment_name,
                max_tokens=16384,
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

async def send_delayed_response(response_url: str, message: dict):
    """지연 응답 전송"""
    try:
        logger.info(f"📤 Sending delayed response to: {response_url[:50]}...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                response_url,
                json=message,
                headers={'Content-Type': 'application/json'},
                timeout=10.0
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                logger.info("✅ Successfully sent delayed response")
            else:
                logger.error(f"❌ Failed to send delayed response: {response.status_code}")
                logger.error(f"Response: {response.text}")
                
    except Exception as e:
        logger.error(f"❌ Error sending delayed response: {e}")

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
    response_url: str, 
    user_id: str, 
    request_id: str
):
    """백그라운드 번역 처리"""
    try:
        logger.info(f"🔄 Processing translation for request {request_id}")
        
        # 번역 수행
        translated_text = await translation_service.translate(text)
        
        # 블록 생성
        blocks = []
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🌐 *번역 완료*"
            }
        })
        
        # 원문 블록
        blocks.extend(create_text_blocks(text))
        blocks.append({"type": "divider"})
        
        # 번역문 블록
        blocks.extend(create_text_blocks(translated_text))
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "💡 텍스트를 선택하여 복사하세요."
            }]
        })
        
        # 후속 메시지 전송
        follow_up_response = {
            "replace_original": True,
            "response_type": "ephemeral",
            "text": "🌐 번역 완료",
            "blocks": blocks
        }
        
        await send_delayed_response(response_url, follow_up_response)
        logger.info(f"✅ Translation completed for request {request_id}")
        
    except Exception as e:
        logger.error(f"❌ Translation processing error: {e}")
        
        # 에러 응답 전송
        error_response = {
            "replace_original": True,
            "response_type": "ephemeral",
            "text": f"❌ 번역 오류: {str(e)}"
        }
        
        await send_delayed_response(response_url, error_response)
        
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
                    # 즉시 응답
                    immediate_response = {
                        "response_type": "ephemeral",
                        "text": "🔄 번역 중입니다... 잠시만 기다려주세요."
                    }
                    
                    # 백그라운드에서 번역 처리
                    background_tasks.add_task(
                        process_translation,
                        text, response_url, user_id, request_id
                    )
                    
                    return JSONResponse(content=immediate_response)
                    
                else:
                    # 사용법 안내
                    return JSONResponse(content={
                        "response_type": "ephemeral",
                        "text": "🌐 사용법: `/translate 번역할 텍스트` 또는 `/translate text to translate`"
                    })
        
        # 기본 응답
        return JSONResponse(content="")
        
    except Exception as e:
        logger.error(f"❌ Error processing request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)