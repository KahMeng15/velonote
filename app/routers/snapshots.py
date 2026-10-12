"""Resource Snapshots management endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.db import Resource, ResourceSnapshot, User
from app.schemas.schemas import ResourceSnapshotCreate, ResourceSnapshotResponse
from app.utils.auth import get_current_user
from app.utils.db import get_db

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/{resource_id}", response_model=list[ResourceSnapshotResponse])
async def list_snapshots(
    resource_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List all snapshots for a resource"""
    # Verify resource belongs to user
    resource = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    snapshots = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.resource_id == resource_id, ResourceSnapshot.user_id == current_user.id
        )
        .order_by(ResourceSnapshot.created_at.desc())
        .all()
    )

    return snapshots


@router.post("/{resource_id}", response_model=ResourceSnapshotResponse, status_code=201)
async def create_snapshot(
    resource_id: str,
    body: ResourceSnapshotCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a named snapshot of the current resource content"""
    # Verify resource belongs to user
    resource = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    snapshot = ResourceSnapshot(
        resource_id=resource_id, user_id=current_user.id, name=body.name, content=body.content
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get("/{resource_id}/{snapshot_id}", response_model=ResourceSnapshotResponse)
async def get_snapshot(
    resource_id: str,
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single snapshot's content"""
    snapshot = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.id == snapshot_id,
            ResourceSnapshot.resource_id == resource_id,
            ResourceSnapshot.user_id == current_user.id,
        )
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


@router.delete("/{resource_id}/{snapshot_id}", status_code=204)
async def delete_snapshot(
    resource_id: str,
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a snapshot"""
    snapshot = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.id == snapshot_id,
            ResourceSnapshot.resource_id == resource_id,
            ResourceSnapshot.user_id == current_user.id,
        )
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    db.delete(snapshot)
    db.commit()
    return None
