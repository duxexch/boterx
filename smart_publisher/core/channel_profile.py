"""
Channel Profile System - Deep Understanding of Each Channel
Every channel has a complete identity, audience model, and rules.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import time
from enum import Enum
from pathlib import Path
import yaml
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    NEWS = "news"
    BREAKING = "breaking"
    INJURY = "injury"
    TRANSFER = "transfer"
    LINEUP = "lineup"
    PREDICTION = "prediction"
    PREVIEW = "preview"
    ODDS_ANALYSIS = "odds_analysis"
    VALUE_BET = "value_bet"
    LIVE_UPDATE = "live_update"
    GOAL = "goal"
    CARD = "card"
    SUBSTITUTION = "substitution"
    MOMENTUM_SHIFT = "momentum_shift"
    PROMO = "promo"
    WELCOME_BONUS = "welcome_bonus"
    FREE_BET = "free_bet"
    CASHBACK = "cashback"
    ENHANCED_ODDS = "enhanced_odds"
    LOYALTY = "loyalty"
    DEEP_ANALYSIS = "deep_analysis"
    TACTICAL_BREAKDOWN = "tactical_breakdown"
    STATISTICAL_MODEL = "statistical_model"
    BETTING_STRATEGY = "betting_strategy"
    LIVE_UPDATE = "live_update"


class Tone(str, Enum):
    URGENT_PROFESSIONAL = "urgent_professional"
    CONFIDENT_ANALYTICAL = "confident_analytical"
    INSTANT_INSIGHTFUL = "instant_insightful"
    EXCITING_VALUE_FOCUSED = "exciting_value_focused"
    DEEP_EDUCATIONAL = "deep_educational"


class ChannelProfile(BaseModel):
    """Complete profile of a channel - its identity, audience, rules, and AI agent config"""
    
    # Basic Identity
    id: str
    name: str
    handle: str
    language: str = "ar"
    primary_type: ContentType
    allowed_types: List[ContentType] = []
    forbidden_types: List[ContentType] = []
    
    # AI Agent Identity
    identity: Dict[str, Any] = Field(default_factory=dict)
    
    # Audience Model
    audience: Dict[str, Any] = Field(default_factory=dict)
    
    # Formatting Rules
    formatting: Dict[str, Any] = Field(default_factory=dict)
    
    # Scheduling
    scheduling: Dict[str, Any] = Field(default_factory=dict)
    
    # Quality Gates
    quality_gates: Dict[str, Any] = Field(default_factory=dict)
    
    # AI Agent Config
    ai_agent: Dict[str, Any] = Field(default_factory=dict)
    
    # Runtime State (populated at runtime)
    _runtime_stats: Dict[str, Any] = field(default_factory=dict, exclude=True)
    
    def can_publish_type(self, content_type: ContentType) -> bool:
        """Check if this channel can publish this content type"""
        if content_type in self.forbidden_types:
            return False
        if self.allowed_types and content_type not in self.allowed_types:
            return False
        return True
    
    def get_system_prompt_path(self) -> Optional[str]:
        return self.ai_agent.get("system_prompt_file")
    
    def get_ai_config(self) -> Dict[str, Any]:
        return {
            "model": self.ai_agent.get("model", "claude-3-5-sonnet"),
            "temperature": self.ai_agent.get("temperature", 0.3),
            "max_tokens": self.ai_agent.get("max_tokens", 2000),
            "system_prompt_file": self.ai_agent.get("system_prompt_file"),
            "memory_retention_days": self.ai_agent.get("memory_retention_days", 90),
        }
    
    def is_in_quiet_hours(self, current_time: time) -> bool:
        quiet = self.scheduling.get("quiet_hours", "")
        if not quiet:
            return False
        start_str, end_str = quiet.split("-")
        start = time.fromisoformat(start_str)
        end = time.fromisoformat(end_str)
        if start <= end:
            return start <= current_time <= end
        else:  # crosses midnight
            return current_time >= start or current_time <= end
    
    def is_in_best_window(self, current_time: time) -> bool:
        windows = self.scheduling.get("best_windows", [])
        for window in windows:
            start_str, end_str = window.split("-")
            start = time.fromisoformat(start_str)
            end = time.fromisoformat(end_str)
            if start <= end:
                if start <= current_time <= end:
                    return True
            else:
                if current_time >= start or current_time <= end:
                    return True
        return False
    
    def get_required_tags(self) -> List[str]:
        return self.formatting.get("required_tags", [])
    
    def get_optional_tags(self) -> List[str]:
        return self.formatting.get("optional_tags", [])
    
    def get_max_length(self) -> int:
        return self.formatting.get("max_length", 1000)
    
    def validate_content(self, content: str, metadata: Dict) -> List[str]:
        """Validate content against quality gates - returns list of violations"""
        violations = []
        
        # Min Arabic chars
        min_arabic = self.quality_gates.get("min_arabic_chars", 0)
        if min_arabic:
            arabic_chars = sum(1 for c in content if '\u0600' <= c <= '\u06FF')
            if arabic_chars < min_arabic:
                violations.append(f"Arabic chars {arabic_chars} < {min_arabic}")
        
        # Require source
        if self.quality_gates.get("require_source", False):
            if not metadata.get("source"):
                violations.append("Missing required source")
        
        # Require impact analysis
        if self.quality_gates.get("require_impact_analysis", False):
            if not metadata.get("impact_analysis"):
                violations.append("Missing impact analysis")
        
        # Require odds
        if self.quality_gates.get("require_odds", False):
            if not metadata.get("odds"):
                violations.append("Missing odds")
        
        # Require probabilities
        if self.quality_gates.get("require_probabilities", False):
            if not metadata.get("probabilities"):
                violations.append("Missing probabilities")
        
        # Require tactical reasoning
        if self.quality_gates.get("require_tactical_reasoning", False):
            if not metadata.get("tactical_reasoning"):
                violations.append("Missing tactical reasoning")
        
        # Forbid clickbait
        if self.quality_gates.get("forbid_clickbait", False):
            clickbait_patterns = ["مضمون 100", "ضمان الربح", "لا تخسر", "فرصة عمرك"]
            for pattern in clickbait_patterns:
                if pattern in content:
                    violations.append(f"Clickbait detected: {pattern}")
        
        # Forbid guaranteed language
        if self.quality_gates.get("forbid_guaranteed_language", False):
            guaranteed = ["مضمون", "أكيد", "بالتأكيد", "100%", "بلا مخاطر"]
            for word in guaranteed:
                if word in content:
                    violations.append(f"Guaranteed language: {word}")
        
        # Min confidence
        min_conf = self.quality_gates.get("min_confidence", 0)
        if min_conf and metadata.get("confidence", 1) < min_conf:
            violations.append(f"Confidence {metadata.get('confidence')} < {min_conf}")
        
        # Max length
        max_len = self.get_max_length()
        if len(content) > max_len:
            violations.append(f"Content length {len(content)} > {max_len}")
        
        return violations


class ChannelProfileManager:
    """Manages all channel profiles"""
    
    def __init__(self, config_path: str = "config/channels.yaml"):
        self.config_path = Path(config_path)
        self.profiles: Dict[str, ChannelProfile] = {}
        self._load_profiles()
    
    def _load_profiles(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        for ch_data in data.get("channels", []):
            # Convert string types to enums
            if "primary_type" in ch_data:
                ch_data["primary_type"] = ContentType(ch_data["primary_type"])
            if "allowed_types" in ch_data:
                ch_data["allowed_types"] = [ContentType(t) for t in ch_data["allowed_types"]]
            if "forbidden_types" in ch_data:
                ch_data["forbidden_types"] = [ContentType(t) for t in ch_data["forbidden_types"]]
            
            profile = ChannelProfile(**ch_data)
            self.profiles[profile.id] = profile
        
        # Store global settings
        self.global_settings = data.get("global_settings", {})
    
    def get_profile(self, channel_id: str) -> Optional[ChannelProfile]:
        return self.profiles.get(channel_id)
    
    def get_profiles_for_type(self, content_type: ContentType) -> List[ChannelProfile]:
        return [p for p in self.profiles.values() if p.can_publish_type(content_type)]
    
    def get_all_profiles(self) -> List[ChannelProfile]:
        return list(self.profiles.values())
    
    def get_global_setting(self, key: str, default=None):
        keys = key.split(".")
        val = self.global_settings
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default


# Default instance
_profile_manager = None

def get_channel_manager(config_path: str = "config/channels.yaml") -> ChannelProfileManager:
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ChannelProfileManager(config_path)
    return _profile_manager