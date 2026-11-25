from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ..services.jobs import JobService
from .deps import current_user_id, get_job_service
from .schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, user_id: UUID = Depends(current_user_id), svc: JobService = Depends(get_job_service)):
    job = svc.get_for_user(user_id, job_id)
    return JobOut(id=job.id, status=job.status, progress=job.progress, output_ref=job.output_ref,
                  error_code=job.error_code, error_message=job.error_message,
                  created_at=job.created_at, finished_at=job.finished_at)
