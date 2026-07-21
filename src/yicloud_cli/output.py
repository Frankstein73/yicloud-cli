"""Output formatting shared by all CLI commands."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, TextIO

import click

from .errors import redact_sensitive


_SENSITIVE_FIELD = re.compile(
    r"(?i)(access[_-]?key|secret(?:[_-]?(?:access[_-]?)?key)?|token|password|credential)"
)


class OutputFormat(str, Enum):
    """Supported command output formats."""

    HUMAN = "human"
    JSON = "json"


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class OutputWriter:
    """Render successful command results in a stable format."""

    def __init__(
        self,
        output_format: OutputFormat,
        stream: TextIO | None = None,
        environ: Mapping[str, str] | None = None,
    ):
        self.output_format = output_format
        self.stream = stream
        self.environ = {} if environ is None else environ

    def write(self, value: Any) -> None:
        if value is None:
            return
        value = self._safe_value(value)
        if self.output_format is OutputFormat.JSON:
            click.echo(
                json.dumps(value, default=_json_default, ensure_ascii=False, indent=2),
                file=self.stream,
            )
            return
        click.echo(self._human(value), file=self.stream)

    def _safe_value(self, value: Any) -> Any:
        if is_dataclass(value) and not isinstance(value, type):
            value = asdict(value)
        elif hasattr(value, "model_dump"):
            value = value.model_dump(mode="python")
        elif hasattr(value, "to_dict"):
            value = value.to_dict()

        if isinstance(value, Mapping):
            return {
                key: "[REDACTED]"
                if _SENSITIVE_FIELD.search(str(key))
                else self._safe_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._safe_value(item) for item in value]
        if isinstance(value, str):
            return redact_sensitive(value, self.environ)
        return value

    def _human(self, value: Any) -> str:
        if is_dataclass(value) and not isinstance(value, type):
            value = asdict(value)
        elif hasattr(value, "model_dump"):
            value = value.model_dump(mode="python")
        elif hasattr(value, "to_dict"):
            value = value.to_dict()

        if isinstance(value, dict):
            return "\n".join(
                f"{key}: {self._cell(item)}" for key, item in value.items()
            )
        if isinstance(value, (list, tuple)):
            return self._human_list(value)
        return str(value)

    def _human_list(self, values: list[Any] | tuple[Any, ...]) -> str:
        if not values:
            return "No results."
        if all(isinstance(item, dict) for item in values):
            columns = list(dict.fromkeys(key for item in values for key in item))
            rows = [
                [self._cell(item.get(column, "")) for column in columns]
                for item in values
            ]
            widths = [
                max(len(str(column)), *(len(row[index]) for row in rows))
                for index, column in enumerate(columns)
            ]
            header = "  ".join(
                str(column).ljust(widths[index]) for index, column in enumerate(columns)
            )
            divider = "  ".join("-" * width for width in widths)
            body = [
                "  ".join(
                    cell.ljust(widths[index]) for index, cell in enumerate(row)
                ).rstrip()
                for row in rows
            ]
            return "\n".join([header, divider, *body])
        return "\n".join(f"- {self._cell(item)}" for item in values)

    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(
                value, default=_json_default, ensure_ascii=False, separators=(",", ":")
            )
        return str(value)
