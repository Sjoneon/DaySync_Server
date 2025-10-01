from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
import logging
from dotenv import load_dotenv
from pathlib import Path

# .env 파일 경로 명시적으로 지정
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# 로깅 설정
logger = logging.getLogger(__name__)

# 환경변수에서 데이터베이스 설정 가져오기
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "0000")  # 이제 .env에서 "1234"를 읽음
DB_NAME = os.getenv("DB_NAME", "daysync_db")

# 데이터베이스 URL 생성
SQLALCHEMY_DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 개발환경에서는 DB URL 로깅 (비밀번호는 마스킹)
masked_url = SQLALCHEMY_DATABASE_URL.replace(DB_PASSWORD, "*" * len(DB_PASSWORD))
logger.info(f"데이터베이스 연결 URL: {masked_url}")

try:
    # SQLAlchemy 엔진 생성
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        # 연결 풀 설정
        poolclass=QueuePool,
        pool_size=10,                    # 기본 연결 풀 크기
        max_overflow=20,                 # 풀이 가득 찼을 때 추가로 생성할 수 있는 연결 수
        pool_pre_ping=True,              # 연결 유효성 사전 확인
        pool_recycle=3600,               # 1시간마다 연결 재생성
        # MySQL 특화 설정
        connect_args={
            "charset": "utf8mb4",        # 이모지 등 특수문자 지원
            "collation": "utf8mb4_unicode_ci",
            "autocommit": False,         # 자동 커밋 비활성화
        },
        # 로깅 설정 (개발환경에서만)
        echo=os.getenv("API_DEBUG", "False").lower() == "true",
    )
    
    logger.info("데이터베이스 엔진 생성 완료")
    
except Exception as e:
    logger.error("데이터베이스 엔진 생성 실패: {}".format(e))
    raise e

# 세션 팩토리 생성
SessionLocal = sessionmaker(
    autocommit=False,      # 자동 커밋 비활성화
    autoflush=False,       # 자동 플러시 비활성화
    bind=engine,
    expire_on_commit=False # 커밋 후 객체 만료 방지
)

# SQLAlchemy Base 클래스
Base = declarative_base()

def get_db():
    """
    데이터베이스 세션 의존성 주입 함수
    FastAPI의 Depends와 함께 사용됩니다.
    
    Yields:
        Session: 데이터베이스 세션
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"데이터베이스 세션 오류: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def test_connection():
    """
    데이터베이스 연결 테스트 함수
    
    Returns:
        bool: 연결 성공 여부
    """
    try:
        # 테스트 연결 생성
        connection = engine.connect()
        
        # 간단한 쿼리 실행
        result = connection.execute("SELECT 1 as test")
        test_value = result.fetchone()[0]
        
        connection.close()
        
        if test_value == 1:
            logger.info("데이터베이스 연결 테스트 성공")
            return True
        else:
            logger.error("데이터베이스 연결 테스트 실패: 잘못된 결과")
            return False
            
    except Exception as e:
        logger.error("데이터베이스 연결 테스트 실패: {}".format(e))
        return False

def create_database_if_not_exists():
    """
    데이터베이스가 존재하지 않으면 생성합니다.
    """
    try:
        # 데이터베이스 없이 연결 (mysql 기본 DB 사용)
        base_url = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/mysql"
        base_engine = create_engine(base_url)
        
        # 데이터베이스 존재 확인
        with base_engine.connect() as connection:
            result = connection.execute(f"SHOW DATABASES LIKE '{DB_NAME}'")
            if not result.fetchone():
                # 데이터베이스 생성
                connection.execute(f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                logger.info("데이터베이스 '{}' 생성 완료".format(DB_NAME))
            else:
                logger.info("데이터베이스 '{}' 이미 존재함".format(DB_NAME))
        
        base_engine.dispose()
        
    except Exception as e:
        logger.error("데이터베이스 생성 실패: {}".format(e))
        raise

def init_database():
    """
    데이터베이스 초기화 함수
    애플리케이션 시작 시 호출됩니다.
    """
    try:
        logger.info("데이터베이스 초기화 시작...")
        
        # 1. 데이터베이스 생성 (필요시)
        create_database_if_not_exists()
        
        # 2. 연결 테스트
        if not test_connection():
            raise Exception("데이터베이스 연결 테스트 실패")
        
        # 3. 테이블 생성 (models.py에서 정의된 테이블들)
        from . import models
        models.Base.metadata.create_all(bind=engine)
        logger.info("데이터베이스 테이블 생성/확인 완료")
        
        logger.info("데이터베이스 초기화 완료")
        
    except Exception as e:
        logger.error("데이터베이스 초기화 실패: {}".format(e))
        raise

# 개발환경에서 즉시 연결 테스트
if __name__ == "__main__":
    print("데이터베이스 연결 테스트 실행...")
    
    # 환경변수 출력 (비밀번호 제외)
    print(f"DB_HOST: {DB_HOST}")
    print(f"DB_PORT: {DB_PORT}")
    print(f"DB_USER: {DB_USER}")
    print(f"DB_NAME: {DB_NAME}")
    
    # 연결 테스트
    if test_connection():
        print("데이터베이스 연결 성공!")
    else:
        print("데이터베이스 연결 실패!")
        
    # 데이터베이스 초기화 테스트
    try:
        init_database()
        print("데이터베이스 초기화 성공!")
    except Exception as e:
        print("데이터베이스 초기화 실패: {}".format(e))