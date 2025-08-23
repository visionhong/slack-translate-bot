import logging
import time
from typing import Dict, Any
from slack_bolt.async_app import AsyncApp
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


async def handle_translate_command(ack: Ack, respond: Respond, command: dict):
    await ack()
    
    text = command.get('text', '').strip()
    user_id = command.get('user_id')
    
    if not text:
        await respond("Please provide text to translate. Usage: `/translate [text]`")
        return
    
    try:
        # Check cache first
        cache_key = f"translate:{hash(text)}"
        cached_result = await cache.get(cache_key)
        
        if cached_result:
            logger.info(f"Using cached translation for user {user_id}")
            await respond(f"🌐 {cached_result}")
            return
        
        # Translate
        translated_text = await translation_service.translate(text)
        
        # Cache result
        await cache.set(cache_key, translated_text, ttl=3600)
        
        # Update statistics
        stats['total_translations'] += 1
        if user_id not in stats['user_translations']:
            stats['user_translations'][user_id] = 0
        stats['user_translations'][user_id] += 1
        
        # Respond
        await respond(f"🌐 {translated_text}")
        logger.info(f"Successfully translated text for user {user_id}")
        
    except Exception as e:
        logger.error(f"Translation command error: {e}")
        await respond("Sorry, translation failed. Please try again.")


async def handle_help_command(ack: Ack, respond: Respond, command: dict):
    await ack()
    
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
    
    await respond(help_text)


async def handle_stats_command(ack: Ack, respond: Respond, command: dict):
    await ack()
    
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
    
    await respond(stats_text)