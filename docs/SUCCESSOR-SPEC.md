# Successor spec: a self-hosted task backend to replace Things 3

**Audience:** the Claude Code session on the Linux `homeserver` (100.115.54.2 on the tailnet) that will build this. It is written to be self-contained; everything you need to know about Things and about the current deployment is in here or in the two files it names.

**Status of this document:** derived from the live Things database and from the code in `joshmci9198/things-mcp` (branch `wired`) on 2026-08-28. Every claim about how Things encodes data was checked against real rows and real generated instances, not guessed.

---

## 1. Why this exists

- The Things 3 task database currently lives on `mac-homeserver`, a 2016 MacBook Pro on macOS 12.7.6 running Things **3.22.10**, exposed to the tailnet through the API in `things-mcp-wired` (`api_server.py` REST routes + an MCP server on `/mcp`, port 3400, bearer-token auth).
- Things **3.23** (2026-08-19) requires macOS 13.3. The 2016 MacBook Pro cannot run macOS 13 through any supported path.
- On **2026-08-26 05:00 PT** Things Cloud stopped syncing with the 3.22.10 client (last successful sync in its own metadata; two local changes have sat in its outbound queue since; the app holds no connection to the cloud). The API is serving a snapshot frozen at that moment. The user's laptop and phone run 3.23 and are current.
- Decision: **replace Things with a self-hosted backend on the Linux homeserver.** The user will supply their own Mac and iPhone clients. Things' own apps cannot be pointed at a third-party server (private protocol), so this is a replacement, not a re-hosting.

## 2. Deliverables, in order

1. **Import** the export file (§4) into a new database with the model in §5. Verify counts (§10.3).
2. **Recurrence engine** with the semantics in §7, including the daily materialization job. This is the only part with real difficulty; do it with tests before any UI.
3. **REST API** matching §8.1 route-for-route, and **MCP server** matching §8.2 tool-for-tool, both behind the same bearer-token middleware as today (§8.3). Existing consumers must keep working by changing only a hostname and a token.
4. **Deployment** on the homeserver (§11): systemd, `tailscale serve`, backups, timezone.
5. Cut over consumers (§9) and retire the Mac service.

Everything client-side (web UI, iOS Shortcuts, native apps) is out of scope for this spec and for the first pass. Build the API to be pleasant to consume from a client the user writes later: JSON everywhere, stable IDs, no server-rendered HTML.

### Non-goals

- **No sync engine.** The server is the single source of truth; clients are online. Offline editing with conflict resolution is the hard problem Things spent a decade on. Do not build it.
- No Things Cloud compatibility, no import from anything except the export in §4.
- No attempt to reproduce Things' UI, keyboard shortcuts, or its "natural language date" parsing beyond the fixed keywords in §8.4.
- Do not re-implement `things.py`; the model in §5 is simpler than Things' schema on purpose.

## 3. Inputs you will be given

| Input | What it is |
|---|---|
| `things-export.json` | Complete decoded snapshot of the Things DB, produced by `scripts/export_things.py` from `things-mcp-wired` **run on the user's laptop** (the current copy; the homeserver copy is stale as of 2026-08-26). Format in §4. |
| `api_server.py` from `things-mcp-wired` | The REST routes and auth middleware to reproduce. ~370 lines, read it once. |
| `src/things_mcp/server.py` from the same repo | The 26 MCP tools to reproduce. Signatures are listed in §8.2 so you may not need it. |
| A fresh bearer token | Generate with `openssl rand -hex 32`. Do **not** reuse the old Mac token. |

## 4. Export file format (`things-export/1`)

Top level:

```json
{
  "export": {
    "format": "things-export/1",
    "generated_at": "2026-08-28T18:52:10-07:00",
    "source_db": "...main.sqlite",
    "include_trashed": false,
    "counts": {"to-do": 1158, "project": 46, "heading": 212, "repeat_template": 365,
               "trashed": 0, "areas": 3, "tags": 13, "checklist_items": 1762},
    "encodings": { "...documentation of enum values..." }
  },
  "areas": [ {"uuid", "title", "visible", "index", "tags": [tag uuid...]} ],
  "tags":  [ {"uuid", "title", "shortcut", "parent": tag uuid|null, "index"} ],
  "tasks": [ Task ... ]
}
```

The counts above are from the stale homeserver DB and will be a little higher in the laptop export. Trashed items are excluded unless `--include-trashed` was used; there were 2,217 of them, and they should stay excluded.

**Task** (one object for to-dos, projects, headings *and* repeat templates — Things stores them all in one table):

| Field | Type | Meaning |
|---|---|---|
| `uuid` | string, 22 chars | Things' ID. **Keep it as the primary key** so URLs, notes and the user's memory that reference IDs keep working. |
| `type` | `to-do` \| `project` \| `heading` | |
| `status` | `open` \| `completed` \| `canceled` | |
| `trashed` | bool | always false unless exported with `--include-trashed` |
| `title`, `notes` | string | notes is plain text / Markdown-ish, may be long |
| `start` | `inbox` \| `anytime` \| `someday` | the "bucket" — see §6 |
| `start_date` | `YYYY-MM-DD` or null | the date the item is scheduled for ("When") |
| `evening` | bool | scheduled for This Evening (Things' `startBucket = 1`) |
| `reminder_time` | `HH:MM` or null | local time of the reminder on `start_date` |
| `deadline` | `YYYY-MM-DD` or null | |
| `stop_date` | ISO datetime with offset, or null | when it was completed/canceled. **This is the date that matters for reports**, not `created`. |
| `created`, `modified` | ISO datetime with offset | |
| `index` | int | manual sort order within its list |
| `today_index` | int | manual sort order within Today |
| `area` | area uuid or null | direct membership in an area |
| `project` | task uuid or null | direct membership in a project |
| `heading` | task uuid or null | membership in a heading (which belongs to a project). **A to-do under a heading has `project = null`**; its project is `heading.project`. |
| `tags` | [tag uuid] | |
| `checklist` | [ {uuid, title, status, stop_date, index, created, modified} ] | ordered |
| `repeat_template` | task uuid or null | set on to-dos that were generated from a repeating template |
| `is_repeat_template` | bool | true for the 365 template rows |
| `repeat` | object, only on templates | see below |

**Repeat block** (normalized; `raw` keeps Things' original dictionary for reference):

```json
"repeat": {
  "unit": "day|week|month|year",
  "interval": 1,
  "mode": "fixed_schedule|after_completion",
  "on": [ {"month": 8, "day": 17} ],
  "start_offset_days": -14,
  "rule_start_date": "2026-08-02",
  "last_anchor_date": "2026-08-16",
  "end_date": null,
  "repeat_count": null,
  "rule_version": 4,
  "next_instance_date": "2027-08-03",
  "instance_creation_start_date": "2026-08-16",
  "instances_created": 2,
  "paused": false,
  "after_completion_reference_date": null,
  "raw": {"fu": 4, "fa": 1, "tp": 0, "of": [{"dy": 16, "mo": 7}], "ts": -14, "...": "..."}
}
```

Semantics are in §7. Templates have `start = someday`, `status = open`, no `start_date`, no `deadline` (a placeholder was blanked by the exporter), and are almost all filed under a heading (343) or an area (21). They must be imported as templates, never shown as to-dos.

## 5. Data model

Use PostgreSQL if the homeserver already runs it for other services; otherwise SQLite in WAL mode is entirely adequate (the whole dataset is ~1.5 MB of JSON). Either way, one schema:

```
areas        id (things uuid), title, index, visible, created, modified
tags         id, title, shortcut, parent_id, index
area_tags    area_id, tag_id
projects     id, title, notes, status, start, start_date, evening, deadline,
             stop_date, area_id, index, today_index, created, modified
headings     id, title, project_id, index, status, created, modified
todos        id, title, notes, status, start, start_date, evening, reminder_time,
             deadline, stop_date, area_id, project_id, heading_id,
             index, today_index, template_id, created, modified
todo_tags    todo_id, tag_id            (projects also carry tags: project_tags)
checklist    id, todo_id, title, status, stop_date, index, created, modified
templates    id, title, notes, area_id, heading_id, project_id, tags,
             checklist (JSON array of titles), unit, interval, mode, on (JSON),
             start_offset_days, rule_start_date, last_anchor_date, end_date,
             repeat_count, next_instance_date, instances_created, paused,
             after_completion_reference_date, created, modified
```

Rules:

- **IDs**: keep Things' 22-character UUIDs for imported rows. New rows get 22-char base62 IDs from the same alphabet so nothing downstream has to special-case them.
- **Timestamps** are stored UTC; **`start_date` / `deadline` are calendar dates, no timezone**. "Today" is computed in `America/Los_Angeles` (§11). Don't store dates as midnight-UTC datetimes; that class of bug is why Things packs dates as integers.
- **Derived, never stored**: a to-do's effective project is `project_id ?? heading.project_id`; its effective area is `area_id ?? project.area_id`. Provide both as `project`, `project_title`, `area`, `area_title` in every API response (§8.1) — the current fork of things.py had to be patched to do exactly this, and the SSNC report silently returns `[]` without it.
- **Status transitions**: `open → completed` sets `stop_date = now`; `open → canceled` likewise; either back to `open` clears it. Completing a project does not touch its to-dos (Things asks; the API doesn't). Deleting is a soft `trashed` flag with a separate `GET /api/trash`; purge on a 30-day job.
- Sorting: `index` within the containing list, `today_index` within Today. Preserve on import; on insert, append (max+1).

## 6. View semantics

These are what the read endpoints return. `today` means the local calendar date in `America/Los_Angeles`.

| View | Definition |
|---|---|
| **Inbox** | open to-dos with `start = inbox` |
| **Today** | open to-dos with `start_date <= today`, plus open to-dos with `deadline <= today` (overdue or due today, shown regardless of start_date). Ordered by `today_index`. Evening items are the subset with `evening = true`; return them in the same list with the flag, ordered after non-evening. |
| **Upcoming** | open to-dos with `start_date > today`, ordered by `start_date` then `index`. Also open to-dos with `deadline > today` and no start date. **Plus future repeat instances** — see §7.5. |
| **Anytime** | open to-dos with `start = anytime` and (no `start_date` or `start_date <= today`) |
| **Someday** | open to-dos with `start = someday`, plus every open to-do inside a project whose own `start = someday` |
| **Logbook** | completed and canceled to-dos/projects, filtered on **`stop_date`** within a period, newest first |
| **Trash** | `trashed = true` |
| Project view | open to-dos of the project grouped by heading (heading order, then `index`), with headings' titles |
| Area view | projects of the area + to-dos filed directly in the area |

**Someday-project filtering (must keep):** Things hides to-dos that belong to a Someday project from Today, Upcoming and Anytime even if the to-do itself has a date. `things-mcp` reimplemented that in `filter_someday_project_tasks`; reproduce it. A to-do is "in a Someday project" if its effective project (§5) has `start = someday`.

## 7. Recurrence engine

Everything in this section was verified against templates and their generated instances in the real database; the letter codes are Things' and appear in `repeat.raw`.

### 7.1 Rule fields

- `unit` (`fu`): `day`=16, `week`=256, `month`=8, `year`=4.
- `interval` (`fa`): every N units. Real data: mostly 1; a "every 5 days", "every 2 weeks", "every 6 months", "every 87 days" exist.
- `mode` (`tp`): `fixed_schedule` (0, 357 templates) or `after_completion` (1, 8 templates).
- `on` (`of`): a list of one or more "which date" specs. Things stores day and month **zero-based**; the exporter already converted them to 1-based `day`/`month`. Weekday `wd` is `0 = Sunday … 6 = Saturday` and is left as-is. `weekday_ordinal` is `1..4` or `-1` (last).
  - `year`: `{month, day}` — e.g. every year on Aug 17. Or `{month, weekday, weekday_ordinal}` — last Sunday of December. A rule may list several (`Bi-Annual Maintenance`: last Sunday of March **and** of September, `interval = 1` year).
  - `month`: `{day}` — the 6th; or `{weekday, weekday_ordinal}` — last Sunday.
  - `week`: `{weekday}`.
  - `day`: `{day: 1}` placeholder, ignore.
- `start_offset_days` (`ts`): ≤ 0. **When nonzero, the rule produces a deadline, not a start date**: each instance gets `deadline = rule date` and `start_date = rule date + start_offset_days`, so it enters Today `|ts|` days ahead of the deadline. Verified: a yearly Aug 17 rule with `ts = -14` produced an instance with `start_date = 2026-08-03`, `deadline = 2026-08-17`. When `ts = 0` the instance gets `start_date = rule date` and no deadline. 334 of the 365 templates use a negative offset (mostly −7, −14, −30, −45).
- `rule_start_date` (`sr`): where the series began; `end_date` (`ed`, null = none — Things stores a year-4001 sentinel); `repeat_count` (`rc`, null = unlimited). All 365 have no end and no count, but support both.
- `next_instance_date`: the date the next instance is *due to appear* (its `start_date`, i.e. already offset). For `after_completion` templates it is null until the current instance is completed.
- `paused`: no new instances while true. Completing the current instance of a paused template must not create the next one.

### 7.2 Instance creation — fixed schedule

An **instance** is an ordinary to-do row with `template_id` set, and a copy of the template's title, notes, tags, checklist (all items open), area/project/heading, `evening`, `reminder_time`.

A daily job (run at 00:05 local, and once at service start) does, per unpaused fixed-schedule template:

1. Compute rule dates from the `on` specs and `interval`, starting from `rule_start_date`, forward until the first rule date `R` with `R + start_offset_days > (last created instance's start_date)`. Standard calendar math (`dateutil.rrule` covers all of it: `YEARLY/MONTHLY/WEEKLY/DAILY`, `interval`, `bymonth`, `bymonthday`, `byweekday(n)`; month/day pairs that don't exist in a year — Feb 30 — are skipped by rrule, which matches Things).
2. If `R + start_offset_days <= today`, create the instance with `start_date = R + offset`, `deadline = R if offset != 0 else null`, `start = anytime`. Increment `instances_created`, set `next_instance_date` to the following occurrence.
3. Things creates exactly one instance at a time and only when its start date arrives — never in advance. **Do the same.** The observed DB had zero open instances with a future start date across 365 templates. Upcoming shows future ones as *projections* (§7.5).
4. If an open instance of the template already exists when the next one is due, still create the next one (Things does; the user can end up with two "Send rewards" open). Do not dedupe.

### 7.3 Instance creation — after completion

No instances are scheduled ahead. When an instance of an `after_completion` template is completed (or canceled): compute `R = completion date + interval units` (for `month`/`year` with a `day` spec, land on that day-of-month of the target month), create the next instance with `start_date = R + offset`, `deadline` per the offset rule, and record `after_completion_reference_date = completion date`. If `paused`, record the reference date and create nothing; resuming creates from it.

### 7.4 Completing instances

- Completing a **fixed-schedule** instance is just completing a to-do. It does not advance the schedule; the daily job already knows when the next one is due. (This is what 3.23's "complete early" is: the checkbox on a not-yet-materialized future instance. For us: `POST /api/templates/{id}/complete-next` materializes the next instance already completed with `stop_date = now`, and advances `next_instance_date`.)
- Completing an **after-completion** instance triggers §7.3.

### 7.5 Upcoming projections

`GET /api/upcoming` must include future repeat instances that don't exist yet, because that's what the user sees in Things. For each unpaused fixed-schedule template, compute occurrences from `next_instance_date` for the requested horizon (default 90 days, `?days=`), and emit them with `"projected": true`, `"id": "<template id>@<YYYY-MM-DD>"`, and the template's title/tags/project. They are read-only; `POST /api/templates/{id}/complete-next` and `POST /api/templates/{id}/skip-next` are the only writes against a projection. After-completion templates project nothing.

### 7.6 Editing templates

`PATCH /api/templates/{id}` accepts any rule field. Changing the rule recomputes `next_instance_date` from today; it never touches existing instances (Things 3.23's "Update Rule"). "Make Exception" is: edit the *instance* to-do's dates directly — no template involvement, which is already how it works.

`pause`, `resume`, `stop` (= delete template, keep instances) as sub-resources. Bulk forms accept a list of IDs.

### 7.7 Tests you must have

Encode each of these from the export (all real): every-year Aug-17 with −14 offset; every-5-days; every-2-weeks Sunday; last-Sunday-monthly; last-Sunday-of-December yearly; twice-yearly last Sunday of March & September; monthly-on-the-6th with −4 offset; after-completion every-6-months on the 1st; after-completion daily. For each: given `rule_start_date` and a "today", assert the exact instance `start_date` and `deadline` the job creates, and assert nothing is created a day early. Add a leap-year (Feb 29 yearly) and a "31st of a 30-day month" case.

## 8. API

### 8.1 REST routes — reproduce exactly

All under `/api`, JSON, bearer auth except `/api/health`. Response objects for to-dos carry at least: `uuid, type, title, notes, status, start, start_date, evening, reminder_time, deadline, stop_date, created, modified, index, today_index, tags (titles), checklist, project, project_title, area, area_title, heading, heading_title, template_id, projected`. Absent values are `null`, not omitted (things.py omitted keys; that was a nuisance — don't).

| Route | Behavior |
|---|---|
| `GET /api/health` | `{"ok": true}`, **no auth** |
| `GET /api/health/auth` | `{"ok": true}` if the bearer token is valid, else the normal 401. Lets consumers test their token. |
| `GET /api/inbox`, `/today`, `/upcoming`, `/anytime`, `/someday` | bare arrays per §6 |
| `GET /api/projects`, `/areas`, `/tags` | bare arrays; `?include_items=true` nests contents |
| `GET /api/todos?project=<id>&tag=<title>` | open to-dos, both filters optional |
| `GET /api/search?q=` | title+notes substring, case-insensitive; 400 if `q` missing |
| `GET /api/get/{uuid}` | any object by id, 404 if missing; to-dos include checklist |
| `POST /api/add/todo` | body `{title (required), notes, when, deadline, tags[], checklist_items[], list_id, list_title, heading, heading_id}` → `{"ok": true, "uuid": ..., "title": ...}`. **Return the new uuid** (the URL scheme couldn't; consumers wanted it). |
| `POST /api/add/project` | `{title, notes, when, deadline, tags[], area_id, area_title, todos[]}` |
| `POST /api/update/todo` | `{id (required), title, notes, when, deadline, tags[], add_tags[], completed, canceled, list, list_id, heading, heading_id, checklist_items[], prepend_checklist_items[], append_checklist_items[]}` |
| `POST /api/update/project` | `{id, title, notes, when, deadline, tags[], completed, canceled}` |
| `GET /api/ssnc/completed?since=` | **Stable contract, consumed by the weekly SSNC automation on this same homeserver.** See below. |

**`/api/ssnc/completed`**: `since` is required, `<count><unit>` with unit `d|w|m|y` (`7d`, `1w`, `26w`, `3m`, `1y`); anything else → 400 with a message. Returns a bare JSON array of completed to-dos whose **`stop_date`** (completion time, never creation time) is within the window **and** whose effective `project_title` starts with `SSNC` (prefix, case-sensitive). Empty array is a normal result. The SSNC to-dos are filed under headings, so the effective-project rule in §5 is load-bearing here. The 10-second `nudge_things()` wait in the old server existed only to let the Things app flush; delete the concept.

New, because the old server couldn't: `GET /api/logbook?period=7d`, `GET /api/trash`, `DELETE /api/todo/{id}` (trash), `POST /api/todo/{id}/restore`, the template routes in §7, `GET /api/headings?project=`, `GET /api/tagged/{tag}`, bulk update `POST /api/update/todos` with `ids[]`. Add `?limit=&offset=` to every list route, returning `X-Total-Count`.

### 8.2 MCP tools — reproduce name-for-name

Mounted at `/mcp` (Streamable HTTP), same bearer middleware. Claude Desktop and Claude Code currently use these; keep names and parameters so only the URL and token change in their config. Use the current `fastmcp` (3.x) or the official `mcp` SDK; either is fine.

Read tools return text **and** `structured_content = {items, count, total, offset, limit}`; all accept `limit`, `offset`.

```
get_inbox() get_today() get_upcoming() get_anytime() get_someday()
get_logbook(period="7d", limit=50)          period as in ssnc `since`, filters on stop_date
get_trash()
get_todos(project_uuid=None, include_items=True)
get_projects(include_items=False) get_areas(include_items=False) get_tags(include_items=False)
get_tagged_items(tag)                        tag by title
get_tag_usage(only_unused=False) -> str      counts per tag
get_headings(project_uuid=None)
search_todos(query)
search_advanced(status=None, start_date=None, deadline=None, tag=None, area=None, type=None, last=None)
      status: incomplete|completed|canceled; start_date/deadline: "YYYY-MM-DD", "future", "past", or True/False;
      type: to-do|project|heading; last: period ("1w") over creation date (keep that quirk; it's documented)
get_recent(period)                           created within period
```

Write tools return a short string (`"Created to-do <uuid>: <title>"`):

```
add_todo(title, notes=None, when=None, deadline=None, tags=None, checklist_items=None,
         list_id=None, list_title=None, heading=None, heading_id=None)
add_project(title, notes=None, when=None, deadline=None, tags=None, area_id=None, area_title=None, todos=None)
add_area(title)
update_todo(id, title=None, notes=None, when=None, deadline=None, tags=None, add_tags=None,
            completed=None, canceled=None, list=None, list_id=None, heading=None, heading_id=None,
            checklist_items=None, prepend_checklist_items=None, append_checklist_items=None)
bulk_update_todos(ids, list=None, list_id=None, tags=None, add_tags=None, when=None, deadline=None,
                  heading=None, heading_id=None, completed=None, canceled=None)
update_project(id, title=None, notes=None, when=None, deadline=None, tags=None, completed=None, canceled=None)
update_area(id, title=None, tags=None)
show_item(id, query=None, filter_tags=None)  was "open in the Things app"; now return the item + its contents
search_items(query) -> str                   same as search_todos, string form
```

Add `get_templates()`, `update_template(id, ...)`, `complete_next(id)`, `skip_next(id)`, `delete_todo(id)`, `restore_todo(id)` — things the old server could not do through the URL scheme.

### 8.3 Auth

Copy `BearerAuthMiddleware` from `api_server.py`: raw ASGI (because `/mcp` streams and `BaseHTTPMiddleware` buffers), constant-time compare, `401` + `WWW-Authenticate: Bearer realm=...` on failure, `503` if the token env var is empty, exact-path exemption set `{"/api/health"}`. **No "no token means no auth" mode** — the server refuses to start without `TASKS_TOKEN`. Token comes from an env file readable only by the service user.

### 8.4 `when` and list parameters (from the Things URL scheme; consumers use these)

`when`: `today` (start=anytime, start_date=today), `tomorrow`, `evening` (today + evening flag), `anytime` (clears start_date), `someday`, `YYYY-MM-DD`, or `YYYY-MM-DD@HH:MM` (also sets `reminder_time`). Reject anything else with 400 — the old docstring promised natural language ("next tuesday") but that was Things parsing it; don't pretend.

`list_id` / `list_title` (`list` on update): a project **or** area; id wins over title; title match is exact, case-insensitive, 404 if no match. `heading_id` / `heading`: heading within the target project; id wins. `tags` replaces, `add_tags` appends; unknown tag titles are **created** (Things silently dropped them; consumers found that maddening). `deadline` is `YYYY-MM-DD`.

## 9. Consumers to repoint at cutover

| Consumer | Where | Change |
|---|---|---|
| SSNC weekly automation ("automation-backend") | this homeserver | base URL → the new service, new token, verify `/api/health/auth` → 200 before the first weekly run |
| Claude Desktop / Claude Code MCP config | user's laptop | `/mcp` URL + token |
| Anything else hitting `mac-homeserver.tail1228bf.ts.net:3400` | grep the user's other repos for that hostname | same |
| `com.obsidian-sync.things-mcp` launchd service on the Mac | `mac-homeserver` | leave running until the new service has served one successful weekly SSNC run, then unload; the Mac keeps the frozen Things DB as a backup |

## 10. Migration

### 10.1 Producing the export

On the **laptop** (the copy that is still syncing):

```bash
git clone git@github.com:joshmci9198/things-mcp.git && cd things-mcp && git checkout wired
python3 scripts/export_things.py --out ~/things-export.json
```

System python3 is enough; no dependencies. Quit Things first so nothing is mid-write. Copy the file to the homeserver over the tailnet.

### 10.2 Import rules

- Import order: areas, tags, projects, headings, templates, to-dos, checklist, tag links. All in one transaction; the import is **idempotent** (upsert on uuid) so it can be re-run after a fresh export right before cutover.
- `type = heading` → `headings` (every heading has a `project`).
- `is_repeat_template = true` → `templates`, never `todos`. Carry `tags` and `checklist` titles onto the template so instances inherit them. Set `next_instance_date` from the export; if null and `mode = fixed_schedule`, compute it.
- To-dos with `repeat_template` set → `todos.template_id`. Leave their status as exported (238 open, 126 completed in the stale copy).
- Keep `index`, `today_index`, `created`, `modified`, `stop_date` verbatim.
- Convert `stop_date` and friends to UTC on the way in; they carry offsets.
- `start = someday` to-dos inside Someday projects stay as they are; §6 handles display.

### 10.3 Verify before calling it done

Print and compare against `export.counts`: areas, tags, projects (by status), headings, templates (by unit and mode), to-dos (by status and by `start`), checklist items, to-dos with tags, to-dos with `template_id`. Then spot-check by hand: `GET /api/today` on cutover day should list the same items Things shows on the laptop; `GET /api/ssnc/completed?since=26w` must return the same to-dos the old endpoint returned on 2026-08-26 (the user can run the old one for comparison while the Mac is still up).

Run the daily job once against the imported data with "today" set to the export date and assert it creates **nothing** — every template's next instance is in the future at export time. Then set "today" to the earliest `next_instance_date` and assert exactly those templates fire.

## 11. Deployment

- Service user without a login shell; code under `/opt/tasks` (or wherever the other services live — match local convention); `systemd` unit with `Restart=always`, `EnvironmentFile=` for the token, `TZ=America/Los_Angeles` (the user's timezone; "today" depends on it).
- Bind `127.0.0.1` only; expose with `tailscale serve` on a port of your choosing (3400 is free once the Mac is retired; using a different port during the overlap avoids confusion). Tailscale key expiry should be disabled for this node, as it is for the Mac.
- Backups: nightly `sqlite3 .backup` (or `pg_dump`) to a dated file, keep 30; plus a nightly JSON export in the same `things-export/1` format so the data is never trapped in one schema again.
- Logging to journald; log every write route at INFO with the id and the changed fields — the old system's worst failures were silent.
- Timer/cron for the daily materialization at 00:05 local and a 30-day trash purge.

## 12. Acceptance checklist

- [ ] Import from the laptop export passes §10.3.
- [ ] Recurrence tests in §7.7 pass; daily job is idempotent (running it twice creates nothing the second time).
- [ ] Every route in §8.1 and tool in §8.2 exists with the listed parameters; `curl` without a token → 401; with token → 200; `/api/health` open.
- [ ] `/api/ssnc/completed?since=1w` returns heading-filed SSNC to-dos completed this week and returns `[]`, not an error, when there are none.
- [ ] `/api/upcoming` shows projected repeat instances with `projected: true`.
- [ ] Completing an after-completion instance creates the next one; completing a fixed-schedule one does not.
- [ ] Backups run and restore into a scratch DB.
- [ ] Claude Desktop connects to `/mcp` with the new token and `get_today` returns the same list as `/api/today`.

## 13. Decisions the user still has to make (ask before starting the affected part)

1. **Extend the existing to-do app on the homeserver, or build this beside it?** The user mentioned an existing "basic todos" service. If its model can absorb §5 without contortions, extend it; if it's a flat list, build this standalone and let the old one die. Ask for its schema first.
2. **Postgres or SQLite** — follow whatever the other services on the box use.
3. **Port** for the new service during the overlap period.
4. Whether the 2,217 trashed items should come along (recommendation: no).

## Appendix A — things the old system taught us; don't relearn them

- Filtering "completed in the last N" on creation date instead of completion date silently drops a third of the results. Always filter on `stop_date`.
- To-dos under headings have no direct project link. Resolve through the heading or reports come back empty with no error.
- Templates are rows in the same table as to-dos, parked in Someday with a fake deadline. Hide them from every to-do listing.
- Things creates one repeat instance at a time, on the day it's due; it never pre-creates. Upcoming's future repeats are projections.
- A negative `start_offset_days` means "deadline on the rule date, appear N days before." It is the common case (334/365), not the exception.
- Silent fallbacks (no token → no auth; app not responding → return stale data) cost days of debugging. Fail loudly.
