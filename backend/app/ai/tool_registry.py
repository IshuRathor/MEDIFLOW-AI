from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from time import perf_counter
from typing import Callable, Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker
from app.database.db import SessionLocal


_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ai-tool")


@dataclass(frozen=True)
class _ToolUserContext:
    """Detached authorization context safe to pass to a worker thread."""

    id: int | None
    role: str


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    allowed_roles: tuple[str, ...]
    handler: Callable
    input_schema: dict
    kind: Literal["read", "approval_write"]


class ToolRegistry:
    def __init__(
        self,
        session_factory: Callable | None = None,
        timeout_seconds: float = 5.0,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._session_factory = session_factory or SessionLocal
        self._custom_session_factory = session_factory is not None
        self._timeout_seconds = timeout_seconds
        self._executor = executor or _TOOL_EXECUTOR

    def _session_factory_for(self, request_db) -> Callable:
        # Use the request's configured engine (including test dependency
        # overrides), while creating an independent Session for the worker.
        if not self._custom_session_factory and isinstance(request_db, Session):
            return sessionmaker(
                bind=request_db.get_bind(),
                autocommit=False,
                autoflush=False,
            )
        return self._session_factory

    def _invoke(
        self,
        tool: Tool,
        user: _ToolUserContext,
        parameters: dict,
        session_factory: Callable,
    ) -> dict:
        """Run one handler with a thread-owned session and bounded transaction."""
        session = session_factory()
        try:
            result = tool.handler(db=session, user=user, **parameters)
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

            if result["status"] == "success":
                session.commit()
            else:
                session.rollback()
            return result
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

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
        # Keep db in the public signature for callers, but never pass this
        # request-scoped session into a worker thread.
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
        worker_user = _ToolUserContext(
            id=getattr(user, "id", None),
            role=user.role,
        )
        worker_session_factory = self._session_factory_for(db)

        for attempt in range(attempts):
            try:
                future = self._executor.submit(
                    self._invoke,
                    tool,
                    worker_user,
                    parameters,
                    worker_session_factory,
                )
                try:
                    result = future.result(timeout=self._timeout_seconds)
                except FuturesTimeout:
                    # cancel() only prevents work that has not started. A running
                    # handler owns its session until it returns and _invoke closes it.
                    cancelled_before_start = future.cancel()
                    message = "The tool timed out."
                    outcome = None
                    if tool.kind == "approval_write":
                        if cancelled_before_start:
                            message = "The operation did not start before timing out. You can retry."
                        else:
                            message = (
                                "The operation timed out and may still be processing. "
                                "Its outcome is unknown; check its status before retrying."
                            )
                            outcome = "unknown"
                    timeout_result = {"status": "error", "message": message}
                    if outcome:
                        timeout_result["outcome"] = outcome
                    return timeout_result, {
                        "tool": name,
                        "status": "error",
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }

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
