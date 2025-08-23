import logging
from slack_bolt.async_app import AsyncApp

from .config import settings
from .handlers.command import handle_translate_command, handle_help_command, handle_stats_command
from .handlers.events import handle_app_mention, handle_direct_message, handle_reaction_added

logger = logging.getLogger(__name__)


def create_slack_app() -> AsyncApp:
    """Create and configure Slack app"""
    app = AsyncApp(
        token=settings.slack.bot_token,
        signing_secret=settings.slack.signing_secret
    )
    
    # Register slash commands
    app.command("/translate")(handle_translate_command)
    app.command("/translate-help")(handle_help_command) 
    app.command("/translate-stats")(handle_stats_command)
    
    # Register event handlers
    app.event("app_mention")(handle_app_mention)
    app.event("message")(handle_direct_message)
    app.event("reaction_added")(handle_reaction_added)
    
    return app


async def start():
    """Start the bot (simplified for Vercel)"""
    logger.info("Bot initialized for Vercel serverless deployment")
    return create_slack_app()