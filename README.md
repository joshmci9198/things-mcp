# Things MCP Server

This [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction) server lets you use Claude Desktop to interact with your task management data in [Things 3](https://culturedcode.com/things) from Cultured Code. You can ask Claude to create tasks, analyze projects, help manage priorities, and more.

This server leverages the [Things.py](https://github.com/thingsapi/things.py) library and the [Things URL Scheme](https://culturedcode.com/things/help/url-scheme/). 

<a href="https://glama.ai/mcp/servers/t9cgixg2ah"><img width="380" height="200" src="https://glama.ai/mcp/servers/t9cgixg2ah/badge" alt="Things Server MCP server" /></a>

## Support the Project

If you find this project helpful, consider supporting its development:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/haldick)

## Features

- Access to all major Things lists (Inbox, Today, Upcoming, etc.)
- Project and area management
- Tag operations
- Advanced search capabilities
- Recent items
- Detailed item information including checklists
- Support for nested data (projects within areas, todos within projects)
- Someday project filtering: tasks in Someday projects are automatically excluded from Today, Upcoming, and Anytime views, matching Things UI behavior


## Installation

### Prerequisites
- macOS (Things 3 is Mac-only)
- Things 3 app with "Enable Things URLs" turned on (Settings → General)
- A MCP client, such as Claude Desktop or Claude Code
- [uv](https://docs.astral.sh/uv/) Python package manager: `brew install uv`

### Install via uvx (Any MCP Client)

Things MCP is published on PyPI and can be run directly with `uvx`:

```bash
uvx things-mcp
```

Configure your MCP client to use `uvx` with `things-mcp` as the argument.

### Claude Desktop

#### Option 1: One-Click Install (Recommended)

1. Download the latest file from the [releases page](https://github.com/hald/things-mcp/releases)
2. Double-click the `.mcpb` file
3. Done!

#### Option 2: Manual Config

1. Go to **Claude → Settings → Developer → Edit Config**
2. Add the Things server:

```json
{
  "mcpServers": {
    "things": {
      "command": "uvx",
      "args": ["things-mcp"]
    }
  }
}
```

3. Save and restart Claude Desktop

### Claude Code

```bash
claude mcp add-json things '{"command":"uvx","args":["things-mcp"]}'
```

To make it available globally (across all projects), add `-s user`:
```bash
claude mcp add-json -s user things '{"command":"uvx","args":["things-mcp"]}'
```

### Verify it's working

After installation:
- If using Claude Desktop, you should see "Things MCP" in the "Search and tools" list
- Try asking: "What's in my Things inbox?"

### Sample Usage with Claude Desktop
* "What's on my todo list today?"
* "Create a todo to pack for my beach vacation next week, include a packing checklist."
* "Evaluate my current todos using the Eisenhower matrix."
* "Help me conduct a GTD-style weekly review using Things."
* "Show me tasks that haven't been modified in over a month."

#### Tips
* Create a project in Claude with custom instructions that explains how you use Things and organize areas, projects, tags, etc. Tell Claude what information you want included when it creates a new task (eg asking it to include relevant details in the task description might be helpful).
* Try adding another MCP server that gives Claude access to your calendar. This will let you ask Claude to block time on your calendar for specific tasks, create todos from upcoming calendar events (eg prep for a meeting), etc.
* Use task ages to identify stale items: "Which tasks in my Anytime list are older than 2 weeks?"


## Available Tools

### List Views
- `get-inbox` - Get todos from Inbox
- `get-today` - Get todos due today
- `get-upcoming` - Get upcoming todos
- `get-anytime` - Get todos from Anytime list
- `get-someday` - Get todos from Someday list, including tasks in Someday projects
- `get-logbook` - Get completed todos
- `get-trash` - Get trashed todos

### Basic Operations
- `get-todos` - Get todos, optionally filtered by project
- `get-projects` - Get all projects
- `get-areas` - Get all areas

### Tag Operations
- `get-tags` - Get all tags
- `get-tagged-items` - Get items with a specific tag
- `get-tag-usage` - Report how many items use each tag, sorted by usage; flag unused tags for cleanup

### Search Operations
- `search-todos` - Simple search by title/notes
- `search-advanced` - Advanced search with multiple filters

### Time-based Operations
- `get-recent` - Get recently created items

### Things URL Scheme Operations
- `add-todo` - Create a new todo
- `add-project` - Create a new project
- `add-area` - Create a new Area (via AppleScript; Things URL scheme has no add-area command)
- `update-area` - Update an existing Area: rename or set tags (via AppleScript)
- `update-todo` - Update an existing todo
- `bulk-update-todos` - Apply the same update to many todos in a single operation
- `update-project` - Update an existing project
- `show-item` - Show a specific item or list in Things
- `search-items` - Search for items in Things

## Tool Parameters

### Pagination (most read tools)
The list/search read tools (`get-inbox`, `get-today`, `get-upcoming`, `get-anytime`, `get-someday`, `get-logbook`, `get-trash`, `get-todos`, `get-projects`, `get-areas`, `get-tags`, `get-tagged-items`, `get-headings`, `search-todos`, `search-advanced`, `get-recent`) accept optional pagination:
- `limit` - Maximum number of items to return (default: all; `get-logbook` defaults to 50)
- `offset` - Number of items to skip from the start (default: 0)

When neither is set, output is unchanged. When set, a `Showing X-Y of Z items` header is prepended so you know how much more there is. An `offset` past the end is reported distinctly from an empty result.

These same read tools also return **structured content** alongside the human-readable text: MCP clients receive the raw item dicts plus `count`/`total`/`offset`/`limit` under `structured_content`, so data can be consumed programmatically without parsing the formatted text.

### get-todos
- `project_uuid` (optional) - Filter todos by project
- `include_items` (optional, default: true) - Include checklist items

### get-projects / get-areas / get-tags
- `include_items` (optional, default: false) - Include contained items

### search-advanced
- `status` - Filter by status (incomplete/completed/canceled)
- `start_date` - Filter by start date (YYYY-MM-DD)
- `deadline` - Filter by deadline (YYYY-MM-DD)
- `tag` - Filter by tag
- `area` - Filter by area UUID
- `type` - Filter by item type (to-do/project/heading)
- `last` - Filter by creation date (e.g., '3d' for last 3 days, '1w' for last week)

### get-recent
- `period` - Time period (e.g., '3d', '1w', '2m', '1y')

### get-logbook
- `period` (optional, default: '7d') - Look-back window by completion date. Accepts `d`/`w`/`m`/`y` (e.g., '3d', '1w', '2m', '1y'); months ≈ 30 days, years ≈ 365 days
- `limit` (optional, default: 50) - Maximum number of completed items to return

### get-tag-usage
- `only_unused` (optional, default: false) - Return only tags that no item references (cleanup candidates)

### update-todo (checklist & tags)
- `tags` - Replace all tags on the todo
- `add_tags` - Append tags without removing existing ones
- `checklist_items` - Replace the entire checklist with this list
- `prepend_checklist_items` - Add these items to the top of the checklist
- `append_checklist_items` - Add these items to the bottom of the checklist

### bulk-update-todos
Applies the same change to every todo in `ids` in a single operation. Requires the Things auth token to be enabled (Things → Settings → General → Enable Things URLs → Manage); the server reads it automatically.
- `ids` (required) - List of todo UUIDs to update
- `list` / `list_id` - Move all into a project/area (by title or UUID)
- `tags` / `add_tags` - Replace or append tags on all
- `when` - Reschedule all (keyword or YYYY-MM-DD)
- `deadline` - Set deadline on all (YYYY-MM-DD)
- `heading` / `heading_id` - Move all under a heading (by title or UUID)
- `completed` / `canceled` - Mark all completed or canceled

### Scheduling with Reminders (add-todo, add-project, update-todo, update-project)
- `when` - Accepts multiple formats:
  - Keywords: `today`, `tomorrow`, `evening`, `anytime`, `someday`
  - Date: `YYYY-MM-DD` (e.g., `2024-01-15`)
  - DateTime with reminder: `YYYY-MM-DD@HH:MM` (e.g., `2024-01-15@14:30`)

## Troubleshooting

If it's not working:

1. **Make sure Things 3 is installed and has been opened at least once**
   - The Things database needs to exist for the server to work

2. **Check that "Enable Things URLs" is turned on**
   - Open Things → Settings → General → Enable Things URLs

3. **Claude Desktop can't find `uvx`**
   - Install uv globally with Homebrew (`brew install uv`) 
   - **Alternative**: Use the full path to `uvx` in your config. Find it with `which uvx` (typically `/Users/USERNAME/.local/bin/uvx`)

## Development

### Running Tests

The project includes a comprehensive unit test suite for the URL scheme and formatter modules.

```bash
# Install test dependencies
uv sync --extra test

# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_url_scheme.py

# Run tests matching a pattern
uv run pytest -k "test_add_todo"
```

### MCP Integration Test

The project includes an integration test plan that can be executed by Claude (via Claude Cowork or Claude Code) to verify all MCP tools work correctly against a live Things database.

See [`docs/mcp_integration_test_plan.md`](docs/mcp_integration_test_plan.md) for the full test plan.

### Project Structure

```
things-mcp/
├── src/things_mcp/      # Main package
│   ├── __init__.py      # Package exports
│   ├── __main__.py      # Entry point for python -m
│   ├── server.py        # MCP server implementation
│   ├── url_scheme.py    # Things URL scheme implementation
│   └── formatters.py    # Data formatting utilities
├── tests/               # Unit tests
│   ├── conftest.py      # Test fixtures and configuration
│   ├── test_url_scheme.py
│   ├── test_formatters.py
│   ├── test_someday_filtering.py
│   └── test_mcp_server_filtering.py
├── docs/                # Documentation
│   └── mcp_integration_test_plan.md  # Claude-executable integration test
├── manifest.json        # MCPB package manifest
├── build_mcpb.sh        # MCPB package build script
├── pyproject.toml       # Project dependencies, build config, and pytest config
├── .env.example         # Sample environment configuration
└── run.sh               # Convenience runner script
```

### HTTP Transport

By default, the server uses stdio transport for communication with MCP clients. For remote access scenarios, you can run the server with HTTP transport.

#### Configuration

Set these environment variables to enable HTTP transport:

| Variable | Default | Description |
|----------|---------|-------------|
| `THINGS_MCP_TRANSPORT` | `stdio` | Transport type: `stdio` or `http` |
| `THINGS_MCP_HOST` | `127.0.0.1` | HTTP server bind address |
| `THINGS_MCP_PORT` | `8000` | HTTP server port |

#### Example

```bash
# Using uvx
THINGS_MCP_TRANSPORT=http THINGS_MCP_HOST=0.0.0.0 THINGS_MCP_PORT=8000 uvx things-mcp

# Or from source
THINGS_MCP_TRANSPORT=http THINGS_MCP_HOST=0.0.0.0 THINGS_MCP_PORT=8000 uv run things-mcp
```

See `.env.example` for a sample configuration file.

## Wired Deployment (this fork)

`api_server.py` serves the MCP protocol *and* a plain REST API from a single
port, so consumers that don't speak MCP can still read and write Things:

| Path | Purpose |
|------|---------|
| `/mcp` | FastMCP server, mounted for Claude and other agents |
| `/api/*` | REST routes for automations (list views, search, add, update) |

`start.sh` binds it to `127.0.0.1` (port 3400 by default). Tailnet reachability
comes from `tailscale serve`, which terminates TLS and proxies to that loopback
port:

```bash
tailscale serve --bg --https=3400 http://127.0.0.1:3400
tailscale serve status   # verify — must not say "No serve config"
```

This exposes `https://<node>.<tailnet>.ts.net:3400` to the tailnet. Keep the
bind on loopback so the surface stops at the tailnet and never reaches the
local LAN.

### Authentication

Every route except `/api/health` requires a bearer token, including `/mcp` —
the MCP mount grants the same full read/write access to the Things database
that the REST routes do. Without it, any device on the tailnet could read and
modify the entire database.

```bash
printf 'THINGS_MCP_TOKEN=%s\n' "$(openssl rand -hex 32)" >> .env
chmod 600 .env
launchctl kickstart -k gui/$(id -u)/com.obsidian-sync.things-mcp
```

`.env` is gitignored; `start.sh` loads it before launching the server. The
server **refuses to start** if `THINGS_MCP_TOKEN` is unset, and returns 503
rather than serving data if it somehow reaches a request without one. That is
deliberate — a silent insecure fallback is exactly how `start.sh` previously
ended up binding `0.0.0.0` and exposing this database to the whole LAN.

Callers pass it as a normal bearer credential:

```bash
curl -H "Authorization: Bearer $THINGS_MCP_TOKEN" \
  https://mac-homeserver.tail1228bf.ts.net:3400/api/today
```

MCP clients need the same header in their HTTP transport config. Anything that
consumed this API before the token existed — automations on other tailnet
hosts, shortcuts — will get 401 until updated.

**Requires Tailscale >= 1.102.** On the macOS `macsys` build at 1.98.2, serve
silently no-ops: the CLI prints success, the daemon logs the
`POST /localapi/v0/serve-config`, and the config is then discarded — nothing
ever listens on the tailnet address. Always confirm with `serve status` rather
than trusting the command's own output.

Reference the node by its MagicDNS name (`mac-homeserver.tail1228bf.ts.net`),
never by tailnet IP: a Tailscale update can re-register the Mac as a new node
with a new IP. Keeping the Mac's `ComputerName`/`HostName`/`LocalHostName` set
to `mac-homeserver` stops that re-registration from also losing the node's name.

It runs under launchd via
`~/Library/LaunchAgents/com.obsidian-sync.things-mcp.plist` with `KeepAlive`
and `RunAtLoad`, logging to `stdout.log` / `stderr.log` in this directory.

To restart after changing `api_server.py` or `start.sh`:

```bash
launchctl kickstart -k gui/$(id -u)/com.obsidian-sync.things-mcp
```

### Host hardening (files outside this repo)

Three system files are part of this deployment but are not in git. They are
listed here because every one of them has already been forgotten or
mis-debugged at least once.

| File | Purpose |
|------|---------|
| `/etc/pf.anchors/tailscale-ssh` | pf rules: ports 22 and 3400 reachable from the tailnet only |
| `/Library/LaunchDaemons/com.obsidian-sync.pf-enable.plist` | enables pf at boot |
| `/etc/ssh/sshd_config.d/99-hardening.conf` | key-only SSH, no root login |
| `/etc/newsyslog.d/things-mcp.conf` | caps `stdout.log` / `stderr.log` / `pf-enable.log` |

**pf is not enabled at boot by macOS.** Apple's
`/System/Library/LaunchDaemons/com.apple.pfctl.plist` runs `pfctl -f
/etc/pf.conf`, which *loads* the ruleset but never enables it — there is no
`-e`. `pfctl -e` is runtime-only state and does not survive a reboot, so rules
sit parsed and inert after every restart. That is what
`com.obsidian-sync.pf-enable.plist` exists to fix; Apple's plist is on the
sealed read-only system volume and cannot be edited. Verify with `pfctl -si`
after a reboot, not after a manual `pfctl -e`.

**`pass quick on lo0 all` must stay the first rule in the anchor.** macOS
`/etc/pf.conf` has no `set skip on lo0`, so pf filters loopback like any other
interface, and the `block ... port 3400` rule would otherwise drop
`127.0.0.1:3400` — killing the API outright, since uvicorn binds loopback and
`tailscale serve` reaches it over loopback. `set skip` is only valid in the main
ruleset, not inside an anchor, hence the `quick` pass. Without `quick`, pf's
last-match-wins evaluation would let the later `block` override it.

**SSH is tailnet-only; there is no LAN fallback.** If Tailscale is down on this
Mac, recovery requires physical console access. This is deliberate — re-add
`pass in on en0 proto tcp from 192.168.0.0/24 to any port 22` to trade some
exposure for a remote escape hatch.

**`ListenAddress` in `sshd_config` does nothing on macOS.** sshd is socket-
activated by launchd (`ssh.plist`, `inetdCompatibility`), so launchd owns the
listening socket and sshd never consults `ListenAddress`. Restricting which
interfaces reach port 22 is a pf job. A stale `ListenAddress` pinned to an old
Tailscale IP lived in the hardening file for months doing nothing, and would
have broken SSH entirely had sshd ever run standalone.

**pf fails open on a bad ruleset.** A syntax error in the anchor means no
filtering at all, silently, at boot. Always dry-run before loading:

```bash
sudo pfctl -n -f /etc/pf.conf && sudo pfctl -f /etc/pf.conf
sudo pfctl -a tailscale-ssh -sr
```

**You cannot test the LAN block from this Mac.** Traffic to its own LAN address
routes over `lo0` (`route -n get 192.168.0.236` → `interface: lo0`) and matches
the loopback pass rule. Test from another host on the LAN:
`nc -z -w 4 192.168.0.236 22`.

**Tailscale key expiry is disabled** for this node. Left enabled, the key
expires roughly every 180 days and the node silently drops off the tailnet,
taking serve and remote SSH with it.

**Things is opted out of App Nap.** Set on 2026-08-16 with

```bash
defaults write com.culturedcode.ThingsMac NSAppSleepDisabled -bool YES
```

and read back with `defaults read`. It lives in
`~/Library/Preferences/com.culturedcode.ThingsMac.plist`, so it survives
reboots and Things updates; Things only reads it at launch, so it takes effect
after the next quit/reopen. See the next section for why.

### Why `nudge_things()` exists

**Do not delete this.** `/api/ssnc/completed` reads the Things SQLite
database directly, and GUI-originated changes — a to-do checked off by hand —
only reach SQLite on Things' internal flush timer. Measured on 2026-08-16:
about **8 seconds** with the screen unlocked and Things active, but somewhere
between **4 and 8 minutes** with the screen locked. The difference is macOS
App Nap throttling an occluded, non-active app's timers. Anything finished in
that window is invisible to the report.

Two earlier implementations did nothing on this box, silently:

- **Focus switching** (`open -a Finder` / `open -a Things3`). A background
  process cannot change the frontmost app while the screen is locked, and the
  homeserver's screen is locked essentially always. Verified by watching the
  frontmost process stay `loginwindow` through the whole sequence.
- **AppleScript** (`osascript -e 'tell application "Things3" to count ...'`).
  Works from Terminal because Terminal holds a TCC Automation grant for
  Things. The service runs under launchd with `/bin/bash` as its responsible
  process, which has no such grant and no desktop on which to prompt for one,
  so the Apple event hangs until it times out (`-1712`). Worse, killing the
  hung `osascript` left Things unresponsive to *all* Apple events for 40–100 s
  afterwards. Verified with a throwaway launchd job.

The current implementation just waits `THINGS_FLUSH_WAIT_SECONDS` (10 s) —
longer than the flush timer — before reading. That needs no permissions and no
focus. It only works because App Nap is disabled (above); with Things napping
the timer is not honoured and no amount of waiting is reliable.

Testing note: neither the URL scheme nor AppleScript is a stand-in for a GUI
edit. Both write to SQLite in under a second. Only a real click in the app
exercises the timer, so measuring this requires someone at the keyboard.
Measured 2026-08-16 with App Nap off: a GUI delete on the homeserver reached
SQLite in ~2 s.

**Changes made on other devices are a separate, slower path.** They arrive
via Things Cloud sync, which the locked homeserver picks up on its own
schedule — measured at 5½ and 7–8½ minutes for two to-dos added on a laptop.
`open -g -a Things3` was tested as a wake-up (it needs no TCC and works
locked) and does *not* trigger a sync: nothing for 3 min hands-off, nothing
for 90 s after the poke, then it landed on its own. There is no lever for
this from the service without a TCC Automation grant, so the API simply lags
remote-device edits by up to ~8 minutes. Irrelevant for a weekly report;
worth knowing for anything near-real-time.

### `/api/ssnc/completed` contract

Consumed over the tailnet by automation-backend on a weekly schedule. **The
response shape and the `since` parameter are a stable contract — don't change
them.**

```
GET /api/ssnc/completed?since=26w
```

- `since` is required and takes a count plus a unit — `7d`, `1w`, `26w`, `3m`,
  `1y`. An unparseable value returns 400 rather than a 500.
- The window is measured against each to-do's **completion** date (`stop_date`),
  i.e. when it was actually finished. See the warning below.
- Returns a bare JSON array of completed to-do objects, consumed directly.
- Filters to to-dos whose `project_title` starts with `SSNC` — a prefix match,
  not an exact project name.
- An empty array means nothing was logged in that window. It is a normal
  result, not an error.

**Do not "simplify" this back to `things.completed(last=since)`.** That looks
like the obvious implementation and is wrong: `last=` filters on
`TASK.creationDate`, not completion date. A to-do created three weeks ago and
checked off yesterday is then absent from a `?since=1w` query — silently, with
no error, indistinguishable from an empty week. About a third of the completed
to-dos in this database span a week or more between creation and completion,
and a weekly report is precisely the case where that matters. `completed_since()`
filters on `stop_date` for this reason. Upstream hit the same bug in
`get_logbook` and fixed it the same way (hald/things-mcp#46).

### Required patch to things.py

This deployment depends on a patch to `things.py` that resolves
`project`/`project_title` and `area`/`area_title` for to-dos filed under a
**heading**. Upstream returns `NULL` for those fields in that case, because the
task row links to the heading rather than to the project.

Without the patch, `/api/ssnc/completed` matches nothing for any heading-filed
to-do and returns `[]` — which is indistinguishable from "nothing was logged"
at every layer downstream. The failure is silent. See `patches/README.md`.
