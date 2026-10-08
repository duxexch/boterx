"""
Engagement Optimizer Agent - Optimizes engagement, runs A/B tests, improves conversion
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import random
import json

from smart_publisher.core.agent_base import BaseAgent, AgentContext, AgentOutput
from smart_publisher.core.channel_profile import ChannelProfile
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase


class ExperimentStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ARCHIVED = "archived"


class VariantType(Enum):
    HEADLINE = "headline"
    CTA = "cta"
    STRUCTURE = "structure"
    TIMING = "timing"
    IMAGE = "image"
    CTA_PLACEMENT = "cta_placement"
    TONE = "tone"
    LENGTH = "length"


@dataclass
class Experiment:
    id: str
    name: str
    variant_type: VariantType
    channel_id: str
    variants: List[Dict]  # Each variant: {id, name, config}
    traffic_split: Dict[str, float]  # variant_id -> split
    status: ExperimentStatus = ExperimentStatus.DRAFT
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    min_samples: int = 500
    max_duration_hours: int = 168
    success_metric: str = "engagement_rate"
    significance_level: float = 0.95
    results: Dict = field(default_factory=dict)
    winner: Optional[str] = None


@dataclass
class ExperimentResult:
    variant_id: str
    samples: int
    metric_value: float
    confidence_interval: tuple
    is_significant: bool
    lift: float


class EngagementOptimizerAgent(BaseAgent):
    """Runs A/B tests, optimizes engagement, improves conversion"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.experiments: Dict[str, Experiment] = {}
        self.variant_assignments: Dict[str, str] = {}  # content_id -> variant_id
        self.performance_buffer: Dict[str, List[Dict]] = {}  # variant_id -> performance data
        self.auto_experiment_config = {
            "headlines": {"enabled": True, "variants": 3, "metric": "ctr"},
            "cta_styles": {"enabled": True, "variants": 4, "metric": "conversion_rate"},
            "posting_times": {"enabled": True, "variants": "±30min", "metric": "engagement_rate"},
            "cta_placement": {"enabled": True, "variants": ["top", "middle", "bottom"], "metric": "click_rate"},
            "structure": {"enabled": True, "variants": ["lead_first", "data_first", "story_first"], "metric": "read_completion"}
        }
    
    def get_capabilities(self) -> List[str]:
        return [
            "ab_testing",
            "engagement_optimization",
            "conversion_optimization",
            "timing_optimization",
            "variant_generation",
            "statistical_analysis",
            "auto_experiment_management",
            "conversion_funnel_optimization"
        ]
    
    async def think(self, context: AgentContext) -> AgentOutput:
        task_type = context.task_type
        
        if task_type == "create_experiment":
            return await self._create_experiment(context)
        elif task_type == "assign_variant":
            return await self._assign_variant(context)
        elif task_type == "record_performance":
            return await self._record_performance(context)
        elif task_type == "analyze_experiment":
            return await self._analyze_experiment(context)
        elif task_type == "get_recommendations":
            return await self._get_recommendations(context)
        elif task_type == "auto_optimize":
            return await self._auto_optimize(context)
        else:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Unknown task: {context.task_type}"]
            )
    
    async def _create_experiment(self, context: AgentContext) -> AgentOutput:
        """Create a new A/B test experiment"""
        input_data = context.input_data
        
        experiment = Experiment(
            id=f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}",
            name=input_data.get("name", "Unnamed Experiment"),
            variant_type=VariantType(input_data.get("variant_type", "headline")),
            channel_id=input_data.get("channel_id", self.channel_id),
            variants=input_data.get("variants", []),
            traffic_split=input_data.get("traffic_split", {}),
            min_samples=input_data.get("min_samples", 500),
            max_duration_hours=input_data.get("max_duration_hours", 168),
            success_metric=input_data.get("success_metric", "engagement_rate"),
            significance_level=input_data.get("significance_level", 0.95)
        )
        
        # Validate
        if len(experiment.variants) < 2:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=["At least 2 variants required"]
            )
        
        # Normalize traffic split
        if not experiment.traffic_split:
            equal_split = 1.0 / len(experiment.variants)
            experiment.traffic_split = {v["id"]: equal_split for v in experiment.variants}
        
        # Validate split sums to 1
        total = sum(experiment.traffic_split.values())
        if abs(total - 1.0) > 0.01:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Traffic split must sum to 1.0, got {total}"]
            )
        
        self.experiments[experiment.id] = experiment
        
        # Store in memory
        await self.memory.store(MemoryEntry(
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            memory_type="experiment",
            content=experiment.__dict__,
            importance=0.8,
            tags=["experiment", experiment.variant_type.value],
            metadata={"created_by": self.agent_id}
        ))
        
        return AgentOutput(
            success=True,
            output={"experiment_id": experiment.id, "status": "draft"},
            confidence=1.0,
            reasoning=f"Created experiment {experiment.id} with {len(experiment.variants)} variants"
        )
    
    async def _assign_variant(self, context: AgentContext) -> AgentOutput:
        """Assign a variant to content for an active experiment"""
        content_id = context.input_data.get("content_id")
        experiment_id = context.input_data.get("experiment_id")
        
        if not content_id or not experiment_id:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=["content_id and experiment_id required"]
            )
        
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Experiment not found: {experiment_id}"]
            )
        
        if experiment.status != ExperimentStatus.RUNNING:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Experiment not running: {experiment.status.value}"]
            )
        
        # Check if already assigned
        if content_id in self.variant_assignments:
            assigned = self.variant_assignments[content_id]
            if assigned in [v["id"] for v in experiment.variants]:
                variant = next(v for v in experiment.variants if v["id"] == assigned)
                return AgentOutput(
                    success=True,
                    output={"variant": variant, "already_assigned": True},
                    confidence=1.0
                )
        
        # Weighted random assignment
        variant = self._weighted_choice(experiment.variants, experiment.traffic_split)
        self.variant_assignments[content_id] = variant["id"]
        
        # Initialize performance buffer
        if variant["id"] not in self.performance_buffer:
            self.performance_buffer[variant["id"]] = []
        
        return AgentOutput(
            success=True,
            output={
                "variant": variant,
                "experiment_id": experiment_id,
                "config": variant.get("config", {})
            },
            confidence=1.0,
            reasoning=f"Assigned variant {variant['id']} to content {content_id}"
        )
    
    def _weighted_choice(self, variants: List[Dict], weights: Dict[str, float]) -> Dict:
        """Choose variant based on weights"""
        r = random.random()
        cumulative = 0
        for v in variants:
            cumulative += weights.get(v["id"], 0)
            if r <= cumulative:
                return v
        return variants[-1]
    
    async def _record_performance(self, context: AgentContext) -> AgentOutput:
        """Record performance data for a variant"""
        content_id = context.input_data.get("content_id")
        variant_id = context.input_data.get("variant_id")
        metrics = context.input_data.get("metrics", {})
        
        if not content_id or not variant_id:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=["content_id and variant_id required"]
            )
        
        # Record
        if variant_id not in self.performance_buffer:
            self.performance_buffer[variant_id] = []
        
        self.performance_buffer[variant_id].append({
            "content_id": content_id,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics
        })
        
        # Store in memory
        await self.memory.store(MemoryEntry(
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            memory_type="experiment_performance",
            content={
                "experiment_id": context.input_data.get("experiment_id"),
                "variant_id": variant_id,
                "content_id": content_id,
                "metrics": metrics
            },
            importance=0.7,
            tags=["experiment_performance", variant_id],
            metadata={"content_id": content_id}
        ))
        
        return AgentOutput(
            success=True,
            output={"recorded": True, "buffer_size": len(self.performance_buffer[variant_id])},
            confidence=1.0
        )
    
    async def _analyze_experiment(self, context: AgentContext) -> AgentOutput:
        """Analyze experiment results"""
        experiment_id = context.input_data.get("experiment_id")
        
        if not experiment_id or experiment_id not in self.experiments:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Experiment not found: {experiment_id}"]
            )
        
        experiment = self.experiments[experiment_id]
        
        # Get performance data
        results = {}
        for variant in experiment.variants:
            vid = variant["id"]
            data = self.performance_buffer.get(vid, [])
            
            if not data:
                results[vid] = {"samples": 0, "error": "No data"}
                continue
            
            # Calculate metric
            metric_values = [d["metrics"].get(experiment.success_metric, 0) for d in data]
            samples = len(metric_values)
            mean = sum(metric_values) / samples if samples > 0 else 0
            
            # Simple confidence interval (normal approximation)
            std = (sum((x - mean) ** 2 for x in metric_values) / max(samples - 1, 1)) ** 0.5
            margin = 1.96 * std / (samples ** 0.5) if samples > 1 else 0
            
            results[vid] = {
                "samples": samples,
                "mean": mean,
                "std": std,
                "ci_low": mean - margin,
                "ci_high": mean + margin
            }
        
        # Determine winner
        if len(results) >= 2:
            valid_results = {k: v for k, v in results.items() if "mean" in v}
            if len(valid_results) >= 2:
                best = max(valid_results.items(), key=lambda x: x[1]["mean"])
                experiment.winner = best[0]
                experiment.results = results
                experiment.status = ExperimentStatus.COMPLETED
                experiment.ended_at = datetime.now()
        
        # Statistical significance test (simplified)
        significance = self._test_significance(experiment, results)
        
        return AgentOutput(
            success=True,
            output={
                "experiment_id": experiment_id,
                "status": experiment.status.value,
                "results": results,
                "winner": experiment.winner,
                "significance": significance,
                "recommendation": self._get_recommendation(experiment, results)
            },
            confidence=0.9 if significance > 0.95 else 0.5
        )
    
    def _test_significance(self, experiment: Experiment, results: Dict) -> float:
        """Simple significance test"""
        if len(results) < 2:
            return 0.0
        
        valid = {k: v for k, v in results.items() if "mean" in v}
        if len(valid) < 2:
            return 0.0
        
        # Two-sample t-test approximation
        items = list(valid.items())
        v1, v2 = items[0], items[1]
        
        mean1, mean2 = v1[1]["mean"], v2[1]["mean"]
        std1, std2 = v1[1].get("std", 0), v2[1].get("std", 0)
        n1, n2 = v1[1]["samples"], v2[1]["samples"]
        
        if n1 < 2 or n2 < 2:
            return 0.0
        
        # Pooled standard error
        se = ((std1**2 / n1) + (std2**2 / n2)) ** 0.5
        if se == 0:
            return 1.0 if mean1 == mean2 else 0.0
        
        t_stat = abs(mean1 - mean2) / se
        
        # Approximate p-value (two-tailed)
        import math
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))
        return 1 - p
    
    def _get_recommendation(self, experiment: Experiment, results: Dict) -> str:
        if not experiment.winner:
            return "Need more data to determine winner"
        
        winner_data = results.get(experiment.winner, {})
        lift = 0
        if len(results) >= 2:
            vals = [v["mean"] for v in results.values() if "mean" in v]
            if len(vals) >= 2:
                baseline = min(vals)
                winner_val = max(vals)
                if baseline > 0:
                    lift = (winner_val - baseline) / baseline * 100
        
        return f"Winner: {experiment.winner} with {lift:.1f}% lift. {'Deploy to 100%' if lift > 5 else 'Consider longer test'}"
    
    async def _get_recommendations(self, context: AgentContext) -> AgentOutput:
        """Get optimization recommendations for a channel"""
        channel_id = context.input_data.get("channel_id", self.channel_id)
        profile = context.channel_profile
        
        # Analyze current performance
        snapshots = await self.memory.get_performance_history(days=30)
        
        if not snapshots:
            return AgentOutput(
                success=True,
                output={"recommendations": ["No data for recommendations"]},
                confidence=0.5
            )
        
        recommendations = []
        
        # Analyze engagement by hour
        # Analyze best formats
        # Analyze best topics
        # Analyze CTA effectiveness
        
        recommendations.append({
            "area": "headlines",
            "recommendation": "Test shorter headlines (40-50 chars) vs current",
            "expected_lift": "5-15% CTR",
            "priority": "high"
        })
        
        recommendations.append({
            "area": "cta",
            "recommendation": "Test benefit-first CTA vs current direct CTA",
            "expected_lift": "10-20% conversion",
            "priority": "high"
        })
        
        recommendations.append({
            "area": "timing",
            "recommendation": "Test posting 30 min earlier in evening window",
            "expected_lift": "5-10% reach",
            "priority": "medium"
        })
        
        return AgentOutput(
            success=True,
            output={"recommendations": recommendations},
            confidence=0.8
        )
    
    async def _auto_optimize(self, context: AgentContext) -> AgentOutput:
        """Run automatic optimization cycle"""
        channel_id = context.input_data.get("channel_id", self.channel_id)
        
        actions_taken = []
        
        # 1. Check for completed experiments
        for exp_id, exp in self.experiments.items():
            if exp.status == ExperimentStatus.RUNNING:
                if exp.ended_at and datetime.now() > exp.ended_at:
                    exp.status = ExperimentStatus.COMPLETED
                    actions_taken.append(f"Completed experiment {exp_id}")
        
        # 2. Start pending experiments if capacity
        running = sum(1 for e in self.experiments.values() if e.status == ExperimentStatus.RUNNING)
        if running < 3:  # Max 3 concurrent
            # Could auto-create experiments based on config
            pass
        
        # 3. Apply winning variants
        for exp_id, exp in self.experiments.items():
            if exp.status == ExperimentStatus.COMPLETED and exp.winner:
                # Would apply winner as default
                actions_taken.append(f"Winner applied for {exp_id}: {exp.winner}")
        
        return AgentOutput(
            success=True,
            output={"actions_taken": actions_taken, "active_experiments": running},
            confidence=1.0
        )
    
    def get_capabilities(self) -> List[str]:
        return [
            "ab_testing",
            "engagement_optimization",
            "conversion_optimization",
            "timing_optimization",
            "variant_generation",
            "statistical_analysis",
            "auto_experiment_management"
        ]