"""
Publisher Orchestrator - Main Entry Point for Smart Publishing System
Coordinates all agents, manages workflow, handles scheduling and monitoring.
"""

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging
import signal
import sys
from pathlib import Path

from smart_publisher.core.agent_base import AgentFactory, BaseAgent
from smart_publisher.core.channel_profile import ChannelProfile, get_channel_manager
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase
from smart_publisher.agents.channel_agent import ChannelAgent
from smart_publisher.agents.content_strategist import ContentStrategistAgent
from smart_publisher.agents.audience_analyst import AudienceAnalystAgent
from smart_publisher.agents.quality_guardian import QualityGuardianAgent
from smart_publisher.agents.engagement_optimizer import EngagementOptimizerAgent


logger = logging.getLogger(__name__)


class OrchestratorStatus(Enum):
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ScheduledTask:
    id: str
    name: str
    coro: Callable
    interval_seconds: float
    next_run: datetime
    enabled: bool = True
    last_run: Optional[datetime] = None
    run_count: int = 0
    last_error: Optional[str] = None


class PublisherOrchestrator:
    """Main orchestrator for the smart publishing system"""
    
    def __init__(
        self,
        config_dir: str = "config",
        memory_db: str = "data/agent_memory.db",
        shared_kb_db: str = "data/shared_knowledge.db",
        ai_client: Any = None
    ):
        self.config_dir = Path(config_dir)
        self.memory_db = memory_db
        self.shared_kb_db = shared_kb_db
        self.ai_client = ai_client
        
        self.status = OrchestratorStatus.STARTING
        self.factory: Optional[AgentFactory] = None
        self.agents: Dict[str, BaseAgent] = {}
        self.scheduled_tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._main_loop_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            "started_at": None,
            "total_content_processed": 0,
            "total_published": 0,
            "total_failed": 0,
            "ab_tests_run": 0,
            "quality_blocks": 0,
            "improvements_triggered": 0
        }
    
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Publisher Orchestrator...")
        self.status = OrchestratorStatus.STARTING
        
        # Initialize agent factory
        self.factory = AgentFactory(
            memory_db_path=self.memory_db,
            shared_kb_path=self.shared_kb_db,
            ai_client=self.ai_client
        )
        await self.factory.initialize()
        
        # Create core agents
        await self._create_core_agents()
        
        # Setup scheduled tasks
        self._setup_scheduled_tasks()
        
        # Setup signal handlers
        self._setup_signals()
        
        self.status = OrchestratorStatus.RUNNING
        self.stats["started_at"] = datetime.now().isoformat()
        logger.info("Publisher Orchestrator initialized successfully")
    
    async def _create_core_agents(self):
        """Create all core agents for each channel"""
        channel_manager = get_channel_manager()
        profiles = channel_manager.get_all_profiles()
        
        # Create Content Strategist (global)
        strategist = self.factory.create_agent("content_strategist", "global")
        self.agents["content_strategist"] = strategist
        
        # Create Audience Analyst (global)
        analyst = self.factory.create_agent("audience_analyst", "global")
        self.agents["audience_analyst"] = analyst
        
        # Create Quality Guardian (global)
        guardian = self.factory.create_agent("quality_guardian", "global")
        self.agents["quality_guardian"] = guardian
        
        # Create Engagement Optimizer (global)
        optimizer = self.factory.create_agent("engagement_optimizer", "global")
        self.agents["engagement_optimizer"] = optimizer
        
        # Create Channel Agents for each channel
        for profile in profiles:
            agent_type = self._get_agent_type_for_channel(profile)
            agent = self.factory.create_agent(agent_type, profile.id)
            self.agents[f"{agent_type}_{profile.id}"] = agent
            
            # Store channel agent reference
            self.agents[f"channel_{profile.id}"] = agent
        
        logger.info(f"Created {len(self.agents)} agents")
    
    def _get_agent_type_for_channel(self, profile: ChannelProfile) -> str:
        """Map channel to agent type"""
        type_map = {
            "news": "news_agent_ar",
            "prediction": "prediction_agent_ar",
            "promo": "offers_agent_ar",
            "analysis": "analysis_agent_ar",
            "live": "live_agent_ar"
        }
        return type_map.get(profile.primary_type.value, "channel_agent")
    
    def _setup_scheduled_tasks(self):
        """Setup recurring scheduled tasks"""
        
        # Content processing pipeline (every 5 minutes)
        self.add_task(ScheduledTask(
            id="content_pipeline",
            name="Content Processing Pipeline",
            coro=self._run_content_pipeline,
            interval_seconds=300,
            next_run=datetime.now() + timedelta(seconds=30)
        ))
        
        # Quality audit (every hour)
        self.add_task(ScheduledTask(
            id="quality_audit",
            name="Quality Audit",
            coro=self._run_quality_audit,
            interval_seconds=3600,
            next_run=datetime.now() + timedelta(minutes=5)
        ))
        
        # Performance analysis (every 6 hours)
        self.add_task(ScheduledTask(
            id="performance_analysis",
            name="Performance Analysis",
            coro=self._run_performance_analysis,
            interval_seconds=21600,
            next_run=datetime.now() + timedelta(minutes=10)
        ))
        
        # Audience analysis (daily)
        self.add_task(ScheduledTask(
            id="audience_analysis",
            name="Audience Analysis",
            coro=self._run_audience_analysis,
            interval_seconds=86400,
            next_run=datetime.now() + timedelta(hours=1)
        ))
        
        # Experiment management (every 30 minutes)
        self.add_task(ScheduledTask(
            id="experiment_management",
            name="Experiment Management",
            coro=self._run_experiment_management,
            interval_seconds=1800,
            next_run=datetime.now() + timedelta(minutes=15)
        ))
        
        # Self-improvement cycle (every 6 hours)
        self.add_task(ScheduledTask(
            id="self_improvement",
            name="Self Improvement Cycle",
            coro=self._run_self_improvement,
            interval_seconds=21600,
            next_run=datetime.now() + timedelta(hours=2)
        ))
        
        # Health check (every 5 minutes)
        self.add_task(ScheduledTask(
            id="health_check",
            name="Health Check",
            coro=self._run_health_check,
            interval_seconds=300,
            next_run=datetime.now() + timedelta(seconds=60)
        ))
        
        # Memory cleanup (daily)
        self.add_task(ScheduledTask(
            id="memory_cleanup",
            name="Memory Cleanup",
            coro=self._run_memory_cleanup,
            interval_seconds=86400,
            next_run=datetime.now() + timedelta(hours=3)
        ))
    
    def add_task(self, task: ScheduledTask):
        self.scheduled_tasks[task.id] = task
    
    async def start(self):
        """Start the orchestrator"""
        if self.running:
            return
        
        self.running = True
        self._shutdown_event.clear()
        
        # Start main loop
        self._main_loop_task = asyncio.create_task(self._main_loop())
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("Publisher Orchestrator started")
    
    async def stop(self):
        """Stop the orchestrator gracefully"""
        logger.info("Stopping Publisher Orchestrator...")
        self.running = False
        self._shutdown_event.set()
        
        # Cancel tasks
        if self._main_loop_task:
            self._main_loop_task.cancel()
        if self._scheduler_task:
            self._scheduler_task.cancel()
        
        # Wait for tasks to complete
        try:
            await asyncio.gather(
                self._main_loop_task,
                self._scheduler_task,
                return_exceptions=True
            )
        except asyncio.CancelledError:
            pass
        
        self.status = OrchestratorStatus.STOPPED
        logger.info("Publisher Orchestrator stopped")
    
    async def _main_loop(self):
        """Main processing loop"""
        while self.running and not self._shutdown_event.is_set():
            try:
                # Process content queue
                await self._process_content_queue()
                
                # Brief sleep to prevent busy loop
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(30)
    
    async def _scheduler_loop(self):
        """Scheduled tasks loop"""
        while self.running and not self._shutdown_event.is_set():
            try:
                now = datetime.now()
                
                for task in self.scheduled_tasks.values():
                    if not task.enabled:
                        continue
                    
                    if now >= task.next_run:
                        # Run task
                        asyncio.create_task(self._run_scheduled_task(task))
                
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                await asyncio.sleep(30)
    
    async def _run_scheduled_task(self, task: ScheduledTask):
        """Run a scheduled task with error handling"""
        task.last_run = datetime.now()
        task.run_count += 1
        
        try:
            await task.coro()
            task.last_error = None
        except Exception as e:
            task.last_error = str(e)
            logger.error(f"Task {task.name} failed: {e}", exc_info=True)
        finally:
            task.next_run = datetime.now() + timedelta(seconds=task.interval_seconds)
    
    async def _run_content_pipeline(self):
        """Main content processing pipeline"""
        logger.debug("Running content pipeline...")
        
        # This would:
        # 1. Fetch new signals from notification_watcher
        # 2. Route through content_strategist
        # 3. Generate content via channel agents
        # 4. Validate through quality_guardian
        # 5. Publish via unified_publisher
        
        # For now, just check for pending content
        pass
    
    async def _run_quality_audit(self):
        """Run quality audit on recent content"""
        logger.debug("Running quality audit...")
        
        guardian = self.agents.get("quality_guardian")
        if guardian:
            for channel_id in get_channel_manager().profiles.keys():
                try:
                    ctx = AgentContext(
                        task_id=f"audit_{datetime.now().timestamp()}",
                        task_type="audit_channel",
                        input_data={"channel_id": channel_id, "days": 7},
                        channel_profile=get_channel_manager().get_profiles()[0]  # would get correct one
                    )
                    # Actually need proper channel profile
                    pass
                except Exception as e:
                    logger.error(f"Quality audit failed: {e}")
    
    async def _run_performance_analysis(self):
        """Analyze performance across all channels"""
        logger.debug("Running performance analysis...")
        
        for agent_id, agent in self.agents.items():
            if hasattr(agent, '_analyze_performance'):
                try:
                    ctx = AgentContext(
                        task_id=f"perf_{datetime.now().timestamp()}",
                        task_type="analyze_performance",
                        input_data={},
                        channel_profile=get_channel_manager().get_profiles()[0]
                    )
                    # await agent._analyze_performance(ctx)
                except Exception as e:
                    logger.error(f"Performance analysis failed for {agent_id}: {e}")
    
    async def _run_audience_analysis(self):
        """Run audience analysis for all channels"""
        logger.debug("Running audience analysis...")
        
        analyst = self.agents.get("audience_analyst")
        if analyst:
            for channel_id in get_channel_manager().profiles.keys():
                try:
                    # Would run full audience analysis
                    pass
                except Exception as e:
                    logger.error(f"Audience analysis failed for {channel_id}: {e}")
    
    async def _run_experiment_management(self):
        """Manage A/B experiments"""
        logger.debug("Running experiment management...")
        
        optimizer = self.agents.get("engagement_optimizer")
        if optimizer:
            ctx = AgentContext(
                task_id=f"exp_mgmt_{datetime.now().timestamp()}",
                task_type="auto_optimize",
                input_data={},
                channel_profile=get_channel_manager().get_profiles()[0]
            )
            # await optimizer._auto_optimize(ctx)
    
    async def _run_self_improvement(self):
        """Run self-improvement cycle"""
        logger.debug("Running self-improvement cycle...")
        
        # This would trigger pattern mining, prompt updates, etc.
        pass
    
    async def _run_health_check(self):
        """Health check for all agents"""
        try:
            results = await self.factory.health_check_all()
            
            for agent_id, health in results.items():
                if not health.get("healthy", True):
                    logger.warning(f"Agent {agent_id} unhealthy: {health}")
                    
        except Exception as e:
            logger.error(f"Health check failed: {e}")
    
    async def _run_memory_cleanup(self):
        """Clean up old memories"""
        for agent_id, agent in self.agents.items():
            if hasattr(agent, 'memory'):
                await agent.memory.cleanup_old_memories(retention_days=90)
    
    async def _process_content_queue(self):
        """Process pending content in queue"""
        # This would process content from notification_watcher
        pass
    
    def _setup_signals(self):
        """Setup signal handlers for graceful shutdown"""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, lambda s, f: asyncio.create_task(self.stop()))
            except:
                pass  # Windows doesn't support all signals
    
    # ===== Public API Methods =====
    
    async def process_signal(self, signal_data: Dict) -> Dict:
        """Process a new signal from notification_watcher"""
        # 1. Create context
        context = AgentContext(
            task_id=f"signal_{datetime.now().timestamp()}",
            task_type="route_content",
            input_data={"signal": signal_data},
            channel_profile=signal_data.get("channel_profile")
        )
        
        # 2. Route through content strategist
        strategist = self.agents.get("content_strategist")
        if strategist:
            result = await strategist.execute(context)
            if result.success:
                return {"status": "routed", "decisions": result.output.get("decisions", [])}
        
        return {"status": "error", "message": "Routing failed"}
    
    async def generate_content(self, signal: Dict, channel_id: str) -> Dict:
        """Generate content for a specific channel"""
        # Get channel agent
        agent_key = f"channel_{channel_id}"
        agent = self.agents.get(agent_key)
        
        if not agent:
            return {"success": False, "error": f"No agent for channel {channel_id}"}
        
        context = AgentContext(
            task_id=f"gen_{datetime.now().timestamp()}",
            task_type="generate_content",
            input_data={
                "content_type": signal.get("content_type", "news"),
                "raw_content": signal.get("raw_content", ""),
                "source": signal.get("source", {}),
                "match_data": signal.get("match_data")
            },
            channel_profile=get_channel_manager().get_profile(channel_id)
        )
        
        result = await agent.execute(context)
        return {
            "success": result.success,
            "content": result.output,
            "confidence": result.confidence,
            "warnings": result.warnings
        }
    
    async def validate_and_publish(self, content: Dict, channel_id: str) -> Dict:
        """Validate content through quality guardian and publish"""
        # Validate
        guardian = self.agents.get("quality_guardian")
        if guardian:
            ctx = AgentContext(
                task_id=f"validate_{datetime.now().timestamp()}",
                task_type="validate_content",
                input_data={"content": content},
                channel_profile=get_channel_manager().get_profile(channel_id)
            )
            validation = await guardian.execute(ctx)
            
            if not validation.success:
                return {"success": False, "reason": "Quality validation failed", "details": validation.output}
        
        # Would publish via unified_publisher
        return {"success": True, "content": content}
    
    def get_status(self) -> Dict:
        return {
            "status": self.status.value,
            "running": self.running,
            "stats": self.stats,
            "agents": {aid: a.get_status() for aid, a in self.agents.items()},
            "scheduled_tasks": {
                tid: {
                    "name": t.name,
                    "enabled": t.enabled,
                    "next_run": t.next_run.isoformat(),
                    "run_count": t.run_count,
                    "last_error": t.last_error
                }
                for tid, t in self.scheduled_tasks.items()
            }
        }
    
    async def get_all_metrics(self) -> Dict:
        return await self.factory.get_all_metrics()


# CLI Entry Point
async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="VEX Smart Publisher Orchestrator")
    parser.add_argument("--config", default="config", help="Config directory")
    parser.add_argument("--memory-db", default="data/agent_memory.db", help="Memory database path")
    parser.add_argument("--shared-kb", default="data/shared_knowledge.db", help="Shared knowledge DB path")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    orchestrator = PublisherOrchestrator(
        config_dir=args.config,
        memory_db=args.memory_db,
        shared_kb_db=args.shared_kb
    )
    
    await orchestrator.initialize()
    
    if args.once:
        # Run once and exit
        print("Running once...")
        # Would run one cycle
    else:
        await orchestrator.start()
        try:
            await orchestrator._shutdown_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())