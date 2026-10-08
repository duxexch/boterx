"""
Smart Publisher - Intelligent Content Publishing System
"""

__version__ = "1.0.0"
__author__ = "VEX Deals"

from smart_publisher.core.channel_profile import (
    ChannelProfile,
    ContentType,
    ChannelProfileManager,
    get_channel_manager
)

from smart_publisher.core.agent_memory import (
    AgentMemory,
    SharedKnowledgeBase,
    MemoryEntry,
    AgentPerformanceSnapshot
)

from smart_publisher.core.agent_base import (
    BaseAgent,
    AgentContext,
    AgentOutput,
    AgentStatus,
    AgentFactory
)

from smart_publisher.agents.channel_agent import ChannelAgent
from smart_publisher.agents.content_strategist import ContentStrategistAgent, ContentPriority
from smart_publisher.agents.audience_analyst import AudienceAnalystAgent
from smart_publisher.agents.quality_guardian import QualityGuardianAgent, QualityViolation, QualityReport
from smart_publisher.agents.engagement_optimizer import EngagementOptimizerAgent, Experiment, ExperimentStatus

from smart_publisher.core.self_improvement import (
    SelfImprovementEngine,
    ImprovementProposal,
    Pattern,
    ImprovementType
)

from smart_publisher.orchestration.publisher_orchestrator import (
    PublisherOrchestrator,
    OrchestratorStatus,
    ScheduledTask
)

from smart_publisher.orchestration.content_pipeline import (
    ContentPipeline,
    PipelineStage,
    PipelineItem
)

from smart_publisher.orchestration.scheduling_engine import (
    SchedulingEngine,
    SchedulePriority,
    ScheduledItem
)

__all__ = [
    # Core
    "ChannelProfile",
    "ContentType",
    "ChannelProfileManager",
    "get_channel_manager",
    
    # Memory
    "AgentMemory",
    "SharedKnowledgeBase",
    "MemoryEntry",
    "AgentPerformanceSnapshot",
    
    # Agent Base
    "BaseAgent",
    "AgentContext",
    "AgentOutput",
    "AgentStatus",
    "AgentFactory",
    
    # Agents
    "ChannelAgent",
    "ContentStrategistAgent",
    "ContentPriority",
    "AudienceAnalystAgent",
    "QualityGuardianAgent",
    "QualityViolation",
    "QualityReport",
    "EngagementOptimizerAgent",
    "Experiment",
    "ExperimentStatus",
    
    # Self-Improvement
    "SelfImprovementEngine",
    "ImprovementProposal",
    "Pattern",
    "ImprovementType",
    
    # Orchestration
    "PublisherOrchestrator",
    "OrchestratorStatus",
    "ScheduledTask",
    "ContentPipeline",
    "PipelineStage",
    "PipelineItem",
    "SchedulingEngine",
    "SchedulePriority",
    "ScheduledItem",
]