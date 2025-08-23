import asyncio
import logging
from openai import AsyncAzureOpenAI
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self):
        try:
            self.client = AsyncAzureOpenAI(
                api_key=settings.azure_openai.api_key,
                api_version=settings.azure_openai.api_version,
                azure_endpoint=settings.azure_openai.endpoint
            )
            self.deployment_name = settings.azure_openai.deployment_name
            logger.info("AsyncAzureOpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.client = None
            self.deployment_name = settings.azure_openai.deployment_name
    
    def detect_language(self, text: str) -> str:
        # Simple Korean detection - contains Hangul characters
        if any('\uAC00' <= char <= '\uD7A3' for char in text):
            return 'ko'
        return 'en'
    
    async def translate(self, text: str, source_lang: Optional[str] = None, target_lang: Optional[str] = None) -> str:
        logger.info(f"Starting translation for text: {text[:100]}...")
        
        if not text.strip():
            logger.info("Empty text provided, returning as-is")
            return text
        
        # Check if client is available
        if self.client is None:
            logger.error("Azure OpenAI client not available")
            return f"Translation service unavailable. Original text: {text}"
        
        logger.info(f"Azure OpenAI client available, endpoint: {self.client._base_url}")
        logger.info(f"Using deployment: {self.deployment_name}")
        
        # Auto-detect language if not provided
        if source_lang is None:
            source_lang = self.detect_language(text)
        
        logger.info(f"Source language: {source_lang}")
        
        # Default target language based on source
        if target_lang is None:
            target_lang = 'en' if source_lang == 'ko' else 'ko'
        
        logger.info(f"Target language: {target_lang}")
        
        # Skip translation if source and target are the same
        if source_lang == target_lang:
            logger.info("Source and target languages are the same, returning original text")
            return text
        
        try:
            # Prepare translation prompt
            if source_lang == 'ko' and target_lang == 'en':
                prompt = f"Translate the following Korean text to natural English:\n\n{text}"
            elif source_lang == 'en' and target_lang == 'ko':
                prompt = f"Translate the following English text to natural Korean:\n\n{text}"
            else:
                prompt = f"Translate the following text from {source_lang} to {target_lang}:\n\n{text}"
            
            logger.info(f"Sending request to Azure OpenAI with prompt: {prompt[:100]}...")
            
            response = await self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a professional translator. Translate the given text accurately and naturally. Only return the translation, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            logger.info(f"Received response from Azure OpenAI: {response}")
            
            translated_text = response.choices[0].message.content.strip()
            logger.info(f"Extracted translated text: {translated_text}")
            logger.info(f"Translation completed - Original: '{text[:50]}...' -> Translated: '{translated_text[:50]}...'")
            
            return translated_text
            
        except Exception as e:
            logger.error(f"Azure OpenAI translation error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            return f"Translation error: {str(e)}"


# Global instance
translation_service = TranslationService()