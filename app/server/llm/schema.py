"""Codex와 OpenAI가 쓰는 구조화 출력 형식을 맞춘다."""

from typing import Any


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """구조화 출력은 객체의 모든 칸이 필수다. 원래 선택인 칸은 null로 받을 수 있게 한다."""
    strict = dict(schema)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        required = set(schema.get("required", []))
        strict["properties"] = {}
        for name, child in properties.items():
            child = _strict_schema(child)
            strict["properties"][name] = child if name in required else {"anyOf": [child, {"type": "null"}]}
        strict["required"] = list(properties)
        strict["additionalProperties"] = False
    if isinstance(schema.get("items"), dict):
        strict["items"] = _strict_schema(schema["items"])
    if isinstance(schema.get("anyOf"), list):
        strict["anyOf"] = [_strict_schema(part) for part in schema["anyOf"]]
    return strict


def _restore_optional(value: Any, schema: dict[str, Any]) -> Any:
    if isinstance(value, dict) and isinstance(schema.get("properties"), dict):
        properties = schema["properties"]
        required = set(schema.get("required", []))
        return {key: _restore_optional(item, properties.get(key, {})) for key, item in value.items()
                if item is not None or key in required or key not in properties}
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [_restore_optional(item, schema["items"]) for item in value]
    return value
