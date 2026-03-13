from __future__ import annotations

import re
import sys


_SIGNATURE_RE = re.compile(r"^\s*def\s+(?P<name>\w+)\s*\((?P<params>.*)\)\s*(?:->\s*[^:]+)?\s*:?\s*$")
_PARAM_RE = re.compile(r"^\s*(?P<name>\w+)(?:\s*:\s*(?P<type>[^=]+?))?(?:\s*=\s*(?P<default>.+))?\s*$")


def _parse_signature(function_signature: str) -> tuple[str, list[dict[str, str]]]:
    match = _SIGNATURE_RE.match(function_signature)
    if not match:
        return "target", []

    func_name = match.group("name")
    raw_params = match.group("params").strip()
    if not raw_params:
        return func_name, []

    params: list[dict[str, str]] = []
    for chunk in raw_params.split(","):
        part = chunk.strip()
        if not part:
            continue
        p_match = _PARAM_RE.match(part)
        if not p_match:
            continue
        p_name = p_match.group("name")
        p_type = (p_match.group("type") or "any").strip().lower()
        params.append({"name": p_name, "type": p_type})
    return func_name, params


def _is_collection(type_hint: str) -> bool:
    return any(key in type_hint for key in ("list", "dict", "str", "tuple", "set"))


def _base_py_value(type_hint: str) -> str:
    if "int" in type_hint:
        return "1"
    if "float" in type_hint:
        return "1.0"
    if "bool" in type_hint:
        return "True"
    if "list" in type_hint:
        return "[1]"
    if "dict" in type_hint:
        return "{'k': 1}"
    if "str" in type_hint:
        return "'ok'"
    return "None"


def _base_js_value(type_hint: str) -> str:
    if "int" in type_hint or "float" in type_hint:
        return "1"
    if "bool" in type_hint:
        return "true"
    if "list" in type_hint:
        return "[1]"
    if "dict" in type_hint:
        return "{k: 1}"
    if "str" in type_hint:
        return "'ok'"
    return "null"


def _build_py_test(func_name: str, case_name: str, kwargs: dict[str, str]) -> str:
    args = ", ".join(f"{key}={value}" for key, value in kwargs.items())
    return (
        f"def test_{func_name}_{case_name}():\n"
        f"    with pytest.raises(Exception):\n"
        f"        {func_name}({args})\n"
    )


def _build_jest_test(func_name: str, case_name: str, args: list[str]) -> str:
    call_args = ", ".join(args)
    return (
        f"it('should handle {case_name}', () => {{\n"
        f"  expect(() => {func_name}({call_args})).toThrow();\n"
        f"}});\n"
    )


def synthesize_edge_cases(function_signature: str, framework: str) -> list[str]:
    func_name, params = _parse_signature(function_signature)
    target = framework.lower().strip()

    if target in {"jest", "vitest"}:
        as_pytest = False
    else:
        as_pytest = True

    generated: list[str] = []

    for idx, param in enumerate(params):
        name = param["name"]
        p_type = param["type"]

        if as_pytest:
            kwargs = {p["name"]: _base_py_value(p["type"]) for p in params}
            kwargs[name] = "None"
            generated.append(_build_py_test(func_name, f"null_{name}_{idx}", kwargs))
        else:
            args = [_base_js_value(p["type"]) for p in params]
            args[idx] = "null"
            generated.append(_build_jest_test(func_name, f"null_{name}_{idx}", args))

        if _is_collection(p_type):
            if as_pytest:
                kwargs = {p["name"]: _base_py_value(p["type"]) for p in params}
                if "list" in p_type:
                    kwargs[name] = "[]"
                elif "dict" in p_type:
                    kwargs[name] = "{}"
                elif "str" in p_type:
                    kwargs[name] = "''"
                else:
                    kwargs[name] = "[]"
                generated.append(_build_py_test(func_name, f"empty_{name}_{idx}", kwargs))
            else:
                args = [_base_js_value(p["type"]) for p in params]
                if "list" in p_type:
                    args[idx] = "[]"
                elif "dict" in p_type:
                    args[idx] = "{}"
                elif "str" in p_type:
                    args[idx] = "''"
                else:
                    args[idx] = "[]"
                generated.append(_build_jest_test(func_name, f"empty_{name}_{idx}", args))

        if "int" in p_type:
            if as_pytest:
                for boundary_name, boundary_value in (
                    ("zero", "0"),
                    ("negative", "-1"),
                    ("maxsize", str(sys.maxsize)),
                ):
                    kwargs = {p["name"]: _base_py_value(p["type"]) for p in params}
                    kwargs[name] = boundary_value
                    generated.append(_build_py_test(func_name, f"{boundary_name}_{name}_{idx}", kwargs))
            else:
                for boundary_name, boundary_value in (
                    ("zero", "0"),
                    ("negative", "-1"),
                    ("maxsize", "Number.MAX_SAFE_INTEGER"),
                ):
                    args = [_base_js_value(p["type"]) for p in params]
                    args[idx] = boundary_value
                    generated.append(_build_jest_test(func_name, f"{boundary_name}_{name}_{idx}", args))

        if as_pytest:
            kwargs = {p["name"]: _base_py_value(p["type"]) for p in params}
            kwargs[name] = "'wrong_type'"
            generated.append(_build_py_test(func_name, f"type_mismatch_{name}_{idx}", kwargs))
        else:
            args = [_base_js_value(p["type"]) for p in params]
            args[idx] = "'wrong_type'"
            generated.append(_build_jest_test(func_name, f"type_mismatch_{name}_{idx}", args))

        if _is_collection(p_type):
            if as_pytest:
                kwargs = {p["name"]: _base_py_value(p["type"]) for p in params}
                if "str" in p_type:
                    kwargs[name] = "'x' * 10000"
                elif "dict" in p_type:
                    kwargs[name] = "{str(i): i for i in range(10000)}"
                else:
                    kwargs[name] = "[0] * 10000"
                generated.append(_build_py_test(func_name, f"large_{name}_{idx}", kwargs))
            else:
                args = [_base_js_value(p["type"]) for p in params]
                if "str" in p_type:
                    args[idx] = "'x'.repeat(10000)"
                elif "dict" in p_type:
                    args[idx] = "Object.fromEntries(Array.from({ length: 10000 }, (_, i) => [String(i), i]))"
                else:
                    args[idx] = "new Array(10000).fill(0)"
                generated.append(_build_jest_test(func_name, f"large_{name}_{idx}", args))

    return generated
