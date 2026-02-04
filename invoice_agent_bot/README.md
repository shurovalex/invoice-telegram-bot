# Invoice Agent Bot

A conversational AI-powered Telegram bot for creating professional invoices from documents or natural conversation.

## Features

- **Multi-Format Document Processing**: Extract invoice data from PDF, JPEG, PNG, and DOCX files
- **AI-Powered Extraction**: Uses OpenAI GPT-4o/GPT-4o-mini with Gemini fallback
- **Natural Conversation Flow**: Create invoices by simply chatting with the bot
- **Multiple Output Formats**: Generate invoices as PDF, HTML, or DOCX
- **Self-Healing Error Handling**: Automatic retries with exponential backoff
- **State Management**: Persistent conversation state for each user
- **Data Validation**: Pydantic models ensure data integrity
- **Type Safety**: Full type hints throughout the codebase

## Project Structure

```
invoice_agent_bot/
├── bot.py                    # Main entry point
├── requirements.txt          # Python dependencies
├── .env.example             # Environment configuration template
├── README.md                # This file
├── src/
│   ├── __init__.py
│   ├── core/                # Core modules
│   │   ├── config.py        # Configuration management (Pydantic Settings)
│   │   └── state.py         # Conversation state machine
│   ├── models/              # Data models
│   │   └── invoice.py       # Invoice, Customer, Item models (Pydantic)
│   ├── services/            # Business logic services
│   │   ├── ai_client.py     # AI client with fallback (OpenAI/Gemini)
│   │   ├── document_processor.py  # PDF/Image/DOCX processing
│   │   └── invoice_generator.py   # HTML/PDF/DOCX generation
│   ├── utils/               # Utilities
│   │   ├── logger.py        # Structured logging
│   │   ├── error_recovery.py # Retry logic, circuit breaker
│   │   └── storage.py       # SQLite persistence
│   └── bot/                 # Telegram bot handlers
│       └── handlers.py      # Message/command handlers
├── data/                    # Data storage (created at runtime)
│   ├── invoices/           # Generated invoices
│   ├── uploads/            # Temporary uploads
│   ├── logs/               # Log files
│   └── invoice_bot.db      # SQLite database
├── tests/                   # Test files
└── docs/                    # Documentation
```

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd invoice_agent_bot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use VS Code: code .env
```

Required environment variables:

```env
# Telegram Bot Token (get from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# OpenAI API Key
OPENAI_API_KEY=sk-your_openai_key_here

# Optional: Google Gemini API Key (fallback)
GEMINI_API_KEY=your_gemini_key_here
```

### 3. Run the Bot

```bash
python bot.py
```

## Configuration

All configuration is managed through environment variables in the `.env` file:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | Bot token from @BotFather |
| `OPENAI_API_KEY` | Yes* | - | OpenAI API key |
| `GEMINI_API_KEY` | No | - | Gemini API key (fallback) |
| `AI_PROVIDER_PRIORITY` | No | `openai,gemini` | Provider fallback order |
| `MAX_FILE_SIZE_MB` | No | `20` | Max upload size |
| `DEFAULT_CURRENCY` | No | `USD` | Default invoice currency |
| `COMPANY_NAME` | No | `Your Company` | Your company name |
| `CONVERSATION_TIMEOUT_MINUTES` | No | `30` | Session timeout |
| `DEBUG_MODE` | No | `false` | Enable debug logging |
| `TEST_MODE` | No | `false` | Use mock AI responses |

*At least one AI provider key is required

## Usage

### Creating an Invoice from Conversation

1. Start the bot with `/start`
2. Click "Create Invoice" or use `/new`
3. Answer the bot's questions:
   - Customer name
   - Items (format: `Description | Qty | Price`)
   - Notes (optional)
4. Choose output format (PDF, HTML, DOCX)
5. Receive your invoice!

### Creating an Invoice from Document

1. Upload a PDF, image, or DOCX file containing invoice information
2. The bot extracts data using AI
3. Review and confirm the extracted data
4. Choose output format
5. Receive your invoice!

### Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and show main menu |
| `/new` | Create a new invoice |
| `/status` | Check current conversation status |
| `/cancel` | Cancel current operation |
| `/help` | Show help message |

## Development

### VS Code Setup

1. Open the project in VS Code
2. Install recommended extensions:
   - Python (Microsoft)
   - Pylance
   - Python Type Hint
   - autoDocstring

3. Configure Python interpreter to use the virtual environment

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Run with coverage
pytest --cov=src tests/
```

### Code Quality

```bash
# Format code with Black
black src/ bot.py

# Lint with Ruff
ruff check src/ bot.py

# Type check with mypy
mypy src/ bot.py
```

## Architecture

### State Machine

The bot uses a conversation state machine to manage user interactions:

```
IDLE → AWAITING_DOCUMENT → PROCESSING_DOCUMENT → CONFIRMING_EXTRACTED_DATA → REVIEWING → GENERATING → COMPLETED
  ↓
COLLECTING_CUSTOMER → COLLECTING_ITEMS → COLLECTING_DATES → COLLECTING_NOTES → REVIEWING → GENERATING → COMPLETED
```

### AI Client with Fallback

The AI client supports multiple providers with automatic fallback:

1. Try primary provider (OpenAI by default)
2. If fails, retry with exponential backoff
3. If still fails, try fallback provider (Gemini)
4. Return error if all providers fail

### Document Processing Pipeline

```
Upload → Save → Detect Format → Extract Text (OCR if needed) → AI Extraction → Validation → Invoice Data
```

### Error Recovery

- **Retry with Exponential Backoff**: Failed operations retry 3 times
- **Circuit Breaker**: Prevents cascade failures
- **Graceful Degradation**: Falls back to alternative methods

## Troubleshooting

### Common Issues

**Bot doesn't respond:**
- Check `TELEGRAM_BOT_TOKEN` is correct
- Ensure bot is started with `python bot.py`
- Check logs in `data/logs/bot.log`

**AI not working:**
- Verify `OPENAI_API_KEY` or `GEMINI_API_KEY` is set
- Check API key has available credits
- Enable `DEBUG_MODE=true` for detailed logs

**Document processing fails:**
- Check file size is under `MAX_FILE_SIZE_MB`
- Ensure file format is supported
- Install system dependencies (see below)

### System Dependencies

For PDF and image processing, you may need:

**Ubuntu/Debian:**
```bash
sudo apt-get install poppler-utils tesseract-ocr
```

**macOS:**
```bash
brew install poppler tesseract
```

**Windows:**
- Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
- Add to PATH

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see LICENSE file for details

## Support

For issues and feature requests, please use the GitHub issue tracker.

---

Built with ❤️ using Python, python-telegram-bot, and AI
