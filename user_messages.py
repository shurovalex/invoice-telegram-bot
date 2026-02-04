"""
================================================================================
USER-FRIENDLY ERROR MESSAGES
================================================================================
Transforms technical errors into helpful, non-technical messages
Never exposes internal system details to users

This module ensures that users always receive helpful, friendly messages
regardless of what technical errors occur behind the scenes.
"""

from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class UserMessageCategory(Enum):
    """Categories of user-facing messages"""
    TECHNICAL_ISSUE = "technical_issue"
    USER_ERROR = "user_error"
    EXTERNAL_SERVICE = "external_service"
    RECOVERY = "recovery"
    INFORMATION = "information"


@dataclass
class UserMessage:
    """Structured user message"""
    text: str
    category: UserMessageCategory
    show_retry_button: bool = False
    show_help_button: bool = False
    emoji: str = ""
    follow_up: Optional[str] = None
    actions: List[Dict] = field(default_factory=list)


class UserMessageManager:
    """
    Manages user-friendly error messages
    Converts technical errors to helpful, non-technical responses
    """
    
    # Message templates by category
    MESSAGES = {
        # AI Model Issues
        "ai_model_timeout": UserMessage(
            text="I'm taking a bit longer than usual to think about this. Let me try again...",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="🤔",
            show_retry_button=True,
        ),
        "ai_model_rate_limit": UserMessage(
            text="I'm experiencing high demand right now. Please give me a moment...",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="⏳",
            show_retry_button=True,
        ),
        "ai_model_unavailable": UserMessage(
            text="My AI systems are temporarily unavailable. Let me use my backup brain!",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="🧠",
            follow_up="I'm still here to help you with your invoices!",
        ),
        
        # Document Processing Issues
        "document_corrupted": UserMessage(
            text="I couldn't read that file. It might be corrupted or in an unsupported format.",
            category=UserMessageCategory.USER_ERROR,
            emoji="📄❌",
            show_help_button=True,
            follow_up="Could you try uploading a PDF, JPG, or PNG file?",
        ),
        "document_too_large": UserMessage(
            text="That file is too large for me to process. Please try a smaller file (under 20MB).",
            category=UserMessageCategory.USER_ERROR,
            emoji="📦",
            follow_up="You could also try compressing the image or using a lower resolution.",
        ),
        "ocr_failed": UserMessage(
            text="I had trouble reading the text in that image. Could you try a clearer photo?",
            category=UserMessageCategory.USER_ERROR,
            emoji="🔍",
            show_help_button=True,
            follow_up="Tips: Make sure the image is well-lit and the text is clearly visible.",
        ),
        
        # Database Issues
        "database_connection": UserMessage(
            text="I'm having trouble saving your data, but don't worry - your current session is safe!",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="💾",
            follow_up="I'll keep trying to save your information in the background.",
        ),
        "database_timeout": UserMessage(
            text="My database is taking longer than expected to respond...",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="🔄",
        ),
        
        # Network Issues
        "network_error": UserMessage(
            text="I'm having trouble connecting to my services. Let me retry...",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="🌐",
            show_retry_button=True,
        ),
        "download_failed": UserMessage(
            text="I couldn't download your file. Please try uploading it again.",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="📥",
            show_retry_button=True,
        ),
        
        # Webhook Issues
        "webhook_failed": UserMessage(
            text="I couldn't notify external systems, but your invoice was processed successfully!",
            category=UserMessageCategory.EXTERNAL_SERVICE,
            emoji="📡",
            follow_up="I'll retry sending the notification in the background.",
        ),
        
        # Third-Party Service Issues
        "cloudconvert_failed": UserMessage(
            text="I had trouble converting that file format. Could you try a different file?",
            category=UserMessageCategory.EXTERNAL_SERVICE,
            emoji="🔄",
            show_help_button=True,
        ),
        "google_sheets_failed": UserMessage(
            text="I couldn't save to Google Sheets, but your data is safely stored!",
            category=UserMessageCategory.EXTERNAL_SERVICE,
            emoji="📊",
            follow_up="You can export your data anytime from the menu.",
        ),
        "external_api_down": UserMessage(
            text="An external service I use is temporarily down. I'll continue with what I can do!",
            category=UserMessageCategory.EXTERNAL_SERVICE,
            emoji="🔌",
        ),
        
        # User Input Issues
        "invalid_input": UserMessage(
            text="I'm not sure I understood that. Could you rephrase or be more specific?",
            category=UserMessageCategory.USER_ERROR,
            emoji="🤷",
            show_help_button=True,
        ),
        "unknown_command": UserMessage(
            text="I don't recognize that command. Here are some things I can help with:",
            category=UserMessageCategory.USER_ERROR,
            emoji="❓",
            actions=[
                {"text": "📤 Upload Invoice", "callback": "upload"},
                {"text": "📋 View Invoices", "callback": "list"},
                {"text": "❓ Help", "callback": "help"},
            ],
        ),
        
        # Recovery Messages
        "recovering": UserMessage(
            text="I'm recovering from a brief issue. Thanks for your patience!",
            category=UserMessageCategory.RECOVERY,
            emoji="🩹",
        ),
        "using_fallback": UserMessage(
            text="I'm using my backup systems to help you. Everything is working!",
            category=UserMessageCategory.RECOVERY,
            emoji="🔄",
        ),
        "state_recovered": UserMessage(
            text="Good news! I recovered your previous session. Let's continue!",
            category=UserMessageCategory.RECOVERY,
            emoji="✅",
        ),
        
        # General Messages
        "general_error": UserMessage(
            text="I encountered a small hiccup, but I'm still here to help!",
            category=UserMessageCategory.TECHNICAL_ISSUE,
            emoji="⚠️",
            show_retry_button=True,
        ),
        "working_on_it": UserMessage(
            text="I'm working on that for you...",
            category=UserMessageCategory.INFORMATION,
            emoji="⚙️",
        ),
        "almost_done": UserMessage(
            text="Almost done! Just a moment...",
            category=UserMessageCategory.INFORMATION,
            emoji="🏃",
        ),
    }
    
    @classmethod
    def get_message(cls, key: str, **format_args) -> UserMessage:
        """Get a user message by key"""
        message = cls.MESSAGES.get(key, cls.MESSAGES["general_error"])
        
        # Format the text with provided arguments
        text = message.text
        if format_args:
            try:
                text = text.format(**format_args)
            except:
                pass  # Keep original if formatting fails
        
        # Create a copy with formatted text
        return UserMessage(
            text=text,
            category=message.category,
            show_retry_button=message.show_retry_button,
            show_help_button=message.show_help_button,
            emoji=message.emoji,
            follow_up=message.follow_up,
            actions=message.actions.copy() if message.actions else [],
        )
    
    @classmethod
    def get_message_for_error(
        cls,
        error_category: str,
        error_type: str,
        is_retryable: bool = True
    ) -> UserMessage:
        """
        Get appropriate user message for an error
        
        Args:
            error_category: Category of error (ai_model, database, network, etc.)
            error_type: Type of error (timeout, rate_limit, etc.)
            is_retryable: Whether the error is retryable
        """
        # Map error categories to message keys
        error_map = {
            ("ai_model", "timeout"): "ai_model_timeout",
            ("ai_model", "rate_limit"): "ai_model_rate_limit",
            ("ai_model", "unavailable"): "ai_model_unavailable",
            ("document_processing", "corrupted"): "document_corrupted",
            ("document_processing", "too_large"): "document_too_large",
            ("document_processing", "ocr"): "ocr_failed",
            ("database", "connection"): "database_connection",
            ("database", "timeout"): "database_timeout",
            ("network", "error"): "network_error",
            ("file_download", "failed"): "download_failed",
            ("webhook", "failed"): "webhook_failed",
            ("third_party", "cloudconvert"): "cloudconvert_failed",
            ("third_party", "google_sheets"): "google_sheets_failed",
            ("third_party", "api_down"): "external_api_down",
            ("user_input", "invalid"): "invalid_input",
            ("user_input", "unknown_command"): "unknown_command",
        }
        
        key = error_map.get((error_category, error_type), "general_error")
        return cls.get_message(key)
    
    @classmethod
    def format_for_telegram(cls, message: UserMessage) -> str:
        """Format a message for Telegram"""
        parts = []
        
        if message.emoji:
            parts.append(message.emoji)
        
        parts.append(message.text)
        
        if message.follow_up:
            parts.append(f"\n\n{message.follow_up}")
        
        return " ".join(parts)
    
    @classmethod
    def get_retry_keyboard(cls) -> List[List[Dict]]:
        """Get retry keyboard layout"""
        return [[
            {"text": "🔄 Try Again", "callback_data": "retry"},
            {"text": "❓ Help", "callback_data": "help"},
        ]]
    
    @classmethod
    def get_help_keyboard(cls) -> List[List[Dict]]:
        """Get help keyboard layout"""
        return [[
            {"text": "📤 Upload Invoice", "callback_data": "upload"},
            {"text": "📋 My Invoices", "callback_data": "list"},
        ], [
            {"text": "❓ How to Use", "callback_data": "help"},
            {"text": "💬 Contact Support", "callback_data": "support"},
        ]]


class MessageBuilder:
    """Builds complex messages with multiple parts"""
    
    def __init__(self):
        self.parts = []
        self.emoji = ""
        self.actions = []
    
    def add_text(self, text: str, emoji: str = ""):
        """Add text part"""
        if emoji:
            self.parts.append(f"{emoji} {text}")
        else:
            self.parts.append(text)
        return self
    
    def add_line_break(self):
        """Add line break"""
        self.parts.append("")
        return self
    
    def add_bullet(self, text: str):
        """Add bullet point"""
        self.parts.append(f"• {text}")
        return self
    
    def add_numbered(self, number: int, text: str):
        """Add numbered item"""
        self.parts.append(f"{number}. {text}")
        return self
    
    def add_action(self, text: str, callback: str):
        """Add action button"""
        self.actions.append({"text": text, "callback": callback})
        return self
    
    def build(self) -> str:
        """Build the final message"""
        return "\n".join(self.parts)


# Pre-built message sequences for common scenarios
class MessageSequences:
    """Pre-built message sequences for complex interactions"""
    
    @staticmethod
    def recovery_sequence() -> List[UserMessage]:
        """Message sequence for system recovery"""
        return [
            UserMessageManager.get_message("recovering"),
            UserMessageManager.get_message("using_fallback"),
        ]
    
    @staticmethod
    def document_upload_help() -> List[str]:
        """Help messages for document upload issues"""
        return [
            "📄 **Supported Formats:** PDF, JPG, PNG",
            "📏 **Size Limit:** 20MB maximum",
            "💡 **Tips for best results:**",
            "   • Use well-lit, clear images",
            "   • Make sure text is readable",
            "   • Avoid blurry or skewed photos",
        ]
    
    @staticmethod
    def fallback_capabilities() -> str:
        """Message about capabilities in fallback mode"""
        return """
🔄 **I'm in Simplified Mode**

I can still help you with:
✅ Basic invoice data extraction
✅ Manual data entry assistance
✅ Viewing your existing invoices
✅ Answering questions

⚠️ Some advanced features may be limited.
"""
