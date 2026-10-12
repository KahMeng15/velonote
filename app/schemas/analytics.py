from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_subjects: int
    total_notes: int
    questions_asked_7d: int
    study_time_7d_mins: int
