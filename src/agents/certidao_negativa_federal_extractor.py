from __future__ import annotations

from datetime import date

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src.core.base.agents import build_llm, build_runnable_config, truncate_text
from src.exceptions import LLMExtractionError, LLMServiceError


class CertidaoNegativaFederalData(BaseModel):
    cnpj: str | None = Field(
        default=None,
        description="CNPJ do contribuinte/empresa (se disponível).",
    )
    razao_social: str | None = Field(
        default=None,
        description="Razão social / nome empresarial (se disponível).",
    )
    orgao_emissor: str | None = Field(
        default=None,
        description="Órgão emissor (ex: Receita Federal do Brasil / PGFN), se disponível.",
    )
    tipo_certidao: str | None = Field(
        default=None,
        description=(
            "Tipo/denominação da certidão conforme o texto "
            "(ex: Certidão Negativa de Débitos Relativos a Tributos Federais e à Dívida Ativa da União)."
        ),
    )
    numero_certidao: str | None = Field(
        default=None,
        description="Número/identificador da certidão (se disponível).",
    )
    codigo_autenticidade: str | None = Field(
        default=None,
        description="Código de autenticidade/controle para verificação (se disponível).",
    )
    data_emissao: date | None = Field(
        default=None,
        description="Data de emissão/geração da certidão (se disponível).",
    )
    data_validade: date | None = Field(
        default=None,
        description="Data de validade da certidão (se disponível).",
    )
    resultado: str | None = Field(
        default=None,
        description=(
            "Resultado/efeito da certidão conforme o texto (ex: NEGATIVA, POSITIVA, "
            "POSITIVE COM EFEITOS DE NEGATIVA), se disponível."
        ),
    )
    observacoes: str | None = Field(
        default=None,
        description="Observações relevantes do documento (se disponível).",
    )


class CertidaoNegativaFederalExtractionResult(BaseModel):
    data: CertidaoNegativaFederalData = Field(
        description="Dados extraídos da Certidão Negativa Federal.",
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
            "Chaves sugeridas: cnpj, razao_social, orgao_emissor, tipo_certidao, numero_certidao, "
            "codigo_autenticidade, data_emissao, data_validade, resultado."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Observações da extração (ex: campos ausentes, texto incompleto).",
    )


class CertidaoNegativaFederalExtractorState(TypedDict):
    extracted_text: str
    result: CertidaoNegativaFederalExtractionResult | None


async def certidao_negativa_federal_extractor_node(
    state: CertidaoNegativaFederalExtractorState,
    config: RunnableConfig,
) -> CertidaoNegativaFederalExtractorState:
    extracted_text = truncate_text(state["extracted_text"])
    correlation_id = (config.get("metadata") or {}).get("correlation_id")

    llm = build_llm(correlation_id=correlation_id)
    llm_structured = llm.with_structured_output(CertidaoNegativaFederalExtractionResult)

    system = SystemMessage(
        content="""Você é um assistente especializado em extrair dados estruturados de CERTIDÃO NEGATIVA FEDERAL.

O documento costuma ser emitido pela Receita Federal do Brasil e/ou PGFN e comprova regularidade fiscal.
Extraia os campos solicitados do texto fornecido.

Regras:
- Responda APENAS no formato estruturado solicitado.
- Se algum campo não existir no texto, use null (ou lista vazia, quando aplicável).
- NÃO invente valores. Se estiver incerto, reduza a confidence e descreva em notes.
- Para evidências, inclua trechos curtos (até ~200 caracteres) copiados do texto.
- Datas: quando possível, converta para AAAA-MM-DD.
"""
    )

    user_content = f"""Texto extraído da Certidão Negativa Federal (pode estar parcial):
{extracted_text}
"""

    result = await llm_structured.ainvoke(
        [
            system,
            {"role": "user", "content": user_content},
        ]
    )

    return {**state, "result": result}


def build_certidao_negativa_federal_extractor_graph():
    graph = StateGraph(CertidaoNegativaFederalExtractorState)
    graph.add_node("extract", certidao_negativa_federal_extractor_node)
    graph.set_entry_point("extract")
    graph.add_edge("extract", END)
    return graph.compile()


async def extract_certidao_negativa_federal(
    *,
    extracted_text: str,
    correlation_id: str | None = None,
) -> CertidaoNegativaFederalExtractionResult:
    import logging

    logger = logging.getLogger(__name__)

    app = build_certidao_negativa_federal_extractor_graph()
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
            "LLM service error during Certidão Negativa Federal extraction",
            extra={"correlation_id": correlation_id},
        )
        raise LLMServiceError(
            "Failed to invoke LLM for Certidão Negativa Federal extraction",
            original_error=e,
        ) from e

    result = final_state.get("result")
    if result is None:
        raise LLMExtractionError(
            "Certidão Negativa Federal extraction did not produce a result",
            extractor_name="CertidaoNegativaFederalExtractor",
            document_type="CERTIDAO_NEGATIVA",
        )
    return result
