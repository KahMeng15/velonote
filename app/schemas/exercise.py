from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.schemas import SubjectResponse


class MarkingCriterion(BaseModel):
    criterion: str
    max_points: int = 1
    description: str = ""


class ExerciseSubPart(BaseModel):
    id: str
    label: str = ""
    question_text: str = ""
    answer_text: str = ""
    max_marks: int = 0
    question_type: str = "subjective"
    options: Any | None = None
    order: int = 0
    sub_parts: list["ExerciseSubPart"] = []
    marking_scheme: list[MarkingCriterion] = []


class ExerciseQuestionBase(BaseModel):
    question_text: str
    answer_text: str
    question_type: str = "subjective"
    score_type: str = ""
    options: Any | None = None
    order: int = 0
    explanation: str | None = None
    topic: str | None = None
    reference_quote: str | None = None
    difficulty: str | None = None
    reference_resource_id: str | None = None
    reference_resource_title: str | None = None
    max_marks: int = 0
    sub_parts: list[ExerciseSubPart] = []
    marking_scheme: list[MarkingCriterion] = []


class ExerciseQuestionCreate(ExerciseQuestionBase):
    pass


class ExerciseQuestionUpdate(BaseModel):
    question_text: str | None = None
    answer_text: str | None = None
    question_type: str | None = None
    options: Any | None = None
    order: int | None = None
    explanation: str | None = None
    topic: str | None = None
    reference_quote: str | None = None
    max_marks: int | None = None
    sub_parts: list[ExerciseSubPart] | None = None
    marking_scheme: list[MarkingCriterion] | None = None


class ExerciseQuestionResponse(ExerciseQuestionBase):
    id: str

    class Config:
        from_attributes = True


class ExerciseBase(BaseModel):
    title: str
    group_id: str | None = None
    subject_id: str | None = None
    resource_id: str | None = None
    file_path: str | None = None
    file_name: str | None = None
    model: str | None = None
    processing_time_ms: int | None = None
    parameters: Any | None = None


class ExerciseCreate(ExerciseBase):
    pass


class ExerciseUpdate(BaseModel):
    title: str | None = None
    group_id: str | None = None
    subject_id: str | None = None
    resource_id: str | None = None


class ExerciseResponse(ExerciseBase):
    id: str
    created_at: datetime
    updated_at: datetime
    questions: list[ExerciseQuestionResponse] = []
    subject: SubjectResponse | None = None

    class Config:
        from_attributes = True


class ExerciseCheckRequest(BaseModel):
    user_answer: str


class CriterionResult(BaseModel):
    criterion: str
    max_points: int
    awarded_points: int
    rationale: str


class GradeResponse(BaseModel):
    total_awarded: int
    total_max: int
    criterion_results: list[CriterionResult] = []
    feedback: str = ""
    correct_answer: str = ""


class ExerciseExplainRequest(BaseModel):
    scope: str = "source"
    ai_mode: str = "quick"
    output_format: str = "sentence"
    user_answer: str | None = None
    view_mode: str | None = "hide"


class BulkExerciseQuestionUpdate(BaseModel):
    id: int
    question_text: str
    answer_text: str
    question_type: str
    score_type: str = ""
    options: Any | None = None
    order: int
    explanation: str | None = None
    topic: str | None = None
    reference_quote: str | None = None
    max_marks: int = 0
    sub_parts: list[ExerciseSubPart] = []
    marking_scheme: list[MarkingCriterion] = []


class BulkExerciseUpdate(BaseModel):
    questions: list[BulkExerciseQuestionUpdate]


class ExerciseStateSave(BaseModel):
    userAnswers: dict = {}
    gradingResults: dict = {}
    explanations: dict = {}
    revealedAnswers: dict = {}
    showExplanations: dict = {}


class ExerciseGenerateRequest(BaseModel):
    subject_id: str
    resource_ids: list[str] = []
    exercise_ids: list[str] = []
    title: str | None = None
    question_types: list[str] = ["Short answer", "Long answer", "Objective", "Fill in the blank"]
    lengths: list[str] = ["Short", "Medium", "Long"]
    difficulties: list[str] = ["Easy", "Medium", "Hard"]
    num_questions: int = Field(10, ge=1, le=100)


class ExerciseSessionSubmit(BaseModel):
    awarded_marks: int
    total_marks: int
    question_scores: dict
    duration_minutes: int = 0
