"""Structured error handling for dtline."""

import enum


class ErrorCode(enum.Enum):
    CONNECTION_ERROR = "CONNECTION_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    GENERATION_ERROR = "GENERATION_ERROR"
    INVALID_CONFIG = "INVALID_CONFIG"
    IMAGE_NOT_FOUND = "IMAGE_NOT_FOUND"
    PRESET_NOT_FOUND = "PRESET_NOT_FOUND"
    SERVER_BUSY = "SERVER_BUSY"


class DtlineError(Exception):
    code: ErrorCode
    message: str
    details: str | None = None

    def __init__(self, code: ErrorCode, message: str, details: str | None = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{code.value}: {message}")

    def to_dict(self) -> dict:
        result = {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
            },
        }
        if self.details:
            result["error"]["details"] = self.details
        return result


def connection_error(details: str | None = None) -> DtlineError:
    return DtlineError(
        ErrorCode.CONNECTION_ERROR,
        "Failed to connect to Draw Things gRPC server",
        details,
    )


def auth_error(message: str, details: str | None = None) -> DtlineError:
    return DtlineError(ErrorCode.AUTH_ERROR, message, details)


def model_not_found(model: str) -> DtlineError:
    return DtlineError(
        ErrorCode.MODEL_NOT_FOUND,
        f"Model not found on server: {model}",
        "Use 'dtline list-models' to see available models",
    )


def generation_error(message: str, details: str | None = None) -> DtlineError:
    return DtlineError(ErrorCode.GENERATION_ERROR, message, details)


def invalid_config(message: str, details: str | None = None) -> DtlineError:
    return DtlineError(ErrorCode.INVALID_CONFIG, message, details)


def image_not_found(path: str) -> DtlineError:
    return DtlineError(ErrorCode.IMAGE_NOT_FOUND, f"Image file not found: {path}", None)


def preset_not_found(preset: str) -> DtlineError:
    return DtlineError(
        ErrorCode.PRESET_NOT_FOUND,
        f"Preset not found: {preset}",
        "Use 'dtline list-presets' to see available presets",
    )


def server_busy() -> DtlineError:
    return DtlineError(
        ErrorCode.SERVER_BUSY,
        "Server is busy processing another request",
        "The Draw Things server processes ONE request at a time. Do not send parallel requests.",
    )
