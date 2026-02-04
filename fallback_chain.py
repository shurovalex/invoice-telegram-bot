"""
================================================================================
FALLBACK CHAIN FOR AI MODELS
================================================================================
Multi-tier fallback system for AI model failures
Primary -> Secondary -> Tertiary -> Static Response -> Degraded Mode

This module provides a resilient AI model fallback chain that ensures
users always receive a response even when primary AI services fail.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
import time
import re

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ModelTier(Enum):
    """AI Model tiers in fallback chain"""
    PRIMARY = auto()
    SECONDARY = auto()
    TERTIARY = auto()
    LOCAL = auto()
    STATIC = auto()


@dataclass
class ModelConfig:
    """Configuration for an AI model in the fallback chain"""
    name: str
    tier: ModelTier
    client: Any = None  # The actual model client/instance
    timeout: float = 30.0
    max_tokens: int = 2000
    temperature: float = 0.7
    enabled: bool = True
    priority: int = 0  # Lower = higher priority within tier
    cost_per_1k_tokens: float = 0.0
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tier": self.tier.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "capabilities": self.capabilities,
        }


@dataclass
class ModelResponse:
    """Standardized response from any model"""
    content: str
    model_used: str
    tier: ModelTier
    latency_ms: float
    tokens_used: int = 0
    cost: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content[:100] + "..." if len(self.content) > 100 else self.content,
            "model_used": self.model_used,
            "tier": self.tier.name,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
            "success": self.success,
        }


@dataclass
class FallbackStats:
    """Statistics for fallback chain usage"""
    total_calls: int = 0
    primary_success: int = 0
    secondary_success: int = 0
    tertiary_success: int = 0
    local_success: int = 0
    static_fallback: int = 0
    total_failures: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    last_used_model: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "success_by_tier": {
                "primary": self.primary_success,
                "secondary": self.secondary_success,
                "tertiary": self.tertiary_success,
                "local": self.local_success,
                "static": self.static_fallback,
            },
            "total_failures": self.total_failures,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": self.avg_latency_ms,
            "last_used_model": self.last_used_model,
        }


class AIFallbackChain:
    """
    Multi-tier AI model fallback chain
    
    Usage:
        chain = AIFallbackChain()
        chain.add_model(ModelConfig("gpt-4", ModelTier.PRIMARY, openai_client))
        chain.add_model(ModelConfig("claude-3", ModelTier.SECONDARY, anthropic_client))
        chain.add_model(ModelConfig("gpt-3.5", ModelTier.TERTIARY, openai_client))
        
        response = await chain.generate("Extract invoice data from...")
    """
    
    # Static fallback responses for common operations
    STATIC_RESPONSES = {
        "invoice_extraction": """
I apologize, but I'm experiencing technical difficulties with my AI processing systems. 
However, I can still help you! Here's what you can do:

1. **Try again in a moment** - This might be temporary
2. **Upload a clearer image** - Better quality helps processing
3. **Type the details manually** - I can collect: vendor, amount, date, items

What would you prefer to do?
""",
        "general_chat": "I'm having a brief technical issue. Could you repeat that in a moment?",
        "data_validation": "I'm experiencing some delays. Please try again shortly.",
        "error_recovery": "I'm working on recovering from an error. One moment please...",
    }
    
    def __init__(self):
        self._models: Dict[ModelTier, List[ModelConfig]] = {
            tier: [] for tier in ModelTier
        }
        self._stats = FallbackStats()
        self._circuit_breakers: Dict[str, Any] = {}
        self._health_status: Dict[str, Dict] = {}
        
    def add_model(self, config: ModelConfig):
        """Add a model to the fallback chain"""
        self._models[config.tier].append(config)
        # Sort by priority
        self._models[config.tier].sort(key=lambda m: m.priority)
        logger.info(f"Added model {config.name} to tier {config.tier.name}")
        
    def remove_model(self, name: str):
        """Remove a model from the chain"""
        for tier_models in self._models.values():
            tier_models[:] = [m for m in tier_models if m.name != name]
            
    def get_available_models(self, tier: Optional[ModelTier] = None) -> List[ModelConfig]:
        """Get available models, optionally filtered by tier"""
        if tier:
            return [m for m in self._models[tier] if m.enabled]
        
        available = []
        for tier in ModelTier:
            available.extend([m for m in self._models[tier] if m.enabled])
        return available
    
    async def generate(
        self, 
        prompt: str,
        operation_type: str = "general",
        system_prompt: Optional[str] = None,
        max_fallback_tier: Optional[ModelTier] = None,
        context: Optional[Dict] = None
    ) -> ModelResponse:
        """
        Generate response using fallback chain
        
        Args:
            prompt: The user prompt
            operation_type: Type of operation (for static fallback selection)
            system_prompt: Optional system prompt
            max_fallback_tier: Maximum tier to fallback to
            context: Additional context
        """
        start_time = time.time()
        self._stats.total_calls += 1
        
        # Try each tier in order
        tiers_to_try = [ModelTier.PRIMARY, ModelTier.SECONDARY, 
                       ModelTier.TERTIARY, ModelTier.LOCAL]
        
        if max_fallback_tier:
            tier_index = tiers_to_try.index(max_fallback_tier)
            tiers_to_try = tiers_to_try[:tier_index + 1]
        
        last_error = None
        
        for tier in tiers_to_try:
            models = self.get_available_models(tier)
            
            for model_config in models:
                try:
                    response = await self._call_model(
                        model_config, prompt, system_prompt, context
                    )
                    
                    # Update stats
                    self._update_success_stats(tier, response)
                    self._stats.last_used_model = model_config.name
                    
                    logger.info(f"Successfully used {model_config.name} ({tier.name})")
                    return response
                    
                except Exception as e:
                    last_error = e
                    logger.warning(f"Model {model_config.name} failed: {e}")
                    continue
        
        # All models failed, use static fallback
        logger.error(f"All AI models failed, using static fallback")
        self._stats.total_failures += 1
        
        static_response = self._get_static_response(operation_type)
        
        return ModelResponse(
            content=static_response,
            model_used="static_fallback",
            tier=ModelTier.STATIC,
            latency_ms=(time.time() - start_time) * 1000,
            success=False,
            error=str(last_error) if last_error else "All models failed"
        )
    
    async def _call_model(
        self, 
        config: ModelConfig, 
        prompt: str, 
        system_prompt: Optional[str],
        context: Optional[Dict]
    ) -> ModelResponse:
        """Call a specific model with timeout and error handling"""
        start_time = time.time()
        
        try:
            # Use asyncio.wait_for for timeout
            result = await asyncio.wait_for(
                self._execute_model_call(config, prompt, system_prompt, context),
                timeout=config.timeout
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            return ModelResponse(
                content=result["content"],
                model_used=config.name,
                tier=config.tier,
                latency_ms=latency_ms,
                tokens_used=result.get("tokens_used", 0),
                cost=result.get("cost", 0.0),
                success=True,
                metadata=result.get("metadata", {})
            )
            
        except asyncio.TimeoutError:
            raise Exception(f"Model {config.name} timed out after {config.timeout}s")
        except Exception as e:
            raise Exception(f"Model {config.name} error: {e}")
    
    async def _execute_model_call(
        self, 
        config: ModelConfig, 
        prompt: str, 
        system_prompt: Optional[str],
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Execute the actual model call - to be implemented based on model type
        This is a template that should be customized for specific model types
        
        Example implementation for OpenAI:
        """
        # This should be overridden or extended for specific model types
        # Example for OpenAI:
        # return await self._call_openai(config, prompt, system_prompt)
        
        raise NotImplementedError("Model execution not implemented. "
                                   "Subclass and override _execute_model_call")
    
    def _update_success_stats(self, tier: ModelTier, response: ModelResponse):
        """Update statistics on successful call"""
        if tier == ModelTier.PRIMARY:
            self._stats.primary_success += 1
        elif tier == ModelTier.SECONDARY:
            self._stats.secondary_success += 1
        elif tier == ModelTier.TERTIARY:
            self._stats.tertiary_success += 1
        elif tier == ModelTier.LOCAL:
            self._stats.local_success += 1
        
        self._stats.total_cost += response.cost
        self._stats.total_tokens += response.tokens_used
        
        # Update average latency
        total_calls = (self._stats.primary_success + self._stats.secondary_success + 
                      self._stats.tertiary_success + self._stats.local_success)
        current_avg = self._stats.avg_latency_ms
        self._stats.avg_latency_ms = ((current_avg * (total_calls - 1)) + response.latency_ms) / total_calls
    
    def _get_static_response(self, operation_type: str) -> str:
        """Get static fallback response"""
        self._stats.static_fallback += 1
        return self.STATIC_RESPONSES.get(
            operation_type, 
            self.STATIC_RESPONSES["general_chat"]
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fallback chain statistics"""
        return self._stats.to_dict()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all models"""
        status = {}
        for tier, models in self._models.items():
            status[tier.name] = [
                {
                    "name": m.name,
                    "enabled": m.enabled,
                    "capabilities": m.capabilities,
                }
                for m in models
            ]
        return status


class DegradedModeHandler:
    """
    Handles degraded operation when full AI processing is unavailable
    Provides rule-based extraction and simple responses
    """
    
    def __init__(self):
        self._simple_patterns = {
            "extract_invoice": [
                r"vendor[\s:]*(.*?)[\n]",
                r"amount[\s:]*[$]?([\d,.]+)",
                r"date[\s:]*(.*?)[\n]",
                r"invoice[\s#:]*(\w+)",
            ]
        }
    
    async def process_invoice_simple(self, text: str) -> Dict[str, Any]:
        """
        Simple rule-based invoice extraction when AI is unavailable
        """
        result = {
            "vendor": None,
            "amount": None,
            "date": None,
            "invoice_number": None,
            "confidence": "low",
            "method": "rule_based_fallback",
        }
        
        # Try to extract amount (most important)
        amount_patterns = [
            r"total[\s:]*[$]?([\d,]+\.\d{2})",
            r"amount[\s:]*[$]?([\d,]+\.\d{2})",
            r"[$]([\d,]+\.\d{2})",
        ]
        
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    result["amount"] = float(match.group(1).replace(",", ""))
                    break
                except:
                    pass
        
        # Try to extract date
        date_patterns = [
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                result["date"] = match.group(1)
                break
        
        return result
    
    def create_degraded_response(self, extracted_data: Dict) -> str:
        """Create user-friendly response in degraded mode"""
        response = "I'm running in simplified mode. Here's what I found:\n\n"
        
        if extracted_data.get("amount"):
            response += f"💰 **Amount:** ${extracted_data['amount']}\n"
        if extracted_data.get("vendor"):
            response += f"🏢 **Vendor:** {extracted_data['vendor']}\n"
        if extracted_data.get("date"):
            response += f"📅 **Date:** {extracted_data['date']}\n"
        if extracted_data.get("invoice_number"):
            response += f"📄 **Invoice #:** {extracted_data['invoice_number']}\n"
        
        response += "\n⚠️ Please verify these details as I'm in fallback mode."
        
        return response
