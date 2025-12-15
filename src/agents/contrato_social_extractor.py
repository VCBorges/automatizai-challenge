from __future__ import annotations

from datetime import date

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src.core.base.agents import build_llm, build_runnable_config, truncate_text
from src.exceptions import LLMExtractionError, LLMServiceError


class Endereco(BaseModel):
    logradouro: str | None = Field(
        default=None,
        description="Logradouro, ex: Rua das Flores.",
    )
    numero: str | None = Field(
        default=None,
        description="Número, ex: 123.",
    )
    complemento: str | None = Field(
        default=None,
        description="Complemento, ex: Sala 45, Apto 101.",
    )
    bairro: str | None = Field(
        default=None,
        description="Bairro, ex: Centro.",
    )
    cidade: str | None = Field(
        default=None,
        description="Cidade, ex: São Paulo.",
    )
    uf: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="UF, ex: SP.",
    )
    cep: str | None = Field(
        default=None,
        description="CEP no formato 00000-000 (se disponível).",
    )


class Socio(BaseModel):
    nome: str = Field(
        description="Nome completo do sócio.",
    )
    cpf: str | None = Field(
        default=None,
        description="CPF no formato 000.000.000-00 (se disponível).",
    )
    rg: str | None = Field(
        default=None,
        description="RG do sócio (se disponível).",
    )
    nacionalidade: str | None = Field(
        default=None,
        description="Nacionalidade (se disponível).",
    )
    estado_civil: str | None = Field(
        default=None,
        description="Estado civil (se disponível).",
    )
    profissao: str | None = Field(
        default=None,
        description="Profissão/ocupação (se disponível).",
    )
    data_nascimento: date | None = Field(
        default=None,
        description="Data de nascimento (se disponível).",
    )
    endereco: Endereco | None = Field(
        default=None,
        description="Endereço residencial (se disponível).",
    )


class ContratoSocialData(BaseModel):
    razao_social: str | None = Field(
        default=None,
        description="Razão social/denominação social da empresa.",
    )
    cnpj: str | None = Field(
        default=None,
        description="CNPJ da empresa (se disponível no contrato).",
    )
    nire: str | None = Field(
        default=None,
        description="NIRE informado no contrato social (se disponível).",
    )
    data_registro: date | None = Field(
        default=None,
        description="Data de registro na Junta Comercial (se disponível).",
    )
    junta_comercial: str | None = Field(
        default=None,
        description="Junta comercial (ex: JUCESP, JUCERJA), se disponível.",
    )
    sede: Endereco | None = Field(
        default=None,
        description="Endereço da sede da empresa.",
    )
    objeto_social: str | None = Field(
        default=None,
        description="Objeto social (descrição das atividades).",
    )
    socios: list[Socio] = Field(
        default_factory=list,
        description="Lista de sócios identificados no contrato.",
    )


class ContratoSocialExtractionResult(BaseModel):
    data: ContratoSocialData = Field(
        description="Dados extraídos do contrato social.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confiança geral na extração (0.0=baixa, 1.0=alta).",
    )
    evidence: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Evidências por campo (trechos curtos do texto). "
            "Chaves sugeridas: razao_social, cnpj, nire, data_registro, sede, objeto_social, socios."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Observações da extração (ex: campos ausentes, texto incompleto).",
    )


class ContratoSocialExtractorState(TypedDict):
    extracted_text: str
    result: ContratoSocialExtractionResult | None


async def contrato_social_extractor_node(
    state: ContratoSocialExtractorState,
    config: RunnableConfig,
) -> ContratoSocialExtractorState:
    extracted_text = truncate_text(state["extracted_text"])
    correlation_id = (config.get("metadata") or {}).get("correlation_id")

    llm = build_llm(correlation_id=correlation_id)
    llm_structured = llm.with_structured_output(ContratoSocialExtractionResult)

    system = SystemMessage(
        content="""Você é um assistente especializado em extrair dados estruturados de CONTRATO SOCIAL (sociedade empresária limitada) no Brasil.

Extraia os campos solicitados do texto fornecido.

Regras:
- Responda APENAS no formato estruturado solicitado.
- Se algum campo não existir no texto, use null (ou lista vazia, quando aplicável).
- NÃO invente valores. Se estiver incerto, reduza a confidence e descreva em notes.
- Para evidências, inclua trechos curtos (até ~200 caracteres) copiados do texto.
- Datas: quando possível, converta para AAAA-MM-DD.
"""
    )

    user_content = f"""Texto extraído do contrato social (pode estar parcial):
{extracted_text}
"""

    result = await llm_structured.ainvoke(
        [
            system,
            {"role": "user", "content": user_content},
        ]
    )

    return {**state, "result": result}


def build_contrato_social_extractor_graph():
    graph = StateGraph(ContratoSocialExtractorState)
    graph.add_node("extract", contrato_social_extractor_node)
    graph.set_entry_point("extract")
    graph.add_edge("extract", END)
    return graph.compile()


async def extract_contrato_social(
    *,
    extracted_text: str,
    correlation_id: str | None = None,
) -> ContratoSocialExtractionResult:
    import logging

    logger = logging.getLogger(__name__)

    app = build_contrato_social_extractor_graph()
    config = build_runnable_config(correlation_id)

    try:
        final_state = await app.ainvoke(
            {
                "extracted_text": extracted_text,
                "result": None,
            },
            config=config,
        )
    except Exception as e:
        logger.exception(
            "LLM service error during Contrato Social extraction",
            extra={"correlation_id": correlation_id},
        )
        raise LLMServiceError(
            "Failed to invoke LLM for Contrato Social extraction",
            original_error=e,
        ) from e

    result = final_state.get("result")
    if result is None:
        raise LLMExtractionError(
            "Contrato Social extraction did not produce a result",
            extractor_name="ContratoSocialExtractor",
            document_type="CONTRATO_SOCIAL",
        )
    return result
