"""Tasks tool pack: create and list Buster tasks."""

from __future__ import annotations

from pydantic import BaseModel

from buster.agent import get_task_store
from buster.tools.registry import tool


class ListArgs(BaseModel):
    limit: int = 20


class TaskListResult(BaseModel):
    tasks: list[dict]


@tool(id="tasks.list", description="List recent Buster tasks.", pack="tasks", permission="read")
async def tasks_list(args: ListArgs) -> TaskListResult:
    tasks = get_task_store().list(limit=args.limit)
    return TaskListResult(tasks=[t.model_dump() for t in tasks])
