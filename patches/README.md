# Patches

## `0001-things-py-heading-project-area-fallback.patch`

**This patch is load-bearing. `/api/ssnc/completed` returns wrong results
without it, and the failure is silent.**

### What it fixes

`things.py`'s `make_tasks_sql_query()` only resolves a task's project and area
when the task row links *directly* to a project or area. A to-do filed under a
**heading** links to the heading instead, so upstream returns:

```
project = NULL   project_title = NULL   area = NULL   area_title = NULL
```

even though the heading belongs to a project, and that project to an area.

The patch adds the missing fallbacks — project via `PROJECT_OF_HEADING`, area
via `PROJECT.area` and `PROJECT_OF_HEADING.area`, plus the two joins needed to
reach the area rows. Direct links still take precedence, so rows that already
resolved are unchanged; only `NULL`s become populated.

### Why it matters here

`/api/ssnc/completed` filters completed to-dos on `project_title.startswith("SSNC")`.
The SSNC to-dos are filed under headings. Without the patch their
`project_title` is `NULL`, the filter matches nothing, and the endpoint returns
`[]` — indistinguishable from "nothing was logged this week" at every layer
downstream. Nothing errors. Nothing logs a warning. The weekly report is just
silently empty.

### Where it lives

Committed to the fork at `git@github.com:joshmci9198/things.py.git`, branch
`heading-project-area-fallback`, as commit `a8004a2`. Applies on top of
upstream `e67fe48`.

`pyproject.toml` consumes it as a pinned git reference, so a fresh clone gets
the patch automatically — no manual step, nothing to forget:

```toml
dependencies = [
    "things-py @ git+https://github.com/joshmci9198/things.py@a8004a269a1ebbdfb94cc23fdb1426b3284fcde3",
]
```

This is a full SHA on purpose. A branch name would let the dependency change
under the service without anything in this repo changing — exactly the silent
drift this patch exists to prevent. `[tool.hatch.metadata] allow-direct-references`
is set because hatchling rejects direct references otherwise.

**Changing `things.py` now takes a commit, not an edit.** Editing a local
`../things.py` checkout no longer affects this service. To change it: commit and
push to the fork, then update the SHA above and re-run `uv sync`.

The `.patch` file beside this README is kept as a readable record of what the
change is and a fallback if the fork ever becomes unavailable.

### Applying by hand

```bash
git clone https://github.com/thingsapi/things.py ../things.py
cd ../things.py && git checkout e67fe48
git apply ../things-mcp-wired/patches/0001-things-py-heading-project-area-fallback.patch
```

### Upstreaming

This looks like a genuine upstream bug — tasks under headings returning null
project/area is wrong for every consumer, not just this deployment. Worth a PR
to `thingsapi/things.py`. Not blocking anything here.
