"""
AI Client with Fallback Support

Provides a unified interface for multiple AI providers (OpenAI, Gemini)
with automatic fallback when a provider fails.
"""

import json
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Dict, List, Optional, Any, Callable
from datetime import datetime

from src.core.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AIProvider(Enum):
    """Supported AI providers."""
    OPENAI = "openai"
    GEMINI = "gemini"


@dataclass
class AIResponse:
    """Standardized AI response."""
    content: str
    provider: AIProvider
    model: str
    usage: Optional[Dict[str, int]] = None
    latency_ms: Optional[float] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "provider": self.provider.value,
            "model": self.model,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseAIClient(ABC):
    """Abstract base class for AI clients."""
    
    def __init__(self, provider: AIProvider):
        self.provider = provider
        self.settings = get_settings()
        self._client = None
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the client. Returns True if successful."""
        pass
    
    @abstractmethod
    async def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AIResponse:
        """Generate a response from the AI."""
        pass
    
    @abstractmethod
    async def generate_stream(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response from the AI."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the client is properly configured and available."""
        pass
    
    async def close(self) -> None:
        """Close the client and cleanup resources."""
        pass


class OpenAIClient(BaseAIClient):
    """OpenAI API client."""
    
    def __init__(self):
        super().__init__(AIProvider.OPENAI)
        self.model = self.settings.openai_model
        self.max_tokens = self.settings.openai_max_tokens
        self.temperature = self.settings.openai_temperature
    
    def is_available(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.settings.openai_api_key)
    
    async def initialize(self) -> bool:
        """Initialize OpenAI client."""
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            logger.info("OpenAI client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return False
    
    async def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AIResponse:
        """Generate response using OpenAI."""
        import time
        
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        start_time = time.time()
        
        try:
            response = await self._client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=messages,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                temperature=kwargs.get("temperature", self.temperature),
            )
            
            latency = (time.time() - start_time) * 1000
            
            return AIResponse(
                content=response.choices[0].message.content,
                provider=self.provider,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                latency_ms=latency,
            )
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise
    
    async def generate_stream(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using OpenAI."""
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        stream = await self._client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=messages,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
            stream=True,
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def close(self) -> None:
        """Close OpenAI client."""
        if self._client:
            await self._client.close()


class GeminiClient(BaseAIClient):
    """Google Gemini API client."""
    
    def __init__(self):
        super().__init__(AIProvider.GEMINI)
        self.model = self.settings.gemini_model
        self.max_tokens = self.settings.gemini_max_tokens
        self.temperature = self.settings.gemini_temperature
    
    def is_available(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self.settings.gemini_api_key)
    
    async def initialize(self) -> bool:
        """Initialize Gemini client."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.settings.gemini_api_key)
            self._client = genai.GenerativeModel(self.model)
            logger.info("Gemini client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            return False
    
    async def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AIResponse:
        """Generate response using Gemini."""
        import time
        
        if not self._client:
            raise RuntimeError("Gemini client not initialized")
        
        # Combine system prompt with user prompt if provided
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        start_time = time.time()
        
        try:
            response = await self._client.generate_content_async(
                full_prompt,
                generation_config={
                    "max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
                    "temperature": kwargs.get("temperature", self.temperature),
                }
            )
            
            latency = (time.time() - start_time) * 1000
            
            return AIResponse(
                content=response.text,
                provider=self.provider,
                model=self.model,
                latency_ms=latency,
            )
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            raise
    
    async def generate_stream(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response using Gemini."""
        if not self._client:
            raise RuntimeError("Gemini client not initialized")
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        response = await self._client.generate_content_async(
            full_prompt,
            generation_config={
                "max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
            },
            stream=True,
        )
        
        async for chunk in response:
            if chunk.text:
                yield chunk.text


class AIClientManager:
    """
    Manages multiple AI clients with automatic fallback.
    
    Tries providers in priority order and falls back to the next
    available provider if one fails.
    """
    
    # System prompts for different tasks
    INVOICE_EXTRACTION_PROMPT = """You are an expert invoice data extraction assistant.
Your task is to extract structured invoice data from the provided text or document.
Extract the following fields if present:
- invoice_number
- issue_date (in YYYY-MM-DD format)
- due_date (in YYYY-MM-DD format)
- customer_name
- customer_email
- customer_phone
- customer_address
- customer_tax_id
- items (list with description, quantity, unit_price, tax_rate)
- currency (3-letter code like USD, EUR)
- notes
- terms

Return ONLY a valid JSON object with the extracted data. Use null for missing fields.
Be precise and extract exact values as they appear in the document."""

    INVOICE_VALIDATION_PROMPT = """You are an invoice validation assistant.
Review the provided invoice data and identify any issues or missing information.
Check for:
- Missing required fields (customer name, at least one item)
- Invalid dates or amounts
- Incomplete customer information
- Missing payment terms

Return a JSON object with:
- "valid": boolean indicating if invoice is ready
- "issues": list of identified issues
- "suggestions": list of improvement suggestions"""

    CONVERSATION_PROMPT = """You are a helpful invoice creation assistant.
Help the user create professional invoices through a friendly conversation.
Guide them through providing necessary information step by step.
Be concise, professional, and helpful."""

    def __init__(self):
        """Initialize the AI client manager."""
        self.settings = get_settings()
        self._clients: Dict[AIProvider, BaseAIClient] = {}
        self._initialized = False
        self._fallback_chain: List[AIProvider] = []
    
    async def initialize(self) -> bool:
        """
        Initialize all available AI clients.
        
        Returns:
            bool: True if at least one client initialized successfully
        """
        if self._initialized:
            return True
        
        # Create clients based on configuration
        clients_to_try = []
        
        for provider_name in self.settings.ai_provider_priority:
            provider = AIProvider(provider_name)
            
            if provider == AIProvider.OPENAI and self.settings.openai_api_key:
                clients_to_try.append((provider, OpenAIClient()))
            elif provider == AIProvider.GEMINI and self.settings.gemini_api_key:
                clients_to_try.append((provider, GeminiClient()))
        
        # Initialize clients
        for provider, client in clients_to_try:
            if await client.initialize():
                self._clients[provider] = client
                self._fallback_chain.append(provider)
                logger.info(f"AI client ready: {provider.value}")
        
        self._initialized = len(self._clients) > 0
        
        if not self._initialized:
            logger.error("No AI clients could be initialized")
            return False
        
        logger.info(f"AI Manager initialized with {len(self._clients)} provider(s)")
        return True
    
    async def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        task_type: str = "general",
        **kwargs
    ) -> AIResponse:
        """
        Generate AI response with automatic fallback.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            task_type: Type of task (for logging)
            **kwargs: Additional parameters
            
        Returns:
            AIResponse: The generated response
            
        Raises:
            RuntimeError: If all providers fail
        """
        if not self._initialized:
            raise RuntimeError("AI Manager not initialized")
        
        if self.settings.test_mode:
            return self._generate_mock_response(prompt, task_type)
        
        last_error = None
        
        for provider in self._fallback_chain:
            client = self._clients[provider]
            
            try:
                logger.debug(f"Trying {provider.value} for {task_type}")
                response = await client.generate(prompt, system_prompt, **kwargs)
                logger.info(f"Successfully generated with {provider.value}")
                return response
            except Exception as e:
                logger.warning(f"{provider.value} failed: {e}")
                last_error = e
                continue
        
        raise RuntimeError(f"All AI providers failed. Last error: {last_error}")
    
    async def generate_stream(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming AI response with fallback.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            **kwargs: Additional parameters
            
        Yields:
            str: Response chunks
        """
        if not self._initialized:
            raise RuntimeError("AI Manager not initialized")
        
        for provider in self._fallback_chain:
            client = self._clients[provider]
            
            try:
                async for chunk in client.generate_stream(prompt, system_prompt, **kwargs):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"{provider.value} streaming failed: {e}")
                continue
        
        raise RuntimeError("All AI providers failed for streaming")
    
    async def extract_invoice_data(self, text: str) -> Dict[str, Any]:
        """
        Extract structured invoice data from text.
        
        Args:
            text: Text to extract data from
            
        Returns:
            Dict with extracted invoice data
        """
        prompt = f"Extract invoice data from the following text:\n\n{text}\n\nReturn ONLY valid JSON."
        
        response = await self.generate(
            prompt=prompt,
            system_prompt=self.INVOICE_EXTRACTION_PROMPT,
            task_type="invoice_extraction",
        )
        
        try:
            # Try to parse JSON from response
            content = response.content.strip()
            # Remove markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return {"error": "Failed to parse response", "raw_response": response.content}
    
    async def validate_invoice_data(self, invoice_json: str) -> Dict[str, Any]:
        """
        Validate invoice data and provide feedback.
        
        Args:
            invoice_json: JSON string of invoice data
            
        Returns:
            Dict with validation results
        """
        prompt = f"Validate the following invoice data:\n\n{invoice_json}\n\nReturn ONLY valid JSON."
        
        response = await self.generate(
            prompt=prompt,
            system_prompt=self.INVOICE_VALIDATION_PROMPT,
            task_type="invoice_validation",
        )
        
        try:
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content.strip())
        except json.JSONDecodeError:
            return {"valid": False, "issues": ["Failed to parse validation response"]}
    
    def _generate_mock_response(self, prompt: str, task_type: str) -> AIResponse:
        """Generate mock response for testing."""
        logger.info(f"TEST MODE: Generating mock response for {task_type}")
        
        if task_type == "invoice_extraction":
            content = json.dumps({
                "invoice_number": "TEST-001",
                "customer_name": "Test Customer",
                "items": [{"description": "Test Item", "quantity": 1, "unit_price": 100}],
                "currency": "USD",
            })
        elif task_type == "invoice_validation":
            content = json.dumps({
                "valid": True,
                "issues": [],
                "suggestions": ["Add payment terms for clarity"],
            })
        else:
            content = "This is a mock response for testing purposes."
        
        return AIResponse(
            content=content,
            provider=AIProvider.OPENAI,
            model="mock-model",
            latency_ms=100.0,
        )
    
    async def close(self) -> None:
        """Close all AI clients."""
        for client in self._clients.values():
            await client.close()
        self._initialized = False


# Global AI manager instance
_ai_manager: Optional[AIClientManager] = None


async def get_ai_manager() -> AIClientManager:
    """
    Get the global AI manager instance.
    
    Returns:
        AIClientManager: Initialized singleton instance
    """
    global _ai_manager
    if _ai_manager is None:
        _ai_manager = AIClientManager()
        await _ai_manager.initialize()
    return _ai_manager


async def initialize_ai() -> bool:
    """Initialize the AI manager."""
    manager = await get_ai_manager()
    return manager._initialized


async def shutdown_ai() -> None:
    """Shutdown the AI manager."""
    global _ai_manager
    if _ai_manager:
        await _ai_manager.close()
        _ai_manager = None
