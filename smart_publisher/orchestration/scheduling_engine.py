"""
Scheduling Engine - Intelligent content scheduling
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, time
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import asyncio
import logging

logger = logging.getLogger(__name__)


class SchedulePriority(Enum):
    IMMEDIATE = "immediate"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    EVERGREEN = "evergreen"


@dataclass
class ScheduledItem:
    id: str
    content: Dict
    channel_id: str
    priority: SchedulePriority
    scheduled_time: datetime
    created_at: datetime = field(default_factory=datetime.now)
    attempts: int = 0
    max_attempts: int = 3
    status: str = "scheduled"  # scheduled, publishing, published, failed
    metadata: Dict = field(default_factory=dict)


class SchedulingEngine:
    """Intelligent content scheduling engine"""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.schedule: Dict[str, List[ScheduledItem]] = defaultdict(list)  # channel_id -> items
        self.published_history: List[Dict] = []
        self.running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Load channel profiles
        from smart_publisher.core.channel_profile import get_channel_manager
        self.channel_manager = get_channel_manager()
    
    async def start(self):
        self.running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduling engine started")
    
    async def stop(self):
        self.running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
    
    async def schedule_content(
        self,
        content: Dict,
        channel_id: str,
        priority: SchedulePriority = SchedulePriority.NORMAL,
        scheduled_time: Optional[datetime] = None
    ) -> str:
        """Schedule content for publishing"""
        
        if scheduled_time is None:
            scheduled_time = self._calculate_optimal_time(channel_id, priority)
        
        item = ScheduledItem(
            id=f"sched_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(content)}",
            content=content,
            channel_id=channel_id,
            priority=priority,
            scheduled_time=scheduled_time,
            metadata={"source": "pipeline"}
        )
        
        self.schedule[channel_id].append(item)
        # Sort by scheduled time
        self.schedule[channel_id].sort(key=lambda x: x.scheduled_time)
        
        return item.id
    
    def _calculate_optimal_time(self, channel_id: str, priority: SchedulePriority) -> datetime:
        """Calculate optimal publishing time based on channel profile"""
        profile = self.channel_manager.get_profile(channel_id)
        if not profile:
            return datetime.now() + timedelta(minutes=5)
        
        now = datetime.now()
        
        if priority == SchedulePriority.IMMEDIATE:
            return now
        
        # Check if in quiet hours
        if profile.is_in_quiet_hours(now.time()):
            # Schedule for next best window
            return self._next_best_window(profile, now)
        
        # Check if in best window
        if profile.is_in_best_window(now.time()):
            return now + timedelta(minutes=5)
        
        # Find next best window
        return self._next_best_window(profile, now)
    
    def _next_best_window(self, profile, now: datetime) -> datetime:
        windows = profile.scheduling.get("best_windows", [])
        if not windows:
            return now + timedelta(hours=1)
        
        current_time = now.time()
        
        for window in windows:
            start_str, end_str = window.split("-")
            start = datetime.strptime(start_str, "%H:%M").time()
            end = datetime.strptime(end_str, "%H:%M").time()
            
            if start <= current_time <= end:
                # In window
                return now + timedelta(minutes=5)
            elif current_time < start:
                # Next window today
                return datetime.combine(now.date(), start)
        
        # Next window tomorrow
        first_start = datetime.strptime(windows[0].split("-")[0], "%H:%M").time()
        return datetime.combine(now.date() + timedelta(days=1), first_start)
    
    async def _scheduler_loop(self):
        """Main scheduling loop"""
        while True:
            try:
                await self._process_schedule()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def _process_schedule(self):
        """Process due items"""
        now = datetime.now()
        
        for channel_id, items in self.schedule.items():
            # Get due items
            due_items = [item for item in items if item.scheduled_time <= now and item.status == "scheduled"]
            
            for item in due_items:
                try:
                    item.status = "publishing"
                    # Would publish via orchestrator
                    # result = await self.orchestrator.validate_and_publish(item.content, item.channel_id)
                    
                    # For now, just mark as published
                    item.status = "published"
                    self.published_history.append({
                        "item_id": item.id,
                        "channel_id": item.channel_id,
                        "published_at": datetime.now().isoformat(),
                        "priority": item.priority.value
                    })
                    
                except Exception as e:
                    logger.error(f"Publishing failed for {item.id}: {e}")
                    item.attempts += 1
                    item.status = "failed"
                    
                    if item.attempts < item.max_attempts:
                        # Reschedule with backoff
                        item.scheduled_time = datetime.now() + timedelta(minutes=5 * item.attempts)
                        item.status = "scheduled"
                    else:
                        logger.error(f"Item {item.id} failed after {item.max_attempts} attempts")
            
            # Remove completed items
            self.schedule[channel_id] = [
                item for item in items 
                if item.status in ["scheduled", "publishing"]
            ]
    
    def get_schedule_status(self, channel_id: Optional[str] = None) -> Dict:
        if channel_id:
            items = self.schedule.get(channel_id, [])
            return {
                "channel_id": channel_id,
                "scheduled": len([i for i in items if i.status == "scheduled"]),
                "publishing": len([i for i in items if i.status == "publishing"]),
                "next_item": min(items, key=lambda x: x.scheduled_time).scheduled_time.isoformat() if items else None
            }
        
        total_scheduled = sum(len([i for i in items if i.status == "scheduled"]) for items in self.schedule.values())
        total_publishing = sum(len([i for i in items if i.status == "publishing"]) for items in self.schedule.values())
        
        return {
            "total_scheduled": total_scheduled,
            "total_publishing": total_publishing,
            "channels": {cid: len(items) for cid, items in self.schedule.items()},
            "published_today": len([
                p for p in self.published_history 
                if datetime.fromisoformat(p["published_at"]).date() == datetime.now().date()
            ])
        }
    
    def cancel_item(self, item_id: str) -> bool:
        """Cancel a scheduled item"""
        for channel_id, items in self.schedule.items():
            for i, item in enumerate(items):
                if item.id == item_id:
                    items.pop(i)
                    return True
        return False
    
    def reschedule_item(self, item_id: str, new_time: datetime) -> bool:
        """Reschedule an item"""
        for channel_id, items in self.schedule.items():
            for item in items:
                if item.id == item_id:
                    item.scheduled_time = new_time
                    item.status = "scheduled"
                    item.attempts = 0
                    # Re-sort
                    self.schedule[channel_id].sort(key=lambda x: x.scheduled_time)
                    return True
        return False
    
    def get_upcoming(self, channel_id: str, hours: int = 24) -> List[Dict]:
        """Get upcoming scheduled items for a channel"""
        items = self.schedule.get(channel_id, [])
        cutoff = datetime.now() + timedelta(hours=hours)
        
        upcoming = [
            {
                "id": item.id,
                "scheduled_time": item.scheduled_time.isoformat(),
                "priority": item.priority.value,
                "content_preview": str(item.content)[:100]
            }
            for item in items
            if item.status == "scheduled" and item.scheduled_time <= cutoff
        ]
        
        return sorted(upcoming, key=lambda x: x["scheduled_time"])