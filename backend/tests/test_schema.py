import pytest

from app.core.schema.errors import SpecValidationError
from app.core.schema.spec import parse_spec, validate_spec
from conftest import ToyStepModel  # ensures toy time-stepped model registered
import app.models  # noqa: F401


def test_v0_spec_migrated_to_v1():
    raw = {"model": "queueing", "params": {"servers": 2}, "horizon": 500, "seed": 7}
    spec = parse_spec(raw)
    assert spec.schema_version == 1
    assert spec.model_id == "queueing"
    assert spec.params == {"servers": 2}
    assert spec.stop_condition.type == "steps"
    assert spec.stop_condition.value == 500
    assert spec.seed == 7


def test_unknown_model_rejected():
    with pytest.raises(SpecValidationError) as exc:
        validate_spec({"model_id": "nope", "params": {}}, __import__("app.core.registry", fromlist=["registry"]).registry)
    assert exc.value.errors[0]["code"] == "unknown_model"


def test_unknown_model_version_rejected():
    from app.core.registry import registry

    with pytest.raises(SpecValidationError):
        validate_spec({"model_id": "queueing", "model_version": "9.9.9", "params": {}}, registry)


def test_invalid_params_rejected_with_field_code():
    from app.core.registry import registry

    with pytest.raises(SpecValidationError) as exc:
        validate_spec({"model_id": "queueing", "params": {"servers": 0}}, registry)
    codes = [e["code"] for e in exc.value.errors]
    assert any("params.servers" in c for c in codes)


def test_unknown_spec_field_rejected():
    with pytest.raises(SpecValidationError):
        parse_spec({"model_id": "queueing", "bogus_field": 1})


def test_schema_too_new_rejected():
    with pytest.raises(SpecValidationError) as exc:
        parse_spec({"schema_version": 99, "model_id": "queueing"})
    assert exc.value.errors[0]["code"] == "schema_too_new"


def test_until_empty_rejected_for_time_stepped():
    from app.core.registry import registry

    raw = {"model_id": "toy_step", "params": {}, "stop_condition": {"type": "until_empty"}}
    with pytest.raises(SpecValidationError) as exc:
        validate_spec(raw, registry)
    assert exc.value.errors[0]["code"] == "stop_condition_incompatible"


def test_default_stop_condition_is_steps():
    spec = parse_spec({"model_id": "queueing"})
    assert spec.stop_condition.type == "steps"
    assert spec.stop_condition.value == 10000
