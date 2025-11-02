# app/main.py

# uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload  <-- 이 명령어로 서버 실행
# 현재 로컬에서 테스트 중이므로 안드로이드 스튜디오 - ApiClient.java에 있는 로컬 ip를 테스트 환경에 맞게 수정해야 정상 작동합니다.
from fastapi import FastAPI, Depends, HTTPException, Request
from .database import engine, Base
from .routers import users, ai_chat, calendar_alarm, routes  # routes 추가
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import logging
import time
import os
import sys


# 로컬 모듈 임포트 (상대 경로로 수정)
from . import models
from . import schemas
from .database import get_db

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('daysync_api.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 애플리케이션 수명주기 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 실행할 작업들"""
    # 시작 시
    logger.info("DaySync API 서버가 시작됩니다")
    
    # 데이터베이스 테이블 생성
    try:
        logger.info("데이터베이스 테이블 확인 중...")
        models.Base.metadata.create_all(bind=engine)
        logger.info("데이터베이스 테이블 확인/생성 완료")
    except Exception as e:
        logger.error("데이터베이스 초기화 오류: {}".format(e))
        raise
    
    logger.info("서버 열림 _ http://localhost:8000/docs 에서 API 확인")
    
    yield
    
    # 종료 시
    logger.info("DaySync API 서버가 종료됩니다")

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="DaySync API",
    description="""
    DaySync 애플리케이션을 위한 통합 API 서비스입니다.
    
    ## 주요 기능
    
    * **사용자 관리**: UUID 기반 로그인 없는 사용자 시스템
    * **AI 대화**: Gemini 1.5 Flash 기반 AI 비서
    * **버스 정보**: 실시간 버스 정보 제공 (추후 구현_외부 API)
    * **일정 관리**: 개인 일정 및 알람 관리 (추후 구현_고민)
    
    ## 사용 방법
    
    1. **사용자 생성**: POST /api/users/ 로 새 사용자 생성
    2. **UUID 저장**: 반환받은 UUID를 앱에서 저장하여 사용
    3. **API 호출**: 이후 모든 API 호출 시 UUID 사용
    4. **AI 대화**: POST /api/ai/chat 로 AI와 대화
    
    ## 테스트 방법
    
    1. 아래 "Try it out" 버튼을 클릭하여 테스트
    2. POST /api/users/ 로 사용자 생성 테스트
    3. 생성된 UUID로 다른 API 테스트
    """,
    version="0.2.0",
    contact={
        "name": "DaySync 개발자자",
        "email": "spdjdps1649@gmail.com"
    },
    license_info={
        "name": "opensource_MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    lifespan=lifespan
)

# CORS 미들웨어 설정 (안드로이드 앱 연동용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 개발용
        "http://127.0.0.1:3000",  # 개발용
        "https://yourdomain.com", # 운영용 (실제 도메인으로 변경)
        "*"  # 개발 단계에서만 사용, 운영에서는 제거
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 요청 로깅 미들웨어
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """모든 HTTP 요청을 로깅합니다"""
    start_time = time.time()
    
    # 요청 정보 로깅
    logger.info("요청 시작: {} {}".format(request.method, request.url))
    
    # 요청 처리
    response = await call_next(request)
    
    # 응답 시간 계산
    process_time = time.time() - start_time
    
    # 응답 정보 로깅
    logger.info(
        "요청 완료: {} {} - 상태: {} - 시간: {:.3f}초".format(
            request.method, request.url, response.status_code, process_time
        )
    )
    
    return response

# 전역 예외 처리기
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """전역 예외 처리"""
    logger.error("처리되지 않은 예외 발생: {}".format(str(exc)), exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "내부 서버 오류가 발생했습니다",
            "detail": "서버 로그를 확인해주세요"
        }
    )

# 라우터 등록
try:
    app.include_router(users.router)
    logger.info("사용자 라우터 등록 완료")
    
    app.include_router(ai_chat.router)
    logger.info("AI 채팅 라우터 등록 완료")
    
    app.include_router(calendar_alarm.router)
    logger.info("일정/알람 라우터 등록 완료")
    
    app.include_router(routes.router)
    logger.info("경로 라우터 등록 완료")
    
except Exception as e:
    logger.error("라우터 등록 실패: {}".format(e))

# === 기본 엔드포인트 ===

@app.get("/", 
         response_model=schemas.SuccessResponse,
         tags=["Root"],
         summary="API 상태 확인",
         description="API가 정상적으로 실행 중인지 확인합니다.")
async def read_root():
    """
    API의 루트 엔드포인트입니다. 
    API가 정상적으로 실행 중인지 확인할 수 있습니다.
    """
    return schemas.SuccessResponse(
        message="DaySync API에 오신 것을 환영합니다! 서버가 정상적으로 실행 중입니다.",
        data={
            "version": "0.2.0",
            "status": "running",
            "features": ["사용자 관리", "AI 대화", "버스 정보 (예정)", "일정 관리 (예정)"],
            "endpoints": {
                "docs": "/docs",
                "users": "/api/users",
                "ai": "/api/ai",
                "health": "/health"
            }
        }
    )

@app.get("/health", 
         response_model=schemas.HealthCheckResponse,
         tags=["DB_Server"],
         summary="DB_Server_연결확인",
         description="서버와 데이터베이스 연결 상태를 확인합니다.")
async def health_check(db: Session = Depends(get_db)):
    """
    서버와 데이터베이스 연결 상태를 확인합니다.
    모니터링 시스템에서 사용할 수 있습니다.
    """
    try:
        # 간단한 DB 쿼리로 연결 상태 확인
        db.execute("SELECT 1")
        db_status = "connected"
        
        # UUID 생성 테스트
        test_uuid = schemas.generate_uuid()
        uuid_status = "working"
        
    except Exception as e:
        logger.error(f"연결상태 확인 실패: {e}")
        db_status = "disconnected"
        uuid_status = "failed"
        raise HTTPException(
            status_code=503,
            detail="시스템 상태 확인에 실패했습니다"
        )
    
    return schemas.HealthCheckResponse(
        status="healthy",
        timestamp=time.time(),
        database=db_status,
        version="0.2.0"
    )

@app.get("/api/info",
         tags=["Information"],
         summary="API 정보",
         description="API의 상세 정보를 반환합니다.")
async def api_info():
    """
    API 버전, 지원 기능 등의 정보를 반환합니다.
    클라이언트에서 API 호환성 확인에 사용할 수 있습니다.
    """
    return {
        "api_name": "DaySync API",
        "version": "0.2.0",
        "description": "버스 기반 일정-이동 최적화 비서",
        "supported_features": {
            "user_management": True,
            "uuid_generation": True,
            "ai_chat": True,          # AI 채팅 추가
            "chat_sessions": True,    # 세션 관리 추가
            "bus_info": False,        # 추후 구현
            "calendar": False,        # 추후 구현
            "alarms": False,          # 추후 구현
            "weather": False          # 추후 구현
        },
        "endpoints": {
            "users": "/api/users",
            "ai": "/api/ai",          # AI 엔드포인트 추가
            "sessions": "/api/sessions",  # 추후 구현
            "messages": "/api/messages",  # 추후 구현
            "bus": "/api/bus",           # 추후 구현
            "weather": "/api/weather"    # 추후 구현
        },
        "testing": {
            "interactive_docs": "/docs",
            "alternative_docs": "/redoc",
            "quick_test": {
                "step1": "POST /api/users/ (새 사용자 생성)",
                "step2": "GET /api/users/{uuid} (사용자 정보 조회)",
                "step3": "POST /api/ai/chat (AI와 대화)",
                "step4": "PUT /api/users/{uuid} (사용자 정보 수정)"
            }
        },
        "contact": {
            "email": "dev@daysync.app",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }

# UUID 생성 테스트 엔드포인트
@app.get("/test/uuid",
         tags=["Test"],
         summary="UUID 생성 테스트",
         description="UUID 생성 기능을 테스트합니다.")
async def test_uuid_generation():
    """
    UUID 생성 기능을 테스트합니다.
    """
    try:
        # 여러 개의 UUID 생성해서 중복 확인
        uuids = []
        for i in range(5):
            new_uuid = schemas.generate_uuid()
            uuids.append(new_uuid)
            
            # UUID 형식 검증
            if not schemas.validate_uuid_format(new_uuid):
                raise ValueError(f"잘못된 UUID 형식: {new_uuid}")
        
        # 중복 확인
        if len(set(uuids)) != len(uuids):
            raise ValueError("UUID 중복 발생")
        
        return {
            "success": True,
            "message": "UUID 생성 테스트 성공",
            "generated_uuids": uuids,
            "validation": "모든 UUID가 올바른 형식이며 중복이 없습니다"
        }
        
    except Exception as e:
        logger.error(f"UUID 생성 테스트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"UUID 생성 테스트 실패: {str(e)}"
        )

# 개발용 디버그 엔드포인트 (운영에서는 제거)
@app.get("/debug/db-test", 
         tags=["Debug"],
         summary="DB 연결 테스트",
         description="데이터베이스 연결과 테이블 상태를 확인합니다.",
         include_in_schema=False)  # API 문서에서 숨김
async def debug_db_test(db: Session = Depends(get_db)):
    """
    데이터베이스 연결 상태와 테이블 정보를 상세히 테스트합니다.
    개발 환경에서만 사용하세요.
    """
    try:
        # 테이블 존재 확인
        tables_info = {}
        
        # users 테이블 확인
        try:
            user_count = db.query(models.User).count()
            tables_info["users"] = {
                "exists": True,
                "count": user_count
            }
        except Exception as e:
            tables_info["users"] = {
                "exists": False,
                "error": str(e)
            }
        
        # sessions 테이블 확인  
        try:
            session_count = db.query(models.Session).count()
            tables_info["sessions"] = {
                "exists": True,
                "count": session_count
            }
        except Exception as e:
            tables_info["sessions"] = {
                "exists": False,
                "error": str(e)
            }
        
        # messages 테이블 확인
        try:
            message_count = db.query(models.Message).count()
            tables_info["messages"] = {
                "exists": True,
                "count": message_count
            }
        except Exception as e:
            tables_info["messages"] = {
                "exists": False,
                "error": str(e)
            }
        
        # UUID 생성 테스트
        test_uuid = schemas.generate_uuid()
        
        return {
            "status": "성공",
            "message": "데이터베이스 연결이 정상입니다",
            "tables": tables_info,
            "uuid_test": {
                "generated": test_uuid,
                "valid_format": schemas.validate_uuid_format(test_uuid)
            },
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"DB 테스트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"데이터베이스 테스트 실패: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    
    print("DaySync API 서버를 시작합니다...")
    print("API 문서: http://localhost:8000/docs")
    print("대체 문서: http://localhost:8000/redoc")
    print("헬스체크: http://localhost:8000/health")
    
    # 개발 서버 실행
    uvicorn.run(
        "main:app",  # app.main:app에서 main:app으로 변경
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )