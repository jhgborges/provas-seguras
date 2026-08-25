"""
Arquivo de entrada para hospedagem via Passenger (recurso "Setup Python App"
do hPanel da Hostinger, mesma tecnologia usada em cPanel).

O Passenger espera encontrar uma variável chamada `application`. Como o
projeto usa FastAPI (ASGI) e nem todo ambiente Passenger tem suporte nativo
a ASGI, usamos o `a2wsgi` para adaptar automaticamente quando necessário.

Este arquivo deve ficar na RAIZ do diretório da aplicação configurado no
painel (o mesmo nível das pastas backend/ e frontend/).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

from main import app as fastapi_app  # noqa: E402

try:
    # Passenger sem suporte nativo a ASGI: adapta para WSGI
    from a2wsgi import ASGIMiddleware

    application = ASGIMiddleware(fastapi_app)
except ImportError:
    # Passenger 6+ com suporte nativo a ASGI: usa a app diretamente
    application = fastapi_app
