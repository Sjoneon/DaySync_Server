from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import google.generativeai as genai
import os
from datetime import datetime
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

# Gemini 1.5 Flash 모델 초기화
model = genai.GenerativeModel('gemini-2.0-flash')

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

# ========================================
# AI 채팅 엔드포인트
# ========================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest, db: Session = Depends(get_db)):
    """
    사용자 메시지를 Gemini 1.5 Flash에 전달하고 응답을 반환합니다.
    
    - **user_uuid**: 사용자 UUID
    - **message**: 사용자 메시지
    - **session_id**: 기존 세션 ID (선택)
    - **context**: 추가 컨텍스트 정보 (선택)
    """
    try:
        # 1. 사용자 존재 확인
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
        
        # 시스템 프롬프트
        system_prompt = """당신은 DaySync 앱의 AI 비서입니다.
사용자의 일정 관리, 경로 안내, 교통 정보 제공을 도와줍니다.
친절하고 간결하게 답변하며, 필요시 일정 추가나 경로 검색을 제안합니다."""
        
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
        
        ai_response_text = response.text
        
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
            message_id=ai_message.id
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