"""
Tests for the cross-document analyzer deterministic checks.

These tests verify the validation rules without invoking the LLM,
focusing on the deterministic_checks_node logic.
"""

from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from src import enums
from src.agents.cross_document_analyzer import (
    CrossDocumentAnalyzerState,
    deterministic_checks_node,
)
from tests.factories import (
    CartaoCNPJDataFactory,
    CertidaoNegativaFederalDataFactory,
    ContratoSocialDataFactory,
    EnderecoEstabelecimentoFactory,
    EnderecoFactory,
    SocioFactory,
    SocioQSAFactory,
)


def _build_initial_state(
    *,
    contrato_social=None,
    cartao_cnpj=None,
    certidao_negativa=None,
    reference_date=None,
) -> CrossDocumentAnalyzerState:
    """Helper to build initial state for deterministic checks."""
    return CrossDocumentAnalyzerState(
        contrato_social=contrato_social,
        cartao_cnpj=cartao_cnpj,
        certidao_negativa=certidao_negativa,
        reference_date=reference_date or date.today(),
        inconsistencies=None,
        decision=None,
        confidence=None,
        summary=None,
        result=None,
    )


# =============================================================================
# Validação de 6 meses - Certidão Negativa
# =============================================================================


@pytest.mark.asyncio
async def test_certidao_emitted_within_6_months_has_no_inconsistency() -> None:
    """
    When certidão negativa was emitted within the last 6 months,
    no document_older_than_6_months inconsistency should be raised.
    """
    reference_date = date(2025, 6, 15)
    data_emissao = date(2025, 3, 1)  # ~3.5 months ago

    certidao = CertidaoNegativaFederalDataFactory.build(
        data_emissao=data_emissao,
        data_validade=date(2025, 9, 1),  # Still valid
    )

    state = _build_initial_state(
        certidao_negativa=certidao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc for inc in inconsistencies if inc.code == "document_older_than_6_months"
    ]
    assert len(older_than_6_months) == 0


@pytest.mark.asyncio
async def test_certidao_emitted_more_than_6_months_ago_raises_blocker() -> None:
    """
    When certidão negativa was emitted more than 6 months ago,
    a BLOCKER inconsistency should be raised.
    """
    reference_date = date(2025, 6, 15)
    data_emissao = date(2024, 12, 1)  # ~6.5 months ago

    certidao = CertidaoNegativaFederalDataFactory.build(
        data_emissao=data_emissao,
        data_validade=date(2025, 6, 1),  # Even if technically valid
    )

    state = _build_initial_state(
        certidao_negativa=certidao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc for inc in inconsistencies if inc.code == "document_older_than_6_months"
    ]
    assert len(older_than_6_months) == 1
    assert older_than_6_months[0].severity == enums.InconsistencySeverity.BLOCKER
    assert "CERTIDAO_NEGATIVA" in older_than_6_months[0].documents
    assert older_than_6_months[0].field == "data_emissao"


@pytest.mark.asyncio
async def test_certidao_emitted_exactly_6_months_ago_has_no_inconsistency() -> None:
    """
    When certidão negativa was emitted exactly 6 months ago,
    no inconsistency should be raised (edge case - on the boundary).
    """
    reference_date = date(2025, 6, 15)
    data_emissao = reference_date - relativedelta(months=6)  # Exactly 6 months

    certidao = CertidaoNegativaFederalDataFactory.build(
        data_emissao=data_emissao,
        data_validade=date(2025, 12, 15),
    )

    state = _build_initial_state(
        certidao_negativa=certidao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc for inc in inconsistencies if inc.code == "document_older_than_6_months"
    ]
    assert len(older_than_6_months) == 0


@pytest.mark.asyncio
async def test_certidao_without_data_emissao_has_no_6_month_inconsistency() -> None:
    """
    When certidão negativa has no data_emissao,
    no document_older_than_6_months inconsistency should be raised.
    """
    certidao = CertidaoNegativaFederalDataFactory.build(
        data_emissao=None,
        data_validade=date(2025, 12, 31),
    )

    state = _build_initial_state(certidao_negativa=certidao)

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc for inc in inconsistencies if inc.code == "document_older_than_6_months"
    ]
    assert len(older_than_6_months) == 0


# =============================================================================
# Validação de 6 meses - Cartão CNPJ
# =============================================================================


@pytest.mark.asyncio
async def test_cartao_cnpj_situacao_cadastral_within_6_months_has_no_inconsistency() -> (
    None
):
    """
    When cartão CNPJ situação cadastral is within 6 months,
    no document_older_than_6_months inconsistency should be raised.
    """
    reference_date = date(2025, 6, 15)
    data_situacao = date(2025, 4, 1)  # ~2.5 months ago

    cartao = CartaoCNPJDataFactory.build(
        data_situacao_cadastral=data_situacao,
    )

    state = _build_initial_state(
        cartao_cnpj=cartao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc for inc in inconsistencies if inc.code == "document_older_than_6_months"
    ]
    assert len(older_than_6_months) == 0


@pytest.mark.asyncio
async def test_cartao_cnpj_situacao_cadastral_older_than_6_months_raises_warn() -> None:
    """
    When cartão CNPJ situação cadastral is older than 6 months,
    a WARN inconsistency should be raised (not BLOCKER like certidão).
    """
    reference_date = date(2025, 6, 15)
    data_situacao = date(2024, 11, 1)  # ~7.5 months ago

    cartao = CartaoCNPJDataFactory.build(
        data_situacao_cadastral=data_situacao,
    )

    state = _build_initial_state(
        cartao_cnpj=cartao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc
        for inc in inconsistencies
        if inc.code == "document_older_than_6_months"
        and "CARTAO_CNPJ" in inc.documents
    ]
    assert len(older_than_6_months) == 1
    assert older_than_6_months[0].severity == enums.InconsistencySeverity.WARN
    assert older_than_6_months[0].field == "data_situacao_cadastral"


@pytest.mark.asyncio
async def test_cartao_cnpj_without_data_situacao_has_no_6_month_inconsistency() -> None:
    """
    When cartão CNPJ has no data_situacao_cadastral,
    no document_older_than_6_months inconsistency should be raised.
    """
    cartao = CartaoCNPJDataFactory.build(
        data_situacao_cadastral=None,
    )

    state = _build_initial_state(cartao_cnpj=cartao)

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc
        for inc in inconsistencies
        if inc.code == "document_older_than_6_months"
        and "CARTAO_CNPJ" in inc.documents
    ]
    assert len(older_than_6_months) == 0


# =============================================================================
# Validação combinada - Múltiplas inconsistências
# =============================================================================


@pytest.mark.asyncio
async def test_both_certidao_and_cartao_older_than_6_months_raises_both_inconsistencies() -> (
    None
):
    """
    When both certidão and cartão CNPJ are older than 6 months,
    both inconsistencies should be raised.
    """
    reference_date = date(2025, 6, 15)

    certidao = CertidaoNegativaFederalDataFactory.build(
        data_emissao=date(2024, 11, 1),  # ~7.5 months ago
        data_validade=date(2025, 5, 1),  # Also expired
    )
    cartao = CartaoCNPJDataFactory.build(
        data_situacao_cadastral=date(2024, 10, 1),  # ~8.5 months ago
    )

    state = _build_initial_state(
        certidao_negativa=certidao,
        cartao_cnpj=cartao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    older_than_6_months = [
        inc for inc in inconsistencies if inc.code == "document_older_than_6_months"
    ]
    assert len(older_than_6_months) == 2

    # Check certidão (BLOCKER)
    certidao_inc = [
        inc for inc in older_than_6_months if "CERTIDAO_NEGATIVA" in inc.documents
    ]
    assert len(certidao_inc) == 1
    assert certidao_inc[0].severity == enums.InconsistencySeverity.BLOCKER

    # Check cartão (WARN)
    cartao_inc = [
        inc for inc in older_than_6_months if "CARTAO_CNPJ" in inc.documents
    ]
    assert len(cartao_inc) == 1
    assert cartao_inc[0].severity == enums.InconsistencySeverity.WARN


# =============================================================================
# Validações existentes (CNPJ, razão social, etc.) - smoke tests
# =============================================================================


@pytest.mark.asyncio
async def test_cnpj_mismatch_raises_blocker() -> None:
    """
    When CNPJ differs between documents, a BLOCKER inconsistency is raised.
    """
    contrato = ContratoSocialDataFactory.build(cnpj="12.345.678/0001-99")
    cartao = CartaoCNPJDataFactory.build(cnpj="98.765.432/0001-11")

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cnpj_mismatch = [inc for inc in inconsistencies if inc.code == "cnpj_mismatch"]
    assert len(cnpj_mismatch) == 1
    assert cnpj_mismatch[0].severity == enums.InconsistencySeverity.BLOCKER


@pytest.mark.asyncio
async def test_razao_social_mismatch_raises_blocker() -> None:
    """
    When razão social differs between documents, a BLOCKER inconsistency is raised.
    """
    contrato = ContratoSocialDataFactory.build(
        razao_social="Empresa ABC LTDA",
        cnpj="12.345.678/0001-99",
    )
    cartao = CartaoCNPJDataFactory.build(
        razao_social="Empresa XYZ LTDA",
        cnpj="12.345.678/0001-99",  # Same CNPJ
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    razao_mismatch = [
        inc for inc in inconsistencies if inc.code == "razao_social_mismatch"
    ]
    assert len(razao_mismatch) == 1
    assert razao_mismatch[0].severity == enums.InconsistencySeverity.BLOCKER


@pytest.mark.asyncio
async def test_certificate_expired_raises_blocker() -> None:
    """
    When certidão negativa is expired, a BLOCKER inconsistency is raised.
    """
    reference_date = date(2025, 6, 15)

    certidao = CertidaoNegativaFederalDataFactory.build(
        data_emissao=date(2025, 3, 1),  # Recent enough
        data_validade=date(2025, 6, 1),  # Expired (before reference_date)
    )

    state = _build_initial_state(
        certidao_negativa=certidao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    expired = [inc for inc in inconsistencies if inc.code == "certificate_expired"]
    assert len(expired) == 1
    assert expired[0].severity == enums.InconsistencySeverity.BLOCKER


@pytest.mark.asyncio
async def test_endereco_mismatch_raises_warn() -> None:
    """
    When endereço differs between contrato and cartão CNPJ,
    a WARN inconsistency is raised.
    """
    contrato = ContratoSocialDataFactory.build(
        cnpj="12.345.678/0001-99",
        sede=EnderecoFactory.build(cidade="São Paulo", uf="SP"),
    )
    cartao = CartaoCNPJDataFactory.build(
        cnpj="12.345.678/0001-99",
        endereco_estabelecimento=EnderecoEstabelecimentoFactory.build(
            municipio="Rio de Janeiro", uf="RJ"
        ),
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    endereco_mismatch = [
        inc for inc in inconsistencies if inc.code == "endereco_mismatch"
    ]
    assert len(endereco_mismatch) == 1
    assert endereco_mismatch[0].severity == enums.InconsistencySeverity.WARN


@pytest.mark.asyncio
async def test_all_documents_consistent_has_no_inconsistencies() -> None:
    """
    When all documents are consistent and within validity,
    no inconsistencies should be raised.
    """
    reference_date = date(2025, 6, 15)

    contrato = ContratoSocialDataFactory.build(
        razao_social="Empresa Consistente LTDA",
        cnpj="12.345.678/0001-99",
        sede=EnderecoFactory.build(cidade="São Paulo", uf="SP"),
    )
    cartao = CartaoCNPJDataFactory.build(
        razao_social="Empresa Consistente LTDA",
        cnpj="12.345.678/0001-99",
        data_situacao_cadastral=date(2025, 5, 1),  # Recent
        endereco_estabelecimento=EnderecoEstabelecimentoFactory.build(
            municipio="São Paulo", uf="SP"
        ),
    )
    certidao = CertidaoNegativaFederalDataFactory.build(
        razao_social="Empresa Consistente LTDA",
        cnpj="12.345.678/0001-99",
        data_emissao=date(2025, 5, 1),  # Recent
        data_validade=date(2025, 11, 1),  # Valid
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
        certidao_negativa=certidao,
        reference_date=reference_date,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    assert len(inconsistencies) == 0


# =============================================================================
# Validação de CPF dos sócios (Contrato Social vs Cartão CNPJ QSA)
# =============================================================================


@pytest.mark.asyncio
async def test_socio_cpf_match_has_no_inconsistency() -> None:
    """
    When sócio CPF matches between Contrato Social and Cartão CNPJ QSA,
    no inconsistency should be raised.
    """
    contrato = ContratoSocialDataFactory.build(
        socios=[
            SocioFactory.build(nome="João Carlos da Silva", cpf="123.456.789-00"),
            SocioFactory.build(nome="Maria Aparecida Santos", cpf="987.654.321-00"),
        ]
    )
    cartao = CartaoCNPJDataFactory.build(
        qsa=[
            SocioQSAFactory.build(
                nome="João Carlos da Silva", cpf_cnpj="123.456.789-00"
            ),
            SocioQSAFactory.build(
                nome="Maria Aparecida Santos", cpf_cnpj="987.654.321-00"
            ),
        ]
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cpf_mismatch = [inc for inc in inconsistencies if inc.code == "socio_cpf_mismatch"]
    assert len(cpf_mismatch) == 0


@pytest.mark.asyncio
async def test_socio_cpf_mismatch_raises_blocker() -> None:
    """
    When sócio CPF differs between Contrato Social and Cartão CNPJ QSA,
    a BLOCKER inconsistency should be raised.
    """
    contrato = ContratoSocialDataFactory.build(
        socios=[
            SocioFactory.build(nome="Fernanda Lima Oliveira", cpf="555.666.777-88"),
        ]
    )
    cartao = CartaoCNPJDataFactory.build(
        qsa=[
            SocioQSAFactory.build(
                nome="Fernanda Lima Oliveira", cpf_cnpj="555.666.777-99"  # Different!
            ),
        ]
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cpf_mismatch = [inc for inc in inconsistencies if inc.code == "socio_cpf_mismatch"]
    assert len(cpf_mismatch) == 1
    assert cpf_mismatch[0].severity == enums.InconsistencySeverity.BLOCKER
    assert "Fernanda Lima Oliveira" in cpf_mismatch[0].message
    assert "55566677788" in cpf_mismatch[0].values
    assert "55566677799" in cpf_mismatch[0].values


@pytest.mark.asyncio
async def test_socio_cpf_mismatch_with_formatting_differences() -> None:
    """
    When sócio CPF differs only in formatting (dots/dashes),
    no inconsistency should be raised (they are the same CPF).
    """
    contrato = ContratoSocialDataFactory.build(
        socios=[
            SocioFactory.build(nome="João Silva", cpf="123.456.789-00"),
        ]
    )
    cartao = CartaoCNPJDataFactory.build(
        qsa=[
            SocioQSAFactory.build(
                nome="João Silva", cpf_cnpj="12345678900"  # Same CPF, no formatting
            ),
        ]
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cpf_mismatch = [inc for inc in inconsistencies if inc.code == "socio_cpf_mismatch"]
    assert len(cpf_mismatch) == 0


@pytest.mark.asyncio
async def test_socio_cpf_validation_with_name_case_differences() -> None:
    """
    When sócio names differ only in case, the CPF validation
    should still work (names are normalized).
    """
    contrato = ContratoSocialDataFactory.build(
        socios=[
            SocioFactory.build(nome="JOÃO CARLOS DA SILVA", cpf="123.456.789-00"),
        ]
    )
    cartao = CartaoCNPJDataFactory.build(
        qsa=[
            SocioQSAFactory.build(
                nome="João Carlos da Silva", cpf_cnpj="123.456.789-00"
            ),
        ]
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cpf_mismatch = [inc for inc in inconsistencies if inc.code == "socio_cpf_mismatch"]
    assert len(cpf_mismatch) == 0


@pytest.mark.asyncio
async def test_multiple_socios_with_one_cpf_mismatch() -> None:
    """
    When multiple sócios exist but only one has CPF mismatch,
    only one inconsistency should be raised.
    """
    contrato = ContratoSocialDataFactory.build(
        socios=[
            SocioFactory.build(nome="Roberto Mendes Ferreira", cpf="111.222.333-44"),
            SocioFactory.build(nome="Fernanda Lima Oliveira", cpf="555.666.777-88"),
        ]
    )
    cartao = CartaoCNPJDataFactory.build(
        qsa=[
            SocioQSAFactory.build(
                nome="Roberto Mendes Ferreira", cpf_cnpj="111.222.333-44"  # OK
            ),
            SocioQSAFactory.build(
                nome="Fernanda Lima Oliveira", cpf_cnpj="555.666.777-99"  # Mismatch!
            ),
        ]
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cpf_mismatch = [inc for inc in inconsistencies if inc.code == "socio_cpf_mismatch"]
    assert len(cpf_mismatch) == 1
    assert "Fernanda Lima Oliveira" in cpf_mismatch[0].message


@pytest.mark.asyncio
async def test_socio_without_cpf_in_contrato_is_skipped() -> None:
    """
    When sócio in Contrato Social has no CPF,
    no comparison is made (no inconsistency).
    """
    contrato = ContratoSocialDataFactory.build(
        socios=[
            SocioFactory.build(nome="João Silva", cpf=None),
        ]
    )
    cartao = CartaoCNPJDataFactory.build(
        qsa=[
            SocioQSAFactory.build(nome="João Silva", cpf_cnpj="123.456.789-00"),
        ]
    )

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cpf_mismatch = [inc for inc in inconsistencies if inc.code == "socio_cpf_mismatch"]
    assert len(cpf_mismatch) == 0


@pytest.mark.asyncio
async def test_empty_qsa_has_no_inconsistency() -> None:
    """
    When Cartão CNPJ has no QSA, no sócio validation is performed.
    """
    contrato = ContratoSocialDataFactory.build(
        socios=[
            SocioFactory.build(nome="João Silva", cpf="123.456.789-00"),
        ]
    )
    cartao = CartaoCNPJDataFactory.build(qsa=[])

    state = _build_initial_state(
        contrato_social=contrato,
        cartao_cnpj=cartao,
    )

    result = await deterministic_checks_node(state)
    inconsistencies = result.get("inconsistencies") or []

    cpf_mismatch = [inc for inc in inconsistencies if inc.code == "socio_cpf_mismatch"]
    assert len(cpf_mismatch) == 0

