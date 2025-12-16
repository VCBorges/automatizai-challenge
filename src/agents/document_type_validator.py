from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src import enums
from src.core.base.agents import (
    build_llm,
    build_runnable_config,
    limit_list,
    truncate_text,
)


class DocumentTypeValidationResult(BaseModel):
    is_match: bool = Field(
        description="True if the detected document type matches the expected type."
    )
    expected_type: enums.DocumentType = Field(
        description="Document type expected by the system."
    )
    detected_type: enums.DocumentType = Field(
        description="Document type detected from the extracted text."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the detected_type. 0.0=low, 1.0=high.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Short text snippets that support the classification.",
    )
    rationale: str = Field(
        description="Short explanation of why the detected_type was chosen."
    )


class DocumentTypeValidationState(TypedDict):
    expected_type: enums.DocumentType
    extracted_text: str
    result: DocumentTypeValidationResult | None


class ClassifierOutput(BaseModel):
    detected_type: enums.DocumentType = Field(
        description="Detected type among the allowed document types."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the detected_type.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Up to 3 short snippets that support the classification.",
    )
    rationale: str = Field(description="Short explanation of the classification.")


async def document_type_validator_node(
    state: DocumentTypeValidationState,
    config: RunnableConfig,
) -> DocumentTypeValidationState:
    expected_type = state["expected_type"]
    extracted_text = truncate_text(state["extracted_text"])
    correlation_id = (config.get("metadata") or {}).get("correlation_id")

    llm = build_llm(correlation_id=correlation_id)
    llm_structured = llm.with_structured_output(
        ClassifierOutput, method="function_calling"
    )

    system = SystemMessage(
        content="""Você é um classificador de documentos empresariais/jurídicos brasileiros.

Sua tarefa é classificar o texto fornecido em exatamente UM dos tipos abaixo:
- CONTRATO_SOCIAL
- CARTAO_CNPJ
- CERTIDAO_NEGATIVA

Regras:
- Retorne apenas a saída estruturada solicitada.
- Use evidências (trechos curtos) extraídas diretamente do texto fornecido.
- Se o texto estiver incompleto ou ruim, ainda assim escolha o tipo mais provável e reduza a confiança.
"""
    )

    output = await llm_structured.ainvoke(
        [
            system,
            {
                "role": "user",
                "content": f"""Tipo esperado: {expected_type}

Texto extraído (pode estar parcial):
{extracted_text}
""",
            },
        ]
    )

    result = DocumentTypeValidationResult(
        is_match=output.detected_type == expected_type,
        expected_type=expected_type,
        detected_type=output.detected_type,
        confidence=output.confidence,
        evidence=limit_list(output.evidence, max_items=3),
        rationale=output.rationale,
    )

    return {**state, "result": result}


def build_document_type_validator_graph():
    graph = StateGraph(DocumentTypeValidationState)
    graph.add_node("validate", document_type_validator_node)
    graph.set_entry_point("validate")
    graph.add_edge("validate", END)
    return graph.compile()


async def validate_document_type(
    *,
    expected_type: enums.DocumentType,
    extracted_text: str,
    correlation_id: str | None = None,
) -> DocumentTypeValidationResult:
    app = build_document_type_validator_graph()
    config = build_runnable_config(correlation_id)
    final_state = await app.ainvoke(
        {
            "expected_type": expected_type,
            "extracted_text": extracted_text,
            "result": None,
        },
        config=config,
    )
    result = final_state.get("result")
    if result is None:
        raise RuntimeError("Document type validator did not produce a result.")
    return result
