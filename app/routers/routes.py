from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import json
import logging

from ..database import get_db
from ..models import RouteCache
from ..schemas import (
    RouteSaveRequest, 
    RouteResponse, 
    RouteSearchRequest,
    RouteSearchResponse
)

router = APIRouter(prefix="/api/routes", tags=["routes"])
logger = logging.getLogger(__name__)

@router.post("/save", response_model=RouteResponse, status_code=status.HTTP_201_CREATED)
async def save_route(
    request: RouteSaveRequest,
    db: Session = Depends(get_db)
):
    """
    경로 검색 결과를 DB에 저장
    
    - **start_lat/lng**: 출발지 좌표
    - **end_lat/lng**: 도착지 좌표
    - **route_data**: 경로 정보 JSON (RouteInfo 리스트)
    - **user_uuid**: 사용자 UUID (선택사항, 추후 개인화용)
    """
    try:
        # 동일한 좌표로 최근 1시간 내 저장된 데이터 확인
        one_hour_ago = datetime.now() - timedelta(hours=1)
        existing = db.query(RouteCache).filter(
            RouteCache.start_lat == request.start_lat,
            RouteCache.start_lng == request.start_lng,
            RouteCache.end_lat == request.end_lat,
            RouteCache.end_lng == request.end_lng,
            RouteCache.created_at >= one_hour_ago
        ).first()
        
        if existing:
            # 기존 데이터 업데이트
            existing.route_data = json.dumps(request.route_data)
            existing.created_at = datetime.now()
            db.commit()
            db.refresh(existing)
            logger.info(f"경로 캐시 업데이트: ID={existing.id}")
            return RouteResponse(
                id=existing.id,
                start_lat=existing.start_lat,
                start_lng=existing.start_lng,
                end_lat=existing.end_lat,
                end_lng=existing.end_lng,
                route_data=json.loads(existing.route_data),
                created_at=existing.created_at
            )
        
        # 새로운 경로 데이터 저장
        new_route = RouteCache(
            start_lat=request.start_lat,
            start_lng=request.start_lng,
            end_lat=request.end_lat,
            end_lng=request.end_lng,
            route_data=json.dumps(request.route_data)
        )
        
        db.add(new_route)
        db.commit()
        db.refresh(new_route)
        
        logger.info(f"새 경로 캐시 저장: ID={new_route.id}")
        
        return RouteResponse(
            id=new_route.id,
            start_lat=new_route.start_lat,
            start_lng=new_route.start_lng,
            end_lat=new_route.end_lat,
            end_lng=new_route.end_lng,
            route_data=json.loads(new_route.route_data),
            created_at=new_route.created_at
        )
        
    except Exception as e:
        logger.error(f"경로 저장 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"경로 저장 중 오류 발생: {str(e)}"
        )

@router.post("/search", response_model=RouteSearchResponse)
async def search_route(
    request: RouteSearchRequest,
    db: Session = Depends(get_db)
):
    """
    저장된 경로 검색 (좌표 기반)
    
    최근 24시간 내 저장된 경로만 반환
    좌표는 소수점 6자리 이내 오차 허용 (약 11cm)
    """
    try:
        # 24시간 이내 데이터만 조회
        twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
        
        # 좌표 오차 범위 (약 100m)
        lat_tolerance = 0.001
        lng_tolerance = 0.001
        
        cached_route = db.query(RouteCache).filter(
            RouteCache.start_lat.between(
                request.start_lat - lat_tolerance,
                request.start_lat + lat_tolerance
            ),
            RouteCache.start_lng.between(
                request.start_lng - lng_tolerance,
                request.start_lng + lng_tolerance
            ),
            RouteCache.end_lat.between(
                request.end_lat - lat_tolerance,
                request.end_lat + lat_tolerance
            ),
            RouteCache.end_lng.between(
                request.end_lng - lng_tolerance,
                request.end_lng + lng_tolerance
            ),
            RouteCache.created_at >= twenty_four_hours_ago
        ).order_by(RouteCache.created_at.desc()).first()
        
        if cached_route:
            logger.info(f"캐시된 경로 발견: ID={cached_route.id}")
            return RouteSearchResponse(
                found=True,
                route=RouteResponse(
                    id=cached_route.id,
                    start_lat=cached_route.start_lat,
                    start_lng=cached_route.start_lng,
                    end_lat=cached_route.end_lat,
                    end_lng=cached_route.end_lng,
                    route_data=json.loads(cached_route.route_data),
                    created_at=cached_route.created_at
                )
            )
        else:
            logger.info("캐시된 경로 없음")
            return RouteSearchResponse(found=False, route=None)
            
    except Exception as e:
        logger.error(f"경로 검색 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"경로 검색 중 오류 발생: {str(e)}"
        )

@router.get("/recent", response_model=List[RouteResponse])
async def get_recent_routes(
    limit: int = 10,
    user_uuid: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    최근 검색한 경로 목록 조회
    
    - **limit**: 반환할 경로 수 (기본 10개)
    - **user_uuid**: 사용자별 필터링 (추후 구현)
    """
    try:
        routes = db.query(RouteCache).order_by(
            RouteCache.created_at.desc()
        ).limit(limit).all()
        
        return [
            RouteResponse(
                id=route.id,
                start_lat=route.start_lat,
                start_lng=route.start_lng,
                end_lat=route.end_lat,
                end_lng=route.end_lng,
                route_data=json.loads(route.route_data),
                created_at=route.created_at
            )
            for route in routes
        ]
        
    except Exception as e:
        logger.error(f"최근 경로 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"최근 경로 조회 중 오류 발생: {str(e)}"
        )

@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    특정 경로 삭제
    """
    try:
        route = db.query(RouteCache).filter(RouteCache.id == route_id).first()
        
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="경로를 찾을 수 없습니다"
            )
        
        db.delete(route)
        db.commit()
        logger.info(f"경로 삭제: ID={route_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"경로 삭제 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"경로 삭제 중 오류 발생: {str(e)}"
        )

@router.delete("/cleanup/old", status_code=status.HTTP_200_OK)
async def cleanup_old_routes(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """
    오래된 경로 데이터 정리
    
    - **days**: 며칠 이상 된 데이터 삭제 (기본 7일)
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        
        deleted_count = db.query(RouteCache).filter(
            RouteCache.created_at < cutoff_date
        ).delete()
        
        db.commit()
        logger.info(f"{days}일 이전 경로 {deleted_count}개 삭제")
        
        return {
            "message": f"{deleted_count}개의 오래된 경로가 삭제되었습니다",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        logger.error(f"경로 정리 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"경로 정리 중 오류 발생: {str(e)}"
        )