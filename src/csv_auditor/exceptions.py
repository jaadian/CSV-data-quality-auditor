class AuditorError(Exception):
    exit_code: int = 1

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class InputFileError(AuditorError):
    exit_code: int = 3


class EncodingError(AuditorError):
    exit_code: int = 3


class ConfigError(AuditorError):
    exit_code: int = 2


class RuleEvaluationError(AuditorError):
    exit_code: int = 1
