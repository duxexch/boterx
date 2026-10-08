"""
Content Strategist Agent - Central Intelligence for Content Distribution
Decides what content goes where, when, and in what form.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import asyncio
import json

from smart_publisher.core.agent_base import BaseAgent, AgentContext, AgentOutput
from smart_publisher.core.channel_profile import ChannelProfile, ContentType
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase


class ContentPriority(Enum):
    BREAKING = "breaking"      # Urgent, immediate
    HIGH = "high"              # Important, within hour
    NORMAL = "normal"          # Regular scheduling
    LOW = "low"                # When capacity available
    EVERGREEN = "evergreen"    # Timeless, schedule anytime


@dataclass
class ContentRoutingDecision:
    channel_id: str
    priority: ContentPriority
    scheduled_time: Optional[datetime]
    adapted_form: Dict  # How content should be adapted
    reasoning: str
    confidence: float


class ContentStrategistAgent(BaseAgent):
    """Central intelligence for content strategy and distribution"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pending_decisions: Dict[str, ContentRoutingDecision] = {}
        self.content_calendar: Dict[str, List[Dict]] = {}  # channel_id -> scheduled items
        self.type_distribution: Dict[str, Dict[ContentType, int]] = {}  # channel -> type counts
    
    def get_capabilities(self) -> List[str]:
        return [
            "content_routing",
            "schedule_optimization",
            "type_balancing",
            "gap_analysis",
            "cross_channel_coordination",
            "priority_management"
        ]
    
    async def think(self, context: AgentContext) -> AgentOutput:
        task_type = context.task_type
        
        if task_type == "route_content":
            return await self._route_content(context)
        elif task_type == "optimize_schedule":
            return await self._optimize_schedule(context)
        elif task_type == "analyze_gaps":
            return await self._analyze_gaps(context)
        elif task_type == "balance_types":
            return await self._balance_types(context)
        elif task_type == "plan_calendar":
            return await self._plan_calendar(context)
        else:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Unknown task: {context.task_type}"]
            )
    
    async def _route_content(self, context: AgentContext) -> AgentOutput:
        """Decide which channels get this content and how"""
        input_data = context.input_data
        content = input_data.get("content", {})
        content_type = ContentType(input_data.get("content_type", "news"))
        source_signal = input_data.get("signal", {})
        urgency = input_data.get("urgency", "normal")
        
        # Get all compatible channels
        channel_manager = context.channel_profile.__class__.__module__
        # We'll use the channel manager from context
        channels = context.channel_profile  # This is actually the profile
        
        # Actually we need all channels - get from memory or config
        # For now, use the profile's channel manager
        from smart_publisher.core.channel_profile import get_channel_manager
        channel_manager = get_channel_manager()
        all_channels = channel_manager.get_all_profiles()
        
        decisions = []
        
        for profile in all_channels:
            if not profile.can_publish_type(content_type):
                continue
            
            # Calculate fit score
            fit_score = await self._calculate_fit_score(content, content_type, profile, source_signal)
            
            if fit_score < 0.4:
                continue
            
            # Determine priority
            priority = self._determine_priority(content, urgency, profile)
            
            # Calculate scheduled time
            scheduled_time = await self._calculate_schedule_time(profile, priority)
            
            # Determine adaptation needed
            adapted_form = await self._determine_adaptation(content, content_type, profile)
            
            # Confidence based on fit score
            confidence = min(0.9, fit_score + 0.1)
            
            decision = ContentRoutingDecision(
                channel_id=profile.id,
                priority=priority,
                scheduled_time=scheduled_time,
                adapted_form=adapted_form,
                reasoning=f"Fit score: {fit_score:.2f}, Priority: {priority.value}",
                confidence=confidence
            )
            
            decisions.append(decision)
        
        # Sort by priority and confidence
        priority_order = {ContentPriority.BREAKING: 0, ContentPriority.HIGH: 1, 
                         ContentPriority.NORMAL: 2, ContentPriority.LOW: 3, 
                         ContentPriority.EVERGREEN: 4}
        decisions.sort(key=lambda d: (priority_order[d.priority], -d.confidence))
        
        # Store decisions
        task_id = context.task_id
        for d in decisions:
            self.pending_decisions[f"{task_id}_{d.channel_id}"] = d
        
        return AgentOutput(
            success=True,
            output={
                "decisions": [
                    {
                        "channel_id": d.channel_id,
                        "priority": d.priority.value,
                        "scheduled_time": d.scheduled_time.isoformat() if d.scheduled_time else None,
                        "adapted_form": d.adapted_form,
                        "reasoning": d.reasoning,
                        "confidence": d.confidence
                    }
                    for d in decisions
                ],
                "total_channels": len(decisions),
                "content_type": str(content_type)
            },
            confidence=sum(d.confidence for d in decisions) / len(decisions) if decisions else 0,
            reasoning=f"Routed to {len(decisions)} channels"
        )
    
    async def _calculate_fit_score(
        self,
        content: Dict,
        content_type: ContentType,
        profile: ChannelProfile,
        source_signal: Dict
    ) -> float:
        """Calculate how well content fits a channel"""
        score = 0.0
        
        # Type compatibility (40%)
        if content_type == profile.primary_type:
            score += 0.4
        elif content_type in profile.allowed_types:
            score += 0.3
        else:
            score += 0.1
        
        # Language match (20%)
        content_lang = content.get("language", "ar")
        if content_lang == profile.language:
            score += 0.2
        
        # Source alignment (15%)
        source_type = source_signal.get("type", "")
        if source_type in ["official", "verified"] and "official" in profile.audience.get("pain_points", []):
            score += 0.15
        
        # Audience match (15%)
        audience_overlap = self._calculate_audience_overlap(content, profile)
        score += audience_overlap * 0.15
        
        # Current load balancing (10%)
        current_load = self._get_channel_load(profile.id)
        if current_load < 3:
            score += 0.1
        elif current_load > 8:
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _calculate_audience_overlap(self, content: Dict, profile: ChannelProfile) -> float:
        """Calculate content-audience fit"""
        content_tags = set(content.get("tags", []))
        audience_interests = set(profile.audience.get("engagement_triggers", []))
        
        if not audience_interests:
            return 0.5
        
        overlap = len(content_tags & audience_interests)
        return min(1.0, overlap / max(len(audience_interests), 1))
    
    def _get_channel_load(self, channel_id: str) -> int:
        """Get current scheduled items for channel"""
        return len(self.content_calendar.get(channel_id, []))
    
    def _determine_priority(self, content: Dict, urgency: str, profile: ChannelProfile) -> ContentPriority:
        if urgency == "breaking" or content.get("is_breaking"):
            return ContentPriority.BREAKING
        elif urgency == "high":
            return ContentPriority.HIGH
        elif urgency == "low":
            return ContentPriority.LOW
        elif content.get("evergreen"):
            return ContentPriority.EVERGREEN
        else:
            return ContentPriority.NORMAL
    
    async def _calculate_schedule_time(
        self,
        profile: ChannelProfile,
        priority: ContentPriority
    ) -> Optional[datetime]:
        now = datetime.now()
        
        if priority == ContentPriority.BREAKING:
            return now  # ASAP
        
        # Find next best window
        windows = profile.scheduling.get("best_windows", [])
        if not windows:
            return now + timedelta(minutes=profile.scheduling.get("frequency_minutes", 30))
        
        # Find next window
        current_time = now.time()
        for window in windows:
            start_str, end_str = window.split("-")
            start = datetime.strptime(start_str, "%H:%M").time()
            end = datetime.strptime(end_str, "%H:%M").time()
            
            if start <= current_time <= end:
                # In window, schedule soon
                return now + timedelta(minutes=5)
            elif current_time < start:
                # Next window today
                return datetime.combine(now.date(), start)
        
        # Next window tomorrow
        first_window = windows[0]
        start = datetime.strptime(first_window.split("-")[0], "%H:%M").time()
        return datetime.combine(now.date() + timedelta(days=1), start)
    
    async def _determine_adaptation(self, content: Dict, content_type: ContentType, profile: ChannelProfile) -> Dict:
        """Determine how content should be adapted for this channel"""
        return {
            "tone": profile.identity.get("tone", "professional"),
            "structure": profile.formatting.get("structure", "free"),
            "required_tags": profile.get_required_tags(),
            "max_length": profile.get_max_length(),
            "cta_style": profile.formatting.get("cta_style", "link"),
            "language": profile.language,
            "add_source_attribution": profile.quality_gates.get("require_source", False),
            "add_odds": profile.quality_gates.get("require_odds", False),
            "add_probabilities": profile.quality_gates.get("require_probabilities", False),
            "add_tactical_reasoning": profile.quality_gates.get("require_tactical_reasoning", False)
        }
    
    async def _optimize_schedule(self, context: AgentContext) -> AgentOutput:
        """Optimize posting schedule based on performance"""
        channel_id = context.input_data.get("channel_id")
        profile = context.channel_profile
        
        # Get performance data
        from smart_publisher.core.channel_profile import get_channel_manager
        channel_manager = get_channel_manager()
        profile = channel_manager.get_profile(channel_id) or profile
        
        # Get performance history
        snapshots = await self.memory.get_performance_history(days=30)
        
        if not snapshots:
            return AgentOutput(
                success=True,
                output={"message": "No performance data for optimization"},
                confidence=1.0
            )
        
        # Analyze best performing hours
        hour_performance = {}
        for snap in snapshots:
            for post_id in snap.top_performing_posts:
                # Would need post timestamps - simplified
                pass
        
        # For now, return current best windows
        return AgentOutput(
            success=True,
            output={
                "current_windows": profile.scheduling.get("best_windows"),
                "frequency_minutes": profile.scheduling.get("frequency_minutes"),
                "recommendations": [
                    "Monitor engagement by hour for 2 weeks",
                    "A/B test ±30 min around best windows",
                    "Consider audience timezone distribution"
                ]
            },
            confidence=0.7
        )
    
    async def _analyze_gaps(self, context: AgentContext) -> AgentOutput:
        """Analyze content gaps across channels"""
        channel_manager = context.channel_profile.__class__.__module__
        from smart_publisher.core.channel_profile import get_channel_manager
        channel_manager = get_channel_manager()
        all_profiles = channel_manager.get_all_profiles()
        
        gaps = []
        
        for profile in all_profiles:
            # Check type coverage
            allowed = profile.allowed_types
            if profile.primary_type not in allowed:
                gaps.append({
                    "channel": profile.id,
                    "gap": f"Primary type {profile.primary_type} not in allowed types",
                    "severity": "high"
                })
            
            # Check if any allowed type has zero posts recently
            # (would need performance data)
            
            # Check audience interest coverage
            interests = profile.audience.get("engagement_triggers", [])
            if len(interests) < 3:
                gaps.append({
                    "channel": profile.id,
                    "gap": "Few engagement triggers defined",
                    "severity": "medium"
                })
        
        return AgentOutput(
            success=True,
            output={"gaps": gaps, "total_channels": len(all_profiles)},
            confidence=0.8
        )
    
    async def _balance_types(self, context: AgentContext) -> AgentOutput:
        """Balance content types across channels"""
        return AgentOutput(
            success=True,
            output={"message": "Type balancing analysis - integrate with performance data"},
            confidence=0.5
        )
    
    async def _plan_calendar(self, context: AgentContext) -> AgentOutput:
        """Plan content calendar for upcoming period"""
        days = context.input_data.get("days", 7)
        channel_id = context.input_data.get("channel_id")
        
        profile = context.channel_profile
        if channel_id:
            from smart_publisher.core.channel_profile import get_channel_manager
            channel_manager = get_channel_manager()
            profile = channel_manager.get_profile(channel_id) or profile
        
        # Generate calendar skeleton
        calendar = []
        now = datetime.now()
        
        for day in range(days):
            date = now + timedelta(days=day)
            for window in profile.scheduling.get("best_windows", []):
                start_str = window.split("-")[0]
                start_time = datetime.strptime(start_str, "%H:%M").time()
                scheduled = datetime.combine(date.date(), start_time)
                
                freq = profile.scheduling.get("frequency_minutes", 60)
                slots = int(60 / freq * 2)  # 2 hours per window
                
                for i in range(slots):
                    slot_time = scheduled + timedelta(minutes=i * freq)
                    calendar.append({
                        "channel_id": profile.id,
                        "scheduled_time": slot_time.isoformat(),
                        "content_type": profile.primary_type.value,
                        "status": "planned"
                    })
        
        return AgentOutput(
            success=True,
            output={
                "calendar": calendar[:50],  # Limit
                "total_slots": len(calendar),
                "period_days": days
            },
            confidence=0.8
        )
    
    def get_capabilities(self) -> List[str]:
        return [
            "content_routing",
            "schedule_optimization", 
            "type_balancing",
            "gap_analysis",
            "cross_channel_coordination",
            "calendar_planning"
        ]