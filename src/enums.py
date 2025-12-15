import enum


class AnalysisStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AnalysisDecision(enum.StrEnum):
    APROVADO = "APROVADO"
    REPROVADO = "REPROVADO"


class DocumentType(enum.StrEnum):
    CONTRATO_SOCIAL = "CONTRATO_SOCIAL"
    CARTAO_CNPJ = "CARTAO_CNPJ"
    CERTIDAO_NEGATIVA = "CERTIDAO_NEGATIVA"


class InconsistencySeverity(enum.StrEnum):
    BLOCKER = "BLOCKER"
    WARN = "WARN"
