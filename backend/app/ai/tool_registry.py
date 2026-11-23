from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from time import perf_counter
from typing import Callable, Literal

from fastapi import HTTPException


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    allowed_roles: tuple[str, ...]
    handler: Callable
    input_schema: dict
    kind: Literal["read", "approval_write"]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        allowed_roles: tuple[str, ...],
        handler: Callable,
        input_schema: dict | None = None,
        kind: Literal["read", "approval_write"] = "read",
    ) -> None:
        self._tools[name] = Tool(
            name=name,
            description=description,
            allowed_roles=allowed_roles,
            handler=handler,
            input_schema=input_schema or {
                "type": "object",
                "properties": {},
                "required": [],
            },
            kind=kind,
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    def validate_parameters(self, tool: Tool, parameters: dict) -> str | None:
        if not isinstance(parameters, dict):
            return "Tool arguments must be a JSON object"

        allowed = set(tool.input_schema.get("properties", {}).keys())
        unknown = set(parameters) - allowed
        if unknown:
            return f"Unexpected tool arguments: {', '.join(sorted(unknown))}"

        missing = [
            name
            for name in tool.input_schema.get("required", [])
            if name not in parameters
        ]
        if missing:
            return f"Missing required tool arguments: {', '.join(missing)}"

        for name, value in parameters.items():
            specification = tool.input_schema["properties"][name]
            expected = specification.get("type")
            valid = (
                (expected == "string" and isinstance(value, str))
                or (
                    expected == "integer"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                )
                or (
                    expected == "number"
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                )
                or (expected == "boolean" and isinstance(value, bool))
                or (expected == "array" and isinstance(value, list))
            )
            if not valid:
                return f"Invalid type for tool argument '{name}'"
        return None

    def execute(
        self,
        name: str,
        user,
        db,
        parameters: dict,
    ) -> tuple[dict, dict]:
        tool = self._tools.get(name)
        if tool is None:
            return (
                {"status": "error", "message": f"Unknown tool: {name}"},
                {"tool": name, "status": "error", "duration_ms": 0},
            )

        if user.role not in tool.allowed_roles:
            return (
                {
                    "status": "error",
                    "message": "You do not have permission to use this tool.",
                },
                {"tool": name, "status": "error", "duration_ms": 0},
            )

        validation_error = self.validate_parameters(tool, parameters)
        if validation_error:
            return (
                {"status": "error", "message": validation_error},
                {"tool": name, "status": "error", "duration_ms": 0},
            )

        started = perf_counter()
        attempts = 2 if tool.kind == "read" else 1

        for attempt in range(attempts):
            try:
                executor = ThreadPoolExecutor(max_workers=1)
                future = executor.submit(
                    tool.handler,
                    db=db,
                    user=user,
                    **parameters,
                )
                try:
                    result = future.result(timeout=5.0)
                except FuturesTimeout:
                    future.cancel()
                    raise TimeoutError
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)

                if not isinstance(result, dict):
                    raise ValueError("Tool result must be a dictionary")
                if "status" not in result:
                    result = {"status": "success", **result}
                if result["status"] not in {
                    "success",
                    "error",
                    "clarification_required",
                }:
                    raise ValueError("Tool returned an invalid status")

                trace_status = (
                    "success"
                    if result["status"] == "success"
                    else "error"
                )
                return result, {
                    "tool": name,
                    "status": trace_status,
                    "duration_ms": round(
                        (perf_counter() - started) * 1000,
                        2,
                    ),
                }
            except TimeoutError:
                if attempt + 1 < attempts:
                    continue
                return (
                    {"status": "error", "message": "The tool timed out."},
                    {
                        "tool": name,
                        "status": "error",
                        "duration_ms": round(
                            (perf_counter() - started) * 1000,
                            2,
                        ),
                    },
                )
            except HTTPException as exc:
                return (
                    {"status": "error", "message": exc.detail},
                    {
                        "tool": name,
                        "status": "error",
                        "duration_ms": round(
                            (perf_counter() - started) * 1000,
                            2,
                        ),
                    },
                )
            except Exception:
                if attempt + 1 < attempts:
                    continue
                return (
                    {
                        "status": "error",
                        "message": "The tool could not complete the requested operation.",
                    },
                    {
                        "tool": name,
                        "status": "error",
                        "duration_ms": round(
                            (perf_counter() - started) * 1000,
                            2,
                        ),
                    },
                )
