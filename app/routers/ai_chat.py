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

# Gemini API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

genai.configure(api_key=GEMINI_API_KEY)

# 세션 및 메시지 제한 설정
MAX_SESSIONS_PER_USER = 15
MAX_MESSAGES_PER_SESSION = 50
MESSAGE_HISTORY_LIMIT = 10

# 함수 정의
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
            "title": genai.protos.Schema(type=genai.protos.Type.STRING, description="수정할 일정 제목 (검색용)"),
            "search_date": genai.protos.Schema(type=genai.protos.Type.STRING, description="수정할 일정의 날짜 (선택, ISO 8601 형식)"),
            "new_start_time": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 시작 시간 (선택, ISO 8601 형식) - 날짜 변경 시 사용"),
            "new_title": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 제목 (선택)"),
            "new_description": genai.protos.Schema(type=genai.protos.Type.STRING, description="새로운 설명 (선택)")
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
            "title": genai.protos.Schema(type=genai.protos.Type.STRING, description="삭제할 일정 제목"),
            "search_date": genai.protos.Schema(type=genai.protos.Type.STRING, description="삭제할 일정의 날짜 (선택)")
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

# 함수 도구 정의
tools = genai.protos.Tool(
    function_declarations=[
        create_schedule_function,
        create_alarm_function,
        get_schedule_info_function,
        update_schedule_function,
        delete_schedule_function,
        update_alarm_function,
        delete_alarm_function
    ]
)

model = genai.GenerativeModel('gemini-2.0-flash-exp', tools=[tools])

def format_datetime_korean(iso_datetime: str) -> str:
    """ISO 8601 형식을 한국어로 변환"""
    try:
        dt = datetime.fromisoformat(iso_datetime)
        return dt.strftime('%Y년 %m월 %d일 %H시 %M분')
    except:
        return iso_datetime

def execute_function_call(function_name: str, args: dict, user_uuid: str, db: Session):
    """함수 호출 실행 로직"""
    if function_name == "create_schedule":
        if not args.get("title") or not args.get("start_time"):
            return {"status": "error", "message": "제목과 시작 시간이 필요합니다."}
        
        new_event = models.Calendar(
            user_uuid=user_uuid,
            event_title=args.get("title"),
            event_start_time=datetime.fromisoformat(args.get("start_time")),
            event_end_time=datetime.fromisoformat(args.get("end_time")) if args.get("end_time") else None,
            event_description=args.get("description"),
            event_location=args.get("location")
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
            query = query.filter(models.Calendar.event_title.like(f"%{args.get('title')}%"))
        
        if args.get("search_date"):
            search_date = datetime.fromisoformat(args.get("search_date"))
            start_of_day = search_date.replace(hour=0, minute=0, second=0)
            end_of_day = search_date.replace(hour=23, minute=59, second=59)
            query = query.filter(
                models.Calendar.event_start_time >= start_of_day,
                models.Calendar.event_start_time <= end_of_day
            )
        
        events = query.order_by(models.Calendar.event_start_time).all()
        
        if not events:
            return {"status": "error", "message": "해당하는 일정을 찾을 수 없습니다."}
        
        events_info = []
        for event in events:
            korean_time = format_datetime_korean(event.event_start_time.isoformat())
            events_info.append({
                "title": event.event_title,
                "start_time": korean_time,
                "description": event.event_description or "설명 없음",
                "location": event.event_location or "장소 없음"
            })
        
        return {
            "status": "success",
            "message": f"{len(events)}개의 일정을 찾았습니다.",
            "events": events_info
        }
    
    elif function_name == "update_schedule":
        query = db.query(models.Calendar).filter(
            models.Calendar.user_uuid == user_uuid,
            models.Calendar.event_title.like(f"%{args.get('title')}%")
        )
        
        if args.get("search_date"):
            search_date = datetime.fromisoformat(args.get("search_date"))
            start_of_day = search_date.replace(hour=0, minute=0, second=0)
            end_of_day = search_date.replace(hour=23, minute=59, second=59)
            query = query.filter(
                models.Calendar.event_start_time >= start_of_day,
                models.Calendar.event_start_time <= end_of_day
            )
        
        event = query.first()
        
        if not event:
            return {"status": "error", "message": "해당하는 일정을 찾을 수 없습니다."}
        
        if args.get("new_start_time"):
            event.event_start_time = datetime.fromisoformat(args.get("new_start_time"))
        if args.get("new_title"):
            event.event_title = args.get("new_title")
        if args.get("new_description"):
            event.event_description = args.get("new_description")
        
        db.commit()
        db.refresh(event)
        
        korean_time = format_datetime_korean(event.event_start_time.isoformat())
        return {
            "status": "success",
            "message": f"'{event.event_title}' 일정이 {korean_time}(으)로 수정되었습니다."
        }
    
    elif function_name == "delete_schedule":
        query = db.query(models.Calendar).filter(
            models.Calendar.user_uuid == user_uuid,
            models.Calendar.event_title.like(f"%{args.get('title')}%")
        )
        
        if args.get("search_date"):
            search_date = datetime.fromisoformat(args.get("search_date"))
            start_of_day = search_date.replace(hour=0, minute=0, second=0)
            end_of_day = search_date.replace(hour=23, minute=59, second=59)
            query = query.filter(
                models.Calendar.event_start_time >= start_of_day,
                models.Calendar.event_start_time <= end_of_day
            )
        
        event = query.first()
        
        if not event:
            return {"status": "error", "message": "해당하는 일정을 찾을 수 없습니다."}
        
        title = event.event_title
        db.delete(event)
        db.commit()
        
        return {
            "status": "success",
            "message": f"'{title}' 일정이 삭제되었습니다."
        }
    
    elif function_name == "update_alarm":
        alarm = db.query(models.Alarm).filter(
            models.Alarm.user_uuid == user_uuid,
            models.Alarm.label.like(f"%{args.get('label')}%")
        ).first()
        
        if not alarm:
            return {"status": "error", "message": "해당하는 알람을 찾을 수 없습니다."}
        
        if args.get("new_time"):
            alarm.alarm_time = datetime.fromisoformat(args.get("new_time"))
        if args.get("new_label"):
            alarm.label = args.get("new_label")
        
        db.commit()
        db.refresh(alarm)
        
        korean_time = format_datetime_korean(alarm.alarm_time.isoformat())
        return {
            "status": "success",
            "message": f"'{alarm.label}' 알람이 {korean_time}(으)로 수정되었습니다."
        }
    
    elif function_name == "delete_alarm":
        alarm = db.query(models.Alarm).filter(
            models.Alarm.user_uuid == user_uuid,
            models.Alarm.label.like(f"%{args.get('label')}%")
        ).first()
        
        if not alarm:
            return {"status": "error", "message": "해당하는 알람을 찾을 수 없습니다."}
        
        label = alarm.label
        db.delete(alarm)
        db.commit()
        
        return {
            "status": "success",
            "message": f"'{label}' 알람이 삭제되었습니다."
        }
    
    else:
        return {"status": "error", "message": "알 수 없는 함수입니다."}

def cleanup_old_sessions(db: Session, user_uuid: str):
    """오래된 세션 정리 (최근 15개 유지)"""
    sessions = db.query(models.Session).filter(
        models.Session.user_uuid == user_uuid
    ).order_by(models.Session.updated_at.desc()).all()
    
    if len(sessions) > MAX_SESSIONS_PER_USER:
        sessions_to_delete = sessions[MAX_SESSIONS_PER_USER:]
        for session in sessions_to_delete:
            db.delete(session)
        logger.info(f"사용자 {user_uuid}의 오래된 세션 {len(sessions_to_delete)}개 삭제")

def cleanup_old_messages(db: Session, session_id: int):
    """오래된 메시지 정리 (최대 50개 유지)"""
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
        
        current_time = datetime.now()
        system_prompt = f"""당신은 DaySync 앱의 AI 비서입니다.

현재 시간: {current_time.strftime('%Y년 %m월 %d일 %H시 %M분')}

주요 기능:
1. 일정 관리 (추가/조회/수정/삭제)
2. 알람 설정 (추가/조회/수정/삭제)
3. 경로 안내 및 교통 정보

일정/알람 처리 규칙:
- 필요한 정보가 모두 있으면 즉시 함수 호출
- 정보가 부족하면 간단히 한 번만 질문
- "시간", "제목" 등 단어 하나만 말하면 조회로 판단
- 재확인 질문은 하지 말고 바로 실행

시간 변환:
- "3시간 뒤" = {(current_time + timedelta(hours=3)).isoformat()}
- "내일 오전 9시" = {(current_time + timedelta(days=1)).replace(hour=9, minute=0).isoformat()}
- "14일" = {current_time.replace(day=14, hour=0, minute=0).isoformat()}

답변 스타일:
- 친절하고 간결하게 답변
- 일정 관리 외 질문은 정중히 거절"""
        
        if request.context:
            system_prompt += f"\n\n추가 컨텍스트: {request.context}"
        
        # Gemini API 호출
        if conversation_history:
            chat = model.start_chat(history=conversation_history)
            response = chat.send_message(system_prompt + "\n\n" + request.message)
        else:
            response = model.generate_content(system_prompt + "\n\n사용자: " + request.message)
        
        # Function Call 처리
        function_called = None
        ai_response_text = ""
        
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
                                    {"role": "user", "parts": [system_prompt + "\n\n사용자: " + request.message]},
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
        
        return ChatResponse(
            success=True,
            ai_response=ai_response_text,
            session_id=session.id,
            message_id=ai_message.id,
            function_called=function_called
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"AI 처리 중 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI 처리 중 오류 발생: {str(e)}")

@router.get("/sessions/{user_uuid}")
async def get_user_sessions(user_uuid: str, db: Session = Depends(get_db)):
    """세션 목록 조회 (최대 15개)"""
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
    """메시지 목록 조회 (최대 50개)"""
    messages = db.query(models.Message).filter(
        models.Message.session_id == session_id
    ).order_by(models.Message.created_at.asc()).limit(MAX_MESSAGES_PER_SESSION).all()
    
    messages_data = []
    for message in messages:
        messages_data.append({
            "id": message.id,
            "content": message.content,
            "is_user": message.is_user,
            "created_at": message.created_at.isoformat()
        })
    
    return {"success": True, "messages": messages_data}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: Session = Depends(get_db)):
    """세션 삭제"""
    session = db.query(models.Session).filter(
        models.Session.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    
    db.delete(session)
    db.commit()
    
    return {"success": True, "message": "세션이 삭제되었습니다."}