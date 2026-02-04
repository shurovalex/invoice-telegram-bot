# Invoice Collection Bot - Implementation Summary

## Overview

This is a production-ready Telegram bot for collecting invoice data through two modes:
1. **Upload Mode**: Extract data from existing invoices (PDF, DOCX, images) using OCR
2. **Chat Mode**: Step-by-step conversation to collect all invoice details

## Key Features

- ✅ Multiple input types: text, photos (JPEG/PNG), documents (PDF, DOCX)
- ✅ 27-state conversation flow with persistent state management
- ✅ Document upload and OCR-based data extraction
- ✅ Professional PDF invoice generation
- ✅ Comprehensive error handling - never leaves users hanging
- ✅ User-friendly message templates
- ✅ Webhook and polling deployment options

## File Structure

```
invoice_bot/
├── bot.py                      # Main bot application (600+ lines)
├── config.py                   # Configuration settings
├── invoice_data.py             # Data models (InvoiceData, WorkItem)
├── document_processor.py       # File processing and OCR
├── invoice_generator.py        # PDF generation
├── message_templates.py        # User-facing messages
├── error_handler.py            # Error handling
├── webhook_server.py           # Flask webhook server
├── test_bot.py                 # Unit tests
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
├── README.md                   # Full documentation
├── CONVERSATION_FLOW.md        # State machine documentation
└── IMPLEMENTATION_SUMMARY.md   # This file
```

## Conversation States (27 Total)

### Mode Selection
- `SELECT_MODE` - Choose upload or chat mode

### Upload Mode
- `UPLOAD_DOCUMENT` - Wait for file upload
- `CONFIRM_EXTRACTED` - Review extracted data

### Chat Mode - Contractor Info (8 states)
- `CONTRACTOR_NAME`
- `CONTRACTOR_ADDRESS`
- `CONTRACTOR_EMAIL`
- `CONTRACTOR_UTR`
- `CONTRACTOR_NI`
- `CONTRACTOR_BANK`
- `CONTRACTOR_SORT`
- `CONTRACTOR_CARDHOLDER`

### Chat Mode - Invoice Details (4 states)
- `INVOICE_NUMBER`
- `INVOICE_DATE`
- `WORK_START_DATE`
- `WORK_END_DATE`

### Chat Mode - Work Items (6 states)
- `ADD_WORK_ITEM` - Ask to add work item
- `WORK_PROPERTY`
- `WORK_PLOT`
- `WORK_DESCRIPTION`
- `WORK_AMOUNT`
- `MORE_WORK_ITEMS` - Ask for more work items

### Chat Mode - Financials (4 states)
- `OPERATIVE_NAMES`
- `SUBTOTAL`
- `VAT_AMOUNT`
- `CIS_AMOUNT`

### Final
- `CONFIRM_SUMMARY` - Final review and confirmation

## Data Fields Collected

### Contractor Information
| Field | Required | Validation |
|-------|----------|------------|
| Name | Yes | Non-empty string |
| Address | Yes | Non-empty string |
| Email | Yes | Email format |
| UTR | No | 10 digits |
| NI Number | No | UK NI format |
| Bank Account | No | 8 digits |
| Sort Code | No | XX-XX-XX format |
| Cardholder Name | No | String |

### Invoice Details
| Field | Required | Format |
|-------|----------|--------|
| Invoice Number | Yes | String |
| Invoice Date | Yes | DD/MM/YYYY |
| Work Start Date | Yes | DD/MM/YYYY |
| Work End Date | Yes | DD/MM/YYYY |

### Work Items (Multiple)
| Field | Required |
|-------|----------|
| Property Address | Yes |
| Plot Number | No |
| Description | Yes |
| Amount | Yes | Numeric |

### Financial Summary
| Field | Required | Type |
|-------|----------|------|
| Subtotal | Yes | Float |
| VAT Amount | Yes | Float |
| CIS Deduction | Yes | Float |
| Total | Auto | Float |

## Handler Methods

### Entry Points
- `_start()` - Initialize conversation
- `_help()` - Show help
- `_cancel()` - Cancel conversation

### Mode Selection
- `_select_mode_callback()` - Handle mode selection

### Upload Mode
- `_process_document()` - Download and process file
- `_handle_wrong_upload()` - Handle invalid upload
- `_confirm_extracted_callback()` - Confirm extracted data

### Chat Mode - Contractor Info
- `_get_contractor_name()`
- `_get_contractor_address()`
- `_get_contractor_email()`
- `_get_contractor_utr()`
- `_get_contractor_ni()`
- `_get_contractor_bank()`
- `_get_contractor_sort()`
- `_get_contractor_cardholder()`

### Chat Mode - Invoice Details
- `_get_invoice_number()`
- `_get_invoice_date()`
- `_get_work_start_date()`
- `_get_work_end_date()`

### Chat Mode - Work Items
- `_add_work_item_callback()`
- `_get_work_property()`
- `_get_work_plot()`
- `_get_work_description()`
- `_get_work_amount()`
- `_more_work_items_callback()`

### Chat Mode - Financials
- `_get_operative_names()`
- `_get_subtotal()`
- `_get_vat()`
- `_get_cis()`

### Summary & Generation
- `_confirm_summary_callback()` - Final confirmation
- Invoice generation and PDF delivery

## Error Handling Strategy

### Validation Errors
- Invalid input triggers retry message
- User stays in same state
- Specific guidance provided

### File Processing Errors
- Corrupted/unsupported files handled gracefully
- Option to retry or switch to chat mode
- Detailed error messages

### OCR/Extraction Errors
- Fallback to manual entry
- Clear communication about extraction results

### Network/Server Errors
- User-friendly error messages
- Automatic retry suggestions
- Admin notifications (optional)

### Unexpected Errors
- Conversation ends cleanly
- User can restart with /start
- Error logged for debugging

## Message Templates

All user-facing messages are centralized in `message_templates.py`:

- `welcome_message()` - Welcome with mode selection
- `help_message()` - Command help
- `upload_instructions()` - Upload guidance
- `chat_start()` - Chat mode introduction
- `ask_*()` - 15+ question templates
- `full_summary()` - Final review
- `invoice_generated()` - Success message
- `*_error()` - Error messages

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your BOT_TOKEN

# 3. Run in development mode
python bot.py

# 4. Or run in production mode
python webhook_server.py
```

## Testing

```bash
# Run all tests
pytest test_bot.py -v

# Run specific test class
pytest test_bot.py::TestInvoiceData -v
```

## Deployment Options

### Polling (Development)
```python
application.run_polling()
```

### Webhook (Production)
```python
# Set WEBHOOK_URL in .env
python webhook_server.py
```

### Docker
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

## Dependencies

### Required
- `python-telegram-bot>=20.0` - Core bot framework
- `reportlab>=3.6.0` - PDF generation

### Optional (Enhanced Features)
- `PyPDF2>=3.0.0` - PDF text extraction
- `pdfplumber>=0.9.0` - Advanced PDF processing
- `python-docx>=0.8.11` - DOCX processing
- `pytesseract>=0.3.10` - OCR for images
- `weasyprint>=59.0` - HTML to PDF conversion

## Security Considerations

1. **Bot Token**: Store in environment variables, never commit to git
2. **File Uploads**: Validate file types and sizes
3. **User Data**: Clear on conversation end or cancel
4. **Temp Files**: Clean up after processing
5. **Error Messages**: Don't expose internal details

## Customization Points

1. **Message Templates**: Edit `message_templates.py`
2. **Invoice Template**: Modify HTML in `invoice_generator.py`
3. **Validation Rules**: Add to handler methods in `bot.py`
4. **Data Fields**: Extend `InvoiceData` model
5. **PDF Styling**: Customize ReportLab or HTML templates

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot not responding | Check BOT_TOKEN |
| OCR not working | Install Tesseract |
| PDF generation fails | Install ReportLab or WeasyPrint |
| Webhook errors | Check WEBHOOK_URL and SSL |
| File too large | Adjust MAX_FILE_SIZE_MB |

## License

MIT License - See README.md for details.
