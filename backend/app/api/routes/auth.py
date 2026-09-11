from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    VerifyEmailRequest,
)
from app.schemas.user import UserRead
from app.services.auth_service import login, logout, refresh, register, verify_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MessageResponse, status_code=201)
async def register_route(
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    return await register(session, payload, background_tasks)


@router.post("/verify-email", response_model=TokenPair)
async def verify_email_route(payload: VerifyEmailRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await verify_email(session, payload.token)


@router.post("/login", response_model=TokenPair)
async def login_route(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await login(session, payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh_route(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await refresh(session, payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout_route(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> None:
    await logout(session, payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
