#!/usr/bin/env python3
"""
Invoice Collection Agent Bot
A robust Telegram bot for collecting invoice data through conversation or document upload.
"""

import logging
import os
import tempfile
from datetime import datetime
from typing import Dict, Optional

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import Config
from invoice_data import InvoiceData, WorkItem
from document_processor import DocumentProcessor
from invoice_generator import InvoiceGenerator
from message_templates import MessageTemplates
from error_handler import ErrorHandler

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation States
(
    SELECT_MODE,          # User selects upload or chat mode
    # Upload mode states
    UPLOAD_DOCUMENT,      # Waiting for document upload
    CONFIRM_EXTRACTED,    # Confirm extracted data
    # Chat mode states - Contractor info
    CONTRACTOR_NAME,      # Contractor name
    CONTRACTOR_ADDRESS,   # Contractor address
    CONTRACTOR_EMAIL,     # Contractor email
    CONTRACTOR_UTR,       # Contractor UTR
    CONTRACTOR_NI,        # Contractor NI number
    CONTRACTOR_BANK,      # Bank account
    CONTRACTOR_SORT,      # Sort code
    CONTRACTOR_CARDHOLDER,# Cardholder name
    # Invoice details
    INVOICE_NUMBER,       # Invoice number
    INVOICE_DATE,         # Invoice date
    WORK_START_DATE,      # Work start date
    WORK_END_DATE,        # Work end date
    # Work items
    ADD_WORK_ITEM,        # Ask if add work item
    WORK_PROPERTY,        # Property address
    WORK_PLOT,            # Plot number
    WORK_DESCRIPTION,     # Work description
    WORK_AMOUNT,          # Work amount
    MORE_WORK_ITEMS,      # Ask for more work items
    # Operatives
    OPERATIVE_NAMES,      # Operative names
    # Financials
    SUBTOTAL,             # Subtotal
    VAT_AMOUNT,           # VAT amount
    CIS_AMOUNT,           # CIS deduction
    # Summary
    CONFIRM_SUMMARY,      # Confirm all data
    # Final
    GENERATE_INVOICE,     # Generate invoice
) = range(28)


class InvoiceBot:
    """Main bot class handling all conversations and file processing."""
    
    def __init__(self):
        self.config = Config()
        self.doc_processor = DocumentProcessor()
        self.invoice_generator = InvoiceGenerator()
        self.templates = MessageTemplates()
        self.error_handler = ErrorHandler()
        
    def get_application(self) -> Application:
        """Build and return the application with all handlers."""
        application = Application.builder().token(self.config.BOT_TOKEN).build()
        
        # Add conversation handler
        conv_handler = self._build_conversation_handler()
        application.add_handler(conv_handler)
        
        # Add error handler
        application.add_error_handler(self._error_handler)
        
        return application
    
    def _build_conversation_handler(self) -> ConversationHandler:
        """Build the main conversation handler with all states."""
        return ConversationHandler(
            entry_points=[CommandHandler("start", self._start)],
            states={
                # Mode selection
                SELECT_MODE: [
                    CallbackQueryHandler(self._select_mode_callback, pattern="^(upload|chat)$"),
                ],
                
                # Upload mode
                UPLOAD_DOCUMENT: [
                    MessageHandler(filters.Document.ALL | filters.PHOTO, self._process_document),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_wrong_upload),
                ],
                CONFIRM_EXTRACTED: [
                    CallbackQueryHandler(self._confirm_extracted_callback, pattern="^(confirm_data|manual_entry|retry_upload)$"),
                ],
                
                # Chat mode - Contractor info
                CONTRACTOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_name)],
                CONTRACTOR_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_address)],
                CONTRACTOR_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_email)],
                CONTRACTOR_UTR: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_utr)],
                CONTRACTOR_NI: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_ni)],
                CONTRACTOR_BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_bank)],
                CONTRACTOR_SORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_sort)],
                CONTRACTOR_CARDHOLDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_contractor_cardholder)],
                
                # Invoice details
                INVOICE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_invoice_number)],
                INVOICE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_invoice_date)],
                WORK_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_work_start_date)],
                WORK_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_work_end_date)],
                
                # Work items
                ADD_WORK_ITEM: [
                    CallbackQueryHandler(self._add_work_item_callback, pattern="^(add_work|skip_work)$"),
                ],
                WORK_PROPERTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_work_property)],
                WORK_PLOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_work_plot)],
                WORK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_work_description)],
                WORK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_work_amount)],
                MORE_WORK_ITEMS: [
                    CallbackQueryHandler(self._more_work_items_callback, pattern="^(more_work|done_work)$"),
                ],
                
                # Operatives
                OPERATIVE_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_operative_names)],
                
                # Financials
                SUBTOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_subtotal)],
                VAT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_vat)],
                CIS_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_cis)],
                
                # Summary
                CONFIRM_SUMMARY: [
                    CallbackQueryHandler(self._confirm_summary_callback, pattern="^(confirm_all|edit_data|cancel_all)$"),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self._cancel),
                CommandHandler("start", self._start),
                CommandHandler("help", self._help),
            ],
            name="invoice_conversation",
            persistent=True,
        )
    
    # ============ ENTRY POINT ============
    
    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the conversation and present mode selection."""
        user = update.effective_user
        logger.info(f"User {user.id} ({user.username}) started the bot")
        
        # Initialize user data storage
        context.user_data["invoice"] = InvoiceData()
        context.user_data["user_id"] = user.id
        
        # Send welcome message with mode selection
        keyboard = [
            [InlineKeyboardButton("📄 Upload Document", callback_data="upload")],
            [InlineKeyboardButton("💬 Chat to Provide Details", callback_data="chat")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            self.templates.welcome_message(user.first_name),
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return SELECT_MODE
    
    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send help message."""
        await update.message.reply_text(
            self.templates.help_message(),
            parse_mode="Markdown",
        )
    
    async def _cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text(
            self.templates.cancel_message(),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown",
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    # ============ MODE SELECTION ============
    
    async def _select_mode_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle mode selection callback."""
        query = update.callback_query
        await query.answer()
        
        mode = query.data
        context.user_data["mode"] = mode
        
        if mode == "upload":
            await query.edit_message_text(
                self.templates.upload_instructions(),
                parse_mode="Markdown",
            )
            return UPLOAD_DOCUMENT
        else:  # chat mode
            await query.edit_message_text(
                self.templates.chat_start(),
                parse_mode="Markdown",
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=self.templates.ask_contractor_name(),
            )
            return CONTRACTOR_NAME
    
    # ============ UPLOAD MODE HANDLERS ============
    
    async def _process_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process uploaded document (PDF, DOCX, or photo)."""
        processing_msg = None
        try:
            # Send processing message
            processing_msg = await update.message.reply_text(
                "⏳ Processing your document... Please wait.",
            )
            
            # Determine file type and get file
            if update.message.document:
                file = await update.message.document.get_file()
                file_name = update.message.document.file_name
                mime_type = update.message.document.mime_type
            elif update.message.photo:
                # Get largest photo
                photo = update.message.photo[-1]
                file = await photo.get_file()
                file_name = f"photo_{photo.file_id}.jpg"
                mime_type = "image/jpeg"
            else:
                await update.message.reply_text(
                    "❌ Unsupported file type. Please upload a PDF, DOCX, or image.",
                )
                return UPLOAD_DOCUMENT
            
            # Download to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp_file:
                await file.download_to_drive(tmp_file.name)
                tmp_path = tmp_file.name
            
            logger.info(f"Downloaded file: {tmp_path}, MIME: {mime_type}")
            
            # Process document
            invoice_data = await self.doc_processor.process_document(tmp_path, mime_type)
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            # Store extracted data
            context.user_data["invoice"] = invoice_data
            context.user_data["extracted_data"] = invoice_data.to_dict()
            
            # Delete processing message
            if processing_msg:
                await processing_msg.delete()
            
            # Show extracted data for confirmation
            summary = self.templates.extracted_data_summary(invoice_data.to_dict())
            keyboard = [
                [InlineKeyboardButton("✅ Confirm & Continue", callback_data="confirm_data")],
                [InlineKeyboardButton("🔄 Re-upload Document", callback_data="retry_upload")],
                [InlineKeyboardButton("✏️ Enter Manually", callback_data="manual_entry")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                summary,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
            return CONFIRM_EXTRACTED
            
        except Exception as e:
            logger.error(f"Document processing error: {e}")
            if processing_msg:
                await processing_msg.delete()
            
            await update.message.reply_text(
                self.templates.document_processing_error(),
                parse_mode="Markdown",
            )
            return UPLOAD_DOCUMENT
    
    async def _handle_wrong_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle text input when expecting document upload."""
        await update.message.reply_text(
            "❌ Please upload a document (PDF, DOCX) or photo, or type /cancel to exit.",
        )
        return UPLOAD_DOCUMENT
    
    async def _confirm_extracted_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle extracted data confirmation."""
        query = update.callback_query
        await query.answer()
        
        action = query.data
        
        if action == "confirm_data":
            # Data confirmed, show summary and ask for final confirmation
            invoice = context.user_data.get("invoice", InvoiceData())
            await query.edit_message_text(
                self.templates.full_summary(invoice.to_dict()),
                parse_mode="Markdown",
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Generate Invoice", callback_data="confirm_all")],
                [InlineKeyboardButton("✏️ Edit Details", callback_data="edit_data")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_all")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="What would you like to do?",
                reply_markup=reply_markup,
            )
            return CONFIRM_SUMMARY
            
        elif action == "retry_upload":
            await query.edit_message_text(
                self.templates.upload_instructions(),
                parse_mode="Markdown",
            )
            return UPLOAD_DOCUMENT
            
        else:  # manual_entry
            await query.edit_message_text(
                self.templates.chat_start(),
                parse_mode="Markdown",
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=self.templates.ask_contractor_name(),
            )
            return CONTRACTOR_NAME
    
    # ============ CHAT MODE - CONTRACTOR INFO ============
    
    async def _get_contractor_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get contractor name."""
        try:
            name = update.message.text.strip()
            if not name:
                raise ValueError("Name cannot be empty")
            
            context.user_data["invoice"].contractor_name = name
            await update.message.reply_text(self.templates.ask_contractor_address())
            return CONTRACTOR_ADDRESS
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "contractor name")
            return CONTRACTOR_NAME
    
    async def _get_contractor_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get contractor address."""
        try:
            address = update.message.text.strip()
            if not address:
                raise ValueError("Address cannot be empty")
            
            context.user_data["invoice"].contractor_address = address
            await update.message.reply_text(self.templates.ask_contractor_email())
            return CONTRACTOR_EMAIL
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "address")
            return CONTRACTOR_ADDRESS
    
    async def _get_contractor_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get contractor email."""
        try:
            email = update.message.text.strip()
            if "@" not in email or "." not in email:
                raise ValueError("Invalid email format")
            
            context.user_data["invoice"].contractor_email = email
            await update.message.reply_text(self.templates.ask_contractor_utr())
            return CONTRACTOR_UTR
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "email")
            return CONTRACTOR_EMAIL
    
    async def _get_contractor_utr(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get contractor UTR."""
        try:
            utr = update.message.text.strip()
            context.user_data["invoice"].contractor_utr = utr
            await update.message.reply_text(self.templates.ask_contractor_ni())
            return CONTRACTOR_NI
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "UTR")
            return CONTRACTOR_UTR
    
    async def _get_contractor_ni(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get contractor NI number."""
        try:
            ni = update.message.text.strip()
            context.user_data["invoice"].contractor_ni = ni
            await update.message.reply_text(self.templates.ask_bank_account())
            return CONTRACTOR_BANK
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "NI number")
            return CONTRACTOR_NI
    
    async def _get_contractor_bank(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get bank account number."""
        try:
            bank = update.message.text.strip()
            context.user_data["invoice"].bank_account = bank
            await update.message.reply_text(self.templates.ask_sort_code())
            return CONTRACTOR_SORT
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "bank account")
            return CONTRACTOR_BANK
    
    async def _get_contractor_sort(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get sort code."""
        try:
            sort = update.message.text.strip()
            context.user_data["invoice"].sort_code = sort
            await update.message.reply_text(self.templates.ask_cardholder_name())
            return CONTRACTOR_CARDHOLDER
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "sort code")
            return CONTRACTOR_SORT
    
    async def _get_contractor_cardholder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get cardholder name."""
        try:
            cardholder = update.message.text.strip()
            context.user_data["invoice"].cardholder_name = cardholder
            await update.message.reply_text(self.templates.ask_invoice_number())
            return INVOICE_NUMBER
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "cardholder name")
            return CONTRACTOR_CARDHOLDER
    
    # ============ INVOICE DETAILS ============
    
    async def _get_invoice_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get invoice number."""
        try:
            number = update.message.text.strip()
            context.user_data["invoice"].invoice_number = number
            await update.message.reply_text(self.templates.ask_invoice_date())
            return INVOICE_DATE
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "invoice number")
            return INVOICE_NUMBER
    
    async def _get_invoice_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get invoice date."""
        try:
            date_str = update.message.text.strip()
            # Validate date format
            datetime.strptime(date_str, "%d/%m/%Y")
            context.user_data["invoice"].invoice_date = date_str
            await update.message.reply_text(self.templates.ask_work_start_date())
            return WORK_START_DATE
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid date format. Please use DD/MM/YYYY format (e.g., 15/01/2024)."
            )
            return INVOICE_DATE
    
    async def _get_work_start_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get work start date."""
        try:
            date_str = update.message.text.strip()
            datetime.strptime(date_str, "%d/%m/%Y")
            context.user_data["invoice"].work_start_date = date_str
            await update.message.reply_text(self.templates.ask_work_end_date())
            return WORK_END_DATE
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid date format. Please use DD/MM/YYYY format."
            )
            return WORK_START_DATE
    
    async def _get_work_end_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get work end date."""
        try:
            date_str = update.message.text.strip()
            datetime.strptime(date_str, "%d/%m/%Y")
            context.user_data["invoice"].work_end_date = date_str
            
            # Ask if they want to add work items
            keyboard = [
                [InlineKeyboardButton("➕ Add Work Item", callback_data="add_work")],
                [InlineKeyboardButton("⏭️ Skip for Now", callback_data="skip_work")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                self.templates.ask_add_work_item(),
                reply_markup=reply_markup,
            )
            return ADD_WORK_ITEM
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid date format. Please use DD/MM/YYYY format."
            )
            return WORK_END_DATE
    
    # ============ WORK ITEMS ============
    
    async def _add_work_item_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle add work item callback."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "add_work":
            await query.edit_message_text(self.templates.ask_work_property())
            return WORK_PROPERTY
        else:  # skip_work
            await query.edit_message_text(self.templates.ask_operative_names())
            return OPERATIVE_NAMES
    
    async def _get_work_property(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get work property address."""
        try:
            property_addr = update.message.text.strip()
            if "current_work_item" not in context.user_data:
                context.user_data["current_work_item"] = WorkItem()
            context.user_data["current_work_item"].property_address = property_addr
            await update.message.reply_text(self.templates.ask_work_plot())
            return WORK_PLOT
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "property address")
            return WORK_PROPERTY
    
    async def _get_work_plot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get work plot number."""
        try:
            plot = update.message.text.strip()
            context.user_data["current_work_item"].plot = plot
            await update.message.reply_text(self.templates.ask_work_description())
            return WORK_DESCRIPTION
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "plot number")
            return WORK_PLOT
    
    async def _get_work_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get work description."""
        try:
            description = update.message.text.strip()
            context.user_data["current_work_item"].description = description
            await update.message.reply_text(self.templates.ask_work_amount())
            return WORK_AMOUNT
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "description")
            return WORK_DESCRIPTION
    
    async def _get_work_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get work amount."""
        try:
            amount_str = update.message.text.strip().replace("£", "").replace(",", "")
            amount = float(amount_str)
            context.user_data["current_work_item"].amount = amount
            
            # Add to invoice
            work_item = context.user_data["current_work_item"]
            context.user_data["invoice"].work_items.append(work_item)
            del context.user_data["current_work_item"]
            
            # Ask for more work items
            keyboard = [
                [InlineKeyboardButton("➕ Add Another", callback_data="more_work")],
                [InlineKeyboardButton("✅ Done", callback_data="done_work")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ Work item added: £{amount:.2f}\n\nAdd more work items?",
                reply_markup=reply_markup,
            )
            return MORE_WORK_ITEMS
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount. Please enter a number (e.g., 150.00 or 150)."
            )
            return WORK_AMOUNT
    
    async def _more_work_items_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle more work items callback."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "more_work":
            context.user_data["current_work_item"] = WorkItem()
            await query.edit_message_text(self.templates.ask_work_property())
            return WORK_PROPERTY
        else:  # done_work
            await query.edit_message_text(self.templates.ask_operative_names())
            return OPERATIVE_NAMES
    
    # ============ OPERATIVES & FINANCIALS ============
    
    async def _get_operative_names(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get operative names."""
        try:
            names = update.message.text.strip()
            context.user_data["invoice"].operative_names = names
            await update.message.reply_text(self.templates.ask_subtotal())
            return SUBTOTAL
        except Exception as e:
            await self.error_handler.handle_validation_error(update, "operative names")
            return OPERATIVE_NAMES
    
    async def _get_subtotal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get subtotal amount."""
        try:
            amount_str = update.message.text.strip().replace("£", "").replace(",", "")
            subtotal = float(amount_str)
            context.user_data["invoice"].subtotal = subtotal
            await update.message.reply_text(self.templates.ask_vat())
            return VAT_AMOUNT
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount. Please enter a number (e.g., 1000.00 or 1000)."
            )
            return SUBTOTAL
    
    async def _get_vat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get VAT amount."""
        try:
            amount_str = update.message.text.strip().replace("£", "").replace(",", "")
            vat = float(amount_str)
            context.user_data["invoice"].vat_amount = vat
            await update.message.reply_text(self.templates.ask_cis())
            return CIS_AMOUNT
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount. Please enter a number (e.g., 200.00 or 200)."
            )
            return VAT_AMOUNT
    
    async def _get_cis(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get CIS deduction amount."""
        try:
            amount_str = update.message.text.strip().replace("£", "").replace(",", "")
            cis = float(amount_str)
            context.user_data["invoice"].cis_amount = cis
            
            # Calculate total
            invoice = context.user_data["invoice"]
            invoice.calculate_total()
            
            # Show summary
            await update.message.reply_text(
                self.templates.full_summary(invoice.to_dict()),
                parse_mode="Markdown",
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Generate Invoice", callback_data="confirm_all")],
                [InlineKeyboardButton("✏️ Edit Details", callback_data="edit_data")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_all")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="What would you like to do?",
                reply_markup=reply_markup,
            )
            return CONFIRM_SUMMARY
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount. Please enter a number (e.g., 200.00 or 200)."
            )
            return CIS_AMOUNT
    
    # ============ SUMMARY & GENERATION ============
    
    async def _confirm_summary_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle summary confirmation callback."""
        query = update.callback_query
        await query.answer()
        
        action = query.data
        
        if action == "confirm_all":
            # Generate invoice
            processing_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⏳ Generating your invoice... Please wait.",
            )
            
            try:
                invoice = context.user_data["invoice"]
                invoice_path = await self.invoice_generator.generate(invoice)
                
                await processing_msg.delete()
                
                # Send the invoice document
                with open(invoice_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=f"Invoice_{invoice.invoice_number}.pdf",
                        caption=self.templates.invoice_generated(),
                        parse_mode="Markdown",
                    )
                
                # Clean up
                os.unlink(invoice_path)
                context.user_data.clear()
                
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=self.templates.goodbye_message(),
                    parse_mode="Markdown",
                )
                
            except Exception as e:
                logger.error(f"Invoice generation error: {e}")
                await processing_msg.delete()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=self.templates.generation_error(),
                    parse_mode="Markdown",
                )
            
            return ConversationHandler.END
            
        elif action == "edit_data":
            # Restart chat mode for editing
            await query.edit_message_text(
                "Let's update your information. Starting from the beginning..."
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=self.templates.ask_contractor_name(),
            )
            return CONTRACTOR_NAME
            
        else:  # cancel_all
            await query.edit_message_text(
                self.templates.cancel_message(),
                parse_mode="Markdown",
            )
            context.user_data.clear()
            return ConversationHandler.END
    
    # ============ ERROR HANDLER ============
    
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the dispatcher."""
        logger.error(f"Update {update} caused error: {context.error}")
        
        try:
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text(
                    self.templates.unexpected_error(),
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error(f"Error in error handler: {e}")


def main():
    """Run the bot."""
    bot = InvoiceBot()
    application = bot.get_application()
    
    # Run the bot until Ctrl-C is pressed
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
