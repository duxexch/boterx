#!/usr/bin/env python3
"""
SQLAlchemy models for the LangSense Bot
Defines database schema for users, languages, countries, announcements, and messaging
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, 
    UniqueConstraint, Index, BigInteger
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped, mapped_column

Base = declarative_base(cls=AsyncAttrs)

class OutboxType(PyEnum):
    """Types of outbox messages"""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal" 
    COMPLAINT = "complaint"
    SUPPORT = "support"
    BROADCAST = "broadcast"
    ANNOUNCEMENT = "announcement"

class OutboxStatus(PyEnum):
    """Status of outbox messages"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class DeliveryStatus(PyEnum):
    """Status of message delivery"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BLOCKED = "blocked"

class User(Base):
    """User model for storing Telegram user information"""
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    customer_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True, index=True)
    
    # Preferences
    language_code: Mapped[str] = mapped_column(String(5), nullable=False, default='ar')
    country_code: Mapped[str] = mapped_column(String(5), nullable=False, default='SA')
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    outbox_messages = relationship("Outbox", back_populates="user", cascade="all, delete-orphan")
    announcement_deliveries = relationship("AnnouncementDelivery", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"

class Language(Base):
    """Language model for multi-language support"""
    __tablename__ = 'languages'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(5), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rtl: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<Language(code={self.code}, name={self.name})>"

class Country(Base):
    """Country model for regional settings"""
    __tablename__ = 'countries'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(5), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<Country(code={self.code}, name={self.name})>"

class Announcement(Base):
    """Announcement model for system announcements"""
    __tablename__ = 'announcements'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    content_ar: Mapped[str] = mapped_column(Text, nullable=False)
    content_en: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Display settings
    display_duration: Mapped[int] = mapped_column(Integer, default=0)  # 0 = permanent
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    
    # Filtering
    target_language: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    target_country: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    deliveries = relationship("AnnouncementDelivery", back_populates="announcement", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Announcement(id={self.id}, title_ar={self.title_ar[:50]})>"

class AnnouncementDelivery(Base):
    """Track announcement delivery to users"""
    __tablename__ = 'announcement_deliveries'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int] = mapped_column(Integer, ForeignKey('announcements.id'), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    announcement = relationship("Announcement", back_populates="deliveries")
    user = relationship("User", back_populates="announcement_deliveries")
    
    # Unique constraint
    __table_args__ = (UniqueConstraint('announcement_id', 'user_id', name='uq_announcement_user'),)
    
    def __repr__(self):
        return f"<AnnouncementDelivery(announcement_id={self.announcement_id}, user_id={self.user_id}, status={self.status})>"

class Outbox(Base):
    """Outbox for user requests and system messages"""
    __tablename__ = 'outbox'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    type: Mapped[OutboxType] = mapped_column(Enum(OutboxType), nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus), default=OutboxStatus.PENDING)
    
    # Content
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Processing
    processed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # Admin telegram_id
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="outbox_messages")
    recipients = relationship("OutboxRecipient", back_populates="outbox", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_outbox_type_status', 'type', 'status'),
        Index('idx_outbox_created', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Outbox(id={self.id}, type={self.type}, status={self.status})>"

class OutboxRecipient(Base):
    """Track individual message recipients for broadcasts"""
    __tablename__ = 'outbox_recipients'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outbox_id: Mapped[int] = mapped_column(Integer, ForeignKey('outbox.id'), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False)
    
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    outbox = relationship("Outbox", back_populates="recipients")
    
    # Unique constraint
    __table_args__ = (UniqueConstraint('outbox_id', 'user_id', name='uq_outbox_user'),)
    
    def __repr__(self):
        return f"<OutboxRecipient(outbox_id={self.outbox_id}, user_id={self.user_id}, status={self.status})>"
