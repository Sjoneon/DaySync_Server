from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from . import models, schemas

# 로깅 설정
logger = logging.getLogger(__name__)

class UserCRUD:
    """사용자 관련 CRUD 연산 클래스"""
    
    @staticmethod
    def create_user(db: Session, user_data: schemas.UserCreate) -> models.User:
        """
        새로운 사용자 생성
        Args:
            db: 데이터베이스 세션
            user_data: 사용자 생성 데이터
        Returns:
            생성된 사용자 모델
        """
        try:
            # UUID 생성 (중복 체크)
            new_uuid = schemas.generate_uuid()
            while UserCRUD.get_user_by_uuid(db, new_uuid):
                new_uuid = schemas.generate_uuid()
            
            # 사용자 생성
            db_user = models.User(
                uuid=new_uuid,
                nickname=user_data.nickname or "사용자",
                prep_time=user_data.prep_time or 1800,
                created_at=datetime.now(),
                last_active=datetime.now()
            )
            
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            
            logger.info(f"새 사용자 생성됨: UUID={new_uuid}, 닉네임={db_user.nickname}")
            return db_user
            
        except Exception as e:
            db.rollback()
            logger.error(f"사용자 생성 실패: {str(e)}")
            raise
    
    @staticmethod
    def get_user_by_uuid(db: Session, uuid: str) -> Optional[models.User]:
        """
        UUID로 사용자 조회
        Args:
            db: 데이터베이스 세션
            uuid: 사용자 UUID
        Returns:
            사용자 모델 또는 None
        """
        try:
            return db.query(models.User).filter(
                and_(
                    models.User.uuid == uuid,
                    models.User.is_deleted == False
                )
            ).first()
        except Exception as e:
            logger.error(f"사용자 조회 실패: UUID={uuid}, 오류={str(e)}")
            return None
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
        """
        ID로 사용자 조회
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
        Returns:
            사용자 모델 또는 None
        """
        try:
            return db.query(models.User).filter(
                and_(
                    models.User.id == user_id,
                    models.User.is_deleted == False
                )
            ).first()
        except Exception as e:
            logger.error(f"사용자 조회 실패: ID={user_id}, 오류={str(e)}")
            return None
    
    @staticmethod
    def update_user(db: Session, uuid: str, user_update: schemas.UserUpdate) -> Optional[models.User]:
        """
        사용자 정보 수정
        Args:
            db: 데이터베이스 세션
            uuid: 사용자 UUID
            user_update: 수정할 데이터
        Returns:
            수정된 사용자 모델 또는 None
        """
        try:
            db_user = UserCRUD.get_user_by_uuid(db, uuid)
            if not db_user:
                return None
            
            # 수정 가능한 필드만 업데이트
            update_data = user_update.dict(exclude_unset=True)
            
            for field, value in update_data.items():
                if hasattr(db_user, field):
                    setattr(db_user, field, value)
            
            # 마지막 활동 시간 갱신
            db_user.last_active = datetime.now()
            
            db.commit()
            db.refresh(db_user)
            
            logger.info(f"사용자 정보 수정됨: UUID={uuid}, 수정필드={list(update_data.keys())}")
            return db_user
            
        except Exception as e:
            db.rollback()
            logger.error(f"사용자 수정 실패: UUID={uuid}, 오류={str(e)}")
            raise
    
    @staticmethod
    def update_last_active(db: Session, uuid: str) -> bool:
        """
        사용자 마지막 활동 시간 갱신
        Args:
            db: 데이터베이스 세션
            uuid: 사용자 UUID
        Returns:
            성공 여부
        """
        try:
            db_user = UserCRUD.get_user_by_uuid(db, uuid)
            if not db_user:
                return False
            
            db_user.last_active = datetime.now()
            db.commit()
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"마지막 활동 시간 갱신 실패: UUID={uuid}, 오류={str(e)}")
            return False
    
    @staticmethod
    def soft_delete_user(db: Session, uuid: str) -> bool:
        """
        사용자 논리적 삭제 (soft delete)
        Args:
            db: 데이터베이스 세션
            uuid: 사용자 UUID
        Returns:
            성공 여부
        """
        try:
            db_user = UserCRUD.get_user_by_uuid(db, uuid)
            if not db_user:
                return False
            
            db_user.is_deleted = True
            db.commit()
            
            logger.info(f"사용자 논리적 삭제됨: UUID={uuid}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"사용자 삭제 실패: UUID={uuid}, 오류={str(e)}")
            return False
    
    @staticmethod
    def get_user_stats(db: Session, uuid: str) -> Optional[dict]:
        """
        사용자 통계 정보 조회
        Args:
            db: 데이터베이스 세션
            uuid: 사용자 UUID
        Returns:
            통계 정보 딕셔너리 또는 None
        """
        try:
            user = UserCRUD.get_user_by_uuid(db, uuid)
            if not user:
                return None
            
            # 세션 수 계산
            total_sessions = db.query(func.count(models.Session.id)).filter(
                models.Session.user_uuid == uuid
            ).scalar() or 0
            
            # 메시지 수 계산
            total_messages = db.query(func.count(models.Message.id)).join(
                models.Session
            ).filter(
                models.Session.user_uuid == uuid
            ).scalar() or 0
            
            return {
                "uuid": user.uuid,
                "nickname": user.nickname,
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "last_active": user.last_active,
                "created_at": user.created_at
            }
            
        except Exception as e:
            logger.error(f"사용자 통계 조회 실패: UUID={uuid}, 오류={str(e)}")
            return None
    
    @staticmethod
    def cleanup_inactive_users(db: Session, days: int = 30) -> int:
        """
        비활성 사용자 정리 (30일 이상 미접속)
        Args:
            db: 데이터베이스 세션
            days: 비활성 기준 일수
        Returns:
            정리된 사용자 수
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 비활성 사용자 조회
            inactive_users = db.query(models.User).filter(
                and_(
                    models.User.last_active < cutoff_date,
                    models.User.is_deleted == False
                )
            ).all()
            
            # 논리적 삭제 처리
            count = 0
            for user in inactive_users:
                user.is_deleted = True
                count += 1
            
            db.commit()
            
            logger.info(f"비활성 사용자 {count}명 정리됨 (기준: {days}일)")
            return count
            
        except Exception as e:
            db.rollback()
            logger.error(f"비활성 사용자 정리 실패: 오류={str(e)}")
            return 0