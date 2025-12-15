# Document Analysis API

API REST para validação automatizada de documentos empresariais utilizando LLM (Large Language Models).

O sistema recebe documentos PDF (Contrato Social, Cartão CNPJ e Certidão Negativa de Débitos), extrai dados estruturados via LLM, realiza validação cruzada e gera um parecer de aprovação ou reprovação.

## Funcionalidades

- **Extração estruturada de dados** via LLM (LangGraph + OpenRouter)
- **Validação cruzada** entre documentos (CNPJ, razão social, endereço)
- **Regras de negócio**: validade de certidão, documentos com mais de 6 meses
- **Parecer automatizado**: `APROVADO` ou `REPROVADO` com lista de inconsistências
- **Processamento assíncrono** com Celery + Redis
- **Persistência completa** com PostgreSQL

## Requisitos

- Python 3.13+
- Docker e Docker Compose
- Chave de API do [OpenRouter](https://openrouter.ai/)

## Quick Start

### 1. Clonar e configurar

```bash
git clone <repo-url>
cd automatizai-code-challenge

# Copiar arquivo de ambiente
cp .env.example .env
```

### 2. Configurar variáveis de ambiente

Edite o arquivo `.env` e configure:

```env
# OpenRouter (obrigatório)
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_API_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=qwen/qwen3-4b-2507

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=automatizai
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
```

### 3. Rodar com Docker

```bash
docker compose up -d
```

A API estará disponível em:
- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Endpoints da API

### Health Check

```http
GET /v1/health
```

**Response** `200 OK`:
```json
{
  "status": "ok"
}
```

### Criar Análise de Documentos

```http
POST /v1/analyses
Content-Type: multipart/form-data
```

**Form Data**:
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `company_name` | string | Sim | Nome da empresa |
| `contrato_social` | file (PDF) | Não* | Contrato Social |
| `cartao_cnpj` | file (PDF) | Não* | Cartão CNPJ |
| `certidao_negativa` | file (PDF) | Não* | Certidão Negativa |

*Pelo menos um documento é obrigatório.

**Response** `202 Accepted`:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING"
}
```

**Exemplo com curl**:
```bash
curl -X POST http://localhost:8000/v1/analyses \
  -F "company_name=Empresa Exemplo LTDA" \
  -F "contrato_social=@docs/01_contrato_social.pdf" \
  -F "cartao_cnpj=@docs/02_cartao_cnpj.pdf" \
  -F "certidao_negativa=@docs/03_certidao_negativa_federal.pdf"
```

### Consultar Resultado da Análise

```http
GET /v1/analyses/{job_id}
```

**Response** `200 OK`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "company_name": "Empresa Exemplo LTDA",
  "status": "SUCCEEDED",
  "decision": "REPROVADO",
  "error_message": null,
  "error_details": null,
  "finished_at": "2025-01-15T10:30:00Z",
  "created_at": "2025-01-15T10:29:00Z",
  "updated_at": "2025-01-15T10:30:00Z",
  "documents": [
    {
      "id": "...",
      "document_type": "CONTRATO_SOCIAL",
      "filename": "01_contrato_social.pdf",
      "extracted_data": {
        "razao_social": "Empresa Exemplo LTDA",
        "cnpj": "12.345.678/0001-99",
        "sede": { "cidade": "São Paulo", "uf": "SP" }
      }
    }
  ],
  "inconsistencies": [
    {
      "id": "...",
      "code": "cnpj_mismatch",
      "severity": "BLOCKER",
      "message": "CNPJ divergente entre CONTRATO_SOCIAL e CARTAO_CNPJ.",
      "pointers": {
        "field": "cnpj",
        "documents": ["CONTRATO_SOCIAL", "CARTAO_CNPJ"],
        "values": ["12345678000199", "98765432000111"]
      }
    }
  ]
}
```

## Status do Job

| Status | Descrição |
|--------|-----------|
| `PENDING` | Job criado, aguardando processamento |
| `RUNNING` | Processamento em andamento |
| `SUCCEEDED` | Análise concluída com sucesso |
| `FAILED` | Erro durante o processamento |

## Inconsistências Detectadas

| Código | Severidade | Descrição |
|--------|------------|-----------|
| `cnpj_mismatch` | BLOCKER | CNPJ divergente entre documentos |
| `razao_social_mismatch` | BLOCKER | Razão social divergente |
| `certificate_expired` | BLOCKER | Certidão negativa vencida |
| `document_older_than_6_months` | BLOCKER/WARN | Documento emitido há mais de 6 meses |
| `endereco_mismatch` | WARN | Endereço divergente entre documentos |

## Arquitetura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   FastAPI   │────▶│  PostgreSQL │
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                          │ enqueue
                          ▼
                   ┌─────────────┐
                   │    Redis    │
                   └──────┬──────┘
                          │
                          │ consume
                          ▼
                   ┌─────────────┐     ┌─────────────┐
                   │   Celery    │────▶│  OpenRouter │
                   │   Worker    │     │    (LLM)    │
                   └─────────────┘     └─────────────┘
```

### Estrutura de Diretórios

```
src/
├── agents/                 # Agentes LangGraph para extração via LLM
│   ├── cartao_cnpj_extractor.py
│   ├── certidao_negativa_federal_extractor.py
│   ├── contrato_social_extractor.py
│   ├── cross_document_analyzer.py
│   └── document_type_validator.py
├── api/                    # FastAPI routes e middlewares
│   ├── app.py
│   ├── dependencies.py
│   └── v1/routes.py
├── core/                   # Módulos core (database, storage, logging)
│   ├── base/               # Classes base (models, schemas, usecases)
│   ├── database/
│   ├── logging/
│   ├── storage/
│   └── settings.py
├── services/               # Serviços (PDF extraction)
│   └── pdf.py
├── usecases/               # Casos de uso (orquestração)
│   └── analysis.py
├── worker/                 # Celery worker e tasks
│   ├── celery.py
│   └── tasks.py
├── models.py               # SQLModel database models
├── schemas.py              # Pydantic request/response schemas
├── enums.py                # Enumerações
└── exceptions.py           # Exceções customizadas
```

## Desenvolvimento Local

### Sem Docker (requer PostgreSQL e Redis locais)

```bash
# Instalar dependências com uv
uv sync

# Rodar API
uv run python -m src.main

# Rodar worker (em outro terminal)
uv run celery -A src.worker.celery:celery_app worker -l info
```

### Rodar Testes

```bash
# Rodar todos os testes
uv run pytest

# Com coverage
uv run pytest --cov=src

# Testes específicos
uv run pytest tests/agents/test_cross_document_analyzer.py -v
```

Os testes utilizam **Testcontainers** para criar uma instância PostgreSQL temporária, não sendo necessário configurar banco de dados para testes.

## Decisões Técnicas

### Processamento Assíncrono

O processamento de documentos é feito de forma assíncrona via Celery. Isso permite:
- Resposta imediata ao cliente (`202 Accepted`)
- Escalabilidade horizontal (múltiplos workers)
- Resiliência a falhas (retry automático)
- Melhor experiência do usuário para documentos grandes

### LangGraph para Agentes LLM

Utilizamos LangGraph para orquestrar os agentes de extração porque:
- Permite definir grafos de execução com nós especializados
- Facilita observabilidade e debugging de cada etapa
- Suporta retries e fallbacks nativamente
- Integra bem com Langfuse para tracing (opcional)

### Validação Determinística + LLM

A arquitetura separa:
- **Extração via LLM**: campos estruturados com `structured_output`
- **Validação determinística**: regras de negócio em código Python

Isso garante consistência e auditabilidade das decisões de negócio.

### OCR Fallback (Mock)

O sistema detecta PDFs escaneados (pouco texto extraído) e possui estrutura para fallback via OCR. A implementação atual é mock, mas está preparada para integração com:
- Tesseract OCR (open-source)
- AWS Textract
- Google Cloud Vision

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DEBUG` | Modo debug | `True` |
| `OPENROUTER_API_KEY` | Chave da API OpenRouter | - |
| `OPENROUTER_API_BASE_URL` | URL base da API | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | Modelo LLM | `qwen/qwen3-4b-2507` |
| `OPENROUTER_TEMPERATURE` | Temperatura do modelo | `0.0` |
| `POSTGRES_*` | Configurações PostgreSQL | - |
| `REDIS_*` | Configurações Redis | - |
| `LANGFUSE_*` | Configurações Langfuse (opcional) | - |

## Observabilidade

### Logs Estruturados

Todos os logs são emitidos em formato JSON com correlation ID para rastreamento:

```json
{
  "timestamp": "2025-01-15T10:30:00-0300",
  "level": "INFO",
  "correlation_id": "abc12345",
  "message": "Analysis job completed successfully",
  "job_id": "550e8400-...",
  "decision": "APROVADO"
}
```

### Langfuse (Opcional)

Para habilitar tracing de LLM via Langfuse, configure:

```env
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```
