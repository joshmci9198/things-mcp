"""Thin wrapper: mounts the Things MCP server + simple REST routes on one port."""

import hmac
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

# Add things-mcp source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import things
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

from things_mcp.server import mcp
from things_mcp import url_scheme


# --- Authentication ---

# Only the /mcp mount requires `Authorization: Bearer <token>`, where the token
# comes from THINGS_MCP_TOKEN (start.sh loads it from .env, which is gitignored).
# /api/health/auth is also gated, purely so a caller can check that its token
# is valid without touching task data.
#
# The REST routes under /api are NOT token-gated. Their consumers are
# automations on other tailnet hosts that reach this server only through
# `tailscale serve`, and Tailscale device identity is the access control there,
# as it was before the token existed. Be clear about what that means: the REST
# routes grant the same full read/write access to the Things database as /mcp,
# so the token does not keep a tailnet device out of the database -- it only
# gates the MCP mount. The real boundary is the loopback bind plus the tailnet.
# If a device you don't trust ever joins the tailnet, gate /api again (add
# "/api" to PROTECTED_PREFIXES) before worrying about anything else.
#
# There is deliberately no "no token configured means no auth" mode for the
# gated paths. A silent insecure fallback is precisely how this server
# previously ended up bound to 0.0.0.0 and reachable from the whole LAN.
# Misconfiguration fails closed.
PROTECTED_PREFIXES = ("/mcp",)
PROTECTED_PATHS = frozenset({"/api/health/auth"})


def _requires_token(path):
    if path in PROTECTED_PATHS:
        return True
    return any(path == prefix or path.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)

def _expected_token():
    return (os.environ.get("THINGS_MCP_TOKEN") or "").strip()


class BearerAuthMiddleware:
    """Reject requests to token-gated paths without a valid bearer token.

    Written as raw ASGI rather than BaseHTTPMiddleware because the MCP mount
    streams responses (SSE), and BaseHTTPMiddleware buffers them.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _requires_token(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        expected = _expected_token()
        if not expected:
            await self._deny(send, 503, "server misconfigured: THINGS_MCP_TOKEN is not set")
            return

        presented = b""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                presented = value
                break

        # Compared as bytes so a header with undecodable input cannot raise.
        scheme, _, credential = presented.partition(b" ")
        if scheme.lower() != b"bearer" or not hmac.compare_digest(
            credential.strip(), expected.encode("utf-8")
        ):
            await self._deny(send, 401, "unauthorized")
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _deny(send, status, detail):
        body = json.dumps({"error": detail}).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        if status == 401:
            headers.append((b"www-authenticate", b'Bearer realm="things-mcp"'))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


# --- REST routes ---

async def api_health(request: Request):
    return JSONResponse({"ok": True})


async def api_health_auth(request: Request):
    # Same body as /api/health, but listed in PROTECTED_PATHS: reaching it
    # proves the caller's bearer token is valid. Lets an MCP client check its
    # token with a plain curl, without touching task data.
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


# Things writes GUI-originated changes (a to-do checked off by hand) to SQLite
# on an internal timer, measured at ~8 s. Writes made via the URL scheme or
# AppleScript land immediately and never needed help. Waiting longer than the
# timer before reading closes the window where a just-finished to-do is
# missing from the report.
THINGS_FLUSH_WAIT_SECONDS = 10.0


def nudge_things():
    """Give Things time to flush pending GUI edits to SQLite before we read it.

    History, because both previous versions of this function silently did
    nothing on the homeserver and it took a day to notice:

    * Focus switching (`open -a Finder` / `open -a Things3`) — a background
      process cannot change the frontmost app while the screen is locked, and
      the homeserver's screen is always locked. Returned success, did nothing.
    * AppleScript (`osascript ... count to dos`) — the service runs under
      launchd with /bin/bash as its responsible process, which has no TCC
      Automation grant for Things and no desktop on which to ask for one. The
      Apple event hung until it timed out (-1712), and killing the hung
      osascript left Things unresponsive to events for a minute afterwards.

    Neither the URL scheme nor AppleScript can stand in for a GUI edit when
    testing this: both flush in under a second. Only a real click in the app
    exercises the timer.

    What actually made the timer reliable was opting Things out of App Nap
    (`NSAppSleepDisabled`, see README → Host hardening); while napping and
    occluded, the ~8 s flush stretched to minutes. With that set, waiting out
    the interval is the whole job, and it needs no permissions and no focus.
    """
    time.sleep(THINGS_FLUSH_WAIT_SECONDS)


_SINCE_UNITS = {"d": 1, "w": 7, "m": 30, "y": 365}


def since_cutoff(since):
    """Convert a relative offset ('1w', '26w', '7d') to a cutoff datetime.

    Returns None if the string isn't a recognised offset.
    """
    match = re.fullmatch(r"(\d+)([dwmy])", since.strip().lower())
    if not match:
        return None
    count, unit = int(match.group(1)), match.group(2)
    return datetime.now() - timedelta(days=count * _SINCE_UNITS[unit])


def completed_since(cutoff):
    """Completed tasks whose COMPLETION date falls within the window.

    Deliberately does not use things.completed(last=...): that filters on
    TASK.creationDate, so a to-do created three weeks ago and checked off
    yesterday is absent from a ?since=1w query. Roughly a third of the
    completed to-dos in this database span a week or more between creation
    and completion, and the weekly report is exactly the case where that
    matters. Filter on stop_date instead, which is when it was actually done.
    """
    results = []
    for task in things.completed() or []:
        stop = task.get("stop_date")
        if not stop:
            continue
        try:
            stopped = datetime.fromisoformat(str(stop).split(".")[0])
        except ValueError:
            continue
        if stopped >= cutoff:
            results.append(task)
    return results


async def api_ssnc_completed(request: Request):
    since = request.query_params.get("since")
    if not since:
        return JSONResponse({"error": "since parameter required (e.g. ?since=7d or ?since=1w)"}, status_code=400)
    cutoff = since_cutoff(since)
    if cutoff is None:
        return JSONResponse({"error": f"invalid since value {since!r}; expected a count and unit like 7d, 1w, 3m or 1y"}, status_code=400)
    nudge_things()
    results = []
    for todo in completed_since(cutoff):
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
    middleware=[Middleware(BearerAuthMiddleware)],
    routes=[
        # REST API endpoints (for automations). No bearer token here: tailnet-only.
        Route("/api/health", api_health),
        Route("/api/health/auth", api_health_auth),
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
        # MCP protocol endpoint (for Claude / agents) — must be last.
        # Bearer token required (see PROTECTED_PREFIXES).
        Mount("/mcp", mcp_app),
    ],
)

if __name__ == "__main__":
    if not _expected_token():
        sys.exit(
            "THINGS_MCP_TOKEN is not set, refusing to start.\n"
            "Generate a token and store it outside version control:\n"
            "  printf 'THINGS_MCP_TOKEN=%s\\n' \"$(openssl rand -hex 32)\" >> .env\n"
            "start.sh loads .env automatically."
        )
    host = os.environ.get("THINGS_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("THINGS_MCP_PORT", "3400"))
    uvicorn.run(app, host=host, port=port)
