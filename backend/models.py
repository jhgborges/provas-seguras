"""
Modelos ORM para o sistema de aplicação de provas remotas.

Inclui suporte a acessibilidade (preferências por aluno), soft lockdown
(log de eventos de integridade) e hashing de integridade por aluno.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="student")  # student | admin
    # Preferências de acessibilidade persistidas por aluno
    font_level = Column(Integer, default=1)  # 1 a 7 (até 54px)
    high_contrast = Column(Boolean, default=False)
    audio_description = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    attempts = relationship("ExamAttempt", back_populates="student")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    duration_minutes = Column(Integer, default=60)
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    questions = relationship(
        "Question", back_populates="exam", cascade="all, delete-orphan"
    )
    attempts = relationship("ExamAttempt", back_populates="exam")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    order = Column(Integer, default=0)
    kind = Column(String, nullable=False, default="multiple_choice")  # multiple_choice | essay
    statement = Column(Text, nullable=False)
    image_base64 = Column(Text, nullable=True)  # imagem embutida, opcional
    # Para múltipla escolha: alternativas em JSON-string simples "A|B|C|D|E"
    options = Column(Text, nullable=True)
    correct_option = Column(String, nullable=True)  # ex.: "B"

    exam = relationship("Exam", back_populates="questions")


class ExamAttempt(Base):
    """Uma tentativa de prova de um aluno específico."""

    __tablename__ = "exam_attempts"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=utcnow)
    submitted_at = Column(DateTime, nullable=True)
    # Salt único por aluno/tentativa para o hash de integridade
    integrity_salt = Column(String, nullable=False)
    integrity_hash = Column(String, nullable=True)
    status = Column(String, default="in_progress")  # in_progress | submitted | flagged

    exam = relationship("Exam", back_populates="attempts")
    student = relationship("User", back_populates="attempts")
    answers = relationship(
        "Answer", back_populates="attempt", cascade="all, delete-orphan"
    )
    integrity_events = relationship(
        "IntegrityEvent", back_populates="attempt", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option = Column(String, nullable=True)  # múltipla escolha
    essay_text = Column(Text, nullable=True)  # dissertativa
    answered_at = Column(DateTime, default=utcnow)

    attempt = relationship("ExamAttempt", back_populates="answers")


class IntegrityEvent(Base):
    """
    Log de eventos do soft lockdown: perda de foco, saída de fullscreen,
    tentativa de copiar/colar, etc. Não bloqueia a prova, mas registra
    para revisão do professor.
    """

    __tablename__ = "integrity_events"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False)
    event_type = Column(String, nullable=False)  # visibility_change | fullscreen_exit | blocked_key | ...
    detail = Column(String, nullable=True)
    occurred_at = Column(DateTime, default=utcnow)

    attempt = relationship("ExamAttempt", back_populates="integrity_events")
