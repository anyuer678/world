from __future__ import annotations


class SpecValidationError(Exception):
    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        super().__init__(f"spec validation failed: {errors}")

    @staticmethod
    def single(code: str, message: str) -> "SpecValidationError":
        return SpecValidationError([{"code": code, "message": message}])
