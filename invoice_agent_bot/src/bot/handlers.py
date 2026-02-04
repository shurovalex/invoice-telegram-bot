"""
Bot Handlers Module

Telegram bot message handlers for the invoice agent.
Handles all user interactions and coordinates with other services.
"""

import os
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from src.core.config import get_settings
from src.core.state import (
    ConversationState,
    ConversationContext,
    get_conversation_manager,
)
from src.models.invoice import InvoiceData, CustomerInfo, InvoiceItem, OutputFormat
from src.services.ai_client import get_ai_manager
from src.services.document_processor import get_document_processor
from src.services.invoice_generator import get_invoice_generator
from src.utils.storage import get_storage
from src.utils.logger import get_logger
from src.utils.error_recovery import ProcessingError

logger = get_logger(__name__)
settings = get_settings()


# ============================================================================
# Helper Functions
# ============================================================================

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Get the main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📄 Create Invoice", callback_data="create_invoice"),
            InlineKeyboardButton("📤 Upload Document", callback_data="upload_document"),
        ],
        [
            InlineKeyboardButton("📋 My Invoices", callback_data="list_invoices"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_format_keyboard() -> InlineKeyboardMarkup:
    """Get output format selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📄 PDF", callback_data="format_pdf"),
            InlineKeyboardButton("🌐 HTML", callback_data="format_html"),
        ],
        [
            InlineKeyboardButton("📝 DOCX", callback_data="format_docx"),
            InlineKeyboardButton("✅ All Formats", callback_data="format_all"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message with main menu."""
    welcome_text = (
        "👋 Welcome to the *Invoice Agent Bot*!\n\n"
        "I can help you create professional invoices from:\n"
        "• Conversations - Just tell me the details\n"
        "• Documents - Upload PDF, images, or Word files\n\n"
        "What would you like to do?"
    )
    
    await update.effective_message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


# ============================================================================
# Command Handlers
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")
    
    # Reset any existing conversation
    manager = get_conversation_manager()
    await manager.reset_conversation(user.id, update.effective_chat.id)
    
    await send_welcome_message(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "📚 *Invoice Agent Bot - Help*\n\n"
        "*Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/cancel - Cancel current operation\n"
        "/new - Create a new invoice\n"
        "/status - Check conversation status\n\n"
        
        "*How to use:*\n"
        "1. *Create from conversation:*\n"
        "   Click 'Create Invoice' and answer my questions\n\n"
        "2. *Create from document:*\n"
        "   Upload a PDF, image, or Word document\n\n"
        "3. *Download invoices:*\n"
        "   Click 'My Invoices' to see your history\n\n"
        "*Supported formats:* PDF, JPEG, PNG, DOCX"
    )
    
    await update.effective_message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel command."""
    user = update.effective_user
    manager = get_conversation_manager()
    
    # End current conversation
    await manager.end_conversation(user.id, update.effective_chat.id)
    
    await update.effective_message.reply_text(
        "❌ Current operation cancelled. What would you like to do?",
        reply_markup=get_main_keyboard(),
    )
    
    return ConversationHandler.END


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new command to start new invoice."""
    user = update.effective_user
    manager = get_conversation_manager()
    
    # Start new conversation
    ctx = await manager.reset_conversation(user.id, update.effective_chat.id)
    ctx.transition_to(ConversationState.COLLECTING_CUSTOMER)
    
    await update.effective_message.reply_text(
        "📝 Let's create a new invoice!\n\n"
        "First, please provide the *customer name*:",
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    user = update.effective_user
    manager = get_conversation_manager()
    
    ctx = await manager.get(user.id, update.effective_chat.id)
    
    if ctx and ctx.state != ConversationState.IDLE:
        status_text = (
            f"📊 *Current Status*\n\n"
            f"State: `{ctx.state.name}`\n"
            f"Started: {ctx.started_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"Last Activity: {ctx.last_activity.strftime('%Y-%m-%d %H:%M')}\n"
        )
        
        if ctx.invoice_data and ctx.invoice_data.customer:
            status_text += f"\nCustomer: {ctx.invoice_data.customer.name}"
        
        await update.effective_message.reply_text(
            status_text,
            parse_mode="Markdown",
        )
    else:
        await update.effective_message.reply_text(
            "No active conversation. Start with /new or use the menu below:",
            reply_markup=get_main_keyboard(),
        )


# ============================================================================
# Callback Query Handlers
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    manager = get_conversation_manager()
    data = query.data
    
    logger.info(f"User {user.id} clicked: {data}")
    
    if data == "create_invoice":
        ctx = await manager.reset_conversation(user.id, update.effective_chat.id)
        ctx.transition_to(ConversationState.COLLECTING_CUSTOMER)
        
        await query.edit_message_text(
            "📝 *Create New Invoice*\n\n"
            "Please provide the *customer name*:",
            parse_mode="Markdown",
        )
    
    elif data == "upload_document":
        ctx = await manager.reset_conversation(user.id, update.effective_chat.id)
        ctx.transition_to(ConversationState.AWAITING_DOCUMENT)
        
        await query.edit_message_text(
            "📤 *Upload Document*\n\n"
            "Please upload a document (PDF, JPEG, PNG, or DOCX) "
            "containing invoice information.",
            parse_mode="Markdown",
        )
    
    elif data == "list_invoices":
        await handle_list_invoices(update, context)
    
    elif data == "help":
        await help_command(update, context)
    
    elif data.startswith("format_"):
        await handle_format_selection(update, context, data.replace("format_", ""))
    
    elif data == "confirm_data":
        await handle_confirm_data(update, context)
    
    elif data == "edit_data":
        await handle_edit_data(update, context)
    
    elif data == "add_item":
        await handle_add_item(update, context)
    
    elif data == "finish_items":
        await handle_finish_items(update, context)


# ============================================================================
# Document Handler
# ============================================================================

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document uploads."""
    user = update.effective_user
    chat = update.effective_chat
    document = update.message.document
    
    logger.info(f"User {user.id} uploaded: {document.file_name}")
    
    # Check file size
    if document.file_size > settings.max_file_size_bytes:
        await update.message.reply_text(
            f"❌ File too large! Maximum size is {settings.max_file_size_mb}MB.",
            reply_markup=get_main_keyboard(),
        )
        return
    
    # Check file extension
    file_ext = Path(document.file_name).suffix.lower().lstrip(".")
    if file_ext not in settings.supported_formats:
        await update.message.reply_text(
            f"❌ Unsupported file format: {file_ext}\n"
            f"Supported formats: {', '.join(settings.supported_formats)}",
            reply_markup=get_main_keyboard(),
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "⏳ Processing your document... Please wait."
    )
    
    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        
        # Save to storage
        processor = get_document_processor()
        file_path = await processor.save_upload(
            bytes(file_bytes),
            document.file_name,
            user.id
        )
        
        # Process document
        processed = await processor.process_file(file_path)
        
        # Extract invoice data using AI
        ai_manager = await get_ai_manager()
        extracted = await ai_manager.extract_invoice_data(processed.extracted_text)
        
        # Update conversation
        manager = get_conversation_manager()
        ctx = await manager.get_or_create(user.id, chat.id)
        ctx.transition_to(ConversationState.CONFIRMING_EXTRACTED_DATA)
        ctx.extracted_data = extracted
        ctx.uploaded_document = {
            "file_id": document.file_id,
            "file_name": document.file_name,
            "local_path": str(file_path),
        }
        
        # Build invoice from extracted data
        ctx.invoice_data = InvoiceData.from_dict(extracted)
        
        # Show extracted data for confirmation
        await processing_msg.delete()
        await show_extracted_data(update, context, ctx)
        
    except ProcessingError as e:
        await processing_msg.edit_text(
            f"❌ Processing failed: {e.message}\n\n"
            "Please try again or create the invoice manually.",
            reply_markup=get_main_keyboard(),
        )
    except Exception as e:
        logger.error(f"Document processing error: {e}")
        await processing_msg.edit_text(
            "❌ An error occurred while processing your document.\n"
            "Please try again or use /cancel to start over.",
            reply_markup=get_main_keyboard(),
        )


async def show_extracted_data(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    ctx: ConversationContext
) -> None:
    """Show extracted data for user confirmation."""
    invoice = ctx.invoice_data
    
    text = (
        "📋 *Extracted Invoice Data*\n\n"
        f"*Customer:* {invoice.customer.name}\n"
    )
    
    if invoice.customer.email:
        text += f"*Email:* {invoice.customer.email}\n"
    if invoice.customer.phone:
        text += f"*Phone:* {invoice.customer.phone}\n"
    
    text += f"\n*Items:*\n"
    for i, item in enumerate(invoice.items, 1):
        text += f"{i}. {item.description} - {item.quantity} x {item.unit_price}\n"
    
    if invoice.notes:
        text += f"\n*Notes:* {invoice.notes}\n"
    
    text += "\nIs this information correct?"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, looks good", callback_data="confirm_data"),
            InlineKeyboardButton("✏️ No, let me edit", callback_data="edit_data"),
        ],
    ])
    
    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ============================================================================
# Message Handlers
# ============================================================================

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages based on conversation state."""
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text
    
    manager = get_conversation_manager()
    ctx = await manager.get(user.id, chat.id)
    
    if not ctx or ctx.state == ConversationState.IDLE:
        # No active conversation - show menu
        await update.message.reply_text(
            "I'm not sure what you'd like to do. Please choose an option:",
            reply_markup=get_main_keyboard(),
        )
        return
    
    # Handle based on state
    if ctx.state == ConversationState.COLLECTING_CUSTOMER:
        await handle_customer_input(update, context, ctx, text)
    elif ctx.state == ConversationState.COLLECTING_ITEMS:
        await handle_item_input(update, context, ctx, text)
    elif ctx.state == ConversationState.COLLECTING_DATES:
        await handle_date_input(update, context, ctx, text)
    elif ctx.state == ConversationState.COLLECTING_NOTES:
        await handle_notes_input(update, context, ctx, text)
    elif ctx.state == ConversationState.REVIEWING:
        await handle_review_input(update, context, ctx, text)
    else:
        await update.message.reply_text(
            "I'm waiting for something else. Use /cancel to start over.",
            reply_markup=get_main_keyboard(),
        )


async def handle_customer_input(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    ctx: ConversationContext,
    text: str
) -> None:
    """Handle customer name input."""
    ctx.invoice_data.customer = CustomerInfo(name=text)
    ctx.transition_to(ConversationState.COLLECTING_ITEMS)
    
    await update.message.reply_text(
        f"✅ Customer: *{text}*\n\n"
        "Now let's add items to the invoice.\n\n"
        "Send me item details in this format:\n"
        "`Description | Quantity | Unit Price`\n\n"
        "Example: `Consulting Services | 5 | 100`\n\n"
        "Or click 'Finish' when done:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Finish Adding Items", callback_data="finish_items"),
        ]]),
    )


async def handle_item_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: ConversationContext,
    text: str,
) -> None:
    """Handle item input."""
    try:
        # Parse item format: Description | Qty | Price
        parts = [p.strip() for p in text.split("|")]
        
        if len(parts) >= 3:
            description = parts[0]
            quantity = float(parts[1])
            unit_price = float(parts[2])
            
            item = InvoiceItem(
                description=description,
                quantity=quantity,
                unit_price=unit_price,
            )
            
            ctx.invoice_data.add_item(item)
            
            await update.message.reply_text(
                f"✅ Added: {description} - {quantity} x ${unit_price:.2f}\n\n"
                f"Current total: ${ctx.invoice_data.total:.2f}\n\n"
                "Add another item or click 'Finish':",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Finish", callback_data="finish_items"),
                ]]),
            )
        else:
            raise ValueError("Invalid format")
            
    except Exception:
        await update.message.reply_text(
            "❌ Invalid format. Please use:\n"
            "`Description | Quantity | Unit Price`\n\n"
            "Example: `Consulting Services | 5 | 100`",
            parse_mode="Markdown",
        )


async def handle_finish_items(
    update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle finish items button."""
    user = update.effective_user
    chat = update.effective_chat
    
    manager = get_conversation_manager()
    ctx = await manager.get(user.id, chat.id)
    
    if not ctx.invoice_data.items:
        await update.effective_message.reply_text(
            "❌ Please add at least one item before finishing.",
        )
        return
    
    ctx.transition_to(ConversationState.COLLECTING_NOTES)
    
    await update.effective_message.reply_text(
        "✅ Items added!\n\n"
        "Would you like to add any notes or terms?\n"
        "(Send text or type 'skip' to continue):"
    )


async def handle_notes_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: ConversationContext,
    text: str,
) -> None:
    """Handle notes input."""
    if text.lower() != "skip":
        ctx.invoice_data.notes = text
    
    ctx.transition_to(ConversationState.REVIEWING)
    
    # Show invoice summary
    await show_invoice_summary(update, context, ctx)


async def show_invoice_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: ConversationContext,
) -> None:
    """Show invoice summary for review."""
    invoice = ctx.invoice_data
    
    summary = (
        "📋 *Invoice Summary*\n\n"
        f"*Customer:* {invoice.customer.name}\n"
        f"*Items:* {len(invoice.items)}\n"
        f"*Total:* ${invoice.total:.2f}\n\n"
        "Choose output format:"
    )
    
    await update.effective_message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=get_format_keyboard(),
    )


async def handle_format_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    format_choice: str,
) -> None:
    """Handle output format selection."""
    user = update.effective_user
    chat = update.effective_chat
    
    manager = get_conversation_manager()
    ctx = await manager.get(user.id, chat.id)
    
    if not ctx or not ctx.invoice_data:
        await update.effective_message.reply_text(
            "❌ No invoice data found. Please start over with /new",
            reply_markup=get_main_keyboard(),
        )
        return
    
    # Generate invoice number
    storage = await get_storage()
    invoice_number = await storage.invoices.get_next_invoice_number(
        settings.invoice_prefix
    )
    ctx.invoice_data.invoice_number = invoice_number
    
    # Determine formats to generate
    formats_to_generate = []
    if format_choice == "pdf":
        formats_to_generate = [OutputFormat.PDF]
    elif format_choice == "html":
        formats_to_generate = [OutputFormat.HTML]
    elif format_choice == "docx":
        formats_to_generate = [OutputFormat.DOCX]
    else:  # all
        formats_to_generate = [OutputFormat.PDF, OutputFormat.HTML]
    
    # Send generating message
    generating_msg = await update.effective_message.reply_text(
        "⏳ Generating your invoice... Please wait."
    )
    
    try:
        # Generate invoices
        generator = get_invoice_generator()
        results = await generator.generate_multiple(
            ctx.invoice_data,
            formats_to_generate,
        )
        
        # Save to database
        ctx.invoice_data.user_id = user.id
        ctx.invoice_data.chat_id = chat.id
        await storage.invoices.create(ctx.invoice_data)
        
        # Send files
        await generating_msg.delete()
        
        for result in results:
            with open(result.file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat.id,
                    document=f,
                    filename=result.file_path.name,
                    caption=f"📄 Invoice {invoice_number}",
                )
        
        # Complete conversation
        ctx.transition_to(ConversationState.COMPLETED)
        await manager.end_conversation(user.id, chat.id)
        
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"✅ Invoice *{invoice_number}* created successfully!\n\n"
                 "What would you like to do next?",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        
    except Exception as e:
        logger.error(f"Invoice generation failed: {e}")
        await generating_msg.edit_text(
            "❌ Failed to generate invoice. Please try again.",
            reply_markup=get_main_keyboard(),
        )


# ============================================================================
# Additional Handlers
# ============================================================================

async def handle_list_invoices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle list invoices request."""
    user = update.effective_user
    
    try:
        storage = await get_storage()
        invoices = await storage.invoices.list_by_user(user.id, limit=10)
        
        if not invoices:
            await update.effective_message.reply_text(
                "📭 You don't have any invoices yet.\n\n"
                "Create your first invoice with /new",
                reply_markup=get_main_keyboard(),
            )
            return
        
        text = "📋 *Your Recent Invoices*\n\n"
        for inv in invoices:
            status_emoji = {
                "draft": "📝",
                "sent": "📤",
                "paid": "✅",
                "overdue": "⚠️",
            }.get(inv.status.value, "📄")
            
            text += (
                f"{status_emoji} *{inv.invoice_number or 'Draft'}*\n"
                f"   Customer: {inv.customer.name}\n"
                f"   Total: ${inv.total:.2f}\n"
                f"   Status: {inv.status.value.title()}\n\n"
            )
        
        await update.effective_message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        
    except Exception as e:
        logger.error(f"Failed to list invoices: {e}")
        await update.effective_message.reply_text(
            "❌ Failed to retrieve your invoices. Please try again.",
            reply_markup=get_main_keyboard(),
        )


async def handle_confirm_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user confirming extracted data."""
    user = update.effective_user
    chat = update.effective_chat
    
    manager = get_conversation_manager()
    ctx = await manager.get(user.id, chat.id)
    
    ctx.transition_to(ConversationState.REVIEWING)
    await show_invoice_summary(update, context, ctx)


async def handle_edit_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user wanting to edit extracted data."""
    user = update.effective_user
    chat = update.effective_chat
    
    manager = get_conversation_manager()
    ctx = await manager.get(user.id, chat.id)
    
    ctx.transition_to(ConversationState.COLLECTING_CUSTOMER)
    
    await update.effective_message.reply_text(
        "✏️ Let's edit the invoice data.\n\n"
        "Please provide the *customer name*:",
        parse_mode="Markdown",
    )


async def handle_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle add item button."""
    await update.effective_message.reply_text(
        "Send me item details in this format:\n"
        "`Description | Quantity | Unit Price`\n\n"
        "Example: `Consulting Services | 5 | 100`",
        parse_mode="Markdown",
    )


# ============================================================================
# Error Handler
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Update {update} caused error: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ An unexpected error occurred. Please try again or use /cancel to start over.",
            reply_markup=get_main_keyboard(),
        )
