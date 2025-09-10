# app/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, JSON, DECIMAL, ForeignKey, Index
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from .database import Base  # 상대 경로로 수정되었습니다.

class User(Base):
    """사용자 정보 테이블"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    nickname: Mapped[str] = mapped_column(String(50), default='사용자')
    prep_time: Mapped[int] = mapped_column(Integer, default=1800)  # 준비 시간 (초)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    last_active: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="user_owner", cascade="all, delete-orphan")
    favorite_places: Mapped[list["FavoritePlace"]] = relationship("FavoritePlace", back_populates="user_owner", cascade="all, delete-orphan")
    user_preferences: Mapped[list["UserPreference"]] = relationship("UserPreference", back_populates="user_owner", cascade="all, delete-orphan")
    calendars: Mapped[list["Calendar"]] = relationship("Calendar", back_populates="user_owner", cascade="all, delete-orphan")
    alarms: Mapped[list["Alarm"]] = relationship("Alarm", back_populates="user_owner", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship("Notification", back_populates="user_owner", cascade="all, delete-orphan")
    user_patterns: Mapped[list["UserPattern"]] = relationship("UserPattern", back_populates="user_owner", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_uuid', 'uuid'),
        Index('idx_last_active', 'last_active'),
    )

class Session(Base):
    """대화 세션 정보 테이블"""
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default='새 대화')
    category: Mapped[str] = mapped_column(String(50), default='general')
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_owner: Mapped["User"] = relationship("User", back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="session_owner", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_user_updated', 'user_uuid', 'updated_at'),
    )

class Message(Base):
    """사용자 및 AI 메시지 테이블"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_user: Mapped[bool] = mapped_column(Boolean, nullable=False)
    intent: Mapped[str] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    # Relationships
    session_owner: Mapped["Session"] = relationship("Session", back_populates="messages")

    __table_args__ = (
        Index('idx_session_created', 'session_id', 'created_at'),
    )

class RouteCache(Base):
    """검색된 경로 정보 캐싱 테이블"""
    __tablename__ = "route_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    start_lat: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 8), nullable=False)
    start_lng: Mapped[DECIMAL] = mapped_column(DECIMAL(11, 8), nullable=False)
    end_lat: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 8), nullable=False)
    end_lng: Mapped[DECIMAL] = mapped_column(DECIMAL(11, 8), nullable=False)
    route_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_coords', 'start_lat', 'start_lng', 'end_lat', 'end_lng'),
        Index('idx_created', 'created_at'),
    )

class UserPattern(Base):
    """사용자 행동 패턴 저장 테이블 (개인화용)"""
    __tablename__ = "user_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    last_used: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    # Relationships
    user_owner: Mapped["User"] = relationship("User", back_populates="user_patterns")

    __table_args__ = (
        Index('idx_user_pattern', 'user_uuid', 'pattern_type'),
    )

class Calendar(Base):
    """일정 정보 저장 테이블"""
    __tablename__ = "calendars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    event_title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_start_time: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    event_end_time: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    location_alias: Mapped[str] = mapped_column(String(100), nullable=True)
    location_lat: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 8), nullable=True)
    location_lng: Mapped[DECIMAL] = mapped_column(DECIMAL(11, 8), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_owner: Mapped["User"] = relationship("User", back_populates="calendars")
    alarms: Mapped[list["Alarm"]] = relationship("Alarm", back_populates="calendar_event")

    __table_args__ = (
        Index('idx_user_event_start', 'user_uuid', 'event_start_time'),
    )

class Alarm(Base):
    """알람 정보 저장 테이블"""
    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    calendar_event_id: Mapped[int] = mapped_column(Integer, ForeignKey("calendars.id", ondelete="SET NULL"), nullable=True)
    alarm_time: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    label: Mapped[str] = mapped_column(String(255), default='알람')
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    repeat_days: Mapped[str] = mapped_column(String(50), nullable=True)
    sound_uri: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_owner: Mapped["User"] = relationship("User", back_populates="alarms")
    calendar_event: Mapped["Calendar"] = relationship("Calendar", back_populates="alarms")

    __table_args__ = (
        Index('idx_user_alarm_time', 'user_uuid', 'alarm_time', 'is_enabled'),
    )

class Notification(Base):
    """사용자에게 보여줄 앱 내 알림 목록 테이블"""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=True)
    related_item_id: Mapped[int] = mapped_column(Integer, nullable=True)
    related_item_type: Mapped[str] = mapped_column(String(50), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    # Relationships
    user_owner: Mapped["User"] = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index('idx_user_created_read', 'user_uuid', 'created_at', 'is_read'),
    )

class FavoritePlace(Base):
    """사용자가 자주 사용하는 장소 테이블 (집, 회사, 학교 등)"""
    __tablename__ = "favorite_places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    latitude: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 8), nullable=False)
    longitude: Mapped[DECIMAL] = mapped_column(DECIMAL(11, 8), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_owner: Mapped["User"] = relationship("User", back_populates="favorite_places")

    __table_args__ = (
        Index('idx_user_fav_location', 'user_uuid'),
    )

class UserPreference(Base):
    """사용자의 명시적인 앱 설정 테이블"""
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    pref_key: Mapped[str] = mapped_column(String(100), nullable=False)
    pref_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user_owner: Mapped["User"] = relationship("User", back_populates="user_preferences")

    __table_args__ = (
        Index('idx_user_pref_key', 'user_uuid', 'pref_key', unique=True),
    )

class WeatherCache(Base):
    """외부 날씨 API 응답 캐시 테이블"""
    __tablename__ = "weather_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    latitude: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 8), nullable=False)
    longitude: Mapped[DECIMAL] = mapped_column(DECIMAL(11, 8), nullable=False)
    weather_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_weather_location_expires', 'latitude', 'longitude', 'expires_at'),
    )

class PoiCache(Base):
    """외부 주변 장소(POI) API 응답 캐시 테이블"""
    __tablename__ = "poi_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    latitude: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 8), nullable=False)
    longitude: Mapped[DECIMAL] = mapped_column(DECIMAL(11, 8), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    poi_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_poi_loc_cat_query_expires', 'latitude', 'longitude', 'category', 'expires_at'),
    )