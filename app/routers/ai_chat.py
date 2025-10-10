from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import google.generativeai as genai
import os
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

# .env 파일 명시적으로 로드 (추가)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from ..database import get_db
from .. import models

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])

# Gemini API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

genai.configure(api_key=GEMINI_API_KEY)

create_schedule_function = genai.protos.FunctionDeclaration(
    name="create_schedule",
    description="사용자의 일정을 생성합니다. 날짜, 시간, 제목을 파악하여 일정을 추가합니다.",
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
    description="""사용자의 알람을 설정합니다. 
    시간과 레이블을 파악하여 알람을 추가합니다.
    
    상대적 시간 표현 처리 규칙:
    - "3시간 뒤" → 현재 시간 + 3시간을 계산하여 ISO 8601 형식으로 변환
    - "30분 뒤" → 현재 시간 + 30분을 계산
    - "내일 오전 9시" → 다음날 09:00:00으로 계산
    - "오늘 저녁 7시" → 오늘 19:00:00으로 계산
    
    반드시 계산된 ISO 8601 형식으로 time 파라미터를 전달해야 합니다.""",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "time": genai.protos.Schema(
                type=genai.protos.Type.STRING, 
                description="""알람 시간 (ISO 8601 형식: YYYY-MM-DDTHH:MM:SS)
                사용자가 상대적 시간("3시간 뒤", "30분 뒤")으로 말하면 
                현재 시간을 기준으로 계산하여 ISO 8601 형식으로 변환하세요."""
            ),
            "label": genai.protos.Schema(
                type=genai.protos.Type.STRING, 
                description="알람 레이블"
            ),
            "repeat_days": genai.protos.Schema(
                type=genai.protos.Type.STRING, 
                description="반복 요일 (선택, 예: '월,화,수,목,금')"
            )
        },
        required=["time", "label"]
    )
)

schedule_tool = genai.protos.Tool(
    function_declarations=[create_schedule_function, create_alarm_function]
)
# =============================================

# Gemini 2.0 Flash 모델 초기화 (tools 파라미터 추가)
model = genai.GenerativeModel('gemini-2.0-flash', tools=[schedule_tool])

# ===== [새로 추가] Function 실행 헬퍼 함수 =====
def execute_function_call(function_name: str, args: dict, user_uuid: str, db: Session):
    """Gemini가 요청한 함수를 실행합니다."""
    
    if function_name == "create_schedule":
        # 가이드라인 준수: null 체크
        if not args.get("title") or not args.get("start_time"):
            return {"status": "error", "message": "제목과 시작 시간이 필요합니다."}
        
        # 일정 생성
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
        
        return {
            "status": "success",
            "message": f"'{args.get('title')}' 일정이 추가되었습니다.",
            "event_id": new_event.id
        }
    
    elif function_name == "create_alarm":
        # 가이드라인 준수: null 체크
        if not args.get("time") or not args.get("label"):
            return {"status": "error", "message": "시간과 레이블이 필요합니다."}
        
        # 알람 생성
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
        
        return {
            "status": "success",
            "message": f"'{args.get('label')}' 알람이 설정되었습니다.",
            "alarm_id": new_alarm.id
        }
    
    else:
        return {"status": "error", "message": "알 수 없는 함수입니다."}
# =============================================

# ========================================
# Pydantic 스키마
# ========================================

class ChatRequest(BaseModel):
    user_uuid: str
    message: str
    session_id: Optional[int] = None  # 기존 세션 ID (없으면 새로 생성)
    context: Optional[dict] = None  # 추가 컨텍스트 (위치, 일정 등)

class ChatResponse(BaseModel):
    success: bool
    ai_response: str
    session_id: int
    message_id: int
    function_called: Optional[str] = None  # [새로 추가] 호출된 함수명

# ========================================
# AI 채팅 엔드포인트
# ========================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest, db: Session = Depends(get_db)):
    """
    사용자 메시지를 Gemini 2.0 Flash에 전달하고 응답을 반환합니다.
    
    - **user_uuid**: 사용자 UUID
    - **message**: 사용자 메시지
    - **session_id**: 기존 세션 ID (선택)
    - **context**: 추가 컨텍스트 정보 (선택)
    """
    try:
        # 1. 사용자 존재 확인 (가이드라인 준수: null 체크)
        user = db.query(models.User).filter(
            models.User.uuid == request.user_uuid,
            models.User.is_deleted == False
        ).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
        # 2. 세션 처리
        if request.session_id:
            # 기존 세션 조회
            session = db.query(models.Session).filter(
                models.Session.id == request.session_id,
                models.Session.user_uuid == request.user_uuid
            ).first()
            
            if not session:
                raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
        else:
            # 새 세션 생성
            session = models.Session(
                user_uuid=request.user_uuid,
                title="새 대화",
                category="general"
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        
        # 3. 대화 히스토리 조회 (최근 10개 메시지)
        recent_messages = db.query(models.Message).filter(
            models.Message.session_id == session.id
        ).order_by(models.Message.created_at.desc()).limit(10).all()
        
        # 4. 프롬프트 구성
        conversation_history = []
        for msg in reversed(recent_messages):  # 시간 순으로 정렬
            role = "user" if msg.is_user else "model"
            conversation_history.append({
                "role": role,
                "parts": [msg.content]
            })
        
        # ============================================
        # 시스템 프롬프트 (기존 유지 + 날짜 정보만 추가)
        # ============================================
        current_time = datetime.now()
        system_prompt = f"""당신은 DaySync 앱의 전용 AI 비서입니다.

**현재 시간: {current_time.strftime('%Y년 %m월 %d일 %H시 %M분')} (ISO: {current_time.isoformat()})**

**상대적 시간 해석:**
- "내일" = {(current_time + timedelta(days=1)).strftime('%Y-%m-%d')}
- "모레" = {(current_time + timedelta(days=2)).strftime('%Y-%m-%d')}
- "다음 주" = {(current_time + timedelta(weeks=1)).strftime('%Y-%m-%d')}

**⚠️ 시간 계산 규칙 (매우 중요!):**
사용자가 상대적 시간을 말하면 당신이 직접 계산해서 ISO 8601 형식(YYYY-MM-DDTHH:MM:SS)으로 변환하세요.

상대적 시간 변환 예시:
- "3시간 뒤" → {(current_time + timedelta(hours=3)).isoformat()}
- "30분 뒤" → {(current_time + timedelta(minutes=30)).isoformat()}
- "1시간 반 뒤" → {(current_time + timedelta(hours=1, minutes=30)).isoformat()}
- "2시간 30분 뒤" → {(current_time + timedelta(hours=2, minutes=30)).isoformat()}
- "1일 뒤" → {(current_time + timedelta(days=1)).isoformat()}

절대 시간 변환 예시:
- "오후 3시" → {current_time.replace(hour=15, minute=0, second=0).isoformat()}
- "저녁 7시" → {current_time.replace(hour=19, minute=0, second=0).isoformat()}
- "오전 9시 30분" → {current_time.replace(hour=9, minute=30, second=0).isoformat()}
- "내일 오전 9시" → {(current_time + timedelta(days=1)).replace(hour=9, minute=0, second=0).isoformat()}
- "모레 오후 2시" → {(current_time + timedelta(days=2)).replace(hour=14, minute=0, second=0).isoformat()}

❗**절대 사용자에게 ISO 8601 형식으로 알려달라고 요청하지 마세요. 당신이 직접 변환하세요!**

**역할 및 제공 가능한 기능:**
1. 일정 관리 (일정 추가, 수정, 삭제, 조회, 알림 설정)
2. 경로 안내 및 최적 경로 추천
3. 교통 정보 제공 (버스, 지하철, 실시간 교통 상황)
4. 시간 관리 및 준비 시간 계산
5. 위치 기반 서비스 (주변 정보(음식점, 편의점), 도착 시간 예측)

**응답 규칙:**
- 위의 5가지 기능과 직접 관련된 질문에만 답변합니다.
- 일반 지식, 역사, 인물 정보, 뉴스, 학습, 코딩, 번역, 정치 등 앱 기능과 무관한 질문은 정중하게 거절합니다.
- 거절 시 반드시 다음 형식으로 답변합니다:
"죄송합니다. 해당 내용은 DaySync 앱에서 제공하지 않는 정보입니다.

저는 다음과 같은 도움을 드릴 수 있습니다:
- 일정 관리 및 알림 설정
- 경로 안내 및 교통 정보
- 시간 관리 및 준비 시간 계산

어떤 일정이나 경로 관련 도움이 필요하신가요?"

**허용되는 질문 예시:**
- "내일 오전 10시 회의 일정 추가해줘"
- "서원대까지 가는 방법 알려줘"
- "다음 일정이 뭐야?"
- "오늘 집에서 몇 시에 나가야 해?"
- "지금 버스 언제 와?"
- "오늘 오전 9시 30분 알림"
- "3시간 뒤 알람 추가해줘"
- "30분 뒤에 출발 알림"

**거절해야 하는 질문 예시:**
- 특정 인물에 대한 정보 요청 (예: "소예찬이라는 인물에 대해 알려줘")
- 일반 상식 질문 (예: "지구의 나이는?")
- 학습 도움 (예: "수학 문제 풀어줘")
- 코딩 요청 (예: "파이썬 코드 짜줘")
- 창작 요청 (예: "시 써줘", "이야기 만들어줘")
- 번역 요청 (예: "이거 영어로 번역해줘")
- 정치 요청 (예: "너 더불어 민주당, 국민의 힘 좋아해?)

**답변 스타일:**
- 친절하고 간결하게 답변합니다.
- 필요시 일정 추가, 경로 검색, 알림 설정 등을 적극 제안합니다.
- 사용자의 맥락을 고려하여 실용적인 조언을 제공합니다.

**일정/알람 추가 규칙 (중요):**
- 사용자가 일정/알람 추가를 요청하면 즉시 함수를 호출하여 실행합니다.
- 제목, 시간 등 필수 정보가 부족한 경우에만 한 번 질문합니다.
- 정보를 받은 후에는 재확인 없이 바로 추가하고 "추가되었습니다"라고 알립니다.
- "추가하시겠습니까?", "추가해드릴까요?" 같은 재확인 질문을 하지 않습니다.
- 함수 실행 후에는 완료 메시지만 전달하고 추가 질문을 하지 않습니다."""
        
        if request.context:
            system_prompt += f"\n\n추가 컨텍스트: {request.context}"
        
        # 5. Gemini API 호출
        if conversation_history:
            # 대화 히스토리가 있으면 채팅 컨티뉴
            chat = model.start_chat(history=conversation_history)
            response = chat.send_message(system_prompt + "\n\n" + request.message)
        else:
            # 새로운 대화 시작
            response = model.generate_content(system_prompt + "\n\n사용자: " + request.message)
        
        # ===== [새로 추가] Function Call 처리 =====
        function_called = None
        ai_response_text = ""
        
        # 가이드라인 준수: null 체크
        if response and response.candidates and len(response.candidates) > 0:
            if response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        func_call = part.function_call
                        function_called = func_call.name
                        
                        # 함수 실행
                        func_args = dict(func_call.args)
                        result = execute_function_call(func_call.name, func_args, request.user_uuid, db)
                        
                        # 함수 실행 결과를 Gemini에게 전달
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
                            # 새 채팅인 경우
                            history = [
                                {"role": "user", "parts": [system_prompt + "\n\n사용자: " + request.message]},
                                {"role": "model", "parts": [part]}
                            ]
                            chat = model.start_chat(history=history)
                            final_response = chat.send_message(function_response)
                        
                        ai_response_text = final_response.text if final_response else ""
                    elif hasattr(part, 'text'):
                        ai_response_text = part.text
        
        # 응답이 없으면 기본 메시지
        if not ai_response_text:
            ai_response_text = response.text if response else "응답을 생성할 수 없습니다."
        # =============================================
        
        # 6. 사용자 메시지 저장
        user_message = models.Message(
            session_id=session.id,
            content=request.message,
            is_user=True
        )
        db.add(user_message)
        
        # 7. AI 응답 저장
        ai_message = models.Message(
            session_id=session.id,
            content=ai_response_text,
            is_user=False
        )
        db.add(ai_message)
        
        # 8. 세션 업데이트 시간 갱신
        session.updated_at = datetime.now()
        
        db.commit()
        db.refresh(ai_message)
        
        return ChatResponse(
            success=True,
            ai_response=ai_response_text,
            session_id=session.id,
            message_id=ai_message.id,
            function_called=function_called  # [새로 추가]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"AI 처리 중 오류 발생: {str(e)}")


@router.get("/sessions/{user_uuid}")
async def get_user_sessions(user_uuid: str, db: Session = Depends(get_db)):
    """사용자의 모든 대화 세션 목록을 반환합니다."""
    sessions = db.query(models.Session).filter(
        models.Session.user_uuid == user_uuid
    ).order_by(models.Session.updated_at.desc()).all()
    
    return {"success": True, "sessions": sessions}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: int, db: Session = Depends(get_db)):
    """특정 세션의 모든 메시지를 반환합니다."""
    messages = db.query(models.Message).filter(
        models.Message.session_id == session_id
    ).order_by(models.Message.created_at.asc()).all()
    
    return {"success": True, "messages": messages}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: Session = Depends(get_db)):
    """세션을 삭제합니다."""
    session = db.query(models.Session).filter(
        models.Session.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    
    db.delete(session)
    db.commit()
    
    return {"success": True, "message": "세션이 삭제되었습니다."}