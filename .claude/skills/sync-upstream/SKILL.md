---
name: sync-upstream
description: Pull upstream changes into the Things MCP homeserver deployment without losing local patches. Use when syncing things-mcp-wired with hald/things-mcp or things.py with thingsapi/things.py, updating the pinned things-py SHA, or when asked to "update from upstream", "merge upstream", "check for upstream changes", or "update the Things MCP server".
---

# Sync upstream into the Things deployment

Two repos, each a fork carrying local work that must survive the update. The
failure mode is silent: the service keeps returning `200 OK` with an empty or
incomplete array. **Verification at the end is not optional.**

## Layout

| Repo | Path | Mirror branch | Our branch | Upstream |
|---|---|---|---|---|
| MCP server | `~/mac-agents/things-mcp-wired` | `master` | `wired` | `hald/things-mcp` |
| DB library | `~/mac-agents/things.py` | `main` | `heading-project-area-fallback` | `thingsapi/things.py` |

`origin` is `joshmci9198/<repo>` in both. Mirror branches track upstream and
carry **no** local commits — never commit to them.

The two repos are coupled: `things-mcp-wired/pyproject.toml` pins `things-py` to
a **full SHA** on the fork. Changing `things.py` means re-pinning here.

## What must survive

1. **`things.py` heading patch** (`things/database.py`) — resolves
   `project`/`project_title`/`area`/`area_title` for to-dos filed under a
   heading. Upstream returns `NULL`. Without it `/api/ssnc/completed` matches
   nothing and returns `[]`.
2. **`api_server.py`** — Starlette app mounting MCP at `/mcp` and REST at
   `/api/*`. Upstream has no equivalent; it only offers MCP-only
   `mcp.run(transport="http")`.
3. **`completed_since()`** — filters on `stop_date`. Upstream's `last=` filters
   on `creationDate`, which silently drops anything created before the window.
4. **`nudge_things()`** — Things buffers writes; without a focus switch the
   SQLite reads are stale.

## Procedure

### 1. Preflight — capture a baseline before touching anything

```bash
cd ~/mac-agents/things-mcp-wired
# git status exits 0 whether clean or dirty, so test the output, not the code
for r in . ../things.py; do
  [ -z "$(git -C $r status --porcelain)" ] && echo "clean: $r" || { echo "DIRTY: $r"; git -C $r status --short; }
done
curl -s -m 10 http://localhost:3400/api/health || echo "SERVICE DOWN"
curl -s -m 60 'http://localhost:3400/api/ssnc/completed?since=26w' > /tmp/baseline.json
python3 -c "import json;d=json.load(open('/tmp/baseline.json'));print(len(d),'items')"
git rev-parse HEAD > /tmp/rollback-wired.sha
git -C ../things.py rev-parse HEAD > /tmp/rollback-thingspy.sha
```

Record the count. If either repo reports `DIRTY`, stop and ask — do not stash
silently. The two recorded SHAs are the rollback targets for step 8; capture
them before anything moves.

**If the service is already down or the baseline fails to parse, stop.** Without
a known-good baseline there is nothing to compare against afterwards, and a sync
would turn a pre-existing failure into one that looks caused by the update. Fix
or diagnose first, then start over.

### 2. Fetch and report before changing anything

```bash
git fetch upstream && git -C ../things.py fetch upstream
git log --oneline master..upstream/master
git -C ../things.py log --oneline main..upstream/main
git show upstream/master:CHANGELOG.md | head -60
```

Summarise for the user what upstream changed and which items touch files this
deployment actually uses, before proceeding. Reads go through `things.py`
(SQLite); writes go through `url_scheme.py` (Things URL scheme); v0.8.1+ adds a
third path, AppleScript, for area tools.

**If both repos report zero new commits, stop and say so.** Do not proceed to
re-pin, `uv sync`, or restart — bouncing a healthy four-month-uptime service to
apply nothing is pure risk. Each repo is independent: it is normal for one to
have updates and the other none, so sync only the one that moved.

### 2.5 Triage the changelog — decide what to adopt

**Do this before merging, and do not skip it because the merge is clean.** A
clean merge only means nothing broke; it says nothing about what was gained or
missed.

New MCP tools land on `/mcp` automatically and reach `/api/*` **never** — the
REST routes are hand-written in `api_server.py` and bypass `server.py` entirely.
So every new upstream tool is a decision. Read `docs/upstream-adoption.md` for
the propagation table, the triage questions, and what has already been decided,
then:

1. Classify each changelog entry against that table.
2. Present the ones that are genuinely a choice to the user — with a
   recommendation, not an exhaustive list. Skip anything already settled in the
   log; that is what the log is for.
3. **Record the outcome in `docs/upstream-adoption.md`, including declines.**
   An undocumented "no" gets re-asked every sync.

Adopting a tool into REST is separate work, not part of the sync. Note it as a
decision, finish the sync, and do it deliberately afterwards.

### 3. things.py first — it feeds the pin

Tag the currently-pinned commit **before** anything moves. Force-pushing leaves
the old SHA on no branch, and `pyproject.toml` may still need to roll back to
it — a dangling commit is eligible for garbage collection:

```bash
cd ~/mac-agents/things.py
git tag -f "pinned/$(git rev-parse --short HEAD)" HEAD && git push -f origin --tags
```

Then sync, as a single `&&` chain so a failure actually stops the sequence:

```bash
git checkout main && git merge --ff-only upstream/main && git push origin main \
  && git checkout heading-project-area-fallback && git rebase main
```

**The chain matters.** Written as separate lines, a failed `--ff-only` does not
stop the next line — you would rebase onto a stale mirror and it would look like
success.

If `--ff-only` fails, the mirror has picked up a local commit and is no longer a
mirror. Do not resolve it with a merge — inspect with
`git log upstream/main..main`, and once you know what the stray commit is,
either move it onto the work branch or reset the mirror with
`git reset --hard upstream/main`. Ask before discarding anything.

If the rebase stops on a conflict and you cannot resolve it confidently,
`git rebase --abort` returns the branch exactly as it was. Do that rather than
guessing at SQL you don't understand.

Rebase, don't merge — keeps the patch a single clean commit on top of upstream
and stays PR-ready for `thingsapi/things.py`.

**Expect conflicts in `things/database.py`.** The patch edits a large SQL string
in `make_tasks_sql_query()` that upstream also touches. Resolving it means
keeping *both* upstream's changes and these fallbacks:

- `project`/`project_title` via `PROJECT_OF_HEADING`
- `area`/`area_title` via `PROJECT.area` and `PROJECT_OF_HEADING.area`
- the joins `AREA_OF_PROJECT` and `AREA_OF_PROJECT_OF_HEADING`

Direct links must keep precedence — only `NULL`s get populated. Verify before
moving on. Run this **from `~/mac-agents/things.py`** with bare `python3`: the
current directory puts the rebased *working tree* on `sys.path`, which is what
needs testing here. Using the venv python would test the old installed copy and
pass while the rebase is broken.

```bash
python3 -c "
import things
t = [x for x in things.completed() if x.get('heading_title')]
assert t, 'no heading-filed to-dos to test with'
# A heading always belongs to a project, so project_title must resolve.
no_proj = [x for x in t if not x.get('project_title')]
# An area is optional: only assert it when the parent project actually has one.
no_area = []
for x in t:
    if x.get('project_title') and not x.get('area_title'):
        p = things.get(x['project']) if x.get('project') else None
        if p and p.get('area_title'):
            no_area.append(x)
print(f'{len(t)} heading-filed to-dos')
print('FAIL: null project_title ->', len(no_proj)) if no_proj else print('OK: project resolves')
print('FAIL: null area_title despite project having one ->', len(no_area)) if no_area else print('OK: area resolves')
"
git push --force-with-lease origin heading-project-area-fallback
git rev-parse HEAD   # ← the new SHA for the pin
```

Do not assert `area_title` unconditionally — many projects legitimately sit in
no area (Things' built-in tutorial projects, for instance), and ~97 completed
to-dos here have a null area for that reason. A blanket check reports a
false failure on a perfectly intact patch.

`--force-with-lease`, never plain `--force`.

### 4. Re-pin in things-mcp-wired

Only if the SHA actually changed — compare, don't assume:

```bash
OLD=$(grep -oE 'things\.py@[0-9a-f]{40}' pyproject.toml | cut -d@ -f2)
NEW=$(git -C ../things.py rev-parse heading-project-area-fallback)
[ "$OLD" = "$NEW" ] && echo "unchanged — skip step 4" || echo "re-pin: ${OLD:0:7} -> ${NEW:0:7}"
```

If it changed, update all three together or they drift apart:

1. `pyproject.toml` — the full SHA in `things-py @ git+https://...@<sha>`
2. the vendored patch — regenerate (literal filename, no glob: the shell cannot
   expand a wildcard for a redirect target that is being rewritten):
   ```bash
   git -C ../things.py format-patch -1 heading-project-area-fallback --stdout \
     > patches/0001-things-py-heading-project-area-fallback.patch
   ```
3. `patches/README.md` — the short SHA in "Where it lives"

Grep for the old short SHA afterwards to catch any reference missed:
`grep -rn "<old-short-sha>" patches/ README.md pyproject.toml`

### 5. Merge upstream into `wired`

One `&&` chain, for the same reason as step 3 — a failed `--ff-only` must not
fall through into merging a stale mirror:

```bash
cd ~/mac-agents/things-mcp-wired
git checkout master && git merge --ff-only upstream/master && git push origin master \
  && git checkout wired && git merge master
```

Merge here, don't rebase — `wired` is a long-lived deployment branch and its
history is worth keeping.

Conflicts are likeliest in `pyproject.toml` (dependency pins) and `README.md`.
`api_server.py` and `start.sh` should never conflict; upstream has no such files.

**If the merge crosses a FastMCP major version**, treat it as a migration, not a
merge. `api_server.py` calls `mcp.http_app(path="/")`, which upstream does not
use, so its compatibility is untested. Check that `http_app()` still exists with
that signature before restarting, and bound the pin in `pyproject.toml` to the
major version actually being tested.

### 6. Install and restart

```bash
~/.local/bin/uv sync --extra test
.venv/bin/python -c "import things,os;p=os.path.dirname(things.__file__);print(p);print('patch present:', 'AREA_OF_PROJECT' in open(p+'/database.py').read())"
~/.local/bin/uv run pytest -q
```

Use `--extra test`; a bare `uv sync` prunes the test dependencies, and then
pytest cannot run at all.

Two gates before restarting, both cheap:

1. **`patch present: True`.** The path must be inside `.venv/lib/.../site-packages`,
   not `mac-agents/things.py` — the latter means the editable local source came
   back and reproducibility is gone.
2. **The full suite passes.** 121 tests, ~2 seconds. They cover `url_scheme`,
   `formatters`, and the server tools — exactly what an upstream merge touches.
   This is the cheapest signal available and it runs *before* the live service is
   restarted, so a broken merge never reaches the tailnet.

Only then restart:

```bash
launchctl kickstart -k gui/$(id -u)/com.obsidian-sync.things-mcp
```

If tests fail, do not restart. The running service is still on the old code and
is still correct — that is the safe state to debug from.

### 7. Verify — the step that catches silent breakage

```bash
for i in $(seq 1 10); do sleep 2; curl -s -m 4 http://localhost:3400/api/health >/dev/null && break; done
curl -s -m 10 http://localhost:3400/api/health
curl -s -m 60 'http://localhost:3400/api/ssnc/completed?since=26w' | python3 -c "
import sys,json
d=json.load(sys.stdin)
base=json.load(open('/tmp/baseline.json'))
print(f'{len(d)} items (baseline {len(base)})')
bad=[t for t in d if t.get('project_title') is None]
noarea=[t for t in d if t.get('area_title') is None]
head=[t for t in d if t.get('heading_title')]
print('FAIL: null project_title ->', [t['title'] for t in bad]) if bad else print('OK: project resolves')
print('CHECK: null area_title ->', [t['title'] for t in noarea]) if noarea else print('OK: area resolves')
print('OK: heading-filed items present') if head else print('WARN: no heading-filed items — patch not actually exercised')
print('FAIL: fewer items than baseline') if len(d)<len(base) else print('OK: count >= baseline')
"
```

Pass conditions:

- `/api/health` returns `{"ok": true}`
- item count **≥ baseline** (a merge may legitimately add, never silently remove)
- **no** `null` `project_title` — a heading always belongs to a project, so a
  null here means the heading patch is gone
- heading-filed items present — otherwise the patch was never exercised

A null `area_title` is only a failure if that item's project actually has an
area. SSNC to-dos currently sit under `SSNC Report` in `Work`, so a null there
today does mean breakage — but confirm with `things.get(<project uuid>)` rather
than assuming, since a project with no area is legitimate.

`?since=1w` returning `[]` is **correct** when nothing was completed recently.
Never treat it as a failed sync; check `26w` to tell "quiet week" from "broken".

Then commit and push. Always pass a message — a bare `git commit` opens an
editor and hangs:

```bash
git add -A
git commit -F - <<'MSG'
Sync upstream <version> into wired

<what upstream changed, and which parts this deployment actually uses>

Re-pinned things-py to <sha>. Verified after restart: ?since=26w returns
<n> SSNC to-dos with project_title and area_title resolved, including
heading-filed ones; ?since=1w returns [].
MSG
git push origin wired
```

Note the `?since=26w` curl takes a few seconds — it calls `nudge_things()`,
which switches focus to Finder and back to force Things to flush. Use a
generous `-m` timeout; it is not hung.

### 8. If verification fails

Nothing here is irreversible, but **both** repos may need rolling back — step 3
force-pushes `things.py` before the verification that decides. Use the SHAs
recorded in step 1.

```bash
cd ~/mac-agents/things-mcp-wired
git checkout wired && git reset --hard "$(cat /tmp/rollback-wired.sha)"
~/.local/bin/uv sync --extra test        # restores the previously pinned things-py
launchctl kickstart -k gui/$(id -u)/com.obsidian-sync.things-mcp
```

That restores the service. If `things.py` also needs reverting:

```bash
cd ~/mac-agents/things.py
git checkout heading-project-area-fallback
git reset --hard "$(cat /tmp/rollback-thingspy.sha)"
git push --force-with-lease origin heading-project-area-fallback
```

**Why step 3 tags before force-pushing:** once the branch moves, the old commit
is on no branch. GitHub keeps such commits fetchable for a while, but they are
unreferenced and eligible for garbage collection — and `pyproject.toml` may
still be pinned to one. The `pinned/<sha>` tags keep every SHA that was ever
pinned permanently reachable. If a rollback ever reports a missing object, that
is the tag that saves it.

Re-verify with step 7, then report what failed rather than retrying blindly.

## Landmines

- **`?since=1w` → `[]` is normal.** Nothing may have been completed. Not a bug.
- **Never replace `completed_since()` with `things.completed(last=...)`.** `last=`
  filters on creation date; ~⅓ of completed to-dos span a week or more between
  creation and completion, so a weekly report silently loses them.
- **Never delete `nudge_things()`.** It looks like a pointless focus switch. It
  forces Things to flush to SQLite; without it reads are stale. It steals focus
  for ~2s, which is the accepted trade.
- **Never commit to `master` / `main`.** They are mirrors; local commits there
  break `--ff-only` on the next sync.
- **Pin a full SHA, never a branch.** A branch lets the dependency move without
  anything in this repo changing.
- **The endpoint contract is stable.** `/api/ssnc/completed` is consumed over the
  tailnet by automation-backend on a weekly schedule. Keep the bare-array
  response shape, the `since` parameter, and the `SSNC` **prefix** match.
