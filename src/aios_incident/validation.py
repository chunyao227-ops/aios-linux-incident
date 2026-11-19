"""Typed JSON and JSON Schema validation entry points."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import BaseModel, ValidationError

from .exceptions import InputValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def validate_json_schema(instance: Any, model_type: type[BaseModel]) -> None:
    """Validate a JSON-compatible value against a model's generated JSON Schema."""

    schema = model_type.model_json_schema(mode="validation")
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    if errors:
        first = errors[0]
        path = ".".join(str(item) for item in first.absolute_path) or "<root>"
        raise InputValidationError(f"JSON Schema validation failed at {path}: {first.message}")


def validate_model(payload: Any, model_type: type[ModelT]) -> ModelT:
    """Validate a JSON-compatible payload through schema and typed model checks."""

    validate_json_schema(payload, model_type)
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def validate_json_text(text: str, model_type: type[ModelT]) -> ModelT:
    """Parse and validate a JSON string."""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"invalid JSON: {exc.msg} at column {exc.colno}") from exc
    return validate_model(payload, model_type)


def model_to_json(model: BaseModel) -> str:
    """Serialize a model to JSON with deterministic field order."""

    return model.model_dump_json()


def model_from_json(text: str, model_type: type[ModelT]) -> ModelT:
    """Deserialize a model through the shared JSON Schema validation boundary."""

    return validate_json_text(text, model_type)


def get_json_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    """Return the Draft 2020-12-compatible schema for a contract."""

    schema = model_type.model_json_schema(mode="validation")
    try:
        Draft202012Validator.check_schema(schema)
    except JSONSchemaValidationError as exc:
        raise InputValidationError(f"model produced an invalid JSON Schema: {exc.message}") from exc
    return schema
