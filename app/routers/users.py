from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging

from ..database import get_db
from ..crud import UserCRUD
from .. import schemas

# 로깅 설정
logger = logging.getLogger(__name__)

# APIRouter 인스턴스 생성
router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    responses={404: {"description": "사용자를 찾을 수 없습니다"}}
)

@router.post("/", 
             response_model=schemas.UserCreateResponse,
             status_code=status.HTTP_201_CREATED,
             summary="새 사용자 생성",
             description="UUID 기반의 새로운 사용자를 생성합니다. 로그인이 필요하지 않습니다.")
async def create_user(
    user_data: schemas.UserCreate = schemas.UserCreate(),
    db: Session = Depends(get_db)
):
    """
    새로운 사용자를 생성합니다.
    
    Args:
        user_data: 사용자 생성 데이터 (닉네임, 준비시간 등)
        db: 데이터베이스 세션
    
    Returns:
        생성된 사용자의 UUID와 기본 정보
    
    Raises:
        HTTPException: 사용자 생성 실패 시
    """
    try:
        # 사용자 생성
        new_user = UserCRUD.create_user(db, user_data)
        
        logger.info(f"새 사용자 생성 성공: UUID={new_user.uuid}")
        
        return schemas.UserCreateResponse(
            uuid=new_user.uuid,
            nickname=new_user.nickname,
            prep_time=new_user.prep_time,
            message="사용자가 성공적으로 생성되었습니다. 이 UUID를 저장해두세요!"
        )
        
    except Exception as e:
        logger.error(f"사용자 생성 실패: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사용자 생성 중 오류가 발생했습니다"
        )

@router.get("/{user_uuid}",
            response_model=schemas.UserResponse,
            summary="사용자 정보 조회",
            description="UUID로 사용자 정보를 조회합니다.")
async def get_user(
    user_uuid: str,
    db: Session = Depends(get_db)
):
    """
    UUID로 사용자 정보를 조회합니다.
    
    Args:
        user_uuid: 조회할 사용자의 UUID
        db: 데이터베이스 세션
    
    Returns:
        사용자 정보
    
    Raises:
        HTTPException: 사용자를 찾을 수 없거나 UUID 형식이 잘못된 경우
    """
    # UUID 형식 검증
    if not schemas.validate_uuid_format(user_uuid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="올바르지 않은 UUID 형식입니다"
        )
    
    # 사용자 조회
    user = UserCRUD.get_user_by_uuid(db, user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다"
        )
    
    # 마지막 활동 시간 업데이트
    UserCRUD.update_last_active(db, user_uuid)
    
    return user

@router.put("/{user_uuid}",
            response_model=schemas.UserResponse,
            summary="사용자 정보 수정",
            description="사용자의 닉네임, 준비시간 등을 수정합니다.")
async def update_user(
    user_uuid: str,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db)
):
    """
    사용자 정보를 수정합니다.
    
    Args:
        user_uuid: 수정할 사용자의 UUID
        user_update: 수정할 데이터
        db: 데이터베이스 세션
    
    Returns:
        수정된 사용자 정보
    
    Raises:
        HTTPException: 사용자를 찾을 수 없거나 수정 실패 시
    """
    # UUID 형식 검증
    if not schemas.validate_uuid_format(user_uuid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="올바르지 않은 UUID 형식입니다"
        )
    
    try:
        # 사용자 정보 수정
        updated_user = UserCRUD.update_user(db, user_uuid, user_update)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )
        
        logger.info(f"사용자 정보 수정 완료: UUID={user_uuid}")
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사용자 정보 수정 실패: UUID={user_uuid}, 오류={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사용자 정보 수정 중 오류가 발생했습니다"
        )

@router.delete("/{user_uuid}",
               status_code=status.HTTP_204_NO_CONTENT,
               summary="사용자 삭제",
               description="사용자를 논리적으로 삭제합니다.")
async def delete_user(
    user_uuid: str,
    db: Session = Depends(get_db)
):
    """
    사용자를 논리적으로 삭제합니다 (실제 데이터는 보존).
    
    Args:
        user_uuid: 삭제할 사용자의 UUID
        db: 데이터베이스 세션
    
    Raises:
        HTTPException: 사용자를 찾을 수 없거나 삭제 실패 시
    """
    # UUID 형식 검증
    if not schemas.validate_uuid_format(user_uuid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="올바르지 않은 UUID 형식입니다"
        )
    
    # 사용자 삭제
    success = UserCRUD.soft_delete_user(db, user_uuid)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다"
        )
    
    logger.info(f"사용자 삭제 완료: UUID={user_uuid}")

@router.get("/{user_uuid}/stats",
            response_model=schemas.UserStatsResponse,
            summary="사용자 통계 조회",
            description="사용자의 활동 통계를 조회합니다.")
async def get_user_stats(
    user_uuid: str,
    db: Session = Depends(get_db)
):
    """
    사용자의 활동 통계를 조회합니다.
    
    Args:
        user_uuid: 조회할 사용자의 UUID
        db: 데이터베이스 세션
    
    Returns:
        사용자 통계 정보 (세션 수, 메시지 수 등)
    
    Raises:
        HTTPException: 사용자를 찾을 수 없는 경우
    """
    # UUID 형식 검증
    if not schemas.validate_uuid_format(user_uuid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="올바르지 않은 UUID 형식입니다"
        )
    
    # 사용자 통계 조회
    stats = UserCRUD.get_user_stats(db, user_uuid)
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다"
        )
    
    # 마지막 활동 시간 업데이트
    UserCRUD.update_last_active(db, user_uuid)
    
    return schemas.UserStatsResponse(**stats)

# 관리자용 엔드포인트 (개발/테스트용)
@router.post("/debug/cleanup-inactive",
             summary="비활성 사용자 정리",
             description="30일 이상 미접속 사용자를 정리합니다.",
             include_in_schema=False)  # API 문서에서 숨김
async def cleanup_inactive_users(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    비활성 사용자를 정리합니다.
    개발/관리용 엔드포인트입니다.
    
    Args:
        days: 비활성 기준 일수 (기본값: 30일)
        db: 데이터베이스 세션
    
    Returns:
        정리된 사용자 수
    """
    try:
        cleaned_count = UserCRUD.cleanup_inactive_users(db, days)
        
        return {
            "success": True,
            "message": f"{cleaned_count}명의 비활성 사용자가 정리되었습니다",
            "cleaned_count": cleaned_count,
            "criteria_days": days
        }
        
    except Exception as e:
        logger.error(f"비활성 사용자 정리 실패: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="비활성 사용자 정리 중 오류가 발생했습니다"
        )