"""
Channel Agent - Intelligent Agent for a Specific Channel
Each channel has its own agent with unique personality, memory, and learning.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import asyncio

from smart_publisher.core.agent_base import BaseAgent, AgentContext, AgentOutput
from smart_publisher.core.channel_profile import ChannelProfile, ContentType
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase


class ChannelAgent(BaseAgent):
    """Intelligent agent dedicated to a specific channel"""
    
    def __init__(
        self,
        agent_id: str,
        channel_id: str,
        profile: 'ChannelProfile',
        persona_config: Dict,
        memory: 'AgentMemory',
        shared_knowledge: 'SharedKnowledgeBase',
        ai_client: Any = None
    ):
        super().__init__(
            agent_id=agent_id,
            channel_id=channel_id,
            profile=profile,
            persona_config=persona_config,
            memory=memory,
            shared_knowledge=shared_knowledge,
            ai_client=ai_client
        )
        
        # Channel-specific state
        self.content_queue: asyncio.Queue = asyncio.Queue()
        self.pending_reviews: Dict[str, Dict] = {}
        self.performance_window: List[Dict] = []
        self._current_persona_prompt: Optional[str] = None
    
    def get_capabilities(self) -> List[str]:
        return [
            "content_generation",
            "content_adaptation",
            "quality_assessment",
            "audience_engagement",
            "performance_analysis",
            "self_improvement",
            "pattern_recognition",
            "trend_detection"
        ]
    
    async def think(self, context: AgentContext) -> AgentOutput:
        """Main thinking process for channel content generation"""
        
        task_type = context.task_type
        
        if task_type == "generate_content":
            return await self._generate_content(context)
        elif task_type == "adapt_content":
            return await self._adapt_content(context)
        elif task_type == "review_content":
            return await self._review_content(context)
        elif task_type == "analyze_performance":
            return await self._analyze_performance(context)
        elif task_type == "detect_trends":
            return await self._detect_trends(context)
        elif task_type == "optimize_schedule":
            return await self._optimize_schedule(context)
        else:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                reasoning=f"Unknown task type: {task_type}",
                errors=[f"Unsupported task type: {task_type}"]
            )
    
    async def _generate_content(self, context: AgentContext) -> AgentOutput:
        """Generate original content for this channel"""
        
        input_data = context.input_data
        content_type = ContentType(input_data.get("content_type", self.profile.primary_type))
        raw_content = input_data.get("raw_content", "")
        source_info = input_data.get("source", {})
        match_data = input_data.get("match_data")
        
        # Build generation prompt
        prompt = self._build_generation_prompt(
            content_type=content_type,
            raw_content=raw_content,
            source_info=source_info,
            match_data=match_data,
            context=context
        )
        
        # Generate using AI
        generated = await self._call_ai(prompt, context)
        
        if not generated:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                reasoning="AI generation failed",
                errors=["AI generation returned empty"]
            )
        
        # Post-process for channel
        adapted = await self._adapt_for_channel(generated, context)
        
        # Quality check
        violations = self.profile.validate_content(adapted["text"], adapted)
        if violations:
            # Try to fix
            adapted = await self._fix_violations(adapted, violations, context)
            # Re-validate
            violations = self.profile.validate_content(adapted["text"], adapted)
            if violations:
                return AgentOutput(
                    success=False,
                    output=adapted,
                    confidence=0.5,
                    reasoning=f"Quality violations after fix: {violations}",
                    warnings=violations
                )
        
        # Calculate confidence based on various factors
        confidence = self._calculate_confidence(adapted, context)
        
        return AgentOutput(
            success=True,
            output=adapted,
            confidence=confidence,
            reasoning=f"Generated {content_type.value} content for {self.profile.name}",
            used_memories=[m.get("id") for m in context.relevant_memories[:5]],
            new_memories=[{
                "type": "experience",
                "category": "content_generation",
                "content_type": str(content_type),
                "quality_score": confidence
            }]
        )
    
    def _build_generation_prompt(
        self,
        content_type: ContentType,
        raw_content: str,
        source_info: Dict,
        match_data: Optional[Dict],
        context: AgentContext
    ) -> str:
        """Build the generation prompt using persona and channel profile"""
        
        persona = self.persona.get("personality", {})
        identity = self.profile.identity
        
        # Base system prompt
        system_parts = [
            f"أنت {identity.get('persona_name', 'وكيل ذكي')}",
            f"دورك: {self.persona.get('role', 'محرر محتوى')}",
            f"القناة: {self.profile.name} ({self.profile.handle})",
            f"اللغة: {self.profile.language}",
            f"نوع المحتوى: {content_type.value}",
            "",
            "شخصيتك:",
        ]
        
        for trait in persona.get("traits", []):
            system_parts.append(f"- {trait}")
        
        system_parts.append("")
        system_parts.append("أسلوب التواصل:")
        for style in persona.get("communication_style", []):
            system_parts.append(f"- {style}")
        
        system_parts.append("")
        system_parts.append("خبرتك:")
        for exp in persona.get("expertise_areas", []):
            system_parts.append(f"- {exp}")
        
        system_parts.append("")
        system_parts.append("عملية التفكير:")
        for i, step in enumerate(persona.get("thinking_process", []), 1):
            system_parts.append(f"{i}. {step}")
        
        system_parts.append("")
        system_parts.append("معايير الجودة:")
        for std in persona.get("quality_standards", []):
            system_parts.append(f"- {std}")
        
        system_prompt = "\n".join(system_parts)
        
        # User prompt with actual content
        user_parts = [
            f"المحتوى الخام: {raw_content}",
            f"المصدر: {source_info.get('name', 'غير محدد')}",
            f"رابط المصدر: {source_info.get('url', 'غير متوفر')}",
        ]
        
        if match_data:
            user_parts.append(f"مباراة: {match_data.get('home', '')} × {match_data.get('away', '')}")
            user_parts.append(f"الدوري: {match_data.get('league', '')}")
            user_parts.append(f"الوقت: {match_data.get('kickoff', '')}")
            if match_data.get("odds"):
                user_parts.append(f"الأسعار: {match_data['odds']}")
        
        # Add relevant memories as context
        if context.relevant_memories:
            user_parts.append("\nخبرات ذات صلة:")
            for mem in context.relevant_memories[:3]:
                user_parts.append(f"- {json.dumps(mem, ensure_ascii=False)[:200]}")
        
        # Channel formatting requirements
        user_parts.append("\nمتطلبات القناة:")
        user_parts.append(f"- الوسوم المطلوبة: {', '.join(self.profile.get_required_tags())}")
        user_parts.append(f"- الطول الأقصى: {self.profile.get_max_length()} حرف")
        user_parts.append(f"- البنية: {self.profile.formatting.get('structure', 'حرة')}")
        user_parts.append(f"- النبرة: {identity.get('tone', 'مهني')}")
        
        # Quality gates reminder
        gates = self.profile.quality_gates
        if gates:
            user_parts.append("\nبوابات الجودة (مطلوبة):")
            if gates.get("require_source"):
                user_parts.append("- مصدر موثوق مطلوب")
            if gates.get("require_odds"):
                user_parts.append("- نسب/أسعار مطلوبة")
            if gates.get("require_tactical_reasoning"):
                user_parts.append("- أسباب تكتيكية/إحصائية مطلوبة")
            if gates.get("forbid_guaranteed_language"):
                user_parts.append("- ممنوع: كلمات ضمان (مضمون، أكيد، 100%)")
            if gates.get("forbid_clickbait"):
                user_parts.append("- ممنوع: كليك بيت (مضمون 100، فرصة عمرك...)")
        
        user_prompt = "\n".join(user_parts)
        
        return f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
    
    async def _call_ai(self, prompt: str, context: AgentContext) -> Optional[Dict]:
        """Call AI model to generate content"""
        if not self.ai_client:
            # Fallback: return structured template
            return self._fallback_generation(context)
        
        try:
            ai_config = self.profile.get_ai_config()
            
            response = await self.ai_client.chat.completions.create(
                model=ai_config["model"],
                messages=[
                    {"role": "system", "content": prompt.split("USER:")[0].replace("SYSTEM:\n", "")},
                    {"role": "user", "content": prompt.split("USER:")[1] if "USER:" in prompt else prompt}
                ],
                temperature=ai_config.get("temperature", 0.3),
                max_tokens=ai_config.get("max_tokens", 2000),
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"AI call failed: {e}")
            return self._fallback_generation(context)
    
    def _fallback_generation(self, context: AgentContext) -> Dict:
        """Fallback generation without AI"""
        input_data = context.input_data
        return {
            "title": input_data.get("title", "منشور جديد"),
            "text": context.input_data.get("raw_content", "محتوى غير متوفر"),
            "content_type": context.input_data.get("content_type", "news"),
            "tags": self.profile.get_required_tags(),
            "source": context.input_data.get("source", {}),
            "generated_at": datetime.now().isoformat(),
            "fallback": True
        }
    
    async def _adapt_for_channel(self, generated: Dict, context: AgentContext) -> Dict:
        """Adapt generated content for this specific channel"""
        
        adapted = generated.copy()
        
        # Ensure required tags
        required_tags = self.profile.get_required_tags()
        existing_tags = set(adapted.get("tags", []))
        for tag in required_tags:
            if tag not in existing_tags:
                adapted.setdefault("tags", []).append(tag)
        
        # Add channel branding
        adapted["channel_id"] = self.channel_id
        adapted["channel_name"] = self.profile.name
        adapted["language"] = self.profile.language
        adapted["generated_at"] = datetime.now().isoformat()
        adapted["agent_id"] = self.agent_id
        
        # Add CTA appropriate for channel
        adapted["cta"] = self._generate_cta(context)
        
        # Add tracking metadata
        adapted["metadata"] = {
            "agent_id": self.agent_id,
            "channel_id": self.channel_id,
            "content_type": context.input_data.get("content_type"),
            "generated_at": datetime.now().isoformat(),
            "version": 1
        }
        
        return adapted
    
    def _generate_cta(self, context: AgentContext) -> Dict:
        """Generate appropriate CTA for channel"""
        content_type = context.input_data.get("content_type", "news")
        
        ctas = {
            "prediction": {"text": "عرض التحليل الكامل", "url": "/predictions", "style": "primary"},
            "news": {"text": "متابعة الخبر", "url": "/news", "style": "secondary"},
            "promo": {"text": "احصل على العرض", "url": "/bonuses", "style": "primary"},
            "analysis": {"text": "قراءة التحليل الكامل", "url": "/analysis", "style": "primary"},
            "live": {"text": "متابعة مباشرة", "url": "/live", "style": "primary"}
        }
        
        return ctas.get(content_type, {"text": "المزيد", "url": "/", "style": "secondary"})
    
    async def _fix_violations(self, content: Dict, violations: List[str], context: AgentContext) -> Dict:
        """Attempt to fix quality violations"""
        fixed = content.copy()
        text = fixed.get("text", "")
        
        for violation in violations:
            if "Arabic chars" in violation:
                # Add Arabic content
                if "text" in fixed:
                    fixed["text"] = "📰 " + text
            
            elif "Missing required source" in violation:
                source = context.input_data.get("source", {}).get("name", "VEX Deals")
                fixed["text"] = f"{text}\n\n📌 المصدر: {source}"
            
            elif "Guaranteed language" in violation:
                # Remove guaranteed language
                forbidden = ["مضمون", "أكد", "بالتأكيد", "100%", "بلا مخاطر"]
                for word in ["مضمون", "مضمون100", "مضمون 100", "ربح مضمون", "ضمان الربح", "لا تخسر", "خطر صفر"]:
                    text = text.replace(word, "")
                fixed["text"] = text
            
            elif "Clickbait" in violation:
                # Remove clickbait phrases
                clickbait = ["فرصة عمرك", "لا تفوت", "أسرع الآن", "مضمون 100"]
                for phrase in clickbait:
                    text = text.replace(phrase, "")
                fixed["text"] = text
            
            elif "Confidence" in violation:
                # Reduce confidence claims
                text = text.replace("ثقة 100%", "ثقة عالية")
                text = text.replace("بالتأكيد", "باحتمالية عالية")
                fixed["text"] = text
            
            fixed["text"] = text
        
        return fixed
    
    def _calculate_confidence(self, adapted: Dict, context: AgentContext) -> float:
        """Calculate confidence score for generated content"""
        confidence = 0.7  # base
        
        # Boost for having required elements
        if adapted.get("tags"):
            confidence += 0.05
        if adapted.get("cta"):
            confidence += 0.05
        if context.relevant_memories:
            confidence += 0.05
        if context.shared_knowledge:
            confidence += 0.05
        
        # Reduce for fallback
        if adapted.get("fallback"):
            confidence -= 0.3
        
        return max(0.1, min(1.0, confidence))
    
    async def _adapt_content(self, context: AgentContext) -> AgentOutput:
        """Adapt existing content for this channel"""
        input_data = context.input_data
        source_content = input_data.get("content", {})
        
        # Use AI to adapt
        prompt = f"""
        عدّل هذا المحتوى ليناسب قناة "{self.profile.name}":
        
        المحتوى الأصلي: {json.dumps(source_content, ensure_ascii=False)}
        
        متطلبات القناة:
        - النبرة: {self.profile.identity.get('tone', 'مهني')}
        - البنية: {self.profile.formatting.get('structure', 'حرة')}
        - الوسوم: {', '.join(self.profile.get_required_tags())}
        - الطول: {self.profile.get_max_length()} حرف
        - اللغة: {self.profile.language}
        
        أعد المخرجات ك JSON مع: title, text, tags, cta
        """
        
        result = await self._call_ai(prompt, context)
        if result:
            adapted = await self._adapt_for_channel(result, context)
            return AgentOutput(
                success=True,
                output=adapted,
                confidence=0.8,
                reasoning="Content adapted for channel"
            )
        
        return AgentOutput(success=False, output=None, confidence=0, errors=["Adaptation failed"])
    
    async def _review_content(self, context: AgentContext) -> AgentOutput:
        """Review content for quality"""
        content = context.input_data.get("content", {})
        violations = self.profile.validate_content(
            content.get("text", ""), content
        )
        
        return AgentOutput(
            success=len(violations) == 0,
            output={"violations": violations, "passed": len(violations) == 0},
            confidence=1.0 if not violations else 0.5,
            reasoning=f"Found {len(violations)} violations",
            warnings=violations
        )
    
    async def _analyze_performance(self, context: AgentContext) -> AgentOutput:
        """Analyze recent performance"""
        # Get recent performance from memory
        snapshots = await self.memory.get_performance_history(days=7)
        
        if not snapshots:
            return AgentOutput(
                success=True,
                output={"message": "No performance data yet"},
                confidence=1.0
            )
        
        # Analyze trends
        avg_quality = sum(s.metrics.get("quality_score", 0) for s in snapshots) / len(snapshots)
        avg_engagement = sum(s.metrics.get("engagement_rate", 0) for s in snapshots) / len(snapshots)
        
        # Find patterns in top posts
        all_top_posts = []
        for s in snapshots:
            all_top_posts.extend(s.top_performing_posts)
        
        return AgentOutput(
            success=True,
            output={
                "period_days": 7,
                "posts_analyzed": sum(s.posts_count for s in snapshots),
                "avg_quality": avg_quality,
                "avg_engagement": avg_engagement,
                "top_posts_count": len(all_top_posts),
                "trend": "improving" if len(snapshots) > 1 and snapshots[0].metrics.get("quality_score", 0) > snapshots[-1].metrics.get("quality_score", 0) else "stable"
            },
            confidence=0.9,
            reasoning="Performance analysis complete"
        )
    
    async def _detect_trends(self, context: AgentContext) -> AgentOutput:
        """Detect content trends"""
        # This would integrate with audience_analyst
        return AgentOutput(
            success=True,
            output={"trends": [], "message": "Integrate with audience_analyst"},
            confidence=0.5
        )
    
    async def _optimize_schedule(self, context: AgentContext) -> AgentOutput:
        """Optimize posting schedule based on performance"""
        # Analyze best performing times
        return AgentOutput(
            success=True,
            output={"recommendations": [], "message": "Integrate with scheduling_engine"},
            confidence=0.5
        )
    
    async def learn_from_post_performance(self, post_id: str, metrics: Dict):
        """Learn from actual post performance"""
        # Store performance data
        await self.memory.store(MemoryEntry(
            agent_id=self.agent_id,
            channel_id=self.channel_id,
            memory_type="performance",
            content={
                "post_id": post_id,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat(),
                "channel_id": self.channel_id
            },
            importance=0.8,
            tags=["performance", "post_result"],
            metadata={"post_id": post_id}
        ))
        
        # Update performance window
        self.performance_window.append({"post_id": post_id, "metrics": metrics, "time": datetime.now()})
        if len(self.performance_window) > 100:
            self.performance_window = self.performance_window[-100:]
        
        # Trigger learning if performance is poor
        engagement = metrics.get("engagement_rate", 0)
        if engagement < 0.02:  # Very low engagement
            await self._trigger_improvement({
                "type": "low_engagement",
                "post_id": post_id,
                "engagement": engagement,
                "score": engagement / 0.05  # normalize
            })
    
    async def get_insights(self) -> Dict:
        """Get agent insights for reporting"""
        mem_stats = await self.memory.get_stats()
        perf_history = await self.memory.get_performance_history(days=30)
        
        return {
            "agent_id": self.agent_id,
            "channel_id": self.channel_id,
            "channel_name": self.profile.name,
            "persona": self.persona.get("name"),
            "metrics": self.metrics,
            "memory_stats": mem_stats,
            "performance_history_points": len(perf_history),
            "pending_queue_size": self.content_queue.qsize(),
            "status": self.status.value
        }