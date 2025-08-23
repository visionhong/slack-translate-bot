import asyncio
import logging
from openai import AsyncAzureOpenAI
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self):
        self.client = AsyncAzureOpenAI(
            api_key=settings.azure_openai.api_key,
            api_version=settings.azure_openai.api_version,
            azure_endpoint=settings.azure_openai.endpoint
        )
        self.deployment_name = settings.azure_openai.deployment_name
    
    def detect_language(self, text: str) -> str:
        # Simple Korean detection - contains Hangul characters
        if any('\uAC00' <= char <= '\uD7A3' for char in text):
            return 'ko'
        return 'en'
    
    async def translate(self, text: str, source_lang: Optional[str] = None, target_lang: Optional[str] = None) -> str:
        if not text.strip():
            return text
        
        # Auto-detect language if not provided
        if source_lang is None:
            source_lang = self.detect_language(text)
        
        # Default target language based on source
        if target_lang is None:
            target_lang = 'en' if source_lang == 'ko' else 'ko'
        
        # Skip translation if source and target are the same
        if source_lang == target_lang:
            return text
        
        try:
            # Prepare translation prompt
            if source_lang == 'ko' and target_lang == 'en':
                prompt = f"Translate the following Korean text to natural English:\n\n{text}"
            elif source_lang == 'en' and target_lang == 'ko':
                prompt = f"Translate the following English text to natural Korean:\n\n{text}"
            else:
                prompt = f"Translate the following text from {source_lang} to {target_lang}:\n\n{text}"
            
            response = await self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a professional translator. Translate the given text accurately and naturally. Only return the translation, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            translated_text = response.choices[0].message.content.strip()
            logger.info(f"Translated '{text[:50]}...' from {source_lang} to {target_lang}")
            return translated_text
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return f"Translation error: {str(e)}"


# Global instance
translation_service = TranslationService()