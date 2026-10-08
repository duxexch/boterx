"""
Self-Improvement Engine - Automated Learning and Optimization
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json
import statistics

from smart_publisher.core.agent_base import BaseAgent, AgentContext, AgentOutput
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase
from smart_publisher.core.channel_profile import ChannelProfile


class ImprovementType(Enum):
    PROMPT_UPDATE = "prompt_update"
    RULE_ADDITION = "rule_addition"
    TIMING_ADJUSTMENT = "timing_adjustment"
    FORMAT_TEMPLATE = "format_template"
    FORBIDDEN_PATTERN = "forbidden_pattern"
    CONFIDENCE_RECALIBRATION = "confidence_recalibration"
    STRATEGY_SHIFT = "strategy_shift"


@dataclass
class ImprovementProposal:
    id: str
    type: ImprovementType
    agent_id: str
    channel_id: str
    title: str
    description: str
    evidence: List[Dict]
    expected_impact: Dict  # metric -> expected change
    risk_level: str  # low, medium, high
    implementation: Dict  # how to implement
    status: str = "proposed"  # proposed, approved, implementing, deployed, rolled_back
    created_at: datetime = field(default_factory=datetime.now)
    deployed_at: Optional[datetime] = None
    rolled_back_at: Optional[datetime] = None
    metrics_before: Dict = field(default_factory=dict)
    metrics_after: Dict = field(default_factory=dict)


@dataclass
class Pattern:
    id: str
    pattern_type: str  # headline, structure, timing, cta, topic, format
    description: str
    evidence: List[Dict]
    confidence: float
    channels: List[str]
    performance_lift: float
    created_at: datetime = field(default_factory=datetime.now)
    usage_count: int = 0
    validated: bool = False


class SelfImprovementEngine(BaseAgent):
    """Automated self-improvement engine for the publishing system"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proposals: Dict[str, ImprovementProposal] = {}
        self.patterns: Dict[str, Pattern] = {}
        self.improvement_rules = self._load_improvement_rules()
        self.last_cycle: Optional[datetime] = None
        self.cycle_count = 0
    
    def get_capabilities(self) -> List[str]:
        return [
            "pattern_mining",
            "prompt_optimization",
            "rule_generation",
            "confidence_recalibration",
            "ab_test_management",
            "performance_analysis",
            "automated_deployment",
            "rollback_management"
        ]
    
    def _load_improvement_rules(self) -> Dict:
        """Load improvement rules from config"""
        # Would load from improvement_rules.yaml
        return {
            "prompt_update": {
                "trigger": "quality_drop > 10% OR new_pattern_confidence > 90%",
                "cooldown_hours": 168,
                "max_per_cycle": 2
            },
            "rule_addition": {
                "trigger": "pattern_frequency > 5 AND effect_size > 15%",
                "cooldown_hours": 72,
                "max_per_cycle": 3
            },
            "confidence_recalibration": {
                "trigger": "calibration_drift > 10%",
                "cooldown_hours": 168,
                "max_per_cycle": 1
            }
        }
    
    def get_capabilities(self) -> List[str]:
        return [
            "pattern_mining",
            "prompt_optimization",
            "rule_generation",
            "confidence_recalibration",
            "automated_deployment",
            "rollback_management"
        ]
    
    async def think(self, context: AgentContext) -> AgentOutput:
        task_type = context.task_type
        
        if task_type == "run_improvement_cycle":
            return await self._run_improvement_cycle(context)
        elif task_type == "mine_patterns":
            return await self._mine_patterns(context)
        elif task_type == "evaluate_proposals":
            return await self._evaluate_proposals(context)
        elif task_type == "deploy_improvement":
            return await self._deploy_improvement(context)
        elif task_type == "rollback_improvement":
            return await self._rollback_improvement(context)
        elif task_type == "recalibrate_confidence":
            return await self._recalibrate_confidence(context)
        else:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Unknown task: {context.task_type}"]
            )
    
    async def _run_improvement_cycle(self, context: AgentContext) -> AgentOutput:
        """Run a complete self-improvement cycle"""
        self.cycle_count += 1
        self.last_cycle = datetime.now()
        
        results = {
            "cycle": self.cycle_count,
            "started_at": self.last_cycle.isoformat(),
            "phases": {}
        }
        
        # Phase 1: Mine patterns from recent performance
        pattern_result = await self._mine_patterns(context)
        results["phases"]["pattern_mining"] = pattern_result.output
        
        # Phase 2: Generate improvement proposals
        proposals = await self._generate_proposals(context)
        results["phases"]["proposal_generation"] = {"proposals": len(proposals)}
        
        # Phase 3: Evaluate proposals
        eval_result = await self._evaluate_proposals(context)
        results["phases"]["evaluation"] = eval_result.output
        
        # Phase 4: Deploy approved improvements
        deploy_result = await self._deploy_approved(context)
        results["phases"]["deployment"] = deploy_result.output
        
        # Phase 5: Recalibrate confidence
        cal_result = await self._recalibrate_confidence(context)
        results["phases"]["calibration"] = cal_result.output
        
        results["completed_at"] = datetime.now().isoformat()
        
        return AgentOutput(
            success=True,
            output=results,
            confidence=0.9,
            reasoning=f"Completed improvement cycle #{self.cycle_count}"
        )
    
    async def _mine_patterns(self, context: AgentContext) -> AgentOutput:
        """Mine patterns from high-performing content"""
        days = context.input_data.get("days", 7)
        min_performance = context.input_data.get("min_performance", "top_10_percent")
        
        # Get performance data from all agents
        all_snapshots = []
        for agent_id, agent in self.factory._agents.items() if self.factory else {}:
            if hasattr(agent, 'memory'):
                snapshots = await agent.memory.get_performance_history(days=days)
                all_snapshots.extend(snapshots)
        
        if not all_snapshots:
            return AgentOutput(
                success=True,
                output={"patterns_found": 0, "message": "No performance data"},
                confidence=1.0
            )
        
        patterns_found = []
        
        # Analyze top performers
        # This would do actual pattern mining
        # For now, return simulated patterns
        
        patterns_found = [
            {
                "type": "headline",
                "pattern": "Numbered list headlines (\"5 أسباب...\") outperform by 23%",
                "evidence": ["5 posts with numbered headlines in top 10%"],
                "confidence": 0.82,
                "lift": 0.23
            },
            {
                "type": "structure",
                "pattern": "Lead paragraph + bullet points + CTA = 34% higher completion",
                "evidence": ["12 posts with structure in top 20%"],
                "confidence": 0.78,
                "lift": 0.34
            },
            {
                "type": "timing",
                "pattern": "Posts at 20:30 outperform 20:00 by 18%",
                "evidence": ["15 posts at 20:30 vs 20:00"],
                "confidence": 0.72,
                "lift": 0.18
            }
        ]
        
        # Store patterns
        for p in patterns_found:
            pattern = Pattern(
                id=f"pat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.patterns)}",
                pattern_type=p["type"],
                description=p["pattern"],
                evidence=p["evidence"],
                confidence=p["confidence"],
                channels=[self.channel_id],
                performance_lift=p["lift"]
            )
            self.patterns[pattern.id] = pattern
            
            # Store in memory
            await self.memory.store(MemoryEntry(
                agent_id=self.agent_id,
                channel_id=self.channel_id,
                memory_type="pattern",
                content=pattern.__dict__,
                importance=p["confidence"],
                tags=["pattern", p["type"]],
                metadata={"lift": p["lift"]}
            ))
        
        return AgentOutput(
            success=True,
            output={
                "patterns_found": len(patterns_found),
                "patterns": patterns_found
            },
            confidence=0.85
        )
    
    async def _generate_proposals(self, context: AgentContext) -> List[ImprovementProposal]:
        """Generate improvement proposals from patterns"""
        proposals = []
        
        for pattern in self.patterns.values():
            if not pattern.validated or pattern.usage_count > 5:
                continue
            
            if pattern.confidence < 0.75:
                continue
            
            if pattern.performance_lift < 0.10:
                continue
            
            # Generate proposal based on pattern type
            proposal = self._create_proposal_from_pattern(pattern)
            if proposal:
                proposals.append(proposal)
                self.proposals[proposal.id] = proposal
        
        return proposals
    
    def _create_proposal_from_pattern(self, pattern: Pattern) -> Optional[ImprovementProposal]:
        """Create improvement proposal from pattern"""
        
        proposal_templates = {
            "headline": {
                "type": ImprovementType.PROMPT_UPDATE,
                "title": f"Update headline strategy: {pattern.description[:50]}",
                "implementation": {
                    "action": "update_system_prompt",
                    "target": "channel_agents",
                    "change": f"Add headline strategy: {pattern.description}"
                }
            },
            "structure": {
                "type": ImprovementType.FORMAT_TEMPLATE,
                "title": f"Add structure template: {pattern.description[:50]}",
                "implementation": {
                    "action": "add_format_template",
                    "template": "lead_paragraph + bullets + cta",
                    "channels": pattern.channels
                }
            },
            "timing": {
                "type": ImprovementType.TIMING_ADJUSTMENT,
                "title": f"Adjust timing: {pattern.description[:50]}",
                "implementation": {
                    "action": "adjust_schedule",
                    "change": "Shift evening window +30 minutes",
                    "channels": pattern.channels
                }
            },
            "cta": {
                "type": ImprovementType.PROMPT_UPDATE,
                "title": f"Optimize CTA: {pattern.description[:50]}",
                "implementation": {
                    "action": "update_cta_templates",
                    "change": "Benefit-first CTA with urgency"
                }
            }
        }
        
        template = proposal_templates.get(pattern.pattern_type)
        if not template:
            return None
        
        proposal = ImprovementProposal(
            id=f"prop_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.proposals)}",
            type=template["type"],
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            title=template["title"],
            description=f"Based on pattern: {pattern.description}",
            evidence=pattern.evidence,
            expected_impact={"engagement_lift": pattern.performance_lift},
            risk_level="low" if pattern.confidence > 0.8 else "medium",
            implementation=template["implementation"],
            metrics_before={}
        )
        
        return proposal
    
    async def _evaluate_proposals(self, context: AgentContext) -> AgentOutput:
        """Evaluate and approve/reject proposals"""
        approved = []
        rejected = []
        
        for prop in self.proposals.values():
            if prop.status != "proposed":
                continue
            
            # Evaluation criteria
            approved_flag = True
            reasons = []
            
            # Check confidence
            if prop.expected_impact.get("engagement_lift", 0) < 0.05:
                approved_flag = False
                reasons.append("Expected lift too low (<5%)")
            
            # Check risk
            if prop.risk_level == "high":
                approved_flag = False
                reasons.append("Risk level too high")
            
            # Check evidence
            if len(prop.evidence) < 2:
                approved_flag = False
                reasons.append("Insufficient evidence")
            
            # Check cooldown
            rule_key = prop.type.value
            if rule_key in self.improvement_rules:
                rule = self.improvement_rules[rule_key]
                # Would check last deployment time
            
            if approved_flag:
                prop.status = "approved"
                approved.append(prop.id)
            else:
                prop.status = "rejected"
                prop.metadata = {"rejection_reasons": reasons}
                rejected.append(prop.id)
        
        return AgentOutput(
            success=True,
            output={
                "approved": approved,
                "rejected": rejected,
                "total_evaluated": len([p for p in self.proposals.values() if p.status == "proposed"])
            },
            confidence=0.9
        )
    
    async def _deploy_approved(self, context: AgentContext) -> AgentOutput:
        """Deploy approved improvements"""
        deployed = []
        
        for prop in self.proposals.values():
            if prop.status != "approved":
                continue
            
            # Deploy based on type
            success = await self._deploy_improvement(prop)
            
            if success:
                prop.status = "deployed"
                prop.deployed_at = datetime.now()
                prop.metrics_before = await self._capture_metrics(prop.channel_id)
                deployed.append(prop.id)
            else:
                prop.status = "failed"
        
        return AgentOutput(
            success=True,
            output={"deployed": deployed, "count": len(deployed)},
            confidence=0.9
        )
    
    async def _deploy_improvement(self, proposal: ImprovementProposal) -> bool:
        """Deploy a specific improvement"""
        try:
            impl = proposal.implementation
            action = impl.get("action")
            
            if action == "update_system_prompt":
                # Would update agent system prompts
                pass
            elif action == "add_format_template":
                # Would add format template
                pass
            elif action == "adjust_schedule":
                # Would adjust channel scheduling
                pass
            elif action == "update_cta_templates":
                # Would update CTA templates
                pass
            
            return True
        except Exception as e:
            logger.error(f"Deployment failed for {proposal.id}: {e}")
            return False
    
    async def _deploy_approved(self, context: AgentContext) -> AgentOutput:
        """Deploy all approved proposals"""
        return await self._deploy_improvement_all()
    
    async def _deploy_improvement_all(self) -> AgentOutput:
        deployed = []
        for prop in self.proposals.values():
            if prop.status == "approved":
                success = await self._deploy_improvement(prop)
                if success:
                    deployed.append(prop.id)
        
        return AgentOutput(
            success=True,
            output={"deployed": deployed},
            confidence=0.9
        )
    
    async def _capture_metrics(self, channel_id: str) -> Dict:
        """Capture current metrics for comparison"""
        # Would capture current performance metrics
        return {}
    
    async def _recalibrate_confidence(self, context: AgentContext) -> AgentOutput:
        """Recalibrate confidence scores for prediction agents"""
        # This would analyze prediction accuracy vs stated confidence
        return AgentOutput(
            success=True,
            output={"message": "Confidence recalibration - integrate with prediction_agent"},
            confidence=0.5
        )
    
    async def _rollback_improvement(self, context: AgentContext) -> AgentOutput:
        """Rollback a deployed improvement"""
        proposal_id = context.input_data.get("proposal_id")
        
        if proposal_id not in self.proposals:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Proposal not found: {proposal_id}"]
            )
        
        proposal = self.proposals[proposal_id]
        
        if proposal.status != "deployed":
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Proposal not deployed: {proposal.status}"]
            )
        
        # Rollback logic
        proposal.status = "rolled_back"
        proposal.rolled_back_at = datetime.now()
        
        return AgentOutput(
            success=True,
            output={"rolled_back": proposal_id},
            confidence=1.0
        )
    
    def get_capabilities(self) -> List[str]:
        return [
            "pattern_mining",
            "prompt_optimization",
            "rule_generation",
            "confidence_recalibration",
            "ab_test_management",
            "automated_deployment",
            "rollback_management"
        ]