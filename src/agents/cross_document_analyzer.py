from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src import enums
from src.agents.cartao_cnpj_extractor import (
    CartaoCNPJData,
    CartaoCNPJExtractionResult,
)
from src.agents.certidao_negativa_federal_extractor import (
    CertidaoNegativaFederalData,
    CertidaoNegativaFederalExtractionResult,
)
from src.agents.contrato_social_extractor import (
    ContratoSocialData,
    ContratoSocialExtractionResult,
)
from src.core.base.agents import build_llm, build_runnable_config
from src.exceptions import LLMExtractionError, LLMServiceError


class Inconsistency(BaseModel):
    code: str = Field(
        description="Código estável da inconsistência (ex: cnpj_mismatch, certificate_expired).",
    )
    severity: enums.InconsistencySeverity = Field(
        description="Severidade: BLOCKER (reprova) ou WARN (alerta).",
    )
    message: str = Field(
        description="Mensagem explicativa legível para o usuário final.",
    )
    field: str | None = Field(
        default=None,
        description="Campo relacionado à inconsistência (ex: cnpj, razao_social).",
    )
    documents: list[str] = Field(
        default_factory=list,
        description="Lista de documentos envolvidos na inconsistência.",
    )
    values: list[str] = Field(
        default_factory=list,
        description="Valores divergentes encontrados (para auditoria).",
    )


class CrossDocumentAnalysisResult(BaseModel):
    decision: enums.AnalysisDecision = Field(
        description="Decisão final: APROVADO ou REPROVADO.",
    )
    inconsistencies: list[Inconsistency] = Field(
        default_factory=list,
        description="Lista de inconsistências encontradas na análise.",
    )
    summary: str = Field(
        description="Resumo executivo da análise para o usuário final.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confiança geral na análise (0.0=baixa, 1.0=alta).",
    )


class CrossDocumentAnalyzerState(TypedDict):
    # Inputs
    contrato_social: ContratoSocialData | None
    cartao_cnpj: CartaoCNPJData | None
    certidao_negativa: CertidaoNegativaFederalData | None
    reference_date: date | None

    # Intermediate results (populated by nodes)
    inconsistencies: list[Inconsistency] | None
    decision: enums.AnalysisDecision | None
    confidence: float | None
    summary: str | None

    # Final output
    result: CrossDocumentAnalysisResult | None


def _normalize_cnpj(cnpj: str | None) -> str:
    if not cnpj:
        return ""
    return "".join(c for c in cnpj if c.isdigit())


def _normalize_cpf(cpf: str | None) -> str:
    """Normaliza CPF: remove pontuação, mantém apenas dígitos."""
    if not cpf:
        return ""
    return "".join(c for c in cpf if c.isdigit())


def _normalize_text(text: str | None) -> str:
    """Normaliza texto: lowercase, whitespace unificado."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def _normalize_name(name: str | None) -> str:
    """Normaliza nome: lowercase, remove acentos comuns, whitespace unificado."""
    if not name:
        return ""
    # Normalização básica
    normalized = " ".join(name.lower().split())
    # Remove acentos comuns em nomes brasileiros
    replacements = {
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e",
        "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "ü": "u",
        "ç": "c",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


async def deterministic_checks_node(
    state: CrossDocumentAnalyzerState,
) -> CrossDocumentAnalyzerState:
    contrato = state["contrato_social"]
    cartao = state["cartao_cnpj"]
    certidao = state["certidao_negativa"]
    reference_date = state.get("reference_date") or date.today()

    inconsistencies: list[Inconsistency] = []

    # --- CNPJ ---
    cnpjs: list[tuple[str, str]] = []
    if contrato and contrato.cnpj:
        cnpjs.append(("CONTRATO_SOCIAL", _normalize_cnpj(contrato.cnpj)))
    if cartao and cartao.cnpj:
        cnpjs.append(("CARTAO_CNPJ", _normalize_cnpj(cartao.cnpj)))
    if certidao and certidao.cnpj:
        cnpjs.append(("CERTIDAO_NEGATIVA", _normalize_cnpj(certidao.cnpj)))

    if len(cnpjs) >= 2:
        ref_doc, ref_cnpj = cnpjs[0]
        for doc, cnpj in cnpjs[1:]:
            if cnpj != ref_cnpj:
                inconsistencies.append(
                    Inconsistency(
                        code="cnpj_mismatch",
                        severity=enums.InconsistencySeverity.BLOCKER,
                        message=f"CNPJ divergente entre {ref_doc} e {doc}.",
                        field="cnpj",
                        documents=[ref_doc, doc],
                        values=[ref_cnpj, cnpj],
                    )
                )

    razoes: list[tuple[str, str]] = []
    if contrato and contrato.razao_social:
        razoes.append(("CONTRATO_SOCIAL", _normalize_text(contrato.razao_social)))
    if cartao and cartao.razao_social:
        razoes.append(("CARTAO_CNPJ", _normalize_text(cartao.razao_social)))
    if certidao and certidao.razao_social:
        razoes.append(("CERTIDAO_NEGATIVA", _normalize_text(certidao.razao_social)))

    if len(razoes) >= 2:
        ref_doc, ref_razao = razoes[0]
        for doc, razao in razoes[1:]:
            if razao != ref_razao:
                inconsistencies.append(
                    Inconsistency(
                        code="razao_social_mismatch",
                        severity=enums.InconsistencySeverity.BLOCKER,
                        message=f"Razão social divergente entre {ref_doc} e {doc}.",
                        field="razao_social",
                        documents=[ref_doc, doc],
                        values=[ref_razao, razao],
                    )
                )

    if certidao and certidao.data_validade:
        if certidao.data_validade < reference_date:
            inconsistencies.append(
                Inconsistency(
                    code="certificate_expired",
                    severity=enums.InconsistencySeverity.BLOCKER,
                    message=f"Certidão negativa vencida (validade: {certidao.data_validade}).",
                    field="data_validade",
                    documents=["CERTIDAO_NEGATIVA"],
                    values=[str(certidao.data_validade)],
                )
            )

    # --- Validação de 6 meses (documentos não podem ter mais de 6 meses) ---
    six_months_ago = reference_date - relativedelta(months=6)

    if certidao and certidao.data_emissao:
        if certidao.data_emissao < six_months_ago:
            inconsistencies.append(
                Inconsistency(
                    code="document_older_than_6_months",
                    severity=enums.InconsistencySeverity.BLOCKER,
                    message=(
                        f"Certidão negativa emitida há mais de 6 meses "
                        f"(emissão: {certidao.data_emissao})."
                    ),
                    field="data_emissao",
                    documents=["CERTIDAO_NEGATIVA"],
                    values=[str(certidao.data_emissao)],
                )
            )

    if cartao and cartao.data_situacao_cadastral:
        if cartao.data_situacao_cadastral < six_months_ago:
            inconsistencies.append(
                Inconsistency(
                    code="document_older_than_6_months",
                    severity=enums.InconsistencySeverity.WARN,
                    message=(
                        f"Cartão CNPJ com situação cadastral desatualizada "
                        f"(data: {cartao.data_situacao_cadastral})."
                    ),
                    field="data_situacao_cadastral",
                    documents=["CARTAO_CNPJ"],
                    values=[str(cartao.data_situacao_cadastral)],
                )
            )

    if contrato and contrato.sede and cartao and cartao.endereco_estabelecimento:
        sede = contrato.sede
        endereco = cartao.endereco_estabelecimento
        cidade_contrato = _normalize_text(sede.cidade)
        uf_contrato = _normalize_text(sede.uf)
        cidade_cartao = _normalize_text(endereco.municipio)
        uf_cartao = _normalize_text(endereco.uf)

        if cidade_contrato and cidade_cartao:
            if cidade_contrato != cidade_cartao or uf_contrato != uf_cartao:
                inconsistencies.append(
                    Inconsistency(
                        code="endereco_mismatch",
                        severity=enums.InconsistencySeverity.WARN,
                        message=(
                            f"Endereço divergente entre Contrato Social "
                            f"({cidade_contrato}/{uf_contrato}) e Cartão CNPJ "
                            f"({cidade_cartao}/{uf_cartao})."
                        ),
                        field="endereco",
                        documents=["CONTRATO_SOCIAL", "CARTAO_CNPJ"],
                        values=[
                            f"{cidade_contrato}/{uf_contrato}",
                            f"{cidade_cartao}/{uf_cartao}",
                        ],
                    )
                )

    # --- Validação de CPF dos sócios (Contrato Social vs Cartão CNPJ QSA) ---
    if contrato and contrato.socios and cartao and cartao.qsa:
        # Criar dicionário de sócios do contrato: nome normalizado -> cpf normalizado
        contrato_socios: dict[str, str] = {}
        for socio in contrato.socios:
            if socio.nome and socio.cpf:
                nome_norm = _normalize_name(socio.nome)
                cpf_norm = _normalize_cpf(socio.cpf)
                contrato_socios[nome_norm] = cpf_norm

        # Criar dicionário de sócios do QSA: nome normalizado -> cpf normalizado
        qsa_socios: dict[str, str] = {}
        for socio in cartao.qsa:
            if socio.nome and socio.cpf_cnpj:
                nome_norm = _normalize_name(socio.nome)
                cpf_norm = _normalize_cpf(socio.cpf_cnpj)
                qsa_socios[nome_norm] = cpf_norm

        # Comparar CPFs de sócios com mesmo nome
        for nome_contrato, cpf_contrato in contrato_socios.items():
            for nome_qsa, cpf_qsa in qsa_socios.items():
                # Verifica se os nomes são similares (match exato após normalização)
                if nome_contrato == nome_qsa:
                    if cpf_contrato != cpf_qsa:
                        # Encontrar nome original para mensagem legível
                        nome_original = next(
                            (s.nome for s in contrato.socios
                             if _normalize_name(s.nome) == nome_contrato),
                            nome_contrato
                        )
                        inconsistencies.append(
                            Inconsistency(
                                code="socio_cpf_mismatch",
                                severity=enums.InconsistencySeverity.BLOCKER,
                                message=(
                                    f"CPF divergente para o sócio '{nome_original}' "
                                    f"entre Contrato Social e Cartão CNPJ."
                                ),
                                field="socio_cpf",
                                documents=["CONTRATO_SOCIAL", "CARTAO_CNPJ"],
                                values=[cpf_contrato, cpf_qsa],
                            )
                        )

    return {**state, "inconsistencies": inconsistencies}


async def make_decision_node(
    state: CrossDocumentAnalyzerState,
) -> CrossDocumentAnalyzerState:
    contrato = state["contrato_social"]
    cartao = state["cartao_cnpj"]
    certidao = state["certidao_negativa"]
    inconsistencies = state.get("inconsistencies") or []

    # Decisão
    has_blocker = any(
        inc.severity == enums.InconsistencySeverity.BLOCKER for inc in inconsistencies
    )
    decision = (
        enums.AnalysisDecision.REPROVADO
        if has_blocker
        else enums.AnalysisDecision.APROVADO
    )

    # Confiança baseada em dados disponíveis
    docs_available = sum(1 for doc in [contrato, cartao, certidao] if doc is not None)
    base_confidence = docs_available / 3.0
    # Penalidade por inconsistências
    penalty = len(inconsistencies) * 0.1
    confidence = max(0.0, min(1.0, base_confidence - penalty))

    return {**state, "decision": decision, "confidence": confidence}


async def generate_summary_node(
    state: CrossDocumentAnalyzerState,
    config: RunnableConfig,
) -> CrossDocumentAnalyzerState:
    contrato = state["contrato_social"]
    cartao = state["cartao_cnpj"]
    certidao = state["certidao_negativa"]
    inconsistencies = state.get("inconsistencies") or []
    decision = state.get("decision")
    correlation_id = (config.get("metadata") or {}).get("correlation_id")

    llm = build_llm(correlation_id=correlation_id)

    system_prompt = """
Você é um analista jurídico especializado em validação de documentos empresariais.

Você recebeu os dados extraídos de três documentos de uma empresa:
- Contrato Social
- Cartão CNPJ
- Certidão Negativa de Débitos Federais

Também recebeu uma lista de inconsistências encontradas na validação cruzada.

Sua tarefa é gerar um RESUMO EXECUTIVO claro e objetivo para o time jurídico,
explicando:
1. Se os documentos estão consistentes ou não
2. Quais problemas foram encontrados (se houver)
3. A decisão final (APROVADO ou REPROVADO)

Seja direto e profissional. Máximo de 3-4 frases.
"""

    user_content = f"""
## Dados extraídos

### Contrato Social
{contrato.model_dump_json(indent=2) if contrato else "Não fornecido"}

### Cartão CNPJ
{cartao.model_dump_json(indent=2) if cartao else "Não fornecido"}

### Certidão Negativa Federal
{certidao.model_dump_json(indent=2) if certidao else "Não fornecido"}

## Inconsistências encontradas
{[inc.model_dump() for inc in inconsistencies] if inconsistencies else "Nenhuma inconsistência encontrada."}

## Decisão
{decision.value if decision else "INDEFINIDA"}

## Gere o resumo executivo:
"""

    messages = [
        SystemMessage(content=system_prompt),
        {"role": "user", "content": user_content},
    ]

    response = await llm.ainvoke(messages)
    summary = response.content.strip() if response.content else ""

    return {**state, "summary": summary}


async def build_result_node(
    state: CrossDocumentAnalyzerState,
) -> CrossDocumentAnalyzerState:
    result = CrossDocumentAnalysisResult(
        decision=state["decision"] or enums.AnalysisDecision.REPROVADO,
        inconsistencies=state.get("inconsistencies") or [],
        summary=state.get("summary") or "",
        confidence=state.get("confidence") or 0.0,
    )

    return {**state, "result": result}


def build_cross_document_analyzer_graph():
    graph = StateGraph(CrossDocumentAnalyzerState)

    graph.add_node("deterministic_checks", deterministic_checks_node)
    graph.add_node("make_decision", make_decision_node)
    graph.add_node("generate_summary", generate_summary_node)
    graph.add_node("build_result", build_result_node)

    graph.set_entry_point("deterministic_checks")
    graph.add_edge("deterministic_checks", "make_decision")
    graph.add_edge("make_decision", "generate_summary")
    graph.add_edge("generate_summary", "build_result")
    graph.add_edge("build_result", END)

    return graph.compile()


async def analyze_documents(
    *,
    contrato_social: ContratoSocialData | ContratoSocialExtractionResult | None = None,
    cartao_cnpj: CartaoCNPJData | CartaoCNPJExtractionResult | None = None,
    certidao_negativa: CertidaoNegativaFederalData
    | CertidaoNegativaFederalExtractionResult
    | None = None,
    reference_date: date | None = None,
    correlation_id: str | None = None,
) -> CrossDocumentAnalysisResult:
    # Extract .data from ExtractionResult objects if needed
    # Using hasattr for robustness with Jupyter autoreload (isinstance can fail
    # when modules are reimported because class identity changes)
    contrato_data: ContratoSocialData | None = None
    if contrato_social is not None:
        if hasattr(contrato_social, "data") and hasattr(contrato_social, "confidence"):
            contrato_data = contrato_social.data
        else:
            contrato_data = contrato_social

    cartao_data: CartaoCNPJData | None = None
    if cartao_cnpj is not None:
        if hasattr(cartao_cnpj, "data") and hasattr(cartao_cnpj, "confidence"):
            cartao_data = cartao_cnpj.data
        else:
            cartao_data = cartao_cnpj

    certidao_data: CertidaoNegativaFederalData | None = None
    if certidao_negativa is not None:
        if hasattr(certidao_negativa, "data") and hasattr(certidao_negativa, "confidence"):
            certidao_data = certidao_negativa.data
        else:
            certidao_data = certidao_negativa

    app = build_cross_document_analyzer_graph()
    config = build_runnable_config(correlation_id)

    initial_state: CrossDocumentAnalyzerState = {
        "contrato_social": contrato_data,
        "cartao_cnpj": cartao_data,
        "certidao_negativa": certidao_data,
        "reference_date": reference_date or date.today(),
        "inconsistencies": None,
        "decision": None,
        "confidence": None,
        "summary": None,
        "result": None,
    }

    import logging

    logger = logging.getLogger(__name__)

    try:
        final_state = await app.ainvoke(initial_state, config=config)
    except Exception as e:
        logger.exception(
            "LLM service error during cross-document analysis",
            extra={"correlation_id": correlation_id},
        )
        raise LLMServiceError(
            "Failed to invoke LLM for cross-document analysis",
            original_error=e,
        ) from e

    result = final_state.get("result")

    if result is None:
        raise LLMExtractionError(
            "Cross-document analysis did not produce a result",
            extractor_name="CrossDocumentAnalyzer",
        )

    return result
