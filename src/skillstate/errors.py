"""Stable, machine-readable failure categories."""


class SkillStateError(Exception):
    code = "skillstate_error"


class ValidationError(SkillStateError):
    code = "validation_error"


class BudgetExceeded(SkillStateError):
    code = "budget_exceeded"


class ConflictError(SkillStateError):
    code = "conflict"


class NotFoundError(SkillStateError):
    code = "not_found"


class OperationUncertain(SkillStateError):
    code = "operation_uncertain"


class StepLimitExceeded(SkillStateError):
    code = "step_limit"


class SourceChanged(SkillStateError):
    code = "source_changed"
