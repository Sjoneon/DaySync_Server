from pydantic import BaseModel, Field, validator
from typing import Optional, List, Any
from datetime import datetime
import uuid as uuid_pkg

# === 사용자 관련 스키마 ===

class UserBase(BaseModel):
    """사용자 기본 정보 스키마"""
    nickname: Optional[str] = Field(default="사용자", max_length=50, description="사용자 닉네임")
    prep_time: Optional[int] = Field(default=1800, ge=300, le=7200, description="준비 시간(초), 5분~2시간")
    
    @validator('nickname')
    def validate_nickname(cls, v):
        """닉네임 유효성 검사"""
        if v and len(v.strip()) == 0:
            return "사용자"
        return v.strip() if v else "사용자"

class UserCreate(UserBase):
    """사용자 생성 요청 스키마"""
    pass

class UserUpdate(BaseModel):
    """사용자 정보 수정 요청 스키마"""
    nickname: Optional[str] = Field(None, max_length=50, description="수정할 닉네임")
    prep_time: Optional[int] = Field(None, ge=300, le=7200, description="수정할 준비 시간(초)")
    
    @validator('nickname')
    def validate_nickname(cls, v):
        """닉네임 유효성 검사"""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("닉네임은 공백일 수 없습니다")
        return v.strip() if v else v

class UserResponse(UserBase):
    """사용자 정보 응답 스키마"""
    id: int
    uuid: str
    created_at: datetime
    last_active: datetime
    is_deleted: bool
    
    class Config:
        from_attributes = True  # SQLAlchemy 모델에서 변환 허용

class UserCreateResponse(BaseModel):
    """사용자 생성 응답 스키마"""
    uuid: str
    nickname: str
    prep_time: int
    message: str = "사용자가 성공적으로 생성되었습니다"

class UserStatsResponse(BaseModel):
    """사용자 통계 응답 스키마"""
    uuid: str
    nickname: str
    total_sessions: int
    total_messages: int
    last_active: datetime
    created_at: datetime

# === 공통 응답 스키마 ===

class SuccessResponse(BaseModel):
    """성공 응답 표준 스키마"""
    success: bool = True
    message: str
    data: Optional[dict] = None

class ErrorResponse(BaseModel):
    """에러 응답 표준 스키마"""
    success: bool = False
    error: str
    detail: Optional[str] = None

class HealthCheckResponse(BaseModel):
    """헬스체크 응답 스키마"""
    status: str = "healthy"
    timestamp: datetime
    database: str = "connected"
    version: str = "0.1.0"

# === 유틸리티 함수 ===

def generate_uuid() -> str:
    """새로운 UUID 생성"""
    return str(uuid_pkg.uuid4())

def validate_uuid_format(uuid_string: str) -> bool:
    """UUID 형식 유효성 검사"""
    try:
        uuid_obj = uuid_pkg.UUID(uuid_string)
        return str(uuid_obj) == uuid_string
    except (ValueError, TypeError):
        return False
    
# === 경로 관리 함수 ===
class RouteSaveRequest(BaseModel):
    """경로 저장 요청 스키마"""
    start_lat: float = Field(..., description="출발지 위도", ge=-90, le=90)
    start_lng: float = Field(..., description="출발지 경도", ge=-180, le=180)
    end_lat: float = Field(..., description="도착지 위도", ge=-90, le=90)
    end_lng: float = Field(..., description="도착지 경도", ge=-180, le=180)
    route_data: List[dict] = Field(..., description="경로 정보 JSON 배열")
    user_uuid: Optional[str] = Field(None, description="사용자 UUID (선택사항)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_lat": 36.6243,
                "start_lng": 127.4828,
                "end_lat": 36.7224,
                "end_lng": 127.4958,
                "route_data": [
                    {
                        "type": "대중교통",
                        "duration": 25,
                        "bus_wait_time": 5,
                        "bus_number": "501",
                        "start_stop_name": "서원대학교",
                        "end_stop_name": "청주공항"
                    }
                ],
                "user_uuid": "test-uuid-1234"
            }
        }

class RouteResponse(BaseModel):
    """경로 응답 스키마"""
    id: int = Field(..., description="경로 ID")
    start_lat: float = Field(..., description="출발지 위도")
    start_lng: float = Field(..., description="출발지 경도")
    end_lat: float = Field(..., description="도착지 위도")
    end_lng: float = Field(..., description="도착지 경도")
    route_data: List[dict] = Field(..., description="경로 정보 JSON")
    created_at: datetime = Field(..., description="생성 시간")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "start_lat": 36.6357,
                "start_lng": 127.4914,
                "end_lat": 36.6500,
                "end_lng": 127.5000,
                "route_data": [
                    {
                        "type": "대중교통",
                        "duration": 25,
                        "bus_number": "501"
                    }
                ],
                "created_at": "2025-11-02T10:30:00"
            }
        }

class RouteSearchRequest(BaseModel):
    """경로 검색 요청 스키마"""
    start_lat: float = Field(..., description="출발지 위도", ge=-90, le=90)
    start_lng: float = Field(..., description="출발지 경도", ge=-180, le=180)
    end_lat: float = Field(..., description="도착지 위도", ge=-90, le=90)
    end_lng: float = Field(..., description="도착지 경도", ge=-180, le=180)
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_lat": 36.6357,
                "start_lng": 127.4914,
                "end_lat": 36.6500,
                "end_lng": 127.5000
            }
        }

class RouteSearchResponse(BaseModel):
    """경로 검색 응답 스키마"""
    found: bool = Field(..., description="경로 발견 여부")
    route: Optional[RouteResponse] = Field(None, description="발견된 경로 정보")
    
    class Config:
        json_schema_extra = {
            "example": {
                "found": True,
                "route": {
                    "id": 1,
                    "start_lat": 36.6357,
                    "start_lng": 127.4914,
                    "end_lat": 36.6500,
                    "end_lng": 127.5000,
                    "route_data": [],
                    "created_at": "2025-11-02T10:30:00"
                }
            }
        }
