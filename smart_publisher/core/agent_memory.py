"""
Agent Memory System - Persistent Memory for Intelligent Agents
Each agent has long-term memory, learns from experience, and shares knowledge.
"""

import asyncio
import json
import sqlite3
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path
from contextlib import asynccontextmanager
import aiosqlite
import pickle
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from smart_publisher.core.channel_profile import ChannelProfile


@dataclass
class MemoryEntry:
    """A single memory entry"""
    id: str
    agent_id: str
    channel_id: str
    memory_type: str  # "experience", "pattern", "rule", "feedback", "performance", "knowledge"
    content: Dict
    importance: float = 1.0  # 0-1, higher = more important
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    embedding: Optional[bytes] = None  # For vector similarity search
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["accessed_at"] = self.accessed_at.isoformat()
        if self.embedding:
            d["embedding"] = self.embedding.hex()
        return d
    
    @classmethod
    def from_dict(cls, d: Dict) -> "MemoryEntry":
        d = d.copy()
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["accessed_at"] = datetime.fromisoformat(d["accessed_at"])
        if d.get("embedding"):
            d["embedding"] = bytes.fromhex(d["embedding"])
        return cls(**d)


@dataclass
class AgentPerformanceSnapshot:
    """Snapshot of agent performance at a point in time"""
    agent_id: str
    channel_id: str
    timestamp: datetime
    metrics: Dict[str, float]  # quality_score, engagement_rate, etc.
    posts_count: int
    top_performing_posts: List[str]  # post_ids
    worst_performing_posts: List[str]
    learned_patterns: List[str]
    active_rules: List[str]
    confidence_calibration: Optional[float] = None


class AgentMemory:
    """Persistent memory for a single agent"""
    
    def __init__(self, agent_id: str, channel_id: str, db_path: str = "data/agent_memory.db"):
        self.agent_id = agent_id
        self.channel_id = channel_id
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False
        self._cache: Dict[str, MemoryEntry] = {}
        self._cache_lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize database schema"""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 1.0,
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    embedding BLOB,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_channel 
                ON memories(agent_id, channel_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_type 
                ON memories(memory_type)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON memories(created_at)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tags 
                ON memories(tags)
            """)
            
            # Performance snapshots table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS performance_snapshots (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    posts_count INTEGER,
                    top_posts TEXT DEFAULT '[]',
                    worst_posts TEXT DEFAULT '[]',
                    learned_patterns TEXT DEFAULT '[]',
                    active_rules TEXT DEFAULT '[]',
                    confidence_calibration REAL
                )
            """)
            await db.commit()
        
        self._initialized = True
    
    def _generate_id(self, content: Dict) -> str:
        """Generate deterministic ID from content"""
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(f"{self.agent_id}{content_str}".encode()).hexdigest()[:16]
    
    async def store(self, memory: MemoryEntry) -> str:
        """Store a memory entry"""
        if not self._initialized:
            await self.initialize()
        
        memory.id = memory.id or self._generate_id(memory.content)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO memories 
                (id, agent_id, channel_id, memory_type, content, importance, tags, 
                 created_at, accessed_at, access_count, embedding, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.id,
                memory.agent_id,
                memory.channel_id,
                memory.memory_type,
                json.dumps(memory.content, ensure_ascii=False),
                memory.importance,
                json.dumps(memory.tags),
                memory.created_at.isoformat(),
                memory.accessed_at.isoformat(),
                memory.access_count,
                memory.embedding,
                json.dumps(memory.metadata, ensure_ascii=False)
            ))
            await db.commit()
        
        async with self._cache_lock:
            self._cache[memory.id] = memory
        
        return memory.id
    
    async def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a specific memory by ID"""
        async with self._cache_lock:
            if memory_id in self._cache:
                entry = self._cache[memory_id]
                entry.accessed_at = datetime.now()
                entry.access_count += 1
                return entry
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_memory(row)
        return None
    
    async def query(
        self,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_importance: float = 0.0,
        limit: int = 50,
        since: Optional[datetime] = None,
        order_by: str = "importance"  # importance, created_at, accessed_at
    ) -> List[MemoryEntry]:
        """Query memories with filters"""
        if not self._initialized:
            await self.initialize()
        
        query = "SELECT * FROM memories WHERE agent_id = ? AND channel_id = ?"
        params = [self.agent_id, self.channel_id]
        
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        
        if min_importance > 0:
            query += " AND importance >= ?"
            params.append(min_importance)
        
        if since:
            query += " AND created_at >= ?"
            params.append(since.isoformat())
        
        if tags:
            # Simple tag matching - in production use FTS or JSON1
            tag_conditions = " AND ".join(["tags LIKE ?"] * len(tags))
            query += f" AND ({tag_conditions})"
            params.extend([f"%{tag}%" for tag in tags])
        
        order_col = "importance" if order_by == "importance" else order_by
        query += f" ORDER BY {order_col} DESC LIMIT ?"
        params.append(limit)
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_memory(row) for row in rows]
    
    async def search_similar(
        self,
        query_text: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[MemoryEntry]:
        """Search memories by semantic similarity (requires embeddings)"""
        # Simple text search fallback - in production use vector DB
        query = """
            SELECT * FROM memories 
            WHERE agent_id = ? AND channel_id = ?
            AND content LIKE ?
        """
        params = [self.agent_id, self.channel_id, f"%{query_text}%"]
        
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        
        query += " ORDER BY importance DESC LIMIT ?"
        params.append(limit)
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_memory(row) for row in rows]
    
    async def get_recent_experiences(self, hours: int = 24, limit: int = 20) -> List[MemoryEntry]:
        """Get recent experience memories"""
        since = datetime.now() - timedelta(hours=hours)
        return await self.query(
            memory_type="experience",
            since=since,
            limit=limit,
            order_by="created_at"
        )
    
    async def get_learned_patterns(self, limit: int = 50) -> List[MemoryEntry]:
        """Get learned patterns"""
        return await self.query(
            memory_type="pattern",
            limit=limit,
            order_by="importance"
        )
    
    async def get_active_rules(self) -> List[MemoryEntry]:
        """Get active rules"""
        return await self.query(
            memory_type="rule",
            limit=100,
            order_by="importance"
        )
    
    async def store_performance_snapshot(self, snapshot: AgentPerformanceSnapshot):
        """Store a performance snapshot"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO performance_snapshots
                (id, agent_id, channel_id, timestamp, metrics, posts_count,
                 top_posts, worst_posts, learned_patterns, active_rules, confidence_calibration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{self.agent_id}_{snapshot.timestamp.isoformat()}",
                snapshot.agent_id,
                snapshot.channel_id,
                snapshot.timestamp.isoformat(),
                json.dumps(snapshot.metrics),
                snapshot.posts_count,
                json.dumps(snapshot.top_performing_posts),
                json.dumps(snapshot.worst_performing_posts),
                json.dumps(snapshot.learned_patterns),
                json.dumps(snapshot.active_rules),
                snapshot.confidence_calibration
            ))
            await db.commit()
    
    async def get_performance_history(self, days: int = 30) -> List[AgentPerformanceSnapshot]:
        """Get performance history"""
        since = datetime.now() - timedelta(days=days)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT * FROM performance_snapshots 
                   WHERE agent_id = ? AND channel_id = ? AND timestamp >= ?
                   ORDER BY timestamp DESC""",
                (self.agent_id, self.channel_id, since.isoformat())
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_snapshot(row) for row in rows]
    
    def _row_to_memory(self, row) -> MemoryEntry:
        return MemoryEntry(
            id=row[0],
            agent_id=row[1],
            channel_id=row[2],
            memory_type=row[3],
            content=json.loads(row[4]),
            importance=row[5],
            tags=json.loads(row[6]),
            created_at=datetime.fromisoformat(row[7]),
            accessed_at=datetime.fromisoformat(row[8]),
            access_count=row[9],
            embedding=row[10],
            metadata=json.loads(row[11]) if row[11] else {}
        )
    
    def _row_to_snapshot(self, row) -> AgentPerformanceSnapshot:
        return AgentPerformanceSnapshot(
            agent_id=row[1],
            channel_id=row[2],
            timestamp=datetime.fromisoformat(row[3]),
            metrics=json.loads(row[4]),
            posts_count=row[5],
            top_performing_posts=json.loads(row[6]),
            worst_performing_posts=json.loads(row[7]),
            learned_patterns=json.loads(row[8]),
            active_rules=json.loads(row[8]),
            confidence_calibration=row[10]
        )
    
    async def cleanup_old_memories(self, retention_days: int = 90):
        """Remove old, low-importance memories"""
        cutoff = datetime.now() - timedelta(days=retention_days)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """DELETE FROM memories 
                   WHERE agent_id = ? AND channel_id = ? 
                   AND created_at < ? AND importance < 0.3""",
                (self.agent_id, self.channel_id, (datetime.now() - timedelta(days=retention_days)).isoformat())
            )
            await db.commit()
    
    async def get_stats(self) -> Dict:
        """Get memory statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT memory_type, COUNT(*), AVG(importance) 
                   FROM memories WHERE agent_id = ? AND channel_id = ?
                   GROUP BY memory_type""",
                (self.agent_id, self.channel_id)
            ) as cursor:
                rows = await cursor.fetchall()
            
            return {
                "agent_id": self.agent_id,
                "channel_id": self.channel_id,
                "by_type": {row[0]: {"count": row[1], "avg_importance": row[2]} for row in rows},
                "cache_size": len(self._cache)
            }


class SharedKnowledgeBase:
    """Shared knowledge base across all agents"""
    
    def __init__(self, db_path: str = "data/shared_knowledge.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False
    
    async def initialize(self):
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS shared_knowledge (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,  -- pattern, rule, best_practice, anti_pattern
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_agent_id TEXT,
                    source_channel_id TEXT,
                    confidence REAL DEFAULT 1.0,
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    usage_count INTEGER DEFAULT 0,
                    validation_status TEXT DEFAULT 'pending'  -- pending, validated, rejected
                    metadata TEXT DEFAULT '{}'
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_category ON shared_knowledge(category)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tags ON shared_knowledge(tags)
            """)
            await db.commit()
            self._initialized = True
    
    async def add_knowledge(
        self,
        category: str,
        title: str,
        content: Dict,
        source_agent_id: str,
        source_channel_id: str,
        tags: List[str] = None,
        confidence: float = 1.0
    ) -> str:
        await self.initialize()
        
        import hashlib
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        knowledge_id = hashlib.sha256(f"{category}{title}{content_str}".encode()).hexdigest()[:16]
        
        async with aiosqlite.connect(self.db_path) as db:
            # Check if exists
            async with db.execute(
                "SELECT id, version FROM shared_knowledge WHERE id = ?", (knowledge_id,)
            ) as cursor:
                existing = await cursor.fetchone()
            
            if existing:
                # Update existing
                new_version = existing[1] + 1
                await db.execute("""
                    UPDATE shared_knowledge SET
                        content = ?, updated_at = ?, version = ?,
                        confidence = ?, usage_count = usage_count + 1
                    WHERE id = ?
                """, (
                    json.dumps(content, ensure_ascii=False),
                    datetime.now().isoformat(),
                    new_version,
                    confidence,
                    knowledge_id
                ))
            else:
                await db.execute("""
                    INSERT INTO shared_knowledge
                    (id, category, title, content, source_agent_id, source_channel_id,
                     confidence, tags, created_at, updated_at, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    knowledge_id, category, title, json.dumps(content, ensure_ascii=False),
                    source_agent_id, source_channel_id, confidence,
                    json.dumps([]), datetime.now().isoformat(), datetime.now().isoformat()
                ))
            await db.commit()
        
        return knowledge_id
    
    async def get_knowledge(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_confidence: float = 0.7,
        limit: int = 50
    ) -> List[Dict]:
        query = "SELECT * FROM shared_knowledge WHERE confidence >= ? AND validation_status = 'validated'"
        params = [min_confidence]
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        query += " ORDER BY usage_count DESC, confidence DESC LIMIT ?"
        params.append(limit)
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "category": row[1],
                        "title": row[2],
                        "content": json.loads(row[3]),
                        "source_agent_id": row[4],
                        "source_channel_id": row[5],
                        "confidence": row[6],
                        "tags": json.loads(row[7]),
                        "created_at": row[8],
                        "updated_at": row[9],
                        "version": row[10],
                        "usage_count": row[11],
                    }
                    for row in rows
                ]
    
    async def increment_usage(self, knowledge_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE shared_knowledge SET usage_count = usage_count + 1 WHERE id = ?",
                (knowledge_id,)
            )
            await db.commit()