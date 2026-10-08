"""
Content Pipeline - End-to-end content processing
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import asyncio
import logging

from smart_publisher.core.agent_base import BaseAgent, AgentContext, AgentOutput
from smart_publisher.core.channel_profile import ChannelProfile, ContentType
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    INGEST = "ingest"
    ROUTE = "route"
    GENERATE = "generate"
    VALIDATE = "validate"
    OPTIMIZE = "optimize"
    SCHEDULE = "schedule"
    PUBLISH = "publish"
    MONITOR = "monitor"


@dataclass
class PipelineItem:
    id: str
    signal: Dict
    current_stage: PipelineStage
    channel_decisions: List[Dict] = field(default_factory=list)
    generated_content: Dict = field(default_factory=dict)
    validation_result: Optional[Dict] = None
    scheduled_time: Optional[datetime] = None
    published: bool = False
    published_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class ContentPipeline:
    """End-to-end content processing pipeline"""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.queue: asyncio.Queue = asyncio.Queue()
        self.processing: Dict[str, PipelineItem] = {}
        self.completed: Dict[str, PipelineItem] = {}
        self.failed: Dict[str, PipelineItem] = {}
        self.running = False
        self._worker_tasks: List[asyncio.Task] = []
        self.worker_count = 3
    
    async def start(self):
        """Start pipeline workers"""
        self.running = True
        for i in range(self.worker_count):
            task = asyncio.create_task(self._worker(f"worker-{i}"))
            self._worker_tasks.append(task)
        logger.info(f"Content pipeline started with {self.worker_count} workers")
    
    async def stop(self):
        """Stop pipeline workers"""
        self.running = False
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        logger.info("Content pipeline stopped")
    
    async def enqueue(self, signal: Dict) -> str:
        """Add signal to processing queue"""
        item = PipelineItem(
            id=f"pipe_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(signal)}",
            signal=signal,
            current_stage=PipelineStage.INGEST
        )
        await self.queue.put(item)
        return item.id
    
    async def _worker(self, worker_id: str):
        """Pipeline worker"""
        logger.info(f"Pipeline worker {worker_id} started")
        
        while True:
            try:
                item = await self.queue.get()
                self.processing[item.id] = item
                
                await self._process_item(item)
                
                self.queue.task_done()
                del self.processing[item.id]
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
    
    async def _process_item(self, item: PipelineItem):
        """Process a single pipeline item through all stages"""
        try:
            # Stage 1: Ingest
            item.current_stage = PipelineStage.INGEST
            item.updated_at = datetime.now()
            await self._ingest(item)
            
            # Stage 2: Route
            item.current_stage = PipelineStage.ROUTE
            item.updated_at = datetime.now()
            await self._route(item)
            
            # Stage 3: Generate content for each channel
            item.current_stage = PipelineStage.GENERATE
            item.updated_at = datetime.now()
            await self._generate_content(item)
            
            # Stage 4: Validate
            item.current_stage = PipelineStage.VALIDATE
            item.updated_at = datetime.now()
            await self._validate(item)
            
            # Stage 5: Optimize
            item.current_stage = PipelineStage.OPTIMIZE
            item.updated_at = datetime.now()
            await self._optimize(item)
            
            # Stage 6: Schedule
            item.current_stage = PipelineStage.SCHEDULE
            item.updated_at = datetime.now()
            await self._schedule(item)
            
            # Stage 7: Publish
            item.current_stage = PipelineStage.PUBLISH
            item.updated_at = datetime.now()
            await self._publish(item)
            
            # Stage 8: Monitor
            item.current_stage = PipelineStage.MONITOR
            item.updated_at = datetime.now()
            item.published = True
            item.published_at = datetime.now()
            self.completed[item.id] = item
            
        except Exception as e:
            item.error = str(e)
            item.current_stage = PipelineStage.PUBLISH
            self.failed[item.id] = item
            logger.error(f"Pipeline item {item.id} failed at {item.current_stage}: {e}")
    
    async def _ingest(self, item: PipelineItem):
        """Ingest and normalize signal"""
        signal = item.signal
        # Normalize signal data
        item.signal = {
            "id": signal.get("item_id", f"sig_{datetime.now().timestamp()}"),
            "title": signal.get("title", ""),
            "url": signal.get("url", ""),
            "source": signal.get("source", "unknown"),
            "source_url": signal.get("source_url", ""),
            "content_type": signal.get("content_type", "news"),
            "raw_content": signal.get("raw_content", signal.get("title", "")),
            "images": signal.get("images", []),
            "match_data": signal.get("match_data"),
            "timestamp": signal.get("timestamp", datetime.now().isoformat())
        }
    
    async def _route(self, item: PipelineItem):
        """Route content to appropriate channels"""
        strategist = self.orchestrator.agents.get("content_strategist")
        if not strategist:
            raise ValueError("Content strategist not available")
        
        context = AgentContext(
            task_id=f"route_{item.id}",
            task_type="route_content",
            input_data={
                "content": item.signal,
                "urgency": "normal"
            },
            channel_profile=item.signal.get("channel_profile")
        )
        
        result = await strategist.execute(context)
        if result.success:
            item.channel_decisions = result.output.get("decisions", [])
        else:
            raise ValueError(f"Routing failed: {result.errors}")
    
    async def _generate_content(self, item: PipelineItem):
        """Generate content for each target channel"""
        for decision in item.channel_decisions:
            channel_id = decision["channel_id"]
            agent_key = f"channel_{channel_id}"
            agent = self.orchestrator.agents.get(agent_key)
            
            if not agent:
                logger.warning(f"No agent for channel {channel_id}")
                continue
            
            context = AgentContext(
                task_id=f"gen_{item.id}_{channel_id}",
                task_type="generate_content",
                input_data={
                    "content_type": decision["adapted_form"].get("content_type", "news"),
                    "raw_content": item.signal["raw_content"],
                    "source": {
                        "name": item.signal["source"],
                        "url": item.signal["source_url"]
                    },
                    "match_data": item.signal.get("match_data")
                },
                channel_profile=get_channel_manager().get_profile(channel_id)
            )
            
            result = await agent.execute(context)
            if result.success:
                item.generated_content[channel_id] = result.output
            else:
                logger.warning(f"Generation failed for {channel_id}: {result.errors}")
    
    async def _validate(self, item: PipelineItem):
        """Validate all generated content"""
        guardian = self.orchestrator.agents.get("quality_guardian")
        if not guardian:
            raise ValueError("Quality guardian not available")
        
        for channel_id, content in item.generated_content.items():
            profile = get_channel_manager().get_profile(channel_id)
            if not profile:
                continue
            
            context = AgentContext(
                task_id=f"validate_{item.id}_{channel_id}",
                task_type="validate_content",
                input_data={"content": content},
                channel_profile=profile
            )
            
            result = await self.orchestrator.agents["quality_guardian"].execute(context)
            
            if not result.success:
                # Try auto-fix
                fix_result = await self.orchestrator.agents["quality_guardian"].execute(
                    AgentContext(
                        task_id=f"fix_{item.id}_{channel_id}",
                        task_type="suggest_fixes",
                        input_data={"content": content},
                        channel_profile=profile
                    )
                )
                # Apply fixes if possible
                # For now, just record validation result
                item.validation_result = {
                    "channel_id": channel_id,
                    "passed": result.success,
                    "score": result.confidence,
                    "violations": result.output.get("report", {}).get("violations", []) if result.output else []
                }
    
    async def _optimize(self, item: PipelineItem):
        """Optimize content for engagement"""
        optimizer = self.orchestrator.agents.get("engagement_optimizer")
        if not optimizer:
            return
        
        for channel_id, content in item.generated_content.items():
            # Check for active experiments
            # Assign variant if applicable
            pass
    
    async def _schedule(self, item: PipelineItem):
        """Schedule content for publishing"""
        for decision in item.channel_decisions:
            channel_id = decision["channel_id"]
            scheduled_time = decision.get("scheduled_time")
            
            if scheduled_time:
                if isinstance(scheduled_time, str):
                    scheduled_time = datetime.fromisoformat(scheduled_time)
                item.scheduled_time = scheduled_time
            else:
                # Schedule for immediate
                item.scheduled_time = datetime.now()
    
    async def _publish(self, item: PipelineItem):
        """Publish content to channels"""
        for channel_id, content in item.generated_content.items():
            # Validate again before publish
            # Then publish via unified_publisher
            pass
    
    def get_stats(self) -> Dict:
        return {
            "queue_size": self.queue.qsize(),
            "processing": len(self.processing),
            "completed": len(self.completed),
            "failed": len(self.failed)
        }


# Pipeline stages as standalone functions for testing
async def run_ingest_stage(signal: Dict) -> Dict:
    return {"normalized_signal": signal}

async def run_route_stage(signal: Dict, strategist) -> List[Dict]:
    return []

async def run_generate_stage(decisions: List[Dict], orchestrator) -> Dict[str, Dict]:
    return {}

async def run_validate_stage(content: Dict, guardian) -> Dict:
    return {"passed": True, "score": 1.0}

async def run_optimize_stage(content: Dict, optimizer) -> Dict:
    return content

async def run_schedule_stage(decisions: List[Dict]) -> datetime:
    return datetime.now()

async def run_publish_stage(content: Dict, publisher) -> bool:
    return True

async def run_monitor_stage(content_id: str, monitor) -> Dict:
    return {"status": "monitoring"}