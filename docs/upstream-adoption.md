# Upstream adoption log

Decisions about what to take from upstream, and — more usefully — what we
decided *not* to take and why. Without this the same questions get re-litigated
at every sync, and "we already thought about that" is not recoverable from a
git log.

Updated as part of the `sync-upstream` skill, step 2.5.

## How upstream changes reach each surface

Not all upstream work propagates. Which file a change lands in determines
whether it reaches users at all:

| Upstream change in | `/mcp` | `/api/*` | Why |
|---|---|---|---|
| `things.py` | yes | yes | both read through it |
| `src/things_mcp/url_scheme.py` | yes | yes | REST write routes call it directly |
| `src/things_mcp/formatters.py` | yes | no | REST returns raw dicts, not formatted text |
| `src/things_mcp/server.py` | yes | **no** | REST routes are hand-written in `api_server.py` and bypass the MCP tools entirely |

**The last row is the one that bites.** A new MCP tool appears on `/mcp` for
free after a merge and never appears on `/api/*`. Nothing errors; the endpoint
just doesn't exist. Every new upstream tool is therefore a decision, not an
automatic win.

## Triage questions

For each upstream change, ask in order:

1. **Does it fix something we call?** (`things.py` / `url_scheme.py`) — take it,
   no discussion needed; it arrives with the merge.
2. **Is it a new MCP tool?** — it lands on `/mcp` automatically. The question is
   only whether it *also* warrants a REST endpoint.
3. **Would an automation want it over HTTP?** REST exists for consumers that
   don't speak MCP. If no automation would call it, skip it — an unused endpoint
   is surface area to maintain, not a feature.
4. **Does it change a response shape we've promised?** `/api/ssnc/completed` is a
   stable contract consumed by automation-backend. Shape changes need a
   conversation, not a merge.

Record the answer below either way. "Considered and declined" is as valuable as
"adopted" — more so, because it's the one that gets forgotten.

## Decisions

### Pending — from v0.8.0 / v0.8.1, not yet merged

| Change | Surface | Decision | Notes |
|---|---|---|---|
| URL encoding: slashes truncate (#47) | `url_scheme.py` | **Take** | Arrives with merge. Affects all four REST write routes today; a title like `Example 2/13` is silently truncated. |
| `get_today` None-safe sort (#43) | `server.py` + upstream `things.today()` | **Take** | The crash is in `things.today()`, which `/api/today` calls directly. |
| `get_logbook` completion-date filter (#46) | `server.py` | **Already fixed locally** | Same bug, fixed independently in `completed_since()`. On merge, check whether upstream's version supersedes ours or duplicates it. |
| `bulk_update_todos` | `server.py` | **Undecided** | Strongest REST candidate: batch weekly-review moves are exactly an automation job. Needs `THINGS_AUTH_TOKEN`. |
| `get_tag_usage` | `server.py` | **Undecided** | Useful interactively via `/mcp`. No known automation wants it over HTTP. |
| `add_area` / `update_area` | `server.py` | **Undecided** | Introduces AppleScript as a third write mechanism alongside SQLite reads and URL-scheme writes. Worth knowing before adopting. No `delete_area` upstream, deliberately — deleting an area deletes every project inside it. |
| Pagination (`limit`/`offset`) | `server.py` | **Undecided** | REST routes return whole lists today. Only matters if a consumer starts choking on volume. |
| Structured responses | `server.py` | **N/A for REST** | REST already returns raw JSON dicts. This is MCP-side only. |

### Settled

| Change | Decision | Why |
|---|---|---|
| FastMCP 3.x migration | **Deferred, blocking the v0.8.1 merge** | `api_server.py` calls `mcp.http_app(path="/")`, which upstream doesn't use, so 3.x compatibility is untested. Treat as a migration with its own branch and a real restart test, not part of a routine sync. |
| Someday project filtering | **Already upstream** | Shared history, not a local change. A fresh clone of hald has it. |
| Recurrence creation (#42), standalone headings (#10) | **Not possible** | Upstream documented these as Things API limits: `repetition rule` is read-only, and headings can only be created in a project's initial `create`. Don't re-investigate. |
