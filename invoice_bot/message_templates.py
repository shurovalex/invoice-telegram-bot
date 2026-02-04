#!/usr/bin/env python3
"""
Message templates for user interactions.
All user-facing messages are centralized here for easy maintenance and localization.
"""

from typing import Dict, Any, List


class MessageTemplates:
    """Centralized message templates for the bot."""
    
    # ============ WELCOME & GENERAL ============
    
    def welcome_message(self, first_name: str) -> str:
        """Welcome message shown at /start."""
        return f"""👋 Hello {first_name}!

Welcome to the *Invoice Collection Bot*. I can help you create professional invoices quickly and easily.

**How would you like to proceed?**

📄 *Upload Document* - Upload an existing invoice (PDF, DOCX, or photo) and I'll extract the details

💬 *Chat to Provide Details* - Answer a few questions and I'll generate your invoice

Select an option below to get started!"""
    
    def help_message(self) -> str:
        """Help message for /help command."""
        return """ℹ️ *Invoice Collection Bot - Help*

*Available Commands:*
/start - Start a new invoice
/cancel - Cancel current operation
/help - Show this help message

*How it works:*
1. Choose to upload a document or chat to provide details
2. If uploading: Send PDF, DOCX, or photo of your invoice
3. If chatting: Answer questions about your invoice
4. Review and confirm the extracted/entered data
5. Receive your generated invoice as a PDF

*Supported File Types:*
- PDF documents
- Microsoft Word (.docx)
- JPEG/PNG images

*Need help?* Contact support if you encounter any issues."""
    
    def cancel_message(self) -> str:
        """Message shown when user cancels."""
        return """❌ Operation cancelled.

Your invoice data has been discarded. Type /start to begin again anytime!"""
    
    def goodbye_message(self) -> str:
        """Message shown after successful invoice generation."""
        return """✅ *Invoice Generated Successfully!*

Your invoice has been created and sent above. 

Thank you for using the Invoice Collection Bot! 

Type /start to create another invoice anytime."""
    
    # ============ UPLOAD MODE ============
    
    def upload_instructions(self) -> str:
        """Instructions for document upload."""
        return """📄 *Upload Your Invoice Document*

Please upload your invoice document. I accept:
• PDF files (.pdf)
• Microsoft Word documents (.docx)
• Photos/images (.jpg, .jpeg, .png)

*Tips for best results:*
- Ensure the document is clear and readable
- Make sure all text is visible
- For photos, use good lighting and avoid glare

Send your file now, or type /cancel to exit."""
    
    def document_processing_error(self) -> str:
        """Error message when document processing fails."""
        return """❌ *Document Processing Error*

Sorry, I couldn't process your document. This could be due to:
- Unsupported file format
- Corrupted file
- Poor image quality (for photos)

*Please try:*
1. Uploading a different file
2. Converting to PDF format
3. Taking a clearer photo

Or type /cancel to exit and try the chat option instead."""
    
    def extracted_data_summary(self, data: Dict[str, Any]) -> str:
        """Summary of extracted data for confirmation."""
        work_items_summary = ""
        for i, item in enumerate(data.get("work_items", []), 1):
            work_items_summary += f"  {i}. {item.get('description', 'N/A')[:40]}... - £{item.get('amount', 0):.2f}\n"
        
        return f"""📋 *Extracted Data Summary*

Here's what I found in your document:

👤 *Contractor:* {data.get('contractor_name') or 'Not found'}
📧 *Email:* {data.get('contractor_email') or 'Not found'}
🏠 *Address:* {data.get('contractor_address')[:50] + '...' if data.get('contractor_address') and len(data.get('contractor_address')) > 50 else data.get('contractor_address') or 'Not found'}
🆔 *UTR:* {data.get('contractor_utr') or 'Not found'}
🔢 *NI:* {data.get('contractor_ni') or 'Not found'}
💳 *Bank:* {data.get('bank_account') or 'Not found'} | Sort: {data.get('sort_code') or 'Not found'}

📄 *Invoice #:* {data.get('invoice_number') or 'Not found'}
📅 *Date:* {data.get('invoice_date') or 'Not found'}

🔨 *Work Items:*
{work_items_summary or '  None found'}

💰 *Financials:*
  Subtotal: £{data.get('subtotal', 0):.2f}
  VAT: £{data.get('vat_amount', 0):.2f}
  CIS: £{data.get('cis_amount', 0):.2f}
  *Total: £{data.get('total', 0):.2f}*

Please review the extracted data. Is this correct?"""
    
    # ============ CHAT MODE ============
    
    def chat_start(self) -> str:
        """Message when starting chat mode."""
        return """💬 *Let's Create Your Invoice*

I'll ask you a series of questions to gather all the information needed for your invoice. 

*You can type /cancel at any time to exit.*

Let's begin!"""
    
    # Contractor info questions
    def ask_contractor_name(self) -> str:
        return "👤 *Step 1/15: Contractor Name*\n\nWhat is the contractor's full name or company name?"
    
    def ask_contractor_address(self) -> str:
        return "🏠 *Step 2/15: Contractor Address*\n\nWhat is the contractor's address? (Please provide the full address)"
    
    def ask_contractor_email(self) -> str:
        return "📧 *Step 3/15: Email Address*\n\nWhat is the contractor's email address?"
    
    def ask_contractor_utr(self) -> str:
        return "🆔 *Step 4/15: UTR Number*\n\nWhat is the contractor's UTR (Unique Taxpayer Reference)?\n\n(10-digit number, or type 'skip' if not applicable)"
    
    def ask_contractor_ni(self) -> str:
        return "🔢 *Step 5/15: National Insurance Number*\n\nWhat is the contractor's NI number?\n\n(Format: AB123456C, or type 'skip')"
    
    def ask_bank_account(self) -> str:
        return "🏦 *Step 6/15: Bank Account Number*\n\nWhat is the bank account number?\n\n(8 digits, or type 'skip')"
    
    def ask_sort_code(self) -> str:
        return "🔢 *Step 7/15: Sort Code*\n\nWhat is the sort code?\n\n(Format: 12-34-56 or 123456, or type 'skip')"
    
    def ask_cardholder_name(self) -> str:
        return "💳 *Step 8/15: Cardholder Name*\n\nWhat is the name on the bank account?\n\n(or type 'skip')"
    
    # Invoice details questions
    def ask_invoice_number(self) -> str:
        return "📄 *Step 9/15: Invoice Number*\n\nWhat is the invoice number?\n\n(e.g., INV-2024-001)"
    
    def ask_invoice_date(self) -> str:
        return "📅 *Step 10/15: Invoice Date*\n\nWhat is the invoice date?\n\n(Please use DD/MM/YYYY format, e.g., 15/01/2024)"
    
    def ask_work_start_date(self) -> str:
        return "📆 *Step 11/15: Work Start Date*\n\nWhen did the work start?\n\n(DD/MM/YYYY format)"
    
    def ask_work_end_date(self) -> str:
        return "📆 *Step 12/15: Work End Date*\n\nWhen did the work end?\n\n(DD/MM/YYYY format)"
    
    # Work items
    def ask_add_work_item(self) -> str:
        return """🔨 *Step 13/15: Work Items*

Would you like to add work items to this invoice?

Work items include details like:
- Property address
- Plot number
- Description of work
- Amount charged"""
    
    def ask_work_property(self) -> str:
        return "🏠 *Work Item: Property Address*\n\nWhat is the property address for this work?"
    
    def ask_work_plot(self) -> str:
        return "📍 *Work Item: Plot Number*\n\nWhat is the plot number? (or type 'N/A')"
    
    def ask_work_description(self) -> str:
        return "📝 *Work Item: Description*\n\nPlease describe the work performed:"
    
    def ask_work_amount(self) -> str:
        return "💰 *Work Item: Amount*\n\nWhat is the amount for this work?\n\n(Enter just the number, e.g., 150.00)"
    
    # Operatives and financials
    def ask_operative_names(self) -> str:
        return "👷 *Step 14/15: Operative Names*\n\nWho performed the work? (Enter names separated by commas, or type 'N/A')"
    
    def ask_subtotal(self) -> str:
        return "💰 *Step 15/15: Financial Details*\n\nWhat is the subtotal amount (before VAT and deductions)?\n\n(e.g., 1000.00)"
    
    def ask_vat(self) -> str:
        return "💰 *VAT Amount*\n\nWhat is the VAT amount?\n\n(e.g., 200.00, or 0 if not applicable)"
    
    def ask_cis(self) -> str:
        return "💰 *CIS Deduction*\n\nWhat is the CIS (Construction Industry Scheme) deduction amount?\n\n(e.g., 200.00, or 0 if not applicable)"
    
    # ============ SUMMARY & CONFIRMATION ============
    
    def full_summary(self, data: Dict[str, Any]) -> str:
        """Complete invoice summary for final confirmation."""
        work_items_text = ""
        for i, item in enumerate(data.get("work_items", []), 1):
            desc = item.get('description', 'N/A')
            if len(desc) > 40:
                desc = desc[:40] + "..."
            work_items_text += f"  {i}. {desc} - £{item.get('amount', 0):.2f}\n"
        
        return f"""📋 *Invoice Summary*

Please review all the details below:

*Contractor Information:*
👤 Name: {data.get('contractor_name', 'N/A')}
📧 Email: {data.get('contractor_email', 'N/A')}
🏠 Address: {data.get('contractor_address', 'N/A')[:60]}{'...' if data.get('contractor_address') and len(data.get('contractor_address', '')) > 60 else ''}
🆔 UTR: {data.get('contractor_utr', 'N/A')}
🔢 NI: {data.get('contractor_ni', 'N/A')}
💳 Bank: {data.get('bank_account', 'N/A')} | Sort: {data.get('sort_code', 'N/A')}
💳 Cardholder: {data.get('cardholder_name', 'N/A')}

*Invoice Details:*
📄 Number: {data.get('invoice_number', 'N/A')}
📅 Date: {data.get('invoice_date', 'N/A')}
📆 Period: {data.get('work_start_date', 'N/A')} to {data.get('work_end_date', 'N/A')}

*Work Items:*
{work_items_text or '  No work items added'}

👷 Operatives: {data.get('operative_names', 'N/A')}

*Financial Summary:*
  Subtotal: £{data.get('subtotal', 0):.2f}
  VAT: £{data.get('vat_amount', 0):.2f}
  CIS Deduction: £{data.get('cis_amount', 0):.2f}
  ─────────────────
  *TOTAL: £{data.get('total', 0):.2f}*"""
    
    def invoice_generated(self) -> str:
        """Message when invoice is successfully generated."""
        return "✅ Your invoice has been generated successfully!"
    
    def generation_error(self) -> str:
        """Error message when invoice generation fails."""
        return """❌ *Invoice Generation Failed*

Sorry, I encountered an error while generating your invoice. 

*Please try:*
1. Reviewing your data and trying again
2. Starting over with /start
3. Contacting support if the problem persists

We apologize for the inconvenience."""
    
    def unexpected_error(self) -> str:
        """Message for unexpected errors."""
        return """❌ *Oops! Something went wrong.*

I encountered an unexpected error. Don't worry - your data is safe.

*Please try:*
• Sending your message again
• Typing /cancel and starting over
• Contacting support if the issue persists

We apologize for the inconvenience!"""
    
    # ============ PROGRESS MESSAGES ============
    
    def progress_message(self, current: int, total: int, section: str) -> str:
        """Show progress through the conversation."""
        percentage = int((current / total) * 100)
        bar_length = 10
        filled = int((current / total) * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        return f"⏳ *Progress: {bar} {percentage}%*\n\n{section}"
    
    def validation_error(self, field_name: str) -> str:
        """Generic validation error message."""
        return f"❌ Invalid {field_name}. Please check your input and try again."
