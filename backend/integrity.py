"""
Hashing de integridade das respostas da prova.

Cada tentativa (ExamAttempt) recebe um salt aleatório único. No momento
da submissão, calculamos SHA-256(salt + respostas_serializadas) para
detectar qualquer alteração posterior no registro de respostas.
"""
import hashlib
import secrets


def generate_salt() -> str:
    return secrets.token_hex(16)


def compute_integrity_hash(salt: str, answers_serialized: str) -> str:
    payload = f"{salt}:{answers_serialized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def serialize_answers(answers: list) -> str:
    """
    Serializa respostas de forma determinística (ordenada por question_id)
    para que o hash seja reproduzível.
    """
    parts = []
    for a in sorted(answers, key=lambda x: x.question_id):
        val = a.selected_option if a.selected_option is not None else (a.essay_text or "")
        parts.append(f"{a.question_id}={val}")
    return "|".join(parts)
