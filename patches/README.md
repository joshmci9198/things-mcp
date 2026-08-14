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

`pyproject.toml` currently consumes it via an editable local path
(`../things.py`) under `[tool.uv.sources]`, which means **a fresh clone does not
get this patch automatically.** Either apply the patch by hand (below) or, once
the branch is pushed, replace the editable source with a pinned SHA:

```toml
dependencies = [
    "things-py @ git+https://github.com/joshmci9198/things.py@<full-sha>",
]
```

Pin a full SHA, not a branch.

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
