# Slack Translation Bot

Korean ↔ English translation bot for Slack using Azure OpenAI GPT-5-nano model.

## Features

- **Bidirectional Translation**: Korean to English and English to Korean
- **Multiple Interaction Methods**:
  - Direct mentions (`@translate-bot text`)
  - Slash commands (`/translate text`)
  - Direct messages
  - Emoji reactions (🌐)
- **Smart Language Detection**: Automatically detects source language
- **Vercel Deployment**: Serverless deployment support
- **Thread Support**: Responses in threads to maintain context
- **Health Monitoring**: Built-in health checks and statistics

## Vercel Deployment

This bot is configured for deployment on Vercel. See [README-VERCEL.md](README-VERCEL.md) for detailed deployment instructions.

## Quick Setup

1. Deploy to Vercel from GitHub
2. Set environment variables in Vercel dashboard
3. Configure Slack app URLs
4. Test the deployment

## Environment Variables

Required variables:
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`

## Usage

### Slash Commands
- `/translate [text]` - Translate text
- `/translate-help` - Show help
- `/translate-stats` - Show statistics

### Mentions
```
@translate-bot 안녕하세요!
```

### Direct Messages
Send text directly to the bot for translation.

### Emoji Reactions
Add 🌐 emoji to any message to translate it.

## License

MIT License