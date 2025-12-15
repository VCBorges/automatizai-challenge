from __future__ import annotations

import logging
from datetime import date

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src.core.base.agents import build_llm, build_runnable_config
from src.exceptions import LLMExtractionError, LLMServiceError

logger = logging.getLogger(__name__)


class EnderecoEstabelecimento(BaseModel):
    logradouro: str | None = Field(
        default=None,
        description="Logradouro do estabelecimento, ex: Avenida Rio Branco.",
    )
    numero: str | None = Field(
        default=None,
        description="Número do estabelecimento, ex: 156.",
    )
    complemento: str | None = Field(
        default=None,
        description="Complemento do endereço, ex: Sala 1010.",
    )
    bairro: str | None = Field(
        default=None,
        description="Bairro/distrito, se disponível.",
    )
    municipio: str | None = Field(
        default=None,
        description="Município/cidade do estabelecimento, se disponível.",
    )
    uf: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="UF do estabelecimento, ex: SP.",
    )
    cep: str | None = Field(
        default=None,
        description="CEP no formato 00000-000 (se disponível).",
    )


class CNAE(BaseModel):
    codigo: str | None = Field(
        default=None,
        description="Código CNAE (somente números ou com separadores, conforme aparecer no texto).",
    )
    descricao: str | None = Field(
        default=None,
        description="Descrição do CNAE (se disponível).",
    )


class SocioQSA(BaseModel):
    """Sócio/Administrador do Quadro de Sócios e Administradores (QSA)."""

    nome: str = Field(
        description="Nome completo do sócio/administrador.",
    )
    cpf_cnpj: str | None = Field(
        default=None,
        description="CPF (pessoa física) ou CNPJ (pessoa jurídica) do sócio.",
    )
    qualificacao: str | None = Field(
        default=None,
        description="Qualificação do sócio (ex: 49-Sócio-Administrador, 22-Sócio).",
    )


class CartaoCNPJData(BaseModel):
    cnpj: str | None = Field(
        default=None,
        description="CNPJ do estabelecimento (se disponível).",
    )
    razao_social: str | None = Field(
        default=None,
        description="Nome empresarial / razão social (se disponível).",
    )
    nome_fantasia: str | None = Field(
        default=None,
        description="Nome fantasia (se disponível).",
    )
    data_abertura: date | None = Field(
        default=None,
        description="Data de abertura (se disponível).",
    )
    situacao_cadastral: str | None = Field(
        default=None,
        description="Situação cadastral (ex: ATIVA), se disponível.",
    )
    data_situacao_cadastral: date | None = Field(
        default=None,
        description="Data da situação cadastral (se disponível).",
    )
    natureza_juridica: str | None = Field(
        default=None,
        description="Natureza jurídica (se disponível).",
    )
    endereco_estabelecimento: EnderecoEstabelecimento | None = Field(
        default=None,
        description="Endereço do estabelecimento conforme o Cartão CNPJ.",
    )
    cnae_principal: CNAE | None = Field(
        default=None,
        description="CNAE principal (se disponível).",
    )
    cnaes_secundarios: list[CNAE] = Field(
        default_factory=list,
        description="Lista de CNAEs secundários (se disponível).",
    )
    qsa: list[SocioQSA] = Field(
        default_factory=list,
        description="Quadro de Sócios e Administradores (QSA) - lista de sócios/administradores.",
    )


class CartaoCNPJExtractionResult(BaseModel):
    data: CartaoCNPJData = Field(
        description="Dados extraídos do Cartão CNPJ.",
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
            "Chaves sugeridas: cnpj, razao_social, nome_fantasia, data_abertura, "
            "situacao_cadastral, data_situacao_cadastral, natureza_juridica, endereco_estabelecimento, "
            "cnae_principal, cnaes_secundarios, qsa."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Observações da extração (ex: campos ausentes, texto incompleto).",
    )


class CartaoCNPJExtractorState(TypedDict):
    extracted_text: str
    result: CartaoCNPJExtractionResult | None


async def cartao_cnpj_extractor_node(
    state: CartaoCNPJExtractorState,
    config: RunnableConfig,
) -> CartaoCNPJExtractorState:
    extracted_text = state["extracted_text"]
    correlation_id = (config.get("metadata") or {}).get("correlation_id")

    llm = build_llm(correlation_id=correlation_id)
    llm_structured = llm.with_structured_output(CartaoCNPJExtractionResult)

    system = SystemMessage(
        content="""Você é um assistente especializado em extrair dados estruturados de CARTÃO CNPJ (Comprovante de Inscrição e de Situação Cadastral) da Receita Federal do Brasil.

Extraia os campos solicitados do texto fornecido.

Regras:
- Responda APENAS no formato estruturado solicitado.
- Se algum campo não existir no texto, use null (ou lista vazia, quando aplicável).
- NÃO invente valores. Se estiver incerto, reduza a confidence e descreva em notes.
- Para evidências, inclua trechos curtos (até ~200 caracteres) copiados do texto.
- Datas: quando possível, converta para AAAA-MM-DD.
- Para o QSA (Quadro de Sócios e Administradores), extraia nome, CPF/CNPJ e qualificação de cada sócio.
"""
    )

    user_content = f"""Texto extraído do Cartão CNPJ (pode estar parcial):
{extracted_text}
"""
    result = await llm_structured.ainvoke(
        [
            system,
            {"role": "user", "content": user_content},
        ]
    )
    return {**state, "result": result}


def build_cartao_cnpj_extractor_graph():
    graph = StateGraph(CartaoCNPJExtractorState)
    graph.add_node("extract", cartao_cnpj_extractor_node)
    graph.set_entry_point("extract")
    graph.add_edge("extract", END)
    return graph.compile()


async def extract_cartao_cnpj(
    *,
    extracted_text: str,
    correlation_id: str | None = None,
) -> CartaoCNPJExtractionResult:
    app = build_cartao_cnpj_extractor_graph()
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
            "LLM service error during Cartão CNPJ extraction",
            extra={"correlation_id": correlation_id},
        )
        raise LLMServiceError(
            "Failed to invoke LLM for Cartão CNPJ extraction",
            original_error=e,
        ) from e

    result = final_state.get("result")
    if result is None:
        raise LLMExtractionError(
            "Cartão CNPJ extraction did not produce a result",
            extractor_name="CartaoCNPJExtractor",
            document_type="CARTAO_CNPJ",
        )
    return result
