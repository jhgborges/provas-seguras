"""
Sistema de Aplicação de Provas Remotas — API principal.

Recursos:
- Autenticação JWT (aluno / admin)
- CRUD de provas e questões (múltipla escolha + dissertativa, imagem base64)
- Tentativas de prova com soft lockdown (log de eventos de integridade)
- Hash de integridade SHA-256 com salt por tentativa
- Preferências de acessibilidade persistidas por aluno
  (nível de fonte 1-7 / até 54px, alto contraste, audiodescrição via Web Speech API no frontend)
"""
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import Base, engine, get_db
from integrity import compute_integrity_hash, generate_salt, serialize_answers

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sistema de Provas Remotas - Acessível")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrinja em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# AUTENTICAÇÃO
# =========================================================

@app.post("/auth/register", response_model=schemas.UserOut)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já existe")
    user = models.User(
        username=payload.username,
        hashed_password=auth.hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    token = auth.create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.patch("/auth/me/accessibility", response_model=schemas.UserOut)
def update_accessibility(
    prefs: schemas.AccessibilityPrefs,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if prefs.font_level is not None:
        if not 1 <= prefs.font_level <= 7:
            raise HTTPException(status_code=400, detail="font_level deve estar entre 1 e 7")
        current_user.font_level = prefs.font_level
    if prefs.high_contrast is not None:
        current_user.high_contrast = prefs.high_contrast
    if prefs.audio_description is not None:
        current_user.audio_description = prefs.audio_description
    db.commit()
    db.refresh(current_user)
    return current_user


# =========================================================
# PROVAS (ADMIN)
# =========================================================

@app.post("/exams", response_model=schemas.ExamOut)
def create_exam(
    payload: schemas.ExamCreate,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    exam = models.Exam(**payload.dict())
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@app.post("/exams/{exam_id}/questions", response_model=schemas.QuestionOut)
def add_question(
    exam_id: int,
    payload: schemas.QuestionCreate,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    exam = db.query(models.Exam).get(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada")
    question = models.Question(exam_id=exam_id, **payload.dict())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@app.post("/exams/{exam_id}/publish", response_model=schemas.ExamOut)
def publish_exam(
    exam_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    exam = db.query(models.Exam).get(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada")
    exam.is_published = True
    db.commit()
    db.refresh(exam)
    return exam


@app.get("/exams", response_model=List[schemas.ExamOut])
def list_exams(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.Exam)
    if current_user.role != "admin":
        q = q.filter(models.Exam.is_published == True)  # noqa: E712
    return q.all()


@app.get("/questions/{question_id}", response_model=schemas.QuestionOut)
def get_question(
    question_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    question = db.query(models.Question).get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Questão não encontrada")
    return question


@app.put("/questions/{question_id}", response_model=schemas.QuestionOut)
def update_question(
    question_id: int,
    payload: schemas.QuestionUpdate,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    question = db.query(models.Question).get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Questão não encontrada")
    data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(question, field, value)
    db.commit()
    db.refresh(question)
    return question


@app.get("/exams/{exam_id}/questions", response_model=List[schemas.QuestionOut])
def get_exam_questions(
    exam_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    questions = (
        db.query(models.Question)
        .filter(models.Question.exam_id == exam_id)
        .order_by(models.Question.order)
        .all()
    )
    return questions


# =========================================================
# TENTATIVAS DE PROVA (ALUNO) — soft lockdown + integridade
# =========================================================

@app.post("/exams/{exam_id}/start", response_model=schemas.AttemptOut)
def start_attempt(
    exam_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    exam = db.query(models.Exam).get(exam_id)
    if not exam or not exam.is_published:
        raise HTTPException(status_code=404, detail="Prova não disponível")

    attempt = models.ExamAttempt(
        exam_id=exam_id,
        student_id=current_user.id,
        integrity_salt=generate_salt(),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@app.post("/attempts/{attempt_id}/answer")
def submit_answer(
    attempt_id: int,
    payload: schemas.AnswerIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    attempt = _get_owned_attempt(attempt_id, current_user, db)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Tentativa já finalizada")

    existing = (
        db.query(models.Answer)
        .filter(
            models.Answer.attempt_id == attempt_id,
            models.Answer.question_id == payload.question_id,
        )
        .first()
    )
    if existing:
        existing.selected_option = payload.selected_option
        existing.essay_text = payload.essay_text
    else:
        db.add(models.Answer(attempt_id=attempt_id, **payload.dict()))
    db.commit()
    return {"ok": True}


@app.post("/attempts/{attempt_id}/integrity-event")
def log_integrity_event(
    attempt_id: int,
    payload: schemas.IntegrityEventIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Recebe eventos do soft lockdown do frontend: saída de fullscreen,
    troca de aba (Page Visibility API), tecla bloqueada, etc.
    Não bloqueia a prova — apenas registra para revisão posterior.
    """
    attempt = _get_owned_attempt(attempt_id, current_user, db)
    event = models.IntegrityEvent(attempt_id=attempt_id, **payload.dict())
    db.add(event)
    db.commit()
    return {"ok": True}


@app.post("/attempts/{attempt_id}/submit", response_model=schemas.AttemptOut)
def submit_attempt(
    attempt_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timezone

    attempt = _get_owned_attempt(attempt_id, current_user, db)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Tentativa já finalizada")

    serialized = serialize_answers(attempt.answers)
    attempt.integrity_hash = compute_integrity_hash(attempt.integrity_salt, serialized)
    attempt.submitted_at = datetime.now(timezone.utc)
    attempt.status = "submitted"
    db.commit()
    db.refresh(attempt)
    return attempt


def _get_owned_attempt(attempt_id: int, user: models.User, db: Session) -> models.ExamAttempt:
    attempt = db.query(models.ExamAttempt).get(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Tentativa não encontrada")
    if attempt.student_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado a esta tentativa")
    return attempt


# =========================================================
# RELATÓRIOS (ADMIN)
# =========================================================

@app.get("/exams/{exam_id}/attempts", response_model=List[schemas.AttemptOut])
def list_exam_attempts(
    exam_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    return db.query(models.ExamAttempt).filter(models.ExamAttempt.exam_id == exam_id).all()


@app.get("/attempts/{attempt_id}/detail", response_model=schemas.AttemptDetail)
def get_attempt_detail(
    attempt_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """
    Retorna a tentativa completa: dados do aluno, todas as respostas
    já casadas com o enunciado/gabarito de cada questão, e a contagem
    de eventos de integridade registrados (soft lockdown).
    """
    attempt = db.query(models.ExamAttempt).get(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Tentativa não encontrada")

    student = db.query(models.User).get(attempt.student_id)
    answers_by_question = {a.question_id: a for a in attempt.answers}
    questions = (
        db.query(models.Question)
        .filter(models.Question.exam_id == attempt.exam_id)
        .order_by(models.Question.order)
        .all()
    )

    answer_details = []
    for q in questions:
        ans = answers_by_question.get(q.id)
        answer_details.append(
            schemas.AnswerDetail(
                question_id=q.id,
                statement=q.statement,
                kind=q.kind,
                options=q.options,
                correct_option=q.correct_option,
                selected_option=ans.selected_option if ans else None,
                essay_text=ans.essay_text if ans else None,
            )
        )

    return schemas.AttemptDetail(
        id=attempt.id,
        exam_id=attempt.exam_id,
        student_id=attempt.student_id,
        student_username=student.username if student else "desconhecido",
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        status=attempt.status,
        integrity_hash=attempt.integrity_hash,
        answers=answer_details,
        integrity_event_count=len(attempt.integrity_events),
    )


# Serve o frontend estático (login, prova, painel admin)
# Caminho calculado a partir deste arquivo (robusto a diferentes diretórios
# de execução, como no ambiente Passenger/hPanel da Hostinger).
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
)


# =========================================================
# AUTENTICAÇÃO
# =========================================================

@app.post("/auth/register", response_model=schemas.UserOut)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já existe")
    user = models.User(
        username=payload.username,
        hashed_password=auth.hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    token = auth.create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.patch("/auth/me/accessibility", response_model=schemas.UserOut)
def update_accessibility(
    prefs: schemas.AccessibilityPrefs,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if prefs.font_level is not None:
        if not 1 <= prefs.font_level <= 7:
            raise HTTPException(status_code=400, detail="font_level deve estar entre 1 e 7")
        current_user.font_level = prefs.font_level
    if prefs.high_contrast is not None:
        current_user.high_contrast = prefs.high_contrast
    if prefs.audio_description is not None:
        current_user.audio_description = prefs.audio_description
    db.commit()
    db.refresh(current_user)
    return current_user


# =========================================================
# PROVAS (ADMIN)
# =========================================================

@app.post("/exams", response_model=schemas.ExamOut)
def create_exam(
    payload: schemas.ExamCreate,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    exam = models.Exam(**payload.dict())
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@app.post("/exams/{exam_id}/questions", response_model=schemas.QuestionOut)
def add_question(
    exam_id: int,
    payload: schemas.QuestionCreate,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    exam = db.query(models.Exam).get(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada")
    question = models.Question(exam_id=exam_id, **payload.dict())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@app.post("/exams/{exam_id}/publish", response_model=schemas.ExamOut)
def publish_exam(
    exam_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    exam = db.query(models.Exam).get(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada")
    exam.is_published = True
    db.commit()
    db.refresh(exam)
    return exam


@app.get("/exams", response_model=List[schemas.ExamOut])
def list_exams(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.Exam)
    if current_user.role != "admin":
        q = q.filter(models.Exam.is_published == True)  # noqa: E712
    return q.all()


@app.get("/exams/{exam_id}/questions", response_model=List[schemas.QuestionOut])
def get_exam_questions(
    exam_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    questions = (
        db.query(models.Question)
        .filter(models.Question.exam_id == exam_id)
        .order_by(models.Question.order)
        .all()
    )
    return questions


# =========================================================
# TENTATIVAS DE PROVA (ALUNO) — soft lockdown + integridade
# =========================================================

@app.post("/exams/{exam_id}/start", response_model=schemas.AttemptOut)
def start_attempt(
    exam_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    exam = db.query(models.Exam).get(exam_id)
    if not exam or not exam.is_published:
        raise HTTPException(status_code=404, detail="Prova não disponível")

    attempt = models.ExamAttempt(
        exam_id=exam_id,
        student_id=current_user.id,
        integrity_salt=generate_salt(),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@app.post("/attempts/{attempt_id}/answer")
def submit_answer(
    attempt_id: int,
    payload: schemas.AnswerIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    attempt = _get_owned_attempt(attempt_id, current_user, db)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Tentativa já finalizada")

    existing = (
        db.query(models.Answer)
        .filter(
            models.Answer.attempt_id == attempt_id,
            models.Answer.question_id == payload.question_id,
        )
        .first()
    )
    if existing:
        existing.selected_option = payload.selected_option
        existing.essay_text = payload.essay_text
    else:
        db.add(models.Answer(attempt_id=attempt_id, **payload.dict()))
    db.commit()
    return {"ok": True}


@app.post("/attempts/{attempt_id}/integrity-event")
def log_integrity_event(
    attempt_id: int,
    payload: schemas.IntegrityEventIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Recebe eventos do soft lockdown do frontend: saída de fullscreen,
    troca de aba (Page Visibility API), tecla bloqueada, etc.
    Não bloqueia a prova — apenas registra para revisão posterior.
    """
    attempt = _get_owned_attempt(attempt_id, current_user, db)
    event = models.IntegrityEvent(attempt_id=attempt_id, **payload.dict())
    db.add(event)
    db.commit()
    return {"ok": True}


@app.post("/attempts/{attempt_id}/submit", response_model=schemas.AttemptOut)
def submit_attempt(
    attempt_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timezone

    attempt = _get_owned_attempt(attempt_id, current_user, db)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Tentativa já finalizada")

    serialized = serialize_answers(attempt.answers)
    attempt.integrity_hash = compute_integrity_hash(attempt.integrity_salt, serialized)
    attempt.submitted_at = datetime.now(timezone.utc)
    attempt.status = "submitted"
    db.commit()
    db.refresh(attempt)
    return attempt


def _get_owned_attempt(attempt_id: int, user: models.User, db: Session) -> models.ExamAttempt:
    attempt = db.query(models.ExamAttempt).get(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Tentativa não encontrada")
    if attempt.student_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado a esta tentativa")
    return attempt


# =========================================================
# RELATÓRIOS (ADMIN)
# =========================================================

@app.get("/exams/{exam_id}/attempts", response_model=List[schemas.AttemptOut])
def list_exam_attempts(
    exam_id: int,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    return db.query(models.ExamAttempt).filter(models.ExamAttempt.exam_id == exam_id).all()


# Serve o frontend estático (login, prova, painel admin)
# Caminho calculado a partir deste arquivo (robusto a diferentes diretórios
# de execução, como no ambiente Passenger/hPanel da Hostinger).
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
