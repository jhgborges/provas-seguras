# Sistema de Provas Remotas — Acessível para Alunos Neurodivergentes

Sistema de aplicação de provas remotas com foco em **acessibilidade** e
**integridade acadêmica não-punitiva** (soft lockdown), desenvolvido para
uso em contexto universitário (UNIARA).

Este projeto foi recriado a partir da especificação original após perda
do código-fonte, para consolidar tudo em um único lugar organizado.

## Stack

- **Backend:** FastAPI + SQLite (SQLAlchemy) + JWT (python-jose) + bcrypt
- **Frontend:** HTML/CSS/JS puro (sem framework), servido como estático pelo próprio FastAPI

## Recursos principais

### Acessibilidade
- 7 níveis de tamanho de fonte (16px até 54px)
- Modo alto contraste
- Audiodescrição do enunciado das questões via **Web Speech API**
- Preferências persistidas por aluno no banco de dados

### Soft lockdown (integridade não-punitiva)
- Monitora saída de tela cheia (Fullscreen API)
- Monitora troca de aba / minimização (Page Visibility API)
- Bloqueia atalhos de copiar/colar/imprimir/devtools
- **Não bloqueia o aluno** — apenas registra eventos (`IntegrityEvent`) para
  revisão posterior do professor

### Integridade das respostas
- Cada tentativa recebe um **salt aleatório único**
- No envio, calcula-se `SHA-256(salt + respostas_serializadas)`
- Qualquer alteração posterior no banco quebra o hash, permitindo detecção

### Papéis e conteúdo
- Papéis: `student` e `admin`
- Questões de múltipla escolha e dissertativas
- Suporte a imagem embutida em base64 por questão
- Relatórios por prova (lista de tentativas) para o admin

## Instalação

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r ../requirements.txt
uvicorn main:app --reload
```

Acesse `http://localhost:8000` — a página de login é servida automaticamente.

## Primeiros passos

1. Registre um usuário admin:
   ```bash
   curl -X POST http://localhost:8000/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"professor","password":"senha123","full_name":"Prof. João","role":"admin"}'
   ```
2. Faça login em `/index.html` com esse usuário → você cairá no painel `/admin.html`.
3. Crie uma prova, adicione questões, e publique.
4. Registre um usuário `student` e faça login para acessar `/exam.html`.

## Estrutura do projeto

```
remote-exam-system/
├── requirements.txt
├── README.md
├── backend/
│   ├── main.py         # rotas da API
│   ├── models.py        # modelos SQLAlchemy
│   ├── schemas.py        # schemas Pydantic
│   ├── auth.py          # JWT + hashing de senha
│   ├── integrity.py      # hash de integridade SHA-256 com salt
│   └── database.py       # engine/sessão SQLite
└── frontend/
    ├── index.html        # login
    ├── exam.html         # aplicação da prova (aluno)
    ├── admin.html        # painel do professor
    └── static/
        ├── css/style.css
        └── js/
            ├── accessibility.js  # fonte, contraste, audiodescrição
            └── lockdown.js       # soft lockdown

```

## Pontos de atenção para evolução futura

- Trocar `SECRET_KEY` via variável de ambiente `EXAM_JWT_SECRET` em produção
- Restringir CORS (`allow_origins`) antes de expor publicamente
- Adicionar correção automática de múltipla escolha (comparando `selected_option` com `correct_option`)
- Adicionar seleção de prova pelo aluno em `exam.html` (hoje assume a primeira prova publicada)
- Considerar exportação de relatórios de integridade (eventos por tentativa) em CSV/PDF para o professor
