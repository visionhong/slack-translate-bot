import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

start_time = time.time()


@app.get("/api/health")
async def health_check():
    """Health check endpoint for the translation bot"""
    uptime = int(time.time() - start_time)
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "slack-translation-bot",
            "uptime_seconds": uptime,
            "version": "1.0.0",
            "environment": "production"
        }
    )


# For Vercel
def handler_func(request, context=None):
    return app