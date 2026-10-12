"""User Prompts CRUD router"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.db import User, UserPrompt
from app.schemas.schemas import UserPromptCreate, UserPromptResponse, UserPromptUpdate
from app.utils.auth import get_current_user
from app.utils.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[UserPromptResponse])
async def list_user_prompts(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List all user prompts for the current user"""
    prompts = (
        db.query(UserPrompt)
        .filter(UserPrompt.user_id == current_user.id)
        .order_by(UserPrompt.name)
        .all()
    )
    return prompts


@router.post("", response_model=UserPromptResponse, status_code=201)
async def create_user_prompt(
    prompt_data: UserPromptCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new user prompt"""
    if not prompt_data.name:
        raise HTTPException(status_code=400, detail="Prompt name is required")
    if not prompt_data.content:
        raise HTTPException(status_code=400, detail="Prompt content is required")

    prompt = UserPrompt(user_id=current_user.id, name=prompt_data.name, content=prompt_data.content)
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


@router.put("/{prompt_id}", response_model=UserPromptResponse)
async def update_user_prompt(
    prompt_id: int,
    prompt_data: UserPromptUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing user prompt"""
    prompt = (
        db.query(UserPrompt)
        .filter(UserPrompt.id == prompt_id, UserPrompt.user_id == current_user.id)
        .first()
    )

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if prompt_data.name is not None:
        prompt.name = prompt_data.name
    if prompt_data.content is not None:
        prompt.content = prompt_data.content

    prompt.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prompt)
    return prompt


@router.delete("/{prompt_id}")
async def delete_user_prompt(
    prompt_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a user prompt"""
    prompt = (
        db.query(UserPrompt)
        .filter(UserPrompt.id == prompt_id, UserPrompt.user_id == current_user.id)
        .first()
    )

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    db.delete(prompt)
    db.commit()
    return {"success": True, "message": "Prompt deleted"}
