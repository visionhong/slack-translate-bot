import logging
from slack_bolt.async_app import AsyncApp

from ..services.translation import translation_service
from ..utils.cache import cache
from ..handlers.command import stats

logger = logging.getLogger(__name__)


async def handle_app_mention(event: dict, say, client):
    """Handle @bot mentions"""
    text = event.get('text', '')
    user = event.get('user')
    channel = event.get('channel')
    thread_ts = event.get('ts')
    
    # Extract text after bot mention
    if '<@' in text:
        # Find the bot mention and get text after it
        parts = text.split('>', 1)
        if len(parts) > 1:
            text_to_translate = parts[1].strip()
        else:
            text_to_translate = ''
    else:
        text_to_translate = text.strip()
    
    if not text_to_translate:
        await say(
            text="Please provide text to translate! 📝", 
            thread_ts=thread_ts
        )
        return
    
    try:
        # Check cache
        cache_key = f"translate:{hash(text_to_translate)}"
        cached_result = await cache.get(cache_key)
        
        if cached_result:
            await say(
                text=f"🌐 {cached_result}",
                thread_ts=thread_ts
            )
            return
        
        # Translate
        translated_text = await translation_service.translate(text_to_translate)
        
        # Cache result
        await cache.set(cache_key, translated_text, ttl=3600)
        
        # Update stats
        stats['total_translations'] += 1
        if user not in stats['user_translations']:
            stats['user_translations'][user] = 0
        stats['user_translations'][user] += 1
        
        # Reply in thread
        await say(
            text=f"🌐 {translated_text}",
            thread_ts=thread_ts
        )
        
        logger.info(f"App mention translation completed for user {user}")
        
    except Exception as e:
        logger.error(f"App mention error: {e}")
        await say(
            text="Sorry, translation failed. Please try again. 😔",
            thread_ts=thread_ts
        )


async def handle_direct_message(event: dict, say, client):
    """Handle direct messages to the bot"""
    text = event.get('text', '').strip()
    user = event.get('user')
    
    if not text:
        await say("Please send me text to translate! 📝")
        return
    
    try:
        # Check cache
        cache_key = f"translate:{hash(text)}"
        cached_result = await cache.get(cache_key)
        
        if cached_result:
            await say(f"🌐 {cached_result}")
            return
        
        # Translate
        translated_text = await translation_service.translate(text)
        
        # Cache result
        await cache.set(cache_key, translated_text, ttl=3600)
        
        # Update stats
        stats['total_translations'] += 1
        if user not in stats['user_translations']:
            stats['user_translations'][user] = 0
        stats['user_translations'][user] += 1
        
        await say(f"🌐 {translated_text}")
        logger.info(f"DM translation completed for user {user}")
        
    except Exception as e:
        logger.error(f"DM error: {e}")
        await say("Sorry, translation failed. Please try again. 😔")


async def handle_reaction_added(event: dict, client):
    """Handle emoji reactions (🌐) to messages"""
    if event.get('reaction') != 'globe_with_meridians':
        return
    
    user = event.get('user')
    channel = event.get('item', {}).get('channel')
    timestamp = event.get('item', {}).get('ts')
    
    if not all([user, channel, timestamp]):
        return
    
    try:
        # Get the original message
        result = await client.conversations_history(
            channel=channel,
            latest=timestamp,
            limit=1,
            inclusive=True
        )
        
        if not result['messages']:
            return
        
        message = result['messages'][0]
        text = message.get('text', '').strip()
        
        if not text:
            return
        
        # Check cache
        cache_key = f"translate:{hash(text)}"
        cached_result = await cache.get(cache_key)
        
        if cached_result:
            translated_text = cached_result
        else:
            # Translate
            translated_text = await translation_service.translate(text)
            # Cache result
            await cache.set(cache_key, translated_text, ttl=3600)
        
        # Update stats
        stats['total_translations'] += 1
        if user not in stats['user_translations']:
            stats['user_translations'][user] = 0
        stats['user_translations'][user] += 1
        
        # Post translation as a thread reply
        await client.chat_postMessage(
            channel=channel,
            thread_ts=timestamp,
            text=f"🌐 {translated_text}"
        )
        
        logger.info(f"Reaction translation completed for user {user}")
        
    except Exception as e:
        logger.error(f"Reaction handler error: {e}")