from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Callable, Protocol, TypeAlias, cast
from urllib import parse, request
from urllib.error import HTTPError

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]

_CONTAINER_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


class ToolGenerator:
    def generate(self, spec_path: str) -> dict[str, Callable[..., JSONDict]]:
        integration_mod = import_module("claude_experimental.integration")
        require_enabled_obj = integration_mod.__dict__.get("_require_enabled")
        if not callable(require_enabled_obj):
            raise RuntimeError("integration feature gate is unavailable")
        require_enabled = cast(Callable[[], None], require_enabled_obj)
        _ = require_enabled()

        spec = self._load_spec(spec_path)
        operations = self._iter_operations(spec)
        return {name: self._build_callable(meta) for name, meta in operations.items()}

    def generate_module(self, spec_path: str) -> str:
        integration_mod = import_module("claude_experimental.integration")
        require_enabled_obj = integration_mod.__dict__.get("_require_enabled")
        if not callable(require_enabled_obj):
            raise RuntimeError("integration feature gate is unavailable")
        require_enabled = cast(Callable[[], None], require_enabled_obj)
        _ = require_enabled()

        spec = self._load_spec(spec_path)
        operations = self._iter_operations(spec)

        lines: list[str] = [
            "from __future__ import annotations",
            "",
            "import json",
            "from urllib import parse, request",
            "from urllib.error import HTTPError",
            "",
            "",
            "def _map_http_error(err: HTTPError) -> Exception:",
            "    if err.code == 404:",
            "        return FileNotFoundError(f'HTTP 404: {err.reason}')",
            "    if err.code == 400:",
            "        return ValueError(f'HTTP 400: {err.reason}')",
            "    if err.code >= 500:",
            "        return RuntimeError(f'HTTP {err.code}: {err.reason}')",
            "    return RuntimeError(f'HTTP {err.code}: {err.reason}')",
            "",
            "",
            "def _call_endpoint(base_url: str, path: str, method: str, query_params: dict, body, header_param_names: frozenset = frozenset()):",
            "    headers = {k: str(v) for k, v in query_params.items() if k in header_param_names and v is not None}",
            "    query = {k: v for k, v in query_params.items() if k not in header_param_names and v is not None}",
            "    query_string = parse.urlencode(query, doseq=True)",
            "    url = f\"{base_url.rstrip('/')}\" + path",
            "    if query_string:",
            "        url = f\"{url}?{query_string}\"",
            "    payload = None",
            "    if body is not None:",
            "        payload = json.dumps(body).encode('utf-8')",
            "        headers['Content-Type'] = 'application/json'",
            "    req = request.Request(url, data=payload, method=method.upper(), headers=headers)",
            "    try:",
            "        with request.urlopen(req) as response:",
            "            response_bytes = response.read()",
            "            if not response_bytes:",
            "                return {}",
            "            return json.loads(response_bytes.decode('utf-8'))",
            "    except HTTPError as err:",
            "        raise _map_http_error(err) from err",
            "",
        ]

        for endpoint_name, meta in operations.items():
            path_params = meta.path_params
            signature_items = ["base_url", *path_params, "body=None", "**query_params"]
            signature = ", ".join(signature_items)
            lines.append(f"def {endpoint_name}({signature}):")
            lines.append(f"    path = {meta.path_template!r}")
            for param_name in path_params:
                lines.append(
                    f"    path = path.replace('{{{param_name}}}', parse.quote(str({param_name}), safe=''))"
                )
            lines.append(
                f"    return _call_endpoint(base_url=base_url, path=path, method={meta.method!r}, "
                f"query_params=query_params, body=body, "
                f"header_param_names=frozenset({meta.header_params!r}))"
            )
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _build_callable(self, meta: _OperationMeta) -> Callable[..., JSONDict]:
        method = meta.method.upper()
        path_template = meta.path_template
        path_params = meta.path_params
        header_params = set(meta.header_params)

        def endpoint(
            base_url: str,
            *args: object,
            body: JSONDict | None = None,
            **query_params: object,
        ) -> JSONDict:
            if len(args) < len(path_params):
                missing = path_params[len(args) :]
                raise ValueError(f"Missing path parameters: {', '.join(missing)}")

            path = path_template
            for name, value in zip(path_params, args):
                path = path.replace("{" + name + "}", parse.quote(str(value), safe=""))

            # Route in:header params to request headers; everything else is a query param.
            headers: dict[str, str] = {
                key: str(value)
                for key, value in query_params.items()
                if key in header_params and value is not None
            }
            query: dict[str, object] = {
                key: value
                for key, value in query_params.items()
                if key not in header_params and value is not None
            }
            query_string = parse.urlencode(query, doseq=True)
            url = f"{base_url.rstrip('/')}" + path
            if query_string:
                url = f"{url}?{query_string}"

            payload: bytes | None = None
            if body is not None:
                payload = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"

            req = request.Request(url=url, data=payload, method=method, headers=headers)
            try:
                with cast(_HTTPResponse, request.urlopen(req)) as response:
                    data = response.read()
                    if not data:
                        return {}
                    decoded: str = data.decode("utf-8")
                    loaded = cast(object, json.loads(decoded))
                    if isinstance(loaded, dict):
                        return cast(JSONDict, loaded)
                    return {"data": cast(JSONValue, loaded)}
            except HTTPError as err:
                raise self._map_http_error(err) from err

        endpoint.__name__ = meta.endpoint_name
        setattr(endpoint, "__signature__", self._build_signature(path_params))
        return endpoint

    def _build_signature(self, path_params: list[str]) -> inspect.Signature:
        parameters = [inspect.Parameter("base_url", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        for param_name in path_params:
            parameters.append(inspect.Parameter(param_name, inspect.Parameter.POSITIONAL_OR_KEYWORD))
        parameters.append(inspect.Parameter("body", inspect.Parameter.KEYWORD_ONLY, default=None))
        parameters.append(inspect.Parameter("query_params", inspect.Parameter.VAR_KEYWORD))
        return inspect.Signature(parameters, return_annotation=dict[str, JSONValue])

    def _iter_operations(self, spec: JSONDict) -> dict[str, _OperationMeta]:
        paths_value = spec.get("paths")
        if not isinstance(paths_value, dict):
            return {}

        operations: dict[str, _OperationMeta] = {}
        for path_key, path_item_value in paths_value.items():
            if not isinstance(path_item_value, dict):
                continue

            path_item = cast(JSONDict, path_item_value)
            path_level_params = self._extract_params(path_item.get("parameters"))
            for method_key, op_value in path_item.items():
                method = method_key.lower()
                if method not in _CONTAINER_METHODS or not isinstance(op_value, dict):
                    continue

                operation = cast(JSONDict, op_value)
                op_params = self._extract_params(operation.get("parameters"))
                merged_params = self._merge_params(path_level_params, op_params)
                path_params = [param.name for param in merged_params if param.location == "path"]
                header_params = [param.name for param in merged_params if param.location == "header"]
                endpoint_name = self._endpoint_name(method, path_key, operation)
                operations[endpoint_name] = _OperationMeta(
                    endpoint_name=endpoint_name,
                    method=method,
                    path_template=path_key,
                    path_params=path_params,
                    header_params=header_params,
                )

        return operations

    def _merge_params(self, base: list[_ParamMeta], extra: list[_ParamMeta]) -> list[_ParamMeta]:
        result: list[_ParamMeta] = []
        seen: set[tuple[str, str]] = set()
        for param in base + extra:
            key = (param.name, param.location)
            if key in seen:
                continue
            seen.add(key)
            result.append(param)
        return result

    def _extract_params(self, raw_params: JSONValue) -> list[_ParamMeta]:
        if not isinstance(raw_params, list):
            return []

        result: list[_ParamMeta] = []
        for item in raw_params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            location = item.get("in")
            if isinstance(name, str) and isinstance(location, str):
                result.append(_ParamMeta(name=name, location=location))
        return result

    def _endpoint_name(self, method: str, path_value: str, operation: JSONDict) -> str:
        operation_id = operation.get("operationId")
        if isinstance(operation_id, str) and operation_id.strip():
            return self._sanitize_identifier(operation_id)

        parts = [method]
        for part in path_value.strip("/").split("/"):
            if not part:
                continue
            if part.startswith("{") and part.endswith("}"):
                parts.append(f"by_{part[1:-1]}")
            else:
                parts.append(part.replace("-", "_"))
        return self._sanitize_identifier("_".join(parts))

    def _sanitize_identifier(self, value: str) -> str:
        name = re.sub(r"[^0-9a-zA-Z_]", "_", value)
        name = re.sub(r"_+", "_", name).strip("_")
        if not name:
            return "endpoint"
        if name[0].isdigit():
            return f"endpoint_{name}"
        return name

    def _load_spec(self, spec_path: str) -> JSONDict:
        raw_text = Path(spec_path).read_text(encoding="utf-8")
        suffix = Path(spec_path).suffix.lower()
        if suffix == ".json":
            parsed_obj = cast(object, json.loads(raw_text))
        else:
            parsed_obj = self._parse_yaml(raw_text)
        if not isinstance(parsed_obj, dict):
            raise ValueError("OpenAPI spec root must be an object")
        return cast(JSONDict, parsed_obj)

    def _parse_yaml(self, raw_text: str) -> JSONDict:
        lines = raw_text.splitlines()
        root: JSONDict = {}
        stack: list[tuple[int, _Container]] = [(-1, root)]
        index = 0

        while index < len(lines):
            raw_line = lines[index]
            index += 1
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue

            indent = len(raw_line) - len(raw_line.lstrip(" "))
            line = raw_line.strip()
            while len(stack) > 1 and indent <= stack[-1][0]:
                _ = stack.pop()
            parent = stack[-1][1]

            if line.startswith("- "):
                if not isinstance(parent, list):
                    raise ValueError(f"Invalid YAML list placement: {line}")
                item_text = line[2:].strip()
                if not item_text:
                    new_item: JSONDict = {}
                    parent.append(new_item)
                    stack.append((indent, new_item))
                    continue
                if ":" in item_text and not item_text.startswith("{"):
                    key, value = self._split_key_value(item_text)
                    entry: JSONDict = {key: self._parse_scalar(value)}
                    parent.append(entry)
                    stack.append((indent, entry))
                    continue
                parent.append(self._parse_scalar(item_text))
                continue

            key, value = self._split_key_value(line)
            target: JSONDict
            if isinstance(parent, list):
                if not parent or not isinstance(parent[-1], dict):
                    parent.append({})
                last_item = parent[-1]
                if not isinstance(last_item, dict):
                    raise ValueError("Expected mapping item inside YAML list")
                target = cast(JSONDict, last_item)
            else:
                target = parent

            if value == "":
                container = self._detect_container(lines, index, indent)
                target[key] = container
                stack.append((indent, container))
            else:
                target[key] = self._parse_scalar(value)

        return root

    def _split_key_value(self, line: str) -> tuple[str, str]:
        if ":" not in line:
            raise ValueError(f"Invalid YAML line: {line}")
        key, value = line.split(":", 1)
        return key.strip(), value.strip()

    def _detect_container(self, lines: list[str], start_idx: int, current_indent: int) -> _Container:
        idx = start_idx
        while idx < len(lines):
            candidate = lines[idx]
            idx += 1
            if not candidate.strip() or candidate.lstrip().startswith("#"):
                continue
            indent = len(candidate) - len(candidate.lstrip(" "))
            if indent <= current_indent:
                return {}
            if candidate.strip().startswith("- "):
                return []
            return {}
        return {}

    def _parse_scalar(self, value: str) -> JSONValue:
        if value in {"", "null", "~"}:
            return None
        if value in {"true", "True"}:
            return True
        if value in {"false", "False"}:
            return False
        if value.startswith("{") and value.endswith("}"):
            return self._parse_inline_map(value[1:-1].strip())
        if value.startswith("[") and value.endswith("]"):
            return self._parse_inline_list(value[1:-1].strip())
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if re.fullmatch(r"-?\d+\.\d+", value):
            return float(value)
        return value

    def _parse_inline_map(self, content: str) -> JSONDict:
        if not content:
            return {}
        result: JSONDict = {}
        for item in self._split_inline_items(content):
            key, value = self._split_key_value(item)
            result[key] = self._parse_scalar(value)
        return result

    def _parse_inline_list(self, content: str) -> list[JSONValue]:
        if not content:
            return []
        return [self._parse_scalar(item) for item in self._split_inline_items(content)]

    def _split_inline_items(self, text: str) -> list[str]:
        items: list[str] = []
        current: list[str] = []
        depth = 0
        quote: str | None = None

        for char in text:
            if quote is not None:
                current.append(char)
                if char == quote:
                    quote = None
                continue
            if char in {'"', "'"}:
                quote = char
                current.append(char)
                continue
            if char in "[{":
                depth += 1
                current.append(char)
                continue
            if char in "]}":
                depth -= 1
                current.append(char)
                continue
            if char == "," and depth == 0:
                item = "".join(current).strip()
                if item:
                    items.append(item)
                current = []
                continue
            current.append(char)

        tail = "".join(current).strip()
        if tail:
            items.append(tail)
        return items

    def _map_http_error(self, err: HTTPError) -> Exception:
        if err.code == 404:
            return FileNotFoundError(f"HTTP 404: {err.reason}")
        if err.code == 400:
            return ValueError(f"HTTP 400: {err.reason}")
        if err.code >= 500:
            return RuntimeError(f"HTTP {err.code}: {err.reason}")
        return RuntimeError(f"HTTP {err.code}: {err.reason}")


@dataclass
class _ParamMeta:
    name: str
    location: str


@dataclass
class _OperationMeta:
    endpoint_name: str
    method: str
    path_template: str
    path_params: list[str]
    header_params: list[str]


class _HTTPResponse(Protocol):
    def __enter__(self) -> "_HTTPResponse": ...
    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool | None: ...
    def read(self) -> bytes: ...


_Container: TypeAlias = JSONDict | list[JSONValue]
