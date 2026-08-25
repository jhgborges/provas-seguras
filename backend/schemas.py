"""
Schemas Pydantic (request/response) da API.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# --- Auth ---

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "student"


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    font_level: int
    high_contrast: bool
    audio_description: bool

    class Config:
        from_attributes = True


class AccessibilityPrefs(BaseModel):
    font_level: Optional[int] = None  # 1-7
    high_contrast: Optional[bool] = None
    audio_description: Optional[bool] = None


# --- Exam / Question ---

class QuestionCreate(BaseModel):
    order: int = 0
    kind: str = "multiple_choice"
    statement: str
    image_base64: Optional[str] = None
    options: Optional[str] = None  # "A|B|C|D|E"
    correct_option: Optional[str] = None


class QuestionOut(BaseModel):
    id: int
    order: int
    kind: str
    statement: str
    image_base64: Optional[str]
    options: Optional[str]

    class Config:
        from_attributes = True


class ExamCreate(BaseModel):
    title: str
    description: str = ""
    duration_minutes: int = 60


class ExamOut(BaseModel):
    id: int
    title: str
    description: str
    duration_minutes: int
    is_published: bool

    class Config:
        from_attributes = True


# --- Attempt / Answer ---

class AnswerIn(BaseModel):
    question_id: int
    selected_option: Optional[str] = None
    essay_text: Optional[str] = None


class IntegrityEventIn(BaseModel):
    event_type: str
    detail: Optional[str] = None


class AttemptOut(BaseModel):
    id: int
    exam_id: int
    student_id: int
    started_at: datetime
    submitted_at: Optional[datetime]
    status: str
    integrity_hash: Optional[str]

    class Config:
        from_attributes = True
