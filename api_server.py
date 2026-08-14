"""Thin wrapper: mounts the Things MCP server + simple REST routes on one port."""

import os
import subprocess
import sys
import time

# Add things-mcp source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import things
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

from things_mcp.server import mcp
from things_mcp import url_scheme


# --- REST routes ---

async def api_health(request: Request):
    return JSONResponse({"ok": True})


async def api_inbox(request: Request):
    return JSONResponse([t for t in (things.inbox() or [])])


async def api_today(request: Request):
    return JSONResponse([t for t in (things.today() or [])])


async def api_upcoming(request: Request):
    return JSONResponse([t for t in (things.upcoming() or [])])


async def api_anytime(request: Request):
    return JSONResponse([t for t in (things.anytime() or [])])


async def api_someday(request: Request):
    return JSONResponse([t for t in (things.someday() or [])])


async def api_projects(request: Request):
    return JSONResponse([p for p in (things.projects() or [])])


async def api_areas(request: Request):
    return JSONResponse([a for a in (things.areas() or [])])


async def api_tags(request: Request):
    return JSONResponse([t for t in (things.tags() or [])])


async def api_todos(request: Request):
    project = request.query_params.get("project")
    tag = request.query_params.get("tag")
    kwargs = {}
    if project:
        kwargs["project"] = project
    if tag:
        kwargs["tag"] = tag
    return JSONResponse([t for t in (things.todos(**kwargs) or [])])


async def api_search(request: Request):
    query = request.query_params.get("q", "")
    if not query:
        return JSONResponse({"error": "q parameter required"}, status_code=400)
    return JSONResponse([t for t in (things.search(query) or [])])


async def api_get(request: Request):
    uuid = request.path_params["uuid"]
    item = things.get(uuid)
    if item is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(item)


async def api_add_todo(request: Request):
    body = await request.json()
    title = body.get("title")
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)
    url = url_scheme.add_todo(
        title=title,
        notes=body.get("notes"),
        when=body.get("when"),
        deadline=body.get("deadline"),
        tags=body.get("tags"),
        checklist_items=body.get("checklist_items"),
        list_id=body.get("list_id"),
        list_title=body.get("list_title"),
        heading=body.get("heading"),
        heading_id=body.get("heading_id"),
    )
    url_scheme.execute_url(url)
    return JSONResponse({"ok": True, "title": title})


async def api_add_project(request: Request):
    body = await request.json()
    title = body.get("title")
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)
    url = url_scheme.add_project(
        title=title,
        notes=body.get("notes"),
        when=body.get("when"),
        deadline=body.get("deadline"),
        tags=body.get("tags"),
        area_id=body.get("area_id"),
        area_title=body.get("area_title"),
        todos=body.get("todos"),
    )
    url_scheme.execute_url(url)
    return JSONResponse({"ok": True, "title": title})


async def api_update_todo(request: Request):
    body = await request.json()
    todo_id = body.get("id")
    if not todo_id:
        return JSONResponse({"error": "id is required"}, status_code=400)
    url = url_scheme.update_todo(
        id=todo_id,
        title=body.get("title"),
        notes=body.get("notes"),
        when=body.get("when"),
        deadline=body.get("deadline"),
        tags=body.get("tags"),
        completed=body.get("completed"),
        canceled=body.get("canceled"),
        list=body.get("list"),
        list_id=body.get("list_id"),
        heading=body.get("heading"),
        heading_id=body.get("heading_id"),
    )
    url_scheme.execute_url(url)
    return JSONResponse({"ok": True, "id": todo_id})


def nudge_things():
    """Switch focus to force Things to flush DB."""
    try:
        subprocess.run(["open", "-a", "Finder"], timeout=3)
        time.sleep(1)
        subprocess.run(["open", "-a", "Things3"], timeout=3)
        time.sleep(1)
    except Exception:
        pass


async def api_ssnc_completed(request: Request):
    since = request.query_params.get("since")
    if not since:
        return JSONResponse({"error": "since parameter required (e.g. ?since=7d or ?since=2026-03-20)"}, status_code=400)
    nudge_things()
    completed = things.completed(last=since) or []
    results = []
    for todo in completed:
        project_title = todo.get("project_title", "") or ""
        if project_title.startswith("SSNC"):
            results.append(todo)
    return JSONResponse(results)


async def api_update_project(request: Request):
    body = await request.json()
    project_id = body.get("id")
    if not project_id:
        return JSONResponse({"error": "id is required"}, status_code=400)
    url = url_scheme.update_project(
        id=project_id,
        title=body.get("title"),
        notes=body.get("notes"),
        when=body.get("when"),
        deadline=body.get("deadline"),
        tags=body.get("tags"),
        completed=body.get("completed"),
        canceled=body.get("canceled"),
    )
    url_scheme.execute_url(url)
    return JSONResponse({"ok": True, "id": project_id})


# --- Build combined app ---

mcp_app = mcp.http_app(path="/")

app = Starlette(
    lifespan=mcp_app.lifespan,
    routes=[
        # REST API endpoints (for automations)
        Route("/api/health", api_health),
        Route("/api/inbox", api_inbox),
        Route("/api/today", api_today),
        Route("/api/upcoming", api_upcoming),
        Route("/api/anytime", api_anytime),
        Route("/api/someday", api_someday),
        Route("/api/projects", api_projects),
        Route("/api/areas", api_areas),
        Route("/api/tags", api_tags),
        Route("/api/todos", api_todos),
        Route("/api/search", api_search),
        Route("/api/get/{uuid}", api_get),
        Route("/api/add/todo", api_add_todo, methods=["POST"]),
        Route("/api/add/project", api_add_project, methods=["POST"]),
        Route("/api/ssnc/completed", api_ssnc_completed),
        Route("/api/update/todo", api_update_todo, methods=["POST"]),
        Route("/api/update/project", api_update_project, methods=["POST"]),
        # MCP protocol endpoint (for Claude / agents) — must be last
        Mount("/mcp", mcp_app),
    ],
)

if __name__ == "__main__":
    host = os.environ.get("THINGS_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("THINGS_MCP_PORT", "3400"))
    uvicorn.run(app, host=host, port=port)
