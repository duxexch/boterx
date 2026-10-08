"""
Agent Base Class - Foundation for All Intelligent Agents
Every agent has memory, understands its channel, learns, and improves.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import asyncio
import json
import logging
from pathlib import Path

from smart_publisher.core.channel_profile import ChannelProfile, ContentType, get_channel_manager
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase, MemoryEntry


logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    GENERATING = "generating"
    REVIEWING = "reviewing"
    LEARNING = "learning"
    ERROR = "error"


@dataclass
class AgentContext:
    """Context passed to agent for a task"""
    task_id: str
    task_type: str
    input_data: Dict
    channel_profile: 'ChannelProfile'
    shared_knowledge: List[Dict] = field(default_factory=list)
    relevant_memories: List[Dict] = field(default_factory=list)
    constraints: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


@dataclass
class AgentOutput:
    """Result of agent execution"""
    success: bool
    output: Any
    confidence: float = 1.0
    reasoning: str = ""
    used_memories: List[str] = field(default_factory=list)
    used_knowledge: List[str] = field(default_factory=list)
    new_memories: List[Dict] = field(default_factory=list)
    new_knowledge: List[Dict] = field(default_factory=list)
    metrics: Dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Base class for all intelligent agents"""
    
    def __init__(
        self,
        agent_id: str,
        channel_id: str,
        profile: ChannelProfile,
        persona_config: Dict,
        memory: 'AgentMemory',
        shared_knowledge: 'SharedKnowledgeBase',
        ai_client: Any = None
    ):
        self.agent_id = agent_id
        self.channel_id = channel_id
        self.profile = profile
        self.persona = persona_config
        self.memory = memory
        self.shared_knowledge = shared_knowledge
        self.ai_client = ai_client
        
        self.status = AgentStatus.IDLE
        self.current_task_id: Optional[str] = None
        self.metrics = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_confidence": 0.0,
            "avg_latency_ms": 0,
            "memories_created": 0,
            "knowledge_contributed": 0,
            "quality_score": 1.0,
        }
        self._lock = asyncio.Lock()
        self._last_heartbeat = datetime.now()
    
    @abstractmethod
    async def think(self, context: AgentContext) -> AgentOutput:
        """Main thinking process - implement in subclasses"""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent provides"""
        pass
    
    async def execute(self, context: AgentContext) -> AgentOutput:
        """Execute agent with full lifecycle"""
        async with self._lock:
            self.status = AgentStatus.THINKING
            self.current_task_id = context.task_id
            start_time = datetime.now()
            
            try:
                # Gather relevant context
                await self._enrich_context(context)
                
                # Think
                self.status = AgentStatus.GENERATING
                output = await self.think(context)
                
                # Review output quality
                self.status = AgentStatus.REVIEWING
                reviewed_output = await self._review_output(output, context)
                
                # Store memories
                await self._store_memories(reviewed_output, context)
                
                # Contribute knowledge if valuable
                await self._contribute_knowledge(reviewed_output, context)
                
                # Update metrics
                latency = (datetime.now() - start_time).total_seconds() * 1000
                self._update_metrics(reviewed_output, latency)
                
                self.status = AgentStatus.IDLE
                self._last_heartbeat = datetime.now()
                
                return reviewed_output
                
            except Exception as e:
                self.status = AgentStatus.ERROR
                self.metrics["tasks_failed"] += 1
                logger.error(f"Agent {self.agent_id} error: {e}", exc_info=True)
                return AgentOutput(
                    success=False,
                    output=None,
                    confidence=0.0,
                    reasoning=f"Error: {str(e)}",
                    errors=[str(e)]
                )
            finally:
                self.current_task_id = None
    
    async def _enrich_context(self, context: AgentContext):
        """Enrich context with relevant memories and knowledge"""
        # Get relevant memories
        relevant = await self.memory.query(
            memory_type="experience",
            tags=[context.task_type],
            min_importance=0.5,
            limit=10,
            order_by="importance"
        )
        context.relevant_memories = [m.content for m in relevant]
        
        # Get relevant patterns
        patterns = await self.memory.query(
            memory_type="pattern",
            limit=20,
            order_by="importance"
        )
        context.relevant_memories.extend([m.content for m in patterns])
        
        # Get active rules
        rules = await self.memory.get_active_rules()
        context.relevant_memories.extend([m.content for m in rules])
        
        # Get shared knowledge
        knowledge = await self.shared_knowledge.get_knowledge(
            category="best_practice",
            limit=10
        )
        context.shared_knowledge = knowledge
        
        # Channel-specific knowledge
        channel_knowledge = await self.shared_knowledge.get_knowledge(
            category="channel_specific",
            tags=[self.channel_id],
            limit=10
        )
        context.shared_knowledge.extend(channel_knowledge)
    
    async def _review_output(self, output: AgentOutput, context: AgentContext) -> AgentOutput:
        """Review and potentially improve output"""
        # Run through quality guardian checks
        if not output.success:
            return output
        
        # Check confidence threshold
        min_confidence = context.channel_profile.quality_gates.get("min_confidence", 0.5)
        if output.confidence < min_confidence:
            output.warnings.append(f"Confidence {output.confidence} below threshold {min_confidence}")
            output.confidence = min(output.confidence, min_confidence)
        
        # Validate against channel quality gates
        if hasattr(output.output, 'get'):  # dict-like output
            violations = context.channel_profile.validate_content(
                json.dumps(output.output, ensure_ascii=False),
                output.output
            )
            if violations:
                output.warnings.extend(violations)
                output.confidence *= 0.8
        
        return output
    
    async def _store_memories(self, output: AgentOutput, context: AgentContext):
        """Store new memories from this execution"""
        if not output.success:
            # Store failure as learning
            await self.memory.store(MemoryEntry(
                agent_id=self.agent_id,
                channel_id=self.channel_id,
                memory_type="experience",
                content={
                    "task_type": context.task_type,
                    "input": context.input_data,
                    "error": output.errors,
                    "reasoning": output.reasoning,
                    "lesson": "Failed execution - analyze for prevention"
                },
                importance=0.7,
                tags=["failure", context.task_type, "learning"],
                metadata={"task_id": context.task_id}
            ))
            return
        
        # Store successful experience
        exp_id = await self.memory.store(MemoryEntry(
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            memory_type="experience",
            content={
                "task_type": context.task_type,
                "input_summary": self._summarize_input(context.input_data),
                "output_summary": self._summarize_output(output.output),
                "reasoning": output.reasoning,
                "confidence": output.confidence,
                "metrics": output.metrics
            },
            importance=0.6,
            tags=["success", context.task_type],
            metadata={"task_id": context.task_id, "confidence": output.confidence}
        ))
        self.metrics["memories_created"] += 1
        
        # Store any new patterns discovered
        for pattern in output.new_memories:
            if pattern.get("type") == "pattern":
                await self.memory.store(MemoryEntry(
                    agent_id=self.agent_id,
                    channel_id=self.channel_id,
                    memory_type="pattern",
                    content=pattern,
                    importance=pattern.get("importance", 0.7),
                    tags=["pattern", pattern.get("category", "general")],
                    metadata={"source_task": context.task_id}
                ))
                self.metrics["memories_created"] += 1
    
    async def _contribute_knowledge(self, output: AgentOutput, context: AgentContext):
        """Contribute valuable knowledge to shared base"""
        for knowledge in output.new_knowledge:
            if knowledge.get("value_score", 0) >= 0.7:
                await self.shared_knowledge.add_knowledge(
                    category=knowledge.get("category", "best_practice"),
                    title=knowledge.get("title", "Untitled"),
                    content=knowledge.get("content", {}),
                    source_agent_id=self.agent_id,
                    source_channel_id=self.channel_id,
                    tags=knowledge.get("tags", []),
                    confidence=knowledge.get("confidence", 0.8)
                )
                self.metrics["knowledge_contributed"] += 1
    
    def _summarize_input(self, input_data: Dict) -> str:
        """Create brief summary of input"""
        if isinstance(input_data, dict):
            keys = list(input_data.keys())[:5]
            return f"Keys: {', '.join(keys)}"
        return str(input_data)[:100]
    
    def _summarize_output(self, output: Any) -> str:
        """Create brief summary of output"""
        if isinstance(output, dict):
            keys = list(output.keys())[:5]
            return f"Keys: {', '.join(keys)}"
        return str(output)[:100]
    
    def _update_metrics(self, output: AgentOutput, latency_ms: float):
        self.metrics["tasks_completed"] += 1
        self.metrics["avg_confidence"] = (
            (self.metrics["avg_confidence"] * (self.metrics["tasks_completed"] - 1) + output.confidence)
            / self.metrics["tasks_completed"]
        )
        self.metrics["avg_latency_ms"] = (
            (self.metrics["avg_latency_ms"] * (self.metrics["tasks_completed"] - 1) + latency_ms)
            / self.metrics["tasks_completed"]
        )
        if output.confidence > 0:
            self.metrics["quality_score"] = (
                self.metrics["quality_score"] * 0.95 + output.confidence * 0.05
            )
    
    async def learn_from_feedback(self, feedback: Dict):
        """Learn from explicit feedback (human or automated)"""
        feedback_type = feedback.get("type", "implicit")
        score = feedback.get("score", 0.5)  # 0-1
        
        # Store feedback as memory
        await self.memory.store(MemoryEntry(
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            memory_type="feedback",
            content={
                "feedback_type": feedback_type,
                "score": score,
                "details": feedback.get("details", ""),
                "related_task": feedback.get("task_id"),
                "action_taken": feedback.get("action", "recorded")
            },
            importance=0.8 if score < 0.4 else 0.5,
            tags=["feedback", feedback_type],
            metadata={"score": score}
        ))
        
        # If negative feedback, trigger learning
        if score < 0.4:
            await self._trigger_improvement(feedback)
    
    async def _trigger_improvement(self, feedback: Dict):
        """Trigger self-improvement based on negative feedback"""
        # Store as high-importance learning
        await self.memory.store(MemoryEntry(
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            memory_type="learning",
            content={
                "trigger": "negative_feedback",
                "feedback": feedback,
                "analysis": "Negative feedback received - analyze and adapt",
                "proposed_changes": []
            },
            importance=0.9,
            tags=["improvement", "negative_feedback"],
            metadata={"feedback_score": feedback.get("score", 0)}
        ))
        
        # Trigger self-improvement engine
        await self._request_self_improvement()
    
    async def _request_self_improvement(self):
        """Request self-improvement cycle"""
        # Store improvement request
        await self.memory.store(MemoryEntry(
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            memory_type="improvement_request",
            content={
                "trigger": "performance_degradation",
                "metrics_snapshot": self.get_metrics(),
                "requested_at": datetime.now().isoformat(),
                "status": "pending"
            },
            importance=0.8,
            tags=["self_improvement", "pending"],
            metadata={}
        ))
    
    def get_metrics(self) -> Dict:
        return self.metrics.copy()
    
    def get_status(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "channel_id": self.channel_id,
            "status": self.status.value,
            "current_task": self.current_task_id,
            "metrics": self.metrics,
            "last_heartbeat": self._last_heartbeat.isoformat()
        }
    
    async def health_check(self) -> Dict:
        """Health check for monitoring"""
        mem_stats = await self.memory.get_stats()
        return {
            "agent_id": self.agent_id,
            "healthy": self.status != AgentStatus.ERROR,
            "status": self.status.value,
            "metrics": self.metrics,
            "memory_stats": mem_stats,
            "uptime_seconds": (datetime.now() - self._last_heartbeat).total_seconds()
        }


class AgentFactory:
    """Factory for creating agents with proper dependencies"""
    
    def __init__(
        self,
        memory_db_path: str = "data/agent_memory.db",
        shared_kb_path: str = "data/shared_knowledge.db",
        ai_client: Any = None
    ):
        self.memory_db_path = memory_db_path
        self.shared_kb_path = shared_kb_path
        self.ai_client = ai_client
        self.channel_manager = get_channel_manager()
        self.shared_knowledge = SharedKnowledgeBase(shared_kb_path)
        self._agents: Dict[str, BaseAgent] = {}
        self._memories: Dict[str, AgentMemory] = {}
    
    async def initialize(self):
        await self.shared_knowledge.initialize()
    
    def create_agent(
        self,
        agent_type: str,
        channel_id: str,
        custom_config: Dict = None
    ) -> BaseAgent:
        """Create an agent of specified type for a channel"""
        
        # Get channel profile
        profile = self.channel_manager.get_profile(channel_id)
        if not profile:
            raise ValueError(f"Channel profile not found: {channel_id}")
        
        # Get agent ID
        agent_id = f"{agent_type}_{channel_id}"
        
        # Check if already created
        if agent_id in self._agents:
            return self._agents[agent_id]
        
        # Get persona config
        persona_config = self._get_persona_config(agent_type)
        if custom_config:
            persona_config.update(custom_config)
        
        # Create memory
        memory = AgentMemory(agent_id, channel_id, self.memory_db_path)
        
        # Create agent based on type
        agent = self._create_agent_instance(
            agent_type, agent_id, channel_id, profile,
            persona_config, memory, self.shared_knowledge
        )
        
        self._agents[agent_id] = agent
        self._memories[agent_id] = memory
        
        return agent
    
    def _get_persona_config(self, agent_type: str) -> Dict:
        """Load persona config from YAML"""
        # This would load from ai_personas.yaml
        # For now return defaults based on type
        personas = {
            "news_agent_ar": {"name": "news_agent_ar", "model": "claude-3-5-sonnet"},
            "prediction_agent_ar": {"name": "prediction_agent_ar", "model": "claude-3-5-sonnet"},
            "offers_agent_ar": {"name": "offers_agent_ar", "model": "claude-3-5-sonnet"},
            "analysis_agent_ar": {"name": "analysis_agent_ar", "model": "claude-3-opus"},
            "live_agent_ar": {"name": "live_agent_ar", "model": "gpt-4o-mini"},
            "content_strategist": {"name": "content_strategist", "model": "claude-3-5-sonnet"},
            "audience_analyst": {"name": "audience_analyst", "model": "claude-3-5-sonnet"},
            "quality_guardian": {"name": "quality_guardian", "model": "claude-3-5-sonnet"},
            "engagement_optimizer": {"name": "engagement_optimizer", "model": "claude-3-5-sonnet"},
        }
        return personas.get(agent_type, {"name": agent_type, "model": "claude-3-5-sonnet"})
    
    def _create_agent_instance(
        self,
        agent_type: str,
        agent_id: str,
        channel_id: str,
        profile: ChannelProfile,
        persona_config: Dict,
        memory: AgentMemory,
        shared_knowledge: SharedKnowledgeBase
    ) -> BaseAgent:
        """Create specific agent instance"""
        # Import here to avoid circular imports
        from smart_publisher.agents.channel_agent import ChannelAgent
        from smart_publisher.agents.content_strategist import ContentStrategistAgent
        from smart_publisher.agents.audience_analyst import AudienceAnalystAgent
        from smart_publisher.agents.quality_guardian import QualityGuardianAgent
        from smart_publisher.agents.engagement_optimizer import EngagementOptimizerAgent
        
        agent_map = {
            "news_agent_ar": ChannelAgent,
            "prediction_agent_ar": ChannelAgent,
            "offers_agent_ar": ChannelAgent,
            "analysis_agent_ar": ChannelAgent,
            "live_agent_ar": ChannelAgent,
            "content_strategist": ContentStrategistAgent,
            "audience_analyst": AudienceAnalystAgent,
            "quality_guardian": QualityGuardianAgent,
            "engagement_optimizer": EngagementOptimizerAgent,
        }
        
        agent_class = agent_map.get(agent_type, ChannelAgent)
        return agent_class(
            agent_id=agent_id,
            channel_id=channel_id,
            profile=profile,
            persona_config=persona_config,
            memory=memory,
            shared_knowledge=self.shared_knowledge,
            ai_client=self.ai_client
        )
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)
    
    async def initialize_all(self):
        """Initialize all agent memories"""
        for memory in self._memories.values():
            await memory.initialize()
    
    async def health_check_all(self) -> Dict:
        results = {}
        for agent_id, agent in self._agents.items():
            results[agent_id] = await agent.health_check()
        return results
    
    async def get_all_metrics(self) -> Dict:
        return {aid: agent.get_metrics() for aid, agent in self._agents.items()}