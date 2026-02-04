# Invoice Collection Bot

A robust Telegram bot for collecting invoice data through conversation or document upload, with automatic PDF generation.

## Features

- **Multiple Input Types**: Handle text, photos (JPEG/PNG), and documents (PDF, DOCX)
- **Two Input Modes**:
  - **Upload Mode**: Extract data from existing invoices using OCR
  - **Chat Mode**: Step-by-step conversation to collect all invoice details
- **State Management**: Persistent conversation state across multiple user sessions
- **Professional PDF Generation**: Generate formatted invoice PDFs
- **Error Handling**: User-friendly error messages that never leave users hanging
- **Data Validation**: Input validation with helpful error messages

## Quick Start

### 1. Installation

```bash
# Clone or download the bot files
cd invoice_bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Tesseract OCR (required for image processing)
# macOS: brew install tesseract
# Ubuntu/Debian: sudo apt-get install tesseract-ocr
# Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
```

### 2. Configuration

Create a `.env` file in the project root:

```env
BOT_TOKEN=your_telegram_bot_token_here

# Optional: Webhook settings for production
# WEBHOOK_URL=https://yourdomain.com
# WEBHOOK_PORT=8443
# WEBHOOK_PATH=/webhook

# Optional: Admin notifications
# ADMIN_CHAT_ID=your_admin_chat_id

# Optional: Custom paths
# TEMP_DIR=/tmp/invoice_bot
# LOG_LEVEL=INFO
```

Get your bot token from [@BotFather](https://t.me/botfather).

### 3. Run the Bot

```bash
# Development mode (polling)
python bot.py

# Production mode (webhook - requires WEBHOOK_URL in .env)
python webhook_server.py
```

## Conversation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         START (/start)                          │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SELECT MODE                                   │
│         ┌─────────────────┬─────────────────┐                   │
│         │  📄 Upload Doc  │  💬 Chat Input   │                   │
│         └────────┬────────┴────────┬────────┘                   │
└──────────────────┼─────────────────┼────────────────────────────┘
                   │                 │
                   ▼                 ▼
┌──────────────────────┐   ┌──────────────────────────┐
│   UPLOAD_DOCUMENT    │   │   CONTRACTOR_NAME        │
│   (Process file)     │   │   (Step-by-step chat)    │
└──────────┬───────────┘   └────────────┬─────────────┘
           │                            │
           ▼                            ▼
┌──────────────────────┐   ┌──────────────────────────┐
│  CONFIRM_EXTRACTED   │   │   [All contractor fields]│
│  (Review extracted   │   │   [Invoice details]      │
│   data)              │   │   [Work items]           │
└──────────┬───────────┘   │   [Financials]           │
           │               └────────────┬─────────────┘
           │                            │
           └────────────┬───────────────┘
                        │
                        ▼
           ┌────────────────────┐
           │   CONFIRM_SUMMARY  │
           │  (Final review)    │
           └─────────┬──────────┘
                     │
                     ▼
           ┌────────────────────┐
           │ GENERATE_INVOICE   │
           │  (Send PDF)        │
           └────────────────────┘
```

## Data Fields Collected

### Contractor Information
- Name (individual or company)
- Address
- Email
- UTR (Unique Taxpayer Reference)
- NI Number (National Insurance)
- Bank Account Number
- Sort Code
- Cardholder Name

### Invoice Details
- Invoice Number
- Invoice Date
- Work Start Date
- Work End Date

### Work Items (Multiple)
- Property Address
- Plot Number
- Description
- Amount

### Operatives
- Names of workers who performed the work

### Financial Summary
- Subtotal
- VAT Amount
- CIS Deduction
- Total

## Project Structure

```
invoice_bot/
├── bot.py                    # Main bot application
├── config.py                 # Configuration settings
├── invoice_data.py           # Data models
├── document_processor.py     # File processing and OCR
├── invoice_generator.py      # PDF generation
├── message_templates.py      # User-facing messages
├── error_handler.py          # Error handling
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (create this)
├── README.md                 # This file
└── templates/                # HTML templates for invoices
    └── invoice_template.html
```

## API Reference

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Start a new invoice |
| `/cancel` | Cancel current operation |
| `/help` | Show help message |

### Conversation States

| State | Description |
|-------|-------------|
| `SELECT_MODE` | User selects upload or chat mode |
| `UPLOAD_DOCUMENT` | Waiting for file upload |
| `CONFIRM_EXTRACTED` | Review extracted data |
| `CONTRACTOR_NAME` through `CONTRACTOR_CARDHOLDER` | Contractor info collection |
| `INVOICE_NUMBER` through `WORK_END_DATE` | Invoice details |
| `WORK_PROPERTY` through `WORK_AMOUNT` | Work item collection |
| `OPERATIVE_NAMES` | Operative names |
| `SUBTOTAL` through `CIS_AMOUNT` | Financial details |
| `CONFIRM_SUMMARY` | Final confirmation |

## Error Handling

The bot implements comprehensive error handling:

1. **Validation Errors**: Invalid input is caught and user is asked to retry
2. **File Errors**: Corrupted or unsupported files trigger helpful messages
3. **Processing Errors**: OCR failures are handled gracefully
4. **Network Errors**: Connection issues are reported to users
5. **Conversation Errors**: Unexpected errors end the conversation cleanly

All errors are logged and optionally sent to an admin chat.

## Customization

### Message Templates

Edit `message_templates.py` to customize user-facing messages:

```python
class MessageTemplates:
    def welcome_message(self, first_name: str) -> str:
        return f"Your custom welcome message, {first_name}!"
```

### Invoice Template

Modify `templates/invoice_template.html` to change the PDF appearance.

### Data Validation

Add custom validation in the handler methods in `bot.py`:

```python
async def _get_contractor_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if not self._is_valid_email(email):
        await update.message.reply_text("Invalid email format!")
        return CONTRACTOR_EMAIL
    # ...
```

## Deployment

### Using Polling (Development)

```bash
python bot.py
```

### Using Webhooks (Production)

1. Set `WEBHOOK_URL` in your `.env` file
2. Run the webhook server:

```bash
python webhook_server.py
```

Or use a production WSGI server:

```bash
gunicorn webhook_server:app -b 0.0.0.0:8443
```

### Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

## Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=invoice_bot tests/
```

## Troubleshooting

### OCR Not Working

1. Install Tesseract OCR:
   - macOS: `brew install tesseract`
   - Ubuntu: `sudo apt-get install tesseract-ocr`
   - Windows: Download installer

2. Set the path in your code if needed:
   ```python
   pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'
   ```

### PDF Generation Fails

The bot has multiple fallback methods for PDF generation:
1. WeasyPrint (HTML to PDF)
2. ReportLab (native PDF generation)

Install at least one:
```bash
pip install weasyprint  # or
pip install reportlab
```

### Bot Not Responding

1. Check your `BOT_TOKEN` is correct
2. Ensure the bot is running
3. Check logs for errors
4. Verify Telegram API is accessible

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Support

For issues and questions:
- Open an issue on GitHub
- Contact: your-email@example.com
