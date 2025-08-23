import os
import sys
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.bot import create_slack_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI()

# Create Slack app and handler
slack_app = create_slack_app()
handler = AsyncSlackRequestHandler(slack_app)


@app.post("/api/slack/events")
async def slack_events(request: Request):
    """Handle Slack events, commands, and interactions"""
    try:
        return await handler.handle(request)
    except Exception as e:
        logger.error(f"Slack handler error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )


@app.get("/api/slack/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "slack-translate-bot"}


# For Vercel, we need to export the FastAPI app as 'app'
# This is the handler that Vercel will call
def handler_func(request, context=None):
    return app