from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import google.generativeai as genai
import os
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path
import logging

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from ..database import get_db
from .. import models

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

genai.configure(api_key=GEMINI_API_KEY)

MAX_SESSIONS_PER_USER = 15
MAX_MESSAGES_PER_SESSION = 50
MESSAGE_HISTORY_LIMIT = 10

create_schedule_function = genai.protos.FunctionDeclaration(
    name="create_schedule",
    description="사용자의 일정을 생성합니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "title": genai.protos.Schema(type=genai.protos.Type.STRING, description="일정 제목"),
            "start_time": genai.protos.Schema(type=genai.protos.Type.STRING, description="시작 시간 (ISO 8601 형식)"),
            "end_time": genai.protos.Schema(type=genai.protos.Type.STRING, description="종료 시간 (선택)"),
            "description": genai.protos.Schema(type=genai.protos.Type.STRING, description="일정 설명 (선택)"),
            "location": genai.protos.Schema(type=genai.protos.Type.STRING, description="장소 (선택)")
        },
        required=["title", "start_time"]
    )
)

create_alarm_function = genai.protos.FunctionDeclaration(
    name="create_alarm",
    description="사용자의 알람을 설정합니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "time": genai.protos.Schema(type=genai.protos.Type.STRING, description="알람 시간 (ISO 8601 형식)"),
            "label": genai.protos.Schema(type=genai.protos.Type.STRING, description="알람 레이블"),
            "repeat_days": genai.protos.Schema(type=genai.protos.Type.STRING, description="반복 요일 (선택)")
        },
        required=["time", "label"]
    )
)

get_schedule_info_function = genai.protos.FunctionDeclaration(
    name="get_schedule_info",
    description="일정 정보를 조회합니다. 제목이나 날짜로 검색할 수 있습니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "title": genai.protos.Schema(type=genai.protos.Type.STRING, description="조회할 일정 제목 (선택)"),
            "search_date": genai.protos.Schema(type=genai.protos.Type.STRING, description="조회할 날짜 (ISO 8601 형식, 선택)")
        }
    )
)

update_schedule_function = genai.protos.FunctionDeclaration(
    name="update_schedule",
    description="기존 일정을 수정합니다. 날짜 변경, 제목 변경, 설명 변경이 모두 가능합니다. new_start_time으로 날짜와 시간을 변경할 수 있습니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "title": genai.protos.Schema(type=genai.protos.Type.STRING, description="수정할 일정 제목"),
            "new_title": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 제목 (선택)"),
            "new_start_time": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 시작 시간 (선택)"),
            "new_end_time": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 종료 시간 (선택)"),
            "new_description": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 설명 (선택)"),
            "new_location": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 장소 (선택)")
        },
        required=["title"]
    )
)

delete_schedule_function = genai.protos.FunctionDeclaration(
    name="delete_schedule",
    description="일정을 삭제합니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "title": genai.protos.Schema(type=genai.protos.Type.STRING, description="삭제할 일정 제목")
        },
        required=["title"]
    )
)

update_alarm_function = genai.protos.FunctionDeclaration(
    name="update_alarm",
    description="알람을 수정합니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "label": genai.protos.Schema(type=genai.protos.Type.STRING, description="수정할 알람 레이블"),
            "new_time": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 알람 시간 (선택)"),
            "new_label": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 레이블 (선택)")
        },
        required=["label"]
    )
)

delete_alarm_function = genai.protos.FunctionDeclaration(
    name="delete_alarm",
    description="알람을 삭제합니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "label": genai.protos.Schema(type=genai.protos.Type.STRING, description="삭제할 알람 레이블")
        },
        required=["label"]
    )
)

search_route_function = genai.protos.FunctionDeclaration(
    name="search_route",
    description="사용자가 요청한 목적지까지의 경로를 탐색합니다. 출발지가 명시되지 않은 경우 현재 위치 사용 여부를 묻습니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "destination": genai.protos.Schema(type=genai.protos.Type.STRING, description="도착지 주소 또는 장소명"),
            "start_location": genai.protos.Schema(type=genai.protos.Type.STRING, description="출발지 (선택, 없으면 현재 위치 사용 여부 확인)")
        },
        required=["destination"]
    )
)

get_weather_info_function = genai.protos.FunctionDeclaration(
    name="get_weather_info",
    description="날씨 정보를 조회합니다. 오늘, 내일, 모레까지의 날씨만 제공 가능합니다.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "target_date": genai.protos.Schema(
                type=genai.protos.Type.STRING, 
                description="조회할 날짜 (today, tomorrow, day_after_tomorrow 중 하나)"
            )
        },
        required=["target_date"]
    )
)

tools = genai.protos.Tool(
    function_declarations=[
        create_schedule_function,
        create_alarm_function,
        get_schedule_info_function,
        update_schedule_function,
        delete_schedule_function,
        update_alarm_function,
        delete_alarm_function,
        search_route_function,
        get_weather_info_function
    ]
)

model = genai.GenerativeModel('gemini-2.0-flash', tools=[tools])

def is_question_message(message: str) -> bool:
    question_patterns = ['?', '할까요', '하시겠어요', '하실래요', '괜찮으세요', '좋으세요', '어때요', '어떠세요']
    return any(pattern in message for pattern in question_patterns)

def normalize_short_response(message: str, last_ai_message: str = None) -> tuple[str, bool]:
    if not last_ai_message or not is_question_message(last_ai_message):
        return message, False
    
    normalized_msg = message.strip().lower()
    
    positive_patterns = ['응', '어', 'ㅇ', 'ㅇㅇ', 'ᄋ', 'ᄋᄋ', '네', '넵', 'ㄴㅇ', 'yes', 'ok', '오키', '오케이', '좋아', 'ㅇㅋ']
    negative_patterns = ['노', 'ㄴ', 'ㄴㄴ', 'ᄂ', 'ᄂᄂ', '시름', '아니', '아뇨', '싫어', 'no', 'ㄴㄴ', 'ㄴㄴㄴ', '노노']
    
    if normalized_msg in positive_patterns:
        return "네, 그렇게 해주세요", True
    
    if normalized_msg in negative_patterns:
        return "아니요, 필요 없습니다", True
    
    return message, False

def format_datetime_korean(iso_datetime: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_datetime)
        return dt.strftime('%Y년 %m월 %d일 %H시 %M분')
    except:
        return iso_datetime

def execute_function_call(function_name: str, args: dict, user_uuid: str, db: Session):
    if function_name == "create_schedule":
        if not args.get("title") or not args.get("start_time"):
            return {"status": "error", "message": "제목과 시작 시간이 필요합니다."}
        
        new_event = models.Calendar(
            user_uuid=user_uuid,
            event_title=args.get("title"),
            event_start_time=datetime.fromisoformat(args.get("start_time")),
            event_end_time=datetime.fromisoformat(args.get("end_time")) if args.get("end_time") else None,
            description=args.get("description"),
            location_alias=args.get("location")
        )
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        
        korean_time = format_datetime_korean(args.get("start_time"))
        return {
            "status": "success",
            "message": f"{korean_time}에 '{args.get('title')}' 일정이 추가되었습니다.",
            "event_id": new_event.id
        }
    
    elif function_name == "create_alarm":
        if not args.get("time") or not args.get("label"):
            return {"status": "error", "message": "시간과 레이블이 필요합니다."}
        
        new_alarm = models.Alarm(
            user_uuid=user_uuid,
            alarm_time=datetime.fromisoformat(args.get("time")),
            label=args.get("label"),
            is_enabled=True,
            repeat_days=args.get("repeat_days")
        )
        db.add(new_alarm)
        db.commit()
        db.refresh(new_alarm)
        
        korean_time = format_datetime_korean(args.get("time"))
        return {
            "status": "success",
            "message": f"{korean_time}에 '{args.get('label')}' 알람이 설정되었습니다.",
            "alarm_id": new_alarm.id
        }
    
    elif function_name == "get_schedule_info":
        query = db.query(models.Calendar).filter(models.Calendar.user_uuid == user_uuid)
        
        if args.get("title"):
            query = query.filter(models.Calendar.event_title.contains(args.get("title")))
        
        if args.get("search_date"):
            search_date = datetime.fromisoformat(args.get("search_date"))
            query = query.filter(
                models.Calendar.event_start_time >= search_date,
                models.Calendar.event_start_time < search_date + timedelta(days=1)
            )
        
        events = query.order_by(models.Calendar.event_start_time).all()
        
        if not events:
            return {"status": "success", "message": "일정이 없습니다.", "events": []}
        
        events_list = []
        for event in events:
            events_list.append({
                "title": event.event_title,
                "start_time": event.event_start_time.isoformat(),
                "end_time": event.event_end_time.isoformat() if event.event_end_time else None,
                "description": event.description,
                "location": event.location_alias
            })
        
        return {"status": "success", "events": events_list}
    
    elif function_name == "update_schedule":
        if not args.get("title"):
            return {"status": "error", "message": "수정할 일정 제목이 필요합니다."}
        
        event = db.query(models.Calendar).filter(
            models.Calendar.user_uuid == user_uuid,
            models.Calendar.event_title == args.get("title")
        ).first()
        
        if not event:
            return {"status": "error", "message": f"'{args.get('title')}' 일정을 찾을 수 없습니다."}
        
        if args.get("new_title"):
            event.event_title = args.get("new_title")
        if args.get("new_start_time"):
            event.event_start_time = datetime.fromisoformat(args.get("new_start_time"))
        if args.get("new_end_time"):
            event.event_end_time = datetime.fromisoformat(args.get("new_end_time"))
        if args.get("new_description"):
            event.description = args.get("new_description")
        if args.get("new_location"):
            event.location_alias = args.get("new_location")
        
        db.commit()
        
        return {
            "status": "success",
            "message": f"'{args.get('title')}' 일정이 수정되었습니다."
        }
    
    elif function_name == "delete_schedule":
        if not args.get("title"):
            return {"status": "error", "message": "삭제할 일정 제목이 필요합니다."}
        
        event = db.query(models.Calendar).filter(
            models.Calendar.user_uuid == user_uuid,
            models.Calendar.event_title == args.get("title")
        ).first()
        
        if not event:
            return {"status": "error", "message": f"'{args.get('title')}' 일정을 찾을 수 없습니다."}
        
        title = event.event_title
        db.delete(event)
        db.commit()
        
        return {
            "status": "success",
            "message": f"'{title}' 일정이 삭제되었습니다."
        }
    
    elif function_name == "update_alarm":
        if not args.get("label"):
            return {"status": "error", "message": "수정할 알람 레이블이 필요합니다."}
        
        alarm = db.query(models.Alarm).filter(
            models.Alarm.user_uuid == user_uuid,
            models.Alarm.label == args.get("label")
        ).first()
        
        if not alarm:
            return {"status": "error", "message": f"'{args.get('label')}' 알람을 찾을 수 없습니다."}
        
        if args.get("new_time"):
            alarm.alarm_time = datetime.fromisoformat(args.get("new_time"))
        if args.get("new_label"):
            alarm.label = args.get("new_label")
        
        db.commit()
        
        return {
            "status": "success",
            "message": f"'{args.get('label')}' 알람이 수정되었습니다."
        }
    
    elif function_name == "delete_alarm":
        if not args.get("label"):
            return {"status": "error", "message": "삭제할 알람 레이블이 필요합니다."}
        
        alarm = db.query(models.Alarm).filter(
            models.Alarm.user_uuid == user_uuid,
            models.Alarm.label == args.get("label")
        ).first()
        
        if not alarm:
            return {"status": "error", "message": f"'{args.get('label')}' 알람을 찾을 수 없습니다."}
        
        label = alarm.label
        db.delete(alarm)
        db.commit()
        
        return {
            "status": "success",
            "message": f"'{label}' 알람이 삭제되었습니다."
        }
        
    elif function_name == "search_route":
        destination = args.get("destination")
        start_location = args.get("start_location")
        
        if not destination:
            return {"status": "error", "message": "도착지가 필요합니다."}
        
        # 출발지가 명시적으로 제공되지 않은 경우
        if not start_location:
            return {
                "status": "pending",
                "message": "현재 위치를 출발지로 사용할까요?",
                "require_location_confirmation": True,
                "destination": destination
            }
        
        # "현재 위치" 키워드 처리
        if start_location and any(keyword in start_location for keyword in ["현재", "지금", "여기"]):
            start_location = "CURRENT_LOCATION"  # 안드로이드에서 GPS로 처리하도록 특수 값
        
        # 경로 탐색 준비 완료
        return {
            "status": "success",
            "message": f"{start_location}에서 {destination}까지 경로를 탐색합니다.",
            "start_location": start_location,
            "destination": destination,
            "action": "search_route"
        }
    
    elif function_name == "get_weather_info":
        target_date = args.get("target_date")
        
        if not target_date:
            return {"status": "error", "message": "날짜 정보가 필요합니다."}
        
        valid_dates = ["today", "tomorrow", "day_after_tomorrow"]
        if target_date not in valid_dates:
            return {
                "status": "error", 
                "message": "현재는 모레까지의 날씨만 알려드릴 수 있어요"
            }
        
        return {
            "status": "success",
            "action": "get_weather",
            "target_date": target_date,
            "message": "날씨 정보를 조회합니다."
        }
    
    else:
        return {"status": "error", "message": "알 수 없는 함수입니다."}

def cleanup_old_sessions(db: Session, user_uuid: str):
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    inactive_sessions = db.query(models.Session).filter(
        models.Session.user_uuid == user_uuid,
        models.Session.updated_at < thirty_days_ago
    ).all()
    
    if inactive_sessions:
        for session in inactive_sessions:
            db.delete(session)
        logger.info(f"사용자 {user_uuid}의 30일 이상 미사용 세션 {len(inactive_sessions)}개 삭제")
    
    sessions = db.query(models.Session).filter(
        models.Session.user_uuid == user_uuid
    ).order_by(models.Session.updated_at.desc()).all()
    
    if len(sessions) > MAX_SESSIONS_PER_USER:
        sessions_to_delete = sessions[MAX_SESSIONS_PER_USER:]
        for session in sessions_to_delete:
            db.delete(session)
        logger.info(f"사용자 {user_uuid}의 15개 초과 세션 {len(sessions_to_delete)}개 삭제")

def cleanup_old_messages(db: Session, session_id: int):
    messages = db.query(models.Message).filter(
        models.Message.session_id == session_id
    ).order_by(models.Message.created_at.desc()).all()
    
    if len(messages) > MAX_MESSAGES_PER_SESSION:
        messages_to_delete = messages[MAX_MESSAGES_PER_SESSION:]
        for message in messages_to_delete:
            db.delete(message)
        logger.info(f"세션 {session_id}의 오래된 메시지 {len(messages_to_delete)}개 삭제")

class ChatRequest(BaseModel):
    user_uuid: str
    message: str
    session_id: Optional[int] = None
    context: Optional[dict] = None

class ChatResponse(BaseModel):
    success: bool
    ai_response: str
    session_id: int
    message_id: int
    function_called: Optional[str] = None
    route_search_requested: Optional[bool] = None
    start_location: Optional[str] = None
    destination: Optional[str] = None
    weather_requested: Optional[bool] = None
    weather_target_date: Optional[str] = None

class SessionUpdateRequest(BaseModel):
    title: str

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest, db: Session = Depends(get_db)):
    """AI 대화 처리"""
    try:
        user = db.query(models.User).filter(
            models.User.uuid == request.user_uuid,
            models.User.is_deleted == False
        ).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
        # 세션 처리
        if request.session_id:
            session = db.query(models.Session).filter(
                models.Session.id == request.session_id,
                models.Session.user_uuid == request.user_uuid
            ).first()
            
            if not session:
                raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
        else:
            session = models.Session(
                user_uuid=request.user_uuid,
                title="새 대화",
                category="general"
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        
        # 대화 히스토리 조회 (최근 10개)
        recent_messages = db.query(models.Message).filter(
            models.Message.session_id == session.id
        ).order_by(models.Message.created_at.desc()).limit(MESSAGE_HISTORY_LIMIT).all()
        
        # 프롬프트 구성
        conversation_history = []
        for msg in reversed(recent_messages):
            role = "user" if msg.is_user else "model"
            conversation_history.append({
                "role": role,
                "parts": [msg.content]
            })
        
        # 짧은 긍정/부정 표현 전처리
        processed_message = request.message
        was_normalized = False
        
        if recent_messages:
            last_ai_message = None
            for msg in recent_messages:
                if not msg.is_user:
                    last_ai_message = msg.content
                    break
            
            if last_ai_message:
                processed_message, was_normalized = normalize_short_response(request.message, last_ai_message)
                if was_normalized:
                    logger.info(f"짧은 표현 정규화: '{request.message}' -> '{processed_message}'")
        
        current_time = datetime.now()
        system_prompt = f"""당신은 DaySync 앱의 AI 비서입니다.

현재 시간: {current_time.strftime('%Y년 %m월 %d일 %H시 %M분')}

주요 기능: 일정 관리, 알람 설정, 경로 안내, 날씨 정보

== 핵심 대화 원칙 ==
1. 대화 맥락을 정확히 파악하고 기억하세요
2. 한 번 물어본 정보는 절대 다시 묻지 마세요
3. 필요한 정보가 모두 있으면 즉시 함수 호출
4. 정보가 부족하면 딱 한 번만 질문

== 시간 이해 및 변환 규칙 (최우선!) ==
**사용자가 말하는 시간을 이해하고 자동 변환:**
- "6시" → {current_time.replace(hour=6, minute=0, second=0).isoformat()}
- "6시 20분" → {current_time.replace(hour=6, minute=20, second=0).isoformat()}
- "오후 3시" → {current_time.replace(hour=15, minute=0, second=0).isoformat()}
- "내일 9시" → {(current_time + timedelta(days=1)).replace(hour=9, minute=0, second=0).isoformat()}
- "3시간 뒤" → {(current_time + timedelta(hours=3)).isoformat()}

**절대 금지:**
- 사용자에게 "ISO 8601", "형식", "isoformat" 같은 용어 사용
- 사용자에게 "2025-11-09T06:00:00" 같은 형식 보여주기
- 시간을 이해했는데 다시 묻기

**올바른 대화:**
사용자: "6시에 알람"
AI: "알람 레이벨을 알려주세요" (시간은 이미 이해함)
사용자: "운동"
→ create_alarm(time="{current_time.replace(hour=6, minute=0).isoformat()}", label="운동")
→ "6시에 운동 알람을 설정했어요"

== 알람/일정 추가 규칙 ==
필요 정보:
- 알람: 시간 + 레이블
- 일정: 제목 + 시작시간

**시간 정보가 자연스러운 한국어로 제공되면 즉시 이해하고 변환**

대화 예시:
사용자: "내일 오전 9시에 회의"
→ 시작시간(내일 오전 9시)과 제목(회의) 모두 있음
→ 즉시 create_schedule(title="회의", start_time="{(current_time + timedelta(days=1)).replace(hour=9, minute=0).isoformat()}")
→ "내일 오전 9시에 회의 일정을 추가했어요"

사용자: "알림 제목은 간단하고 시작 시간은 6시"
→ 제목(간단)과 시작시간(6시) 모두 있음
→ 즉시 create_schedule(title="간단", start_time="{current_time.replace(hour=6, minute=0).isoformat()}")
→ "6시에 간단 일정을 추가했어요"

절대 금지:
- 시간을 이해했는데 ISO 형식으로 다시 요청
- "형식"이라는 단어 사용
- 정보를 다 받았는데 다시 확인하는 질문

== 알람/일정 삭제 규칙 ==
**사용자가 "삭제"를 명시적으로 말한 경우에만 삭제 동작**

사용자: "나나 알람 삭제해줘"
AI: "알람 레이블이 '나나'인 알람을 삭제할까요?"
사용자: "응"
→ 즉시 delete_alarm(label="나나") 호출

중요: 추가/수정 대화 중에는 절대 삭제 묻지 마세요!

== 경로 탐색 규칙 (최우선!) ==

**CRITICAL: 사용자가 "현재 위치에서"라고 말하면 ALWAYS start_location="현재 위치"를 포함하세요!**

**올바른 함수 호출 예시:**
- 사용자: "현재 위치에서 청주 연일빌딩으로 가는 길"
  → search_route(start_location="현재 위치", destination="청주 연일빌딩")
  
- 사용자: "청주역에서 청주대학교까지"
  → search_route(start_location="청주역", destination="청주대학교")
  
- 사용자: "청주교도소 가는 법"
  → search_route(destination="청주교도소")
  ← 이 경우만 start_location 없음

**절대 금지:**
- "현재 위치에서"라고 말했는데 start_location을 빼먹는 것
- destination만 있으면 된다고 생각하는 것
- 사용자에게 다시 출발지를 물어보는 것

== 날씨 정보 규칙 ==
"오늘 날씨" → get_weather_info(target_date="today")
"내일 날씨" → get_weather_info(target_date="tomorrow")
"모레 날씨" → get_weather_info(target_date="day_after_tomorrow")

== 답변 스타일 ==
- 친절하고 간결하게
- 자연스러운 한국어만 사용
- 사용자에게는 "6시", "내일 오전 9시" 같은 표현만 사용
- 함수 호출 시에만 내부적으로 ISO 형식 사용
- 같은 질문 절대 반복 금지
"""
        
        if request.context:
            # Context에서 날씨 데이터 추출
            if isinstance(request.context, dict) and "weather_data" in request.context:
                weather_info = request.context["weather_data"]
                system_prompt += f"\n\n### 날씨 정보\n{weather_info}\n\n위 날씨 정보를 바탕으로 사용자에게 자연스럽게 설명해주세요."
            else:
                system_prompt += f"\n\n추가 컨텍스트: {request.context}"
        
        # Gemini API 호출
        if conversation_history:
            chat = model.start_chat(history=conversation_history)
            response = chat.send_message(system_prompt + "\n\n" + processed_message)
        else:
            response = model.generate_content(system_prompt + "\n\n사용자: " + processed_message)
        
        # Function Call 처리
        function_called = None
        ai_response_text = ""
        route_search_data = None  # 경로 탐색 데이터 저장용
        weather_request_data = None
        
        if response and response.candidates and len(response.candidates) > 0:
            if response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        func_call = part.function_call
                        function_called = func_call.name
                        
                        try:
                            func_args = dict(func_call.args)
                            logger.info(f"함수 호출: {func_call.name}, 파라미터: {func_args}")
                            
                            result = execute_function_call(func_call.name, func_args, request.user_uuid, db)
                            logger.info(f"함수 실행 결과: {result}")
                            
                            # 경로 탐색 결과 저장
                            if func_call.name == "search_route" and isinstance(result, dict):
                                logger.info(f"🔍 search_route 함수 감지됨")
                                logger.info(f"🔍 result 내용: {result}")
                                logger.info(f"🔍 status 값: '{result.get('status')}'")
                                logger.info(f"🔍 action 값: '{result.get('action')}'")
                                
                                if result.get("status") == "success" and result.get("action") == "search_route":
                                    route_search_data = {
                                        "requested": True,
                                        "start_location": result.get("start_location"),
                                        "destination": result.get("destination")
                                    }
                                    logger.info(f"✅ 경로 탐색 데이터 추출 완료: {route_search_data}")
                                else:
                                    logger.warning(f"❌ 조건 불일치 - status: {result.get('status')}, action: {result.get('action')}")
                                    
                            # 날씨 조회 결과 저장
                            if func_call.name == "get_weather_info" and isinstance(result, dict):
                                if result.get("action") == "get_weather":
                                    weather_request_data = {
                                        "requested": True,
                                        "target_date": result.get("target_date")
                                    }
                            
                            function_response = genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=func_call.name,
                                    response={"result": result}
                                )
                            )
                            
                            # 최종 응답 생성
                            if conversation_history:
                                final_response = chat.send_message(function_response)
                            else:
                                history = [
                                    {"role": "user", "parts": [system_prompt + "\n\n사용자: " + processed_message]},
                                    {"role": "model", "parts": [part]}
                                ]
                                chat = model.start_chat(history=history)
                                final_response = chat.send_message(function_response)
                            
                            ai_response_text = final_response.text if final_response else ""
                        except Exception as e:
                            logger.error(f"함수 실행 중 오류: {str(e)}", exc_info=True)
                            ai_response_text = f"함수 실행 중 오류가 발생했습니다: {str(e)}"
                    elif hasattr(part, 'text'):
                        ai_response_text = part.text
        
        if not ai_response_text:
            ai_response_text = response.text if response else "응답을 생성할 수 없습니다."
        
        # 메시지 저장
        user_message = models.Message(
            session_id=session.id,
            content=request.message,
            is_user=True
        )
        db.add(user_message)
        
        ai_message = models.Message(
            session_id=session.id,
            content=ai_response_text,
            is_user=False
        )
        db.add(ai_message)
        
        # 세션 업데이트 시간 갱신
        session.updated_at = datetime.now()
        
        db.commit()
        db.refresh(ai_message)
        
        # 오래된 데이터 정리
        cleanup_old_messages(db, session.id)
        cleanup_old_sessions(db, request.user_uuid)
        db.commit()
        
        # 경로 탐색 요청 확인
        route_search_requested = False
        route_start_location = None
        route_destination = None
        weather_requested = False
        weather_target_date = None
        
        if route_search_data:
            route_search_requested = route_search_data.get("requested", False)
            route_start_location = route_search_data.get("start_location")
            route_destination = route_search_data.get("destination")
            
            
        if weather_request_data:
            weather_requested = weather_request_data.get("requested", False)
            weather_target_date = weather_request_data.get("target_date")
            
        
        return ChatResponse(
            success=True,
            ai_response=ai_response_text,
            session_id=session.id,
            message_id=ai_message.id,
            function_called=function_called,
            route_search_requested=route_search_requested,
            start_location=route_start_location,
            destination=route_destination,
            weather_requested=weather_requested,
            weather_target_date=weather_target_date
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"AI 처리 중 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI 처리 중 오류 발생: {str(e)}")

@router.get("/sessions/{user_uuid}")
async def get_user_sessions(user_uuid: str, db: Session = Depends(get_db)):
    sessions = db.query(models.Session).filter(
        models.Session.user_uuid == user_uuid
    ).order_by(models.Session.updated_at.desc()).limit(MAX_SESSIONS_PER_USER).all()
    
    sessions_data = []
    for session in sessions:
        sessions_data.append({
            "id": session.id,
            "title": session.title,
            "category": session.category,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        })
    
    return {"success": True, "sessions": sessions_data}

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: int, db: Session = Depends(get_db)):
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    
    messages = db.query(models.Message).filter(
        models.Message.session_id == session_id
    ).order_by(models.Message.created_at).all()
    
    messages_data = []
    for msg in messages:
        messages_data.append({
            "id": msg.id,
            "content": msg.content,
            "is_user": msg.is_user,
            "created_at": msg.created_at.isoformat()
        })
    
    return {"success": True, "messages": messages_data}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, user_uuid: str, db: Session = Depends(get_db)):
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_uuid == user_uuid
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    
    db.delete(session)
    db.commit()
    
    return {"success": True, "message": "세션이 삭제되었습니다."}

@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: int, 
    user_uuid: str, 
    request: SessionUpdateRequest, 
    db: Session = Depends(get_db)
):
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_uuid == user_uuid
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    
    session.title = request.title
    db.commit()
    
    return {"success": True, "message": "세션 제목이 수정되었습니다."}