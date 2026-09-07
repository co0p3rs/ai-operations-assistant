from __future__ import annotations

from typing import Any

from app.providers.data import WORK_ITEMS
from app.providers.protocol import DataSource


class WorkProvider:
    name = DataSource.WORK

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "work_open_tasks",
                "description": "Open internal tasks, optionally filtered by assignee.",
                "parameters": {
                    "type": "object",
                    "properties": {"assignee": {"type": "string"}},
                },
            }
        ]

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool != "work_open_tasks":
            return {"ok": False, "error": f"unknown tool {tool}"}
        assignee = str(arguments.get("assignee") or "")
        rows = [
            row
            for row in WORK_ITEMS
            if row["status"] == "open"
            and (not assignee or assignee.lower() in str(row["assignee"]).lower())
        ]
        return {"ok": True, "tasks": rows}
