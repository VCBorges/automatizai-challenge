"""
Factory-boy factories for creating test data.

This module provides factories for database models and pydantic schemas
used throughout the test suite.
"""

import uuid
from datetime import date

import factory
from factory import LazyFunction, SubFactory

from src import enums, models
from src.agents.cartao_cnpj_extractor import (
    CNAE,
    CartaoCNPJData,
    CartaoCNPJExtractionResult,
    EnderecoEstabelecimento,
    SocioQSA,
)
from src.agents.certidao_negativa_federal_extractor import (
    CertidaoNegativaFederalData,
    CertidaoNegativaFederalExtractionResult,
)
from src.agents.contrato_social_extractor import (
    ContratoSocialData,
    ContratoSocialExtractionResult,
    Endereco,
    Socio,
)
from src.agents.cross_document_analyzer import (
    CrossDocumentAnalysisResult,
    Inconsistency,
)

# =============================================================================
# Database Model Factories
# =============================================================================


class AnalysisJobFactory(factory.Factory):
    """Factory for creating AnalysisJob database model instances."""

    class Meta:
        model = models.AnalysisJob

    id = LazyFunction(uuid.uuid4)
    company_name = factory.Faker("company", locale="pt_BR")
    status = enums.AnalysisStatus.PENDING
    decision = None
    error_message = None
    error_details = None
    finished_at = None


class DocumentFactory(factory.Factory):
    """Factory for creating Document database model instances."""

    class Meta:
        model = models.Document

    id = LazyFunction(uuid.uuid4)
    document_type = enums.DocumentType.CONTRATO_SOCIAL
    filename = factory.LazyAttribute(
        lambda obj: f"{obj.document_type.value.lower()}.pdf"
    )
    content_type = "application/pdf"
    size_bytes = factory.Faker("random_int", min=1024, max=1048576)
    checksum_sha256 = factory.Faker("sha256")
    object_key = factory.LazyAttribute(
        lambda obj: f"{obj.job_id}/{obj.document_type.value}/{obj.filename}"
    )
    extracted_text = None
    extracted_data = None
    llm_model = None
    job_id = LazyFunction(uuid.uuid4)


class AnalysisInconsistencyFactory(factory.Factory):
    """Factory for creating AnalysisInconsistency database model instances."""

    class Meta:
        model = models.AnalysisInconsistency

    id = LazyFunction(uuid.uuid4)
    code = "cnpj_mismatch"
    severity = enums.InconsistencySeverity.BLOCKER
    message = "CNPJ does not match between documents"
    pointers = factory.LazyAttribute(
        lambda obj: {"field": "cnpj", "documents": ["CONTRATO_SOCIAL", "CARTAO_CNPJ"]}
    )
    job_id = LazyFunction(uuid.uuid4)
    document_id = None


# =============================================================================
# Contrato Social Extraction Factories
# =============================================================================


class EnderecoFactory(factory.Factory):
    """Factory for creating Endereco pydantic model instances."""

    class Meta:
        model = Endereco

    logradouro = factory.Faker("street_name", locale="pt_BR")
    numero = factory.Faker("building_number")
    complemento = None
    bairro = factory.Faker("bairro", locale="pt_BR")
    cidade = factory.Faker("city", locale="pt_BR")
    uf = factory.Faker(
        "random_element", elements=["SP", "RJ", "MG", "RS", "PR", "SC", "BA"]
    )
    cep = factory.Faker("postcode", locale="pt_BR")


class SocioFactory(factory.Factory):
    """Factory for creating Socio pydantic model instances."""

    class Meta:
        model = Socio

    nome = factory.Faker("name", locale="pt_BR")
    cpf = factory.Faker("cpf", locale="pt_BR")
    rg = None
    nacionalidade = "Brasileiro(a)"
    estado_civil = factory.Faker(
        "random_element", elements=["Solteiro(a)", "Casado(a)", "Divorciado(a)"]
    )
    profissao = factory.Faker("job", locale="pt_BR")
    data_nascimento = None
    endereco = None


class ContratoSocialDataFactory(factory.Factory):
    """Factory for creating ContratoSocialData pydantic model instances."""

    class Meta:
        model = ContratoSocialData

    razao_social = factory.Faker("company", locale="pt_BR")
    cnpj = factory.Faker("cnpj", locale="pt_BR")
    nire = factory.Faker("numerify", text="###########")
    data_registro = None
    junta_comercial = "JUCESP"
    sede = SubFactory(EnderecoFactory)
    objeto_social = factory.Faker("paragraph", locale="pt_BR")
    socios = factory.LazyFunction(list)


class ContratoSocialExtractionResultFactory(factory.Factory):
    """Factory for creating ContratoSocialExtractionResult pydantic model instances."""

    class Meta:
        model = ContratoSocialExtractionResult

    data = SubFactory(ContratoSocialDataFactory)
    confidence = factory.Faker("pyfloat", min_value=0.7, max_value=1.0)
    evidence = factory.LazyFunction(dict)
    notes = factory.LazyFunction(list)


# =============================================================================
# Cartão CNPJ Extraction Factories
# =============================================================================


class EnderecoEstabelecimentoFactory(factory.Factory):
    """Factory for creating EnderecoEstabelecimento pydantic model instances."""

    class Meta:
        model = EnderecoEstabelecimento

    logradouro = factory.Faker("street_name", locale="pt_BR")
    numero = factory.Faker("building_number")
    complemento = None
    bairro = factory.Faker("bairro", locale="pt_BR")
    municipio = factory.Faker("city", locale="pt_BR")
    uf = factory.Faker(
        "random_element", elements=["SP", "RJ", "MG", "RS", "PR", "SC", "BA"]
    )
    cep = factory.Faker("postcode", locale="pt_BR")


class CNAEFactory(factory.Factory):
    """Factory for creating CNAE pydantic model instances."""

    class Meta:
        model = CNAE

    codigo = factory.Faker("numerify", text="####-#/##")
    descricao = factory.Faker("sentence", locale="pt_BR")


class SocioQSAFactory(factory.Factory):
    """Factory for creating SocioQSA pydantic model instances."""

    class Meta:
        model = SocioQSA

    nome = factory.Faker("name", locale="pt_BR")
    cpf_cnpj = factory.Faker("cpf", locale="pt_BR")
    qualificacao = factory.Faker(
        "random_element", elements=["49-Sócio-Administrador", "22-Sócio"]
    )


class CartaoCNPJDataFactory(factory.Factory):
    """Factory for creating CartaoCNPJData pydantic model instances."""

    class Meta:
        model = CartaoCNPJData

    cnpj = factory.Faker("cnpj", locale="pt_BR")
    razao_social = factory.Faker("company", locale="pt_BR")
    nome_fantasia = factory.Faker("company", locale="pt_BR")
    data_abertura = None
    situacao_cadastral = "ATIVA"
    data_situacao_cadastral = None
    natureza_juridica = "206-2 - Sociedade Empresária Limitada"
    endereco_estabelecimento = SubFactory(EnderecoEstabelecimentoFactory)
    cnae_principal = SubFactory(CNAEFactory)
    cnaes_secundarios = factory.LazyFunction(list)
    qsa = factory.LazyFunction(list)


class CartaoCNPJExtractionResultFactory(factory.Factory):
    """Factory for creating CartaoCNPJExtractionResult pydantic model instances."""

    class Meta:
        model = CartaoCNPJExtractionResult

    data = SubFactory(CartaoCNPJDataFactory)
    confidence = factory.Faker("pyfloat", min_value=0.7, max_value=1.0)
    evidence = factory.LazyFunction(dict)
    notes = factory.LazyFunction(list)


# =============================================================================
# Certidão Negativa Federal Extraction Factories
# =============================================================================


class CertidaoNegativaFederalDataFactory(factory.Factory):
    """Factory for creating CertidaoNegativaFederalData pydantic model instances."""

    class Meta:
        model = CertidaoNegativaFederalData

    cnpj = factory.Faker("cnpj", locale="pt_BR")
    razao_social = factory.Faker("company", locale="pt_BR")
    orgao_emissor = "Receita Federal do Brasil / PGFN"
    tipo_certidao = (
        "Certidão Negativa de Débitos Relativos a Tributos Federais "
        "e à Dívida Ativa da União"
    )
    numero_certidao = factory.Faker("numerify", text="####.####.####.####")
    codigo_autenticidade = factory.Faker("uuid4")
    data_emissao = factory.LazyFunction(date.today)
    data_validade = factory.LazyAttribute(
        lambda obj: date(
            obj.data_emissao.year + 1, obj.data_emissao.month, obj.data_emissao.day
        )
        if obj.data_emissao
        else date(2025, 12, 31)
    )
    resultado = "NEGATIVA"
    observacoes = None


class CertidaoNegativaFederalExtractionResultFactory(factory.Factory):
    """Factory for creating CertidaoNegativaFederalExtractionResult pydantic model instances."""

    class Meta:
        model = CertidaoNegativaFederalExtractionResult

    data = SubFactory(CertidaoNegativaFederalDataFactory)
    confidence = factory.Faker("pyfloat", min_value=0.7, max_value=1.0)
    evidence = factory.LazyFunction(dict)
    notes = factory.LazyFunction(list)


# =============================================================================
# Cross Document Analysis Factories
# =============================================================================


class InconsistencyFactory(factory.Factory):
    """Factory for creating Inconsistency pydantic model instances."""

    class Meta:
        model = Inconsistency

    code = "cnpj_mismatch"
    severity = enums.InconsistencySeverity.BLOCKER
    message = "CNPJ mismatch between documents"
    field = "cnpj"
    documents = factory.LazyFunction(lambda: ["CONTRATO_SOCIAL", "CARTAO_CNPJ"])
    values = factory.LazyFunction(lambda: ["12.345.678/0001-99", "98.765.432/0001-11"])


class CrossDocumentAnalysisResultFactory(factory.Factory):
    """Factory for creating CrossDocumentAnalysisResult pydantic model instances."""

    class Meta:
        model = CrossDocumentAnalysisResult

    decision = enums.AnalysisDecision.APROVADO
    inconsistencies = factory.LazyFunction(list)
    summary = "All documents are consistent. Analysis approved."
    confidence = factory.Faker("pyfloat", min_value=0.7, max_value=1.0)
