"""Study sessions tracking endpoints"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.db import Resource, StudySession, User
from app.utils.auth import get_current_user
from app.utils.db import get_db

router = APIRouter(prefix="/study-sessions", tags=["study-sessions"])


class StudySessionCreate(BaseModel):
    resource_id: str | None = None
    session_type: str  # "exercise", "reading", "pomodoro_study", "pomodoro_break", "stopwatch"
    duration_minutes: int
    questions_attempted: int = 0
    questions_correct: int = 0
    score: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: str | None = "completed"


class StudySessionResponse(BaseModel):
    id: int
    resource_id: str | None = None
    session_type: str
    duration_minutes: int
    questions_attempted: int
    questions_correct: int
    score: float | None
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class CalendarDay(BaseModel):
    date: str
    study_minutes: int
    break_minutes: int
    sessions_count: int


class StudySessionStats(BaseModel):
    total_sessions: int
    total_study_time: int  # minutes
    average_session_duration: float
    total_questions_attempted: int
    total_questions_correct: int
    average_accuracy: float


class PomodoroSettings(BaseModel):
    pomo_study_mins: int
    pomo_break_mins: int
    pomo_long_break_mins: int


@router.get("/settings", response_model=PomodoroSettings)
async def get_pomodoro_settings(current_user: User = Depends(get_current_user)):
    """Fetch user's Pomodoro duration preferences"""
    return PomodoroSettings(
        pomo_study_mins=current_user.pomo_study_mins or 25,
        pomo_break_mins=current_user.pomo_break_mins or 5,
        pomo_long_break_mins=current_user.pomo_long_break_mins or 15,
    )


@router.put("/settings", response_model=PomodoroSettings)
async def update_pomodoro_settings(
    settings: PomodoroSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user's Pomodoro duration preferences"""
    current_user.pomo_study_mins = settings.pomo_study_mins
    current_user.pomo_break_mins = settings.pomo_break_mins
    current_user.pomo_long_break_mins = settings.pomo_long_break_mins
    db.commit()
    return settings


@router.get("/calendar", response_model=list[CalendarDay])
async def get_study_calendar(
    days: int = 30, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get study session totals grouped by day for calendar visualization"""
    from datetime import timedelta

    from sqlalchemy import Date, cast, func

    start_date = datetime.utcnow() - timedelta(days=days)

    sessions = (
        db.query(
            cast(StudySession.created_at, Date).label("day"),
            StudySession.session_type,
            func.sum(StudySession.duration_minutes).label("total_mins"),
            func.count(StudySession.id).label("count"),
        )
        .filter(StudySession.user_id == current_user.id, StudySession.created_at >= start_date)
        .group_by(cast(StudySession.created_at, Date), StudySession.session_type)
        .all()
    )

    # Process into daily buckets
    calendar = {}
    for day, s_type, mins, count in sessions:
        d_str = day.isoformat()
        if d_str not in calendar:
            calendar[d_str] = {"study": 0, "break": 0, "count": 0}

        if "break" in s_type:
            calendar[d_str]["break"] += int(mins or 0)
        else:
            calendar[d_str]["study"] += int(mins or 0)

        calendar[d_str]["count"] += count

    results = [
        CalendarDay(
            date=d, study_minutes=v["study"], break_minutes=v["break"], sessions_count=v["count"]
        )
        for d, v in calendar.items()
    ]

    return sorted(results, key=lambda x: x.date)


@router.get("", response_model=list[StudySessionResponse])
async def get_study_sessions(
    resource_id: str | None = None,
    session_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get study sessions for the current user"""

    query = db.query(StudySession).filter(StudySession.user_id == current_user.id)

    if resource_id:
        query = query.filter(StudySession.resource_id == resource_id)

    if session_type:
        query = query.filter(StudySession.session_type == session_type)

    sessions = query.order_by(StudySession.created_at.desc()).all()
    return sessions


@router.post("", response_model=StudySessionResponse, status_code=status.HTTP_201_CREATED)
async def create_study_session(
    session: StudySessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new study session record"""

    # Verify resource belongs to user if provided
    if session.resource_id:
        resource = (
            db.query(Resource)
            .filter(Resource.id == session.resource_id, Resource.user_id == current_user.id)
            .first()
        )

        if not resource:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    # Calculate score if questions attempted
    score = session.score
    if session.questions_attempted > 0 and not score:
        score = (session.questions_correct / session.questions_attempted) * 100

    db_session = StudySession(
        user_id=current_user.id,
        resource_id=session.resource_id,
        session_type=session.session_type,
        duration_minutes=session.duration_minutes,
        questions_attempted=session.questions_attempted,
        questions_correct=session.questions_correct,
        score=score,
        start_time=session.start_time or datetime.utcnow(),
        end_time=session.end_time or datetime.utcnow(),
        status=session.status or "completed",
    )

    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


@router.get("/stats", response_model=StudySessionStats)
async def get_study_stats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get study statistics for the current user"""

    sessions = db.query(StudySession).filter(StudySession.user_id == current_user.id).all()

    if not sessions:
        return StudySessionStats(
            total_sessions=0,
            total_study_time=0,
            average_session_duration=0.0,
            total_questions_attempted=0,
            total_questions_correct=0,
            average_accuracy=0.0,
        )

    total_time = sum(s.duration_minutes for s in sessions)
    total_questions = sum(s.questions_attempted for s in sessions)
    total_correct = sum(s.questions_correct for s in sessions)

    average_accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0.0
    average_session = total_time / len(sessions) if sessions else 0.0

    return StudySessionStats(
        total_sessions=len(sessions),
        total_study_time=total_time,
        average_session_duration=average_session,
        total_questions_attempted=total_questions,
        total_questions_correct=total_correct,
        average_accuracy=average_accuracy,
    )


@router.get("/{session_id}", response_model=StudySessionResponse)
async def get_study_session(
    session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get a specific study session"""

    session = (
        db.query(StudySession)
        .filter(StudySession.id == session_id, StudySession.user_id == current_user.id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study session not found")

    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study_session(
    session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a study session"""

    session = (
        db.query(StudySession)
        .filter(StudySession.id == session_id, StudySession.user_id == current_user.id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study session not found")

    db.delete(session)
    db.commit()
    return None
