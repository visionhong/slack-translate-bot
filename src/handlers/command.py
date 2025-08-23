import logging
import time
import asyncio
from typing import Dict, Any
from slack_bolt import Ack, Respond

from ..services.translation import translation_service
from ..utils.cache import cache

logger = logging.getLogger(__name__)

# Statistics storage (in-memory for serverless)
stats: Dict[str, Any] = {
    'total_translations': 0,
    'user_translations': {},
    'start_time': time.time()
}


def extract_plain_text_from_rich_text(rich_text_value):
    """Extract plain text from Slack rich text format"""
    if not rich_text_value or not rich_text_value.get('elements'):
        return ""
    
    text_parts = []
    for element in rich_text_value.get('elements', []):
        if element.get('type') == 'rich_text_section':
            for sub_element in element.get('elements', []):
                if sub_element.get('type') == 'text':
                    text_parts.append(sub_element.get('text', ''))
                elif sub_element.get('type') == 'link':
                    text_parts.append(sub_element.get('url', ''))
    
    return '\n'.join(text_parts).strip()


def handle_translate_command(ack: Ack, client, command: dict):
    ack()
    
    text = command.get('text', '').strip()
    user_id = command.get('user_id')
    trigger_id = command.get('trigger_id')
    
    if not text:
        # Show modal for text input if no text provided
        asyncio.run(show_translation_input_modal(client, trigger_id))
        return
    
    # Show translation result modal directly
    asyncio.run(show_translation_result_modal(client, trigger_id, text, user_id))


async def show_translation_input_modal(client, trigger_id):
    """Show modal for text input when no text is provided"""
    try:
        await client.views_open(
            trigger_id=trigger_id,
            view={
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
                            "type": "rich_text_input",
                            "action_id": "text_input",
                            "focus_on_load": True,
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
        )
    except Exception as e:
        logger.error(f"Error showing input modal: {e}")


async def show_translation_result_modal(client, trigger_id, original_text, user_id):
    """Show modal with original text and translation result"""
    try:
        # Check cache first
        cache_key = f"translate:{hash(original_text)}"
        cached_result = await cache.get(cache_key)
        
        if cached_result:
            logger.info(f"Using cached translation for user {user_id}")
            translated_text = cached_result
        else:
            # Translate
            translated_text = await translation_service.translate(original_text)
            # Cache result
            await cache.set(cache_key, translated_text, ttl=3600)
            
            # Update statistics
            stats['total_translations'] += 1
            if user_id not in stats['user_translations']:
                stats['user_translations'][user_id] = 0
            stats['user_translations'][user_id] += 1
        
        # Detect source language for proper labeling
        source_lang = translation_service.detect_language(original_text)
        if source_lang == 'ko':
            original_label = "한국어"
            translated_label = "English"
        else:
            original_label = "English"
            translated_label = "한국어"
        
        await client.views_open(
            trigger_id=trigger_id,
            view={
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
                            "text": f"*{original_label}*\n```{original_text}```"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{translated_label}*\n```{translated_text}```"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "💡 텍스트를 선택하고 복사해서 사용하세요! 모달은 팝아웃하여 창 크기를 조정할 수 있습니다."
                            }
                        ]
                    }
                ]
            }
        )
        
        logger.info(f"Successfully showed translation modal for user {user_id}")
        
    except Exception as e:
        logger.error(f"Translation modal error: {e}")


def handle_translation_input_modal(ack: Ack, body: dict, client):
    """Handle translation input modal submission"""
    ack()
    
    try:
        # Extract rich text from modal and convert to plain text
        rich_text_input = body['view']['state']['values']['text_input_block']['text_input']['rich_text_value']
        user_id = body['user']['id']
        
        # Convert rich text to plain text
        text_input = extract_plain_text_from_rich_text(rich_text_input)
        
        if not text_input or not text_input.strip():
            return
        
        # Show result modal
        # Since we can't directly open another modal, we need to update the current one
        asyncio.run(show_translation_result_update(client, body['view']['id'], text_input.strip(), user_id))
        
    except Exception as e:
        logger.error(f"Translation input modal error: {e}")


async def show_translation_result_update(client, view_id, original_text, user_id):
    """Update modal to show translation result"""
    try:
        # Translate
        translated_text = await translation_service.translate(original_text)
        
        # Update statistics
        stats['total_translations'] += 1
        if user_id not in stats['user_translations']:
            stats['user_translations'][user_id] = 0
        stats['user_translations'][user_id] += 1
        
        # Detect source language
        source_lang = translation_service.detect_language(original_text)
        if source_lang == 'ko':
            original_label = "한국어"
            translated_label = "English"
        else:
            original_label = "English"
            translated_label = "한국어"
        
        await client.views_update(
            view_id=view_id,
            view={
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
                            "text": f"*{original_label}*\n```{original_text}```"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{translated_label}*\n```{translated_text}```"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "💡 텍스트를 선택하고 복사해서 사용하세요! 모달은 팝아웃하여 창 크기를 조정할 수 있습니다."
                            }
                        ]
                    }
                ]
            }
        )
        
    except Exception as e:
        logger.error(f"Translation result update error: {e}")


def handle_help_command(ack: Ack, respond: Respond, command: dict):
    ack()
    
    help_text = """
🌐 **Translation Bot Help**

**Commands:**
• `/translate [text]` - Translate Korean ↔ English
• `/translate-help` - Show this help
• `/translate-stats` - Show usage statistics

**Other ways to use:**
• Mention `@translate-bot [text]` in channels
• Send direct messages to the bot
• React with 🌐 emoji to any message

**Features:**
• Automatic language detection
• Bidirectional Korean ↔ English translation
• Fast caching for better performance

**Examples:**
• `/translate 안녕하세요!` → Hello!
• `/translate Hello world!` → 안녕하세요 세계!
    """
    
    respond(help_text)


def handle_stats_command(ack: Ack, respond: Respond, command: dict):
    ack()
    
    user_id = command.get('user_id')
    uptime = int(time.time() - stats['start_time'])
    user_count = stats['user_translations'].get(user_id, 0)
    
    stats_text = f"""
📊 **Translation Bot Statistics**

**Total Translations:** {stats['total_translations']}
**Your Translations:** {user_count}
**Active Users:** {len(stats['user_translations'])}
**Uptime:** {uptime//3600}h {(uptime%3600)//60}m {uptime%60}s

*Statistics reset on bot restart*
    """
    
    respond(stats_text)