# app/routers/calendar_alarm.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
from ..database import get_db
from .. import models

router = APIRouter(prefix="/api/schedule", tags=["Calendar & Alarm"])

# ========================================
# Pydantic 스키마
# ========================================

class CalendarEventCreate(BaseModel):
    """일정 생성 요청 스키마"""
    user_uuid: str
    event_title: str = Field(..., min_length=1, max_length=255)
    event_start_time: datetime
    event_end_time: Optional[datetime] = None
    description: Optional[str] = None
    location_alias: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None

class CalendarEventUpdate(BaseModel):
    """일정 수정 요청 스키마"""
    event_title: Optional[str] = Field(None, min_length=1, max_length=255)
    event_start_time: Optional[datetime] = None
    event_end_time: Optional[datetime] = None
    description: Optional[str] = None
    location_alias: Optional[str] = None

class CalendarEventResponse(BaseModel):
    """일정 응답 스키마"""
    id: int
    user_uuid: str
    event_title: str
    event_start_time: datetime
    event_end_time: Optional[datetime]
    description: Optional[str]
    location_alias: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class AlarmCreate(BaseModel):
    """알람 생성 요청 스키마"""
    user_uuid: str
    alarm_time: datetime
    label: str = Field(default="알람", max_length=255)
    calendar_event_id: Optional[int] = None
    is_enabled: bool = True
    repeat_days: Optional[str] = None
    sound_enabled: bool = True
    vibration_enabled: bool = True

class AlarmUpdate(BaseModel):
    """알람 수정 요청 스키마"""
    alarm_time: Optional[datetime] = None
    label: Optional[str] = Field(None, max_length=255)
    repeat_days: Optional[str] = None

class AlarmResponse(BaseModel):
    """알람 응답 스키마"""
    id: int
    user_uuid: str
    alarm_time: datetime
    label: str
    is_enabled: bool
    repeat_days: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

# ========================================
# 일정 관리 API
# ========================================

@router.post("/calendar/events", response_model=CalendarEventResponse)
async def create_calendar_event(event: CalendarEventCreate, db: Session = Depends(get_db)):
    """새 일정을 생성합니다."""
    try:
        user = db.query(models.User).filter(
            models.User.uuid == event.user_uuid,
            models.User.is_deleted == False
        ).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
        new_event = models.Calendar(
            user_uuid=event.user_uuid,
            event_title=event.event_title,
            event_start_time=event.event_start_time,
            event_end_time=event.event_end_time,
            description=event.description,
            location_alias=event.location_alias,
            location_lat=event.location_lat,
            location_lng=event.location_lng
        )
        
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        
        return new_event
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"일정 생성 실패: {str(e)}")

@router.get("/calendar/events/{user_uuid}", response_model=List[CalendarEventResponse])
async def get_user_events(user_uuid: str, db: Session = Depends(get_db)):
    """사용자의 모든 일정을 조회합니다."""
    events = db.query(models.Calendar).filter(
        models.Calendar.user_uuid == user_uuid
    ).order_by(models.Calendar.event_start_time.desc()).all()
    
    return events

@router.put("/calendar/events/{event_id}", response_model=CalendarEventResponse)
async def update_calendar_event(
    event_id: int, 
    event_update: CalendarEventUpdate, 
    db: Session = Depends(get_db)
):
    """일정을 수정합니다."""
    try:
        db_event = db.query(models.Calendar).filter(
            models.Calendar.id == event_id
        ).first()
        
        if not db_event:
            raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
        
        update_data = event_update.dict(exclude_unset=True)
        
        for field, value in update_data.items():
            if value is not None:
                setattr(db_event, field, value)
        
        db.commit()
        db.refresh(db_event)
        
        return db_event
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"일정 수정 실패: {str(e)}")

@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(event_id: int, db: Session = Depends(get_db)):
    """일정을 삭제합니다."""
    event = db.query(models.Calendar).filter(models.Calendar.id == event_id).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    
    db.delete(event)
    db.commit()
    
    return {"success": True, "message": "일정이 삭제되었습니다."}

# ========================================
# 알람 관리 API
# ========================================

@router.post("/alarms", response_model=AlarmResponse)
async def create_alarm(alarm: AlarmCreate, db: Session = Depends(get_db)):
    """새 알람을 생성합니다."""
    try:
        user = db.query(models.User).filter(
            models.User.uuid == alarm.user_uuid,
            models.User.is_deleted == False
        ).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
        new_alarm = models.Alarm(
            user_uuid=alarm.user_uuid,
            alarm_time=alarm.alarm_time,
            label=alarm.label,
            calendar_event_id=alarm.calendar_event_id,
            is_enabled=alarm.is_enabled,
            repeat_days=alarm.repeat_days,
            sound_uri=None
        )
        
        db.add(new_alarm)
        db.commit()
        db.refresh(new_alarm)
        
        return new_alarm
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"알람 생성 실패: {str(e)}")

@router.get("/alarms/{user_uuid}", response_model=List[AlarmResponse])
async def get_user_alarms(user_uuid: str, db: Session = Depends(get_db)):
    """사용자의 모든 알람을 조회합니다."""
    alarms = db.query(models.Alarm).filter(
        models.Alarm.user_uuid == user_uuid,
        models.Alarm.is_enabled == True
    ).order_by(models.Alarm.alarm_time).all()
    
    return alarms

@router.put("/alarms/{alarm_id}", response_model=AlarmResponse)
async def update_alarm(
    alarm_id: int, 
    alarm_update: AlarmUpdate, 
    db: Session = Depends(get_db)
):
    """알람을 수정합니다."""
    try:
        db_alarm = db.query(models.Alarm).filter(
            models.Alarm.id == alarm_id
        ).first()
        
        if not db_alarm:
            raise HTTPException(status_code=404, detail="알람을 찾을 수 없습니다.")
        
        update_data = alarm_update.dict(exclude_unset=True)
        
        for field, value in update_data.items():
            if value is not None:
                setattr(db_alarm, field, value)
        
        db.commit()
        db.refresh(db_alarm)
        
        return db_alarm
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"알람 수정 실패: {str(e)}")

@router.delete("/alarms/{alarm_id}")
async def delete_alarm(alarm_id: int, db: Session = Depends(get_db)):
    """알람을 삭제합니다."""
    alarm = db.query(models.Alarm).filter(models.Alarm.id == alarm_id).first()
    
    if not alarm:
        raise HTTPException(status_code=404, detail="알람을 찾을 수 없습니다.")
    
    db.delete(alarm)
    db.commit()
    
    return {"success": True, "message": "알람이 삭제되었습니다."}

@router.put("/alarms/{alarm_id}/toggle")
async def toggle_alarm(alarm_id: int, db: Session = Depends(get_db)):
    """알람을 활성화/비활성화합니다."""
    alarm = db.query(models.Alarm).filter(models.Alarm.id == alarm_id).first()
    
    if not alarm:
        raise HTTPException(status_code=404, detail="알람을 찾을 수 없습니다.")
    
    alarm.is_enabled = not alarm.is_enabled
    db.commit()
    db.refresh(alarm)
    
    return alarm