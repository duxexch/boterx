"""
Quality Guardian Agent - Ensures all content meets quality standards
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import re
import json

from smart_publisher.core.agent_base import BaseAgent, AgentContext, AgentOutput
from smart_publisher.core.channel_profile import ChannelProfile
from smart_publisher.core.agent_memory import AgentMemory, SharedKnowledgeBase


class ViolationSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BLOCKING = "blocking"


@dataclass
class QualityViolation:
    rule_id: str
    severity: ViolationSeverity
    message: str
    location: Optional[str] = None
    suggested_fix: Optional[str] = None
    auto_fixable: bool = False


@dataclass
class QualityReport:
    passed: bool
    score: float  # 0-1
    violations: List[QualityViolation]
    warnings: List[str]
    suggestions: List[str]


class QualityGuardianAgent(BaseAgent):
    """Ensures all content meets quality standards before publishing"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.global_rules = self._load_global_rules()
        self.channel_rules_cache: Dict[str, List[Dict]] = {}
    
    def get_capabilities(self) -> List[str]:
        return [
            "pre_publish_validation",
            "content_quality_scoring",
            "violation_detection",
            "auto_fix_suggestions",
            "rule_management",
            "quality_trend_monitoring"
        ]
    
    def _load_global_rules(self) -> List[Dict]:
        """Load global quality rules"""
        return [
            {
                "id": "no_guaranteed_language",
                "name": "No Guaranteed Language",
                "severity": ViolationSeverity.BLOCKING,
                "pattern": r"\b(مضمون|مضمون100|مضمون 100|ربح مضمون|ضمان الربح|لا تخسر|خطر صفر|بلا مخاطر|أكد|بالتأكيد|100%)\b",
                "message": "لغة الضمان ممنوعة - المراهنة تنطوي على مخاطر",
                "auto_fix": "استبدل ب: 'احتمالية عالية'، 'فرصة قوية'، 'ثقة كبيرة'"
            },
            {
                "id": "no_clickbait",
                "name": "No Clickbait",
                "severity": ViolationSeverity.BLOCKING,
                "pattern": r"(فرصة عمرك|لا تفوت|أسرع الآن|فرصة لا تعوض|سر النجاح|الحل السحري)",
                "message": "كليك بيت ممنوع",
                "auto_fix": "احذف العبارة أو استبدل بوصف موضوعي"
            },
            {
                "id": "require_source",
                "name": "Source Required",
                "severity": ViolationSeverity.CRITICAL,
                "check": "has_source",
                "message": "مصدر موثوق مطلوب",
                "auto_fix": "أضف: 📌 المصدر: [اسم المصدر + الرابط]"
            },
            {
                "id": "arabic_content_minimum",
                "name": "Minimum Arabic Content",
                "severity": ViolationSeverity.WARNING,
                "check": "arabic_ratio",
                "threshold": 0.3,
                "message": "المحتوى يجب أن يحتوي على نسبة معقولة من النص العربي",
                "auto_fix": "أضف مقدمة/خاتمة بالعربية"
            },
            {
                "id": "max_length",
                "name": "Maximum Length",
                "severity": ViolationSeverity.WARNING,
                "check": "max_length",
                "message": "الطول يتجاوز الحد المسموح للقناة",
                "auto_fix": "اختصر المحتوى أو قسمه لجزأين"
            },
            {
                "id": "required_tags",
                "name": "Required Tags Present",
                "severity": ViolationSeverity.CRITICAL,
                "check": "required_tags",
                "message": "وسوم القناة المطلوبة مفقودة",
                "auto_fix": "أضف الوسوم المطلوبة في نهاية المنشور"
            },
            {
                "id": "no_placeholder_leak",
                "name": "No Placeholder Leakage",
                "severity": ViolationSeverity.BLOCKING,
                "pattern": r"\b(فريق المضيف|فريق الضيف|دوري|مباراة XX|نسبة XX)\b",
                "message": "تسرب placeholders - قيم غير مستبدلة",
                "auto_fix": "استبدل جميع placeholders بالبيانات الحقيقية"
            },
            {
                "id": "balanced_confidence",
                "name": "Balanced Confidence",
                "severity": ViolationSeverity.WARNING,
                "check": "confidence_calibration",
                "message": "مستوى الثقة غير معاير - مرتفع جداً أو منخفض جداً",
                "auto_fix": "راجع نماذج الثقة، أضف ملاحظة مخاطر"
            },
            {
                "id": "tactical_reasoning",
                "name": "Tactical Reasoning Required",
                "severity": ViolationSeverity.CRITICAL,
                "check": "has_tactical_reasoning",
                "message": "التوقعات تتطلب أسباباً تكتيكية/إحصائية",
                "auto_fix": "أضف: أسباب تكتيكية (إصابات، فورم، تكتيك، دافع)"
            }
        ]
    
    def get_capabilities(self) -> List[str]:
        return [
            "pre_publish_validation",
            "content_quality_scoring",
            "violation_detection",
            "auto_fix_suggestions",
            "rule_management",
            "quality_trend_monitoring"
        ]
    
    async def think(self, context: AgentContext) -> AgentOutput:
        task_type = context.task_type
        
        if task_type == "validate_content":
            return await self._validate_content(context)
        elif task_type == "score_quality":
            return await self._score_quality(context)
        elif task_type == "suggest_fixes":
            return await self._suggest_fixes(context)
        elif task_type == "audit_channel":
            return await self._audit_channel(context)
        elif task_type == "update_rules":
            return await self._update_rules(context)
        else:
            return AgentOutput(
                success=False,
                output=None,
                confidence=0.0,
                errors=[f"Unknown task: {context.task_type}"]
            )
    
    async def _validate_content(self, context: AgentContext) -> AgentOutput:
        """Validate content against all applicable rules"""
        content = context.input_data.get("content", {})
        channel_profile = context.channel_profile
        
        report = await self._run_validation(content, profile=channel_profile)
        
        return AgentOutput(
            success=report.passed,
            output={
                "report": self._report_to_dict(report),
                "content_id": context.input_data.get("content_id")
            },
            confidence=report.score,
            reasoning=f"Validation {'passed' if report.passed else 'failed'} with {len(report.violations)} violations",
            warnings=report.warnings
        )
    
    async def _run_validation(self, content: Dict, profile: ChannelProfile) -> QualityReport:
        """Run all validation rules"""
        violations = []
        warnings = []
        suggestions = []
        text = content.get("text", "")
        
        # Get channel-specific rules
        channel_rules = self._get_channel_rules(profile)
        all_rules = self.global_rules + channel_rules
        
        for rule in all_rules:
            violation = await self._check_rule(rule, content, profile)
            if violation:
                if violation.severity in [ViolationSeverity.CRITICAL, ViolationSeverity.BLOCKING]:
                    violations.append(violation)
                else:
                    warnings.append(violation.message)
                
                if violation.suggested_fix:
                    suggestions.append(violation.suggested_fix)
        
        # Calculate score
        blocking = len([v for v in violations if v.severity == ViolationSeverity.BLOCKING])
        critical = len([v for v in violations if v.severity == ViolationSeverity.CRITICAL])
        warning_count = len([v for v in violations if v.severity == ViolationSeverity.WARNING])
        
        score = 1.0
        score -= blocking * 0.4
        score -= critical * 0.25
        score -= warning_count * 0.1
        score -= len(suggestions) * 0.02
        score = max(0.0, score)
        
        passed = blocking == 0 and critical == 0
        
        return QualityReport(
            passed=passed,
            score=score,
            violations=violations,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def _get_channel_rules(self, profile: ChannelProfile) -> List[Dict]:
        """Get channel-specific rules"""
        if profile.id in self.channel_rules_cache:
            return self.channel_rules_cache[profile.id]
        
        rules = []
        
        # Channel-specific rules from quality_gates
        gates = profile.quality_gates
        
        if gates.get("require_source"):
            rules.append({
                "id": f"{profile.id}_require_source",
                "name": f"{profile.name} - Source Required",
                "severity": ViolationSeverity.CRITICAL,
                "check": "has_source",
                "message": f"{profile.name}: مصدر موثوق مطلوب"
            })
        
        if gates.get("require_odds"):
            rules.append({
                "id": f"{profile.id}_require_odds",
                "name": f"{profile.name} - Odds Required",
                "severity": ViolationSeverity.CRITICAL,
                "check": "has_odds",
                "message": f"{profile.name}: نسب/أسعار مطلوبة"
            })
        
        if gates.get("require_probabilities"):
            rules.append({
                "id": f"{profile.id}_require_probabilities",
                "name": f"{profile.name} - Probabilities Required",
                "severity": ViolationSeverity.CRITICAL,
                "check": "has_probabilities",
                "message": f"{profile.name}: نسب محسوبة مطلوبة"
            })
        
        if gates.get("require_tactical_reasoning"):
            rules.append({
                "id": f"{profile.id}_tactical_reasoning",
                "name": f"{profile.name} - Tactical Reasoning",
                "severity": ViolationSeverity.CRITICAL,
                "check": "has_tactical_reasoning",
                "message": f"{profile.name}: أسباب تكتيكية/إحصائية مطلوبة"
            })
        
        if gates.get("forbid_guaranteed_language"):
            rules.append({
                "id": f"{profile.id}_no_guaranteed",
                "name": f"{profile.name} - No Guaranteed Language",
                "severity": ViolationSeverity.BLOCKING,
                "pattern": r"\b(مضمون|مضمون100|مضمون 100|ربح مضمون|ضمان الربح|لا تخسر|خطر صفر|بلا مخاطر|أكد|بالتأكيد|100%)\b",
                "message": f"{profile.name}: لغة الضمان ممنوعة"
            })
        
        if gates.get("forbid_clickbait"):
            rules.append({
                "id": f"{profile.id}_no_clickbait",
                "name": f"{profile.name} - No Clickbait",
                "severity": ViolationSeverity.BLOCKING,
                "pattern": r"(فرصة عمرك|لا تفوت|أسرع الآن|فرصة لا تعوض|سر النجاح)",
                "message": f"{profile.name}: كليك بيت ممنوع"
            })
        
        min_len = profile.quality_gates.get("min_arabic_chars", 0)
        if min_len > 0:
            rules.append({
                "id": f"{profile.id}_min_arabic",
                "name": f"{profile.name} - Minimum Arabic",
                "severity": ViolationSeverity.WARNING,
                "check": "arabic_chars",
                "threshold": min_len,
                "message": f"{profile.name}: حد أدنى {min_len} حرف عربي"
            })
        
        max_len = profile.get_max_length()
        rules.append({
            "id": f"{profile.id}_max_length",
            "name": f"{profile.name} - Max Length",
            "severity": ViolationSeverity.WARNING,
            "check": "max_length",
            "threshold": max_len,
            "message": f"{profile.name}: الطول يتجاوز {max_len} حرف"
        })
        
        required_tags = profile.get_required_tags()
        if required_tags:
            rules.append({
                "id": f"{profile.id}_required_tags",
                "name": f"{profile.name} - Required Tags",
                "severity": ViolationSeverity.CRITICAL,
                "check": "required_tags",
                "threshold": required_tags,
                "message": f"{profile.id}: وسوم مطلوبة مفقودة: {', '.join(required_tags)}"
            })
        
        self.channel_rules_cache[profile.id] = rules
        return rules
    
    async def _check_rule(self, rule: Dict, content: Dict, profile: ChannelProfile) -> Optional:
        """Check a single rule against content"""
        from dataclasses import dataclass
        from typing import Optional
        
        @dataclass
        class Violation:
            rule_id: str
            severity: ViolationSeverity
            message: str
            location: Optional[str] = None
            suggested_fix: Optional[str] = None
            auto_fixable: bool = False
        
        text = content.get("text", "")
        check = rule.get("check")
        pattern = rule.get("pattern")
        
        if pattern:
            # Regex pattern check
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity(rule.get("severity", "warning")),
                    message=rule["message"],
                    location=f"Found: {matches[:3]}",
                    suggested_fix=rule.get("auto_fix"),
                    auto_fixable=bool(rule.get("auto_fix"))
                )
        
        elif check == "has_source":
            if not content.get("source") and not content.get("source_url"):
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity(rule.get("severity", "critical")),
                    message=rule["message"],
                    suggested_fix=rule.get("auto_fix"),
                    auto_fixable=True
                )
        
        elif check == "has_odds":
            if not content.get("odds") and not content.get("probabilities"):
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity.CRITICAL,
                    message=rule["message"],
                    suggested_fix="أضف جدول نسب الفوز: هوم%, تعادل%, أواي%"
                )
        
        elif check == "has_probabilities":
            if not content.get("probabilities") and not content.get("confidence"):
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity.CRITICAL,
                    message=rule["message"],
                    suggested_fix="أضف نسب محسوبة: هوم% تعادل% أواي% + ثقة"
                )
        
        elif check == "has_tactical_reasoning":
            text_lower = text.lower()
            tactical_keywords = ["إصابة", "فورم", "تكتيك", "ضغط", "انتقال", "غياب", "عودة", "دافع", "إحصائي", "نموذج"]
            if not any(kw in text_lower for kw in tactical_keywords):
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity.CRITICAL,
                    message=rule["message"],
                    suggested_fix="أضف فقرة 'أسباب تكتيكية' تشرح سبب التوقع"
                )
        
        elif check == "arabic_ratio" or check == "arabic_chars":
            threshold = rule.get("threshold", 0.3)
            if check == "arabic_chars":
                arabic_count = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
                if arabic_count < rule.get("threshold", 100):
                    return Violation(
                        rule_id=rule["id"],
                        severity=ViolationSeverity(rule.get("severity", "warning")),
                        message=f"حروف عربية: {arabic_count} < {rule.get('threshold', 100)}",
                        suggested_fix="أضف محتوى عربي أكثر"
                    )
            else:
                arabic_ratio = sum(1 for c in text if '\u0600' <= c <= '\u06FF') / max(len(text), 1)
                if arabic_ratio < threshold:
                    return Violation(
                        rule_id=rule["id"],
                        severity=ViolationSeverity.WARNING,
                        message=f"نسبة العربية: {arabic_ratio:.1%} < {threshold:.0%}",
                        suggested_fix="أضف محتوى عربي أكثر"
                    )
        
        elif check == "max_length":
            threshold = rule.get("threshold", 1000)
            if len(text) > threshold:
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity.WARNING,
                    message=f"الطول {len(text)} > {threshold}",
                    suggested_fix="اختصر أو قسم المنشور"
                )
        
        elif check == "required_tags":
            required = rule.get("threshold", [])
            tags = content.get("tags", [])
            missing = [t for t in required if t not in tags]
            if missing:
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity.CRITICAL,
                    message=f"وسوم مفقودة: {', '.join(missing)}",
                    suggested_fix=f"أضف: {' '.join(missing)}",
                    auto_fixable=True
                )
        
        elif check == "confidence_calibration":
            confidence = content.get("confidence", 0.5)
            if confidence > 0.95:
                return Violation(
                    rule_id=rule["id"],
                    severity=ViolationSeverity.WARNING,
                    message=f"ثقة مرتفعة جداً: {confidence:.0%}",
                    suggested_fix="قلل الثقة، أضف ملاحظة مخاطر"
                )
        
        return None
    
    async def _score_quality(self, context: AgentContext) -> AgentOutput:
        """Score content quality without blocking"""
        content = context.input_data.get("content", {})
        profile = context.channel_profile
        
        report = await self._run_validation(content, profile)
        
        return AgentOutput(
            success=True,
            output={
                "score": report.score,
                "passed": report.passed,
                "violations_count": len(report.violations),
                "warnings_count": len(report.warnings),
                "details": self._report_to_dict(report)
            },
            confidence=report.score,
            reasoning=f"Quality score: {report.score:.2f}"
        )
    
    async def _suggest_fixes(self, context: AgentContext) -> AgentOutput:
        """Suggest fixes for violations"""
        content = context.input_data.get("content", {})
        profile = context.channel_profile
        
        report = await self._run_validation(content, profile)
        
        fixes = []
        for v in report.violations:
            if v.auto_fixable and v.suggested_fix:
                fixes.append({
                    "rule": v.rule_id,
                    "fix": v.suggested_fix,
                    "auto_applicable": v.auto_fixable
                })
        
        return AgentOutput(
            success=True,
            output={"fixes": fixes, "can_auto_fix": len(fixes) > 0},
            confidence=0.9
        )
    
    async def _audit_channel(self, context: AgentContext) -> AgentOutput:
        """Audit channel quality over time"""
        channel_id = context.input_data.get("channel_id", self.channel_id)
        days = context.input_data.get("days", 7)
        
        snapshots = await self.memory.get_performance_history(days=days)
        
        if not snapshots:
            return AgentOutput(
                success=True,
                output={"message": "No data for audit"},
                confidence=1.0
            )
        
        # Analyze quality trends
        total_posts = sum(s.posts_count for s in snapshots)
        avg_quality = sum(s.metrics.get("quality_score", 0) for s in snapshots) / len(snapshots)
        
        # Quality trend
        quality_trend = "stable"
        if len(snapshots) > 3:
            recent = sum(s.metrics.get("quality_score", 0) for s in snapshots[:3]) / 3
            older = sum(s.metrics.get("quality_score", 0) for s in snapshots[-3:]) / 3
            if recent > older + 0.05:
                quality_trend = "improving"
            elif recent < older - 0.05:
                quality_trend = "declining"
        
        return AgentOutput(
            success=True,
            output={
                "channel_id": channel_id,
                "period_days": days,
                "total_posts": total_posts,
                "avg_quality_score": avg_quality,
                "quality_trend": quality_trend,
                "snapshots_analyzed": len(snapshots),
                "recommendations": self._generate_audit_recommendations(snapshots)
            },
            confidence=0.85
        )
    
    def _generate_audit_recommendations(self, snapshots: List) -> List[str]:
        recs = []
        if not snapshots:
            return ["لا توجد بيانات كافية للتدقيق"]
        
        avg_q = sum(s.metrics.get("quality_score", 0) for s in snapshots) / len(snapshots)
        if avg_q < 0.7:
            recs.append("متوسط الجودة منخفض - مراجعة قواعد النشر وتدريب الوكلاء")
        
        latest = snapshots[0]
        if latest.metrics.get("duplicate_rate", 0) > 0.05:
            recs.append("معدل التكرار مرتفع - تشديد فحص التكرار")
        
        if latest.metrics.get("spam_complaints", 0) > 0.001:
            recs.append("شكاوى سبام - مراجعة تكرار النشر والمحتوى")
        
        return recs or ["الجودة ضمن المعدل الطبيعي"]
    
    async def _update_rules(self, context: AgentContext) -> AgentOutput:
        """Update quality rules"""
        new_rules = context.input_data.get("rules", [])
        
        for rule in new_rules:
            self.global_rules.append(rule)
            # Clear cache to force reload
            self.channel_rules_cache.clear()
        
        return AgentOutput(
            success=True,
            output={"added_rules": len(new_rules)},
            confidence=1.0
        )
    
    def get_capabilities(self) -> List[str]:
        return [
            "pre_publish_validation",
            "content_quality_scoring",
            "violation_detection",
            "auto_fix_suggestions",
            "rule_management",
            "quality_audit"
        ]