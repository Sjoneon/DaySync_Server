#!/usr/bin/env python3
"""
DaySync API 서버 실행 스크립트

사용법:
    python run.py              # 개발 모드로 실행
    python run.py --prod       # 운영 모드로 실행
    python run.py --test       # 테스트 모드로 실행
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# 현재 스크립트의 디렉토리를 Python 경로에 추가
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

def setup_logging(level=logging.INFO):
    """로깅 설정"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('daysync_api.log', encoding='utf-8')
        ]
    )

def check_requirements():
    """필수 패키지 설치 확인"""
    required_packages = [
        'fastapi',
        'uvicorn',
        'sqlalchemy',
        'mysql-connector-python',
        'pydantic',
        'python-dotenv'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("다음 패키지들이 설치되지 않았습니다:")
        for package in missing_packages:
            print("   - {}".format(package))
        print("\n설치 명령어:")
        print("pip install {}".format(' '.join(missing_packages)))
        print("\n또는:")
        print("pip install -r requirements.txt")
        return False
    
    print("모든 필수 패키지가 설치되어 있습니다.")
    return True

def check_env_file():
    """환경설정 파일 확인"""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if not env_file.exists():
        if env_example.exists():
            print(".env 파일이 없습니다.")
            print(".env.example 파일을 .env로 복사하고 설정을 수정하세요:")
            print("cp .env.example .env")
            print("\n기본값으로 계속 진행합니다...")
        else:
            print("환경설정 파일(.env)이 없습니다. 기본값을 사용합니다.")
    else:
        print("환경설정 파일(.env)을 찾았습니다.")
    
    return True

def test_database_connection():
    """데이터베이스 연결 테스트"""
    try:
        print("데이터베이스 연결을 테스트하는 중...")
        
        # database 모듈 import 및 테스트
        from database import test_connection
        
        if test_connection():
            print("데이터베이스 연결 성공!")
            return True
        else:
            print("데이터베이스 연결 실패!")
            return False
            
    except Exception as e:
        print("데이터베이스 연결 테스트 중 오류 발생: {}".format(e))
        return False

def test_uuid_generation():
    """UUID 생성 테스트"""
    try:
        print("UUID 생성을 테스트하는 중...")
        
        from schemas import generate_uuid, validate_uuid_format
        
        # 여러 개 UUID 생성 및 검증
        uuids = []
        for i in range(5):
            uuid = generate_uuid()
            if not validate_uuid_format(uuid):
                raise ValueError("잘못된 UUID 형식: {}".format(uuid))
            uuids.append(uuid)
        
        # 중복 검사
        if len(set(uuids)) != len(uuids):
            raise ValueError("UUID 중복 발생")
        
        print("UUID 생성 및 검증 성공!")
        print("   생성된 예시 UUID: {}".format(uuids[0]))
        return True
        
    except Exception as e:
        print("UUID 생성 테스트 실패: {}".format(e))
        return False

def run_development_server():
    """개발 서버 실행"""
    import uvicorn
    
    print("DaySync API 개발 서버를 시작합니다...")
    print("API 문서: http://localhost:8000/docs")
    print("대체 문서: http://localhost:8000/redoc")
    print("헬스체크: http://localhost:8000/health")
    print("UUID 테스트: http://localhost:8000/test/uuid")
    print("\n종료하려면 Ctrl+C를 누르세요.\n")
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n서버가 종료되었습니다.")
    except Exception as e:
        print("서버 실행 중 오류 발생: {}".format(e))

def run_production_server():
    """운영 서버 실행"""
    import uvicorn
    
    print("DaySync API 운영 서버를 시작합니다...")
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="warning",
            access_log=False,
            workers=4
        )
    except KeyboardInterrupt:
        print("\n서버가 종료되었습니다.")
    except Exception as e:
        print("서버 실행 중 오류 발생: {}".format(e))

def run_tests():
    """시스템 테스트 실행"""
    print("DaySync API 시스템 테스트를 실행합니다...\n")
    
    all_tests_passed = True
    
    # 1. 패키지 확인
    print("1. 필수 패키지 확인")
    if not check_requirements():
        all_tests_passed = False
    print()
    
    # 2. 환경설정 확인
    print("2. 환경설정 확인")
    check_env_file()
    print()
    
    # 3. UUID 생성 테스트
    print("3. UUID 생성 테스트")
    if not test_uuid_generation():
        all_tests_passed = False
    print()
    
    # 4. 데이터베이스 연결 테스트
    print("4. 데이터베이스 연결 테스트")
    if not test_database_connection():
        all_tests_passed = False
    print()
    
    # 결과 출력
    if all_tests_passed:
        print("모든 테스트가 통과했습니다!")
        print("   개발 서버를 시작하려면: python run.py")
        return True
    else:
        print("일부 테스트가 실패했습니다. 위의 오류를 확인하세요.")
        return False

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="DaySync API 서버")
    parser.add_argument(
        '--mode', 
        choices=['dev', 'prod', 'test'],
        default='dev',
        help='실행 모드 (dev: 개발, prod: 운영, test: 테스트)'
    )
    parser.add_argument(
        '--test', 
        action='store_true',
        help='테스트 모드로 실행'
    )
    parser.add_argument(
        '--prod', 
        action='store_true',
        help='운영 모드로 실행'
    )
    
    args = parser.parse_args()
    
    # 플래그에 따른 모드 결정
    if args.test:
        mode = 'test'
    elif args.prod:
        mode = 'prod'
    else:
        mode = args.mode
    
    # 로깅 설정
    log_level = logging.DEBUG if mode == 'dev' else logging.INFO
    setup_logging(log_level)
    
    print("=" * 50)
    print("DaySync API Server")
    print("=" * 50)
    print("작업 디렉토리: {}".format(current_dir))
    print("실행 모드: {}".format(mode))
    print("=" * 50)
    print()
    
    # 모드별 실행
    if mode == 'test':
        success = run_tests()
        sys.exit(0 if success else 1)
    elif mode == 'prod':
        # 운영 모드에서는 기본 테스트만 실행
        if check_requirements() and test_uuid_generation():
            run_production_server()
        else:
            print("기본 테스트 실패. 서버를 시작할 수 없습니다.")
            sys.exit(1)
    else:  # dev 모드
        # 개발 모드에서는 기본 테스트 후 서버 시작
        if check_requirements() and test_uuid_generation():
            run_development_server()
        else:
            print("기본 테스트 실패. 문제를 해결하거나 --test 옵션으로 상세 진단을 실행하세요.")
            sys.exit(1)

if __name__ == "__main__":
    main()