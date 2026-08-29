#!/usr/bin/env python3
"""Export a complete, decoded snapshot of a Things 3 database to JSON.

Standard library only, so it runs with the system python3 on any Mac that has
Things installed — no uv, no things.py. Run it on whichever Mac holds the most
recent data (the one that is still syncing with Things Cloud):

    python3 scripts/export_things.py > things-export.json
    python3 scripts/export_things.py --include-trashed --out things-export.json

The output is the migration source for docs/SUCCESSOR-SPEC.md. Everything the
Things database knows is in here, decoded into plain values: packed dates
become ISO dates, unix timestamps become ISO datetimes with offset, the binary
recurrence-rule plists become both their raw dictionaries and a normalized
`repeat` block whose semantics were verified against real generated
instances (see the spec).

Reads the database read-only and never writes to it.
"""

import argparse
import datetime as dt
import glob
import json
import os
import plistlib
import sqlite3
import sys

DEFAULT_GLOB = os.path.expanduser(
    "~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/"
    "ThingsData-*/Things Database.thingsdatabase/main.sqlite"
)

TYPE = {0: "to-do", 1: "project", 2: "heading"}
STATUS = {0: "open", 2: "canceled", 3: "completed"}
START = {0: "inbox", 1: "anytime", 2: "someday"}
REPEAT_UNIT = {16: "day", 256: "week", 8: "month", 4: "year"}
REPEAT_MODE = {0: "fixed_schedule", 1: "after_completion"}
# Far-future sentinel Things stores when a rule has no end date.
NO_END_DATE = 4e10


def packed_date(value):
    """Things packs dates as YYYYYYYYYYYMMMMDDDDD0000000 in an integer."""
    if not value:
        return None
    year, month, day = (value >> 16) & 0x7FF, (value >> 12) & 0xF, (value >> 7) & 0x1F
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def packed_time(value):
    """reminderTime is hhhhhmmmmmm followed by 20 zero bits."""
    if value is None:
        return None
    return f"{value >> 26:02d}:{(value >> 20) & 0x3F:02d}"


def _from_unix(value):
    if value is None:
        return None
    try:
        return dt.datetime.fromtimestamp(value).astimezone()
    except (ValueError, OverflowError, OSError):
        # Things uses sentinels far outside the unix range (year 1, year 4001)
        # to mean "unset"; treat them as absent.
        return None


def unix_ts(value):
    d = _from_unix(value)
    return d.isoformat(timespec="seconds") if d else None


def unix_date(value):
    d = _from_unix(value)
    return d.date().isoformat() if d else None


def normalize_rule(rule):
    """Translate Things' rt1_recurrenceRule plist into readable fields.

    Field meanings, each checked against generated instances in a live DB:
      fu  unit: 16=day 256=week 8=month 4=year
      fa  interval ("every fa units")
      tp  0 = fixed schedule, 1 = after completion
      of  list of "on" specs; dy and mo are ZERO-based, wd 0=Sunday,
          wdo ordinal within the month (-1 = last)
      ts  start offset in days relative to the rule date (<= 0). When nonzero
          the rule date becomes the instance DEADLINE and the instance's start
          date is rule date + ts, so it shows up |ts| days ahead.
      sr  rule start reference date; ia  most recent instance anchor date
      ed  end date (far-future sentinel = none); rc  repeat count (0 = none)
      rrv rule format version (4 everywhere in the source DB)
    """
    on = []
    for spec in rule.get("of") or []:
        entry = {}
        if "mo" in spec:
            entry["month"] = spec["mo"] + 1
        if "dy" in spec:
            entry["day"] = spec["dy"] + 1
        if "wd" in spec:
            entry["weekday"] = spec["wd"]  # 0 = Sunday ... 6 = Saturday
        if "wdo" in spec:
            entry["weekday_ordinal"] = spec["wdo"]  # 1 = first, -1 = last
        on.append(entry)
    end = rule.get("ed")
    return {
        "unit": REPEAT_UNIT.get(rule.get("fu"), f"unknown:{rule.get('fu')}"),
        "interval": rule.get("fa"),
        "mode": REPEAT_MODE.get(rule.get("tp"), f"unknown:{rule.get('tp')}"),
        "on": on,
        "start_offset_days": rule.get("ts", 0),
        "rule_start_date": unix_date(rule.get("sr")),
        "last_anchor_date": unix_date(rule.get("ia")),
        "end_date": None if (end is None or end > NO_END_DATE) else unix_date(end),
        "repeat_count": rule.get("rc") or None,
        "rule_version": rule.get("rrv"),
    }


def export(db_path, include_trashed):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    q = conn.execute

    areas = [
        {"uuid": r["uuid"], "title": r["title"], "visible": bool(r["visible"]), "index": r["index"]}
        for r in q("SELECT uuid, title, visible, [index] FROM TMArea ORDER BY [index]")
    ]
    tags = [
        {
            "uuid": r["uuid"],
            "title": r["title"],
            "shortcut": r["shortcut"],
            "parent": r["parent"],
            "index": r["index"],
        }
        for r in q("SELECT uuid, title, shortcut, parent, [index] FROM TMTag ORDER BY [index]")
    ]
    area_tags = {}
    for r in q("SELECT areas, tags FROM TMAreaTag"):
        area_tags.setdefault(r["areas"], []).append(r["tags"])
    for a in areas:
        a["tags"] = area_tags.get(a["uuid"], [])

    task_tags = {}
    for r in q("SELECT tasks, tags FROM TMTaskTag"):
        task_tags.setdefault(r["tasks"], []).append(r["tags"])

    checklists = {}
    for r in q(
        "SELECT uuid, task, title, status, stopDate, [index], creationDate, userModificationDate "
        "FROM TMChecklistItem ORDER BY task, [index]"
    ):
        checklists.setdefault(r["task"], []).append(
            {
                "uuid": r["uuid"],
                "title": r["title"],
                "status": STATUS.get(r["status"], r["status"]),
                "stop_date": unix_ts(r["stopDate"]),
                "index": r["index"],
                "created": unix_ts(r["creationDate"]),
                "modified": unix_ts(r["userModificationDate"]),
            }
        )

    where = "" if include_trashed else "WHERE trashed = 0"
    tasks = []
    counts = {"to-do": 0, "project": 0, "heading": 0, "repeat_template": 0, "trashed": 0}
    for r in q(f"SELECT * FROM TMTask {where} ORDER BY creationDate"):
        task = {
            "uuid": r["uuid"],
            "type": TYPE.get(r["type"], r["type"]),
            "status": STATUS.get(r["status"], r["status"]),
            "trashed": bool(r["trashed"]),
            "title": r["title"] or "",
            "notes": r["notes"] or "",
            "start": START.get(r["start"], r["start"]),
            "start_date": packed_date(r["startDate"]),
            "evening": r["startBucket"] == 1,
            "reminder_time": packed_time(r["reminderTime"]),
            "deadline": packed_date(r["deadline"]),
            "stop_date": unix_ts(r["stopDate"]),
            "created": unix_ts(r["creationDate"]),
            "modified": unix_ts(r["userModificationDate"]),
            "index": r["index"],
            "today_index": r["todayIndex"],
            "area": r["area"],
            "project": r["project"],
            "heading": r["heading"],
            "tags": task_tags.get(r["uuid"], []),
            "checklist": checklists.get(r["uuid"], []),
            "repeat_template": r["rt1_repeatingTemplate"],
        }
        task["is_repeat_template"] = r["rt1_recurrenceRule"] is not None
        if task["is_repeat_template"]:
            # A template is not a real to-do: Things parks it in Someday with a
            # placeholder deadline (year 1953) and no start date. The schedule
            # lives entirely in `repeat`; blank the placeholders so an importer
            # cannot mistake them for data.
            task["deadline"] = None
            task["start_date"] = None
            raw = plistlib.loads(r["rt1_recurrenceRule"])
            repeat = normalize_rule(raw)
            repeat.update(
                {
                    "next_instance_date": packed_date(r["rt1_nextInstanceStartDate"]),
                    "instance_creation_start_date": packed_date(r["rt1_instanceCreationStartDate"]),
                    "instances_created": r["rt1_instanceCreationCount"],
                    "paused": bool(r["rt1_instanceCreationPaused"]),
                    "after_completion_reference_date": unix_date(r["rt1_afterCompletionReferenceDate"]),
                    "raw": {k: (v if not isinstance(v, bytes) else v.hex()) for k, v in raw.items()},
                }
            )
            task["repeat"] = repeat
            counts["repeat_template"] += 1
        if not task["is_repeat_template"]:
            counts[task["type"]] = counts.get(task["type"], 0) + 1
        if task["trashed"]:
            counts["trashed"] += 1
        tasks.append(task)

    return {
        "export": {
            "format": "things-export/1",
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_db": db_path,
            "source_db_mtime": unix_ts(os.path.getmtime(db_path)),
            "include_trashed": include_trashed,
            "counts": {**counts, "areas": len(areas), "tags": len(tags),
                       "checklist_items": sum(len(v) for v in checklists.values())},
            "encodings": {
                "type": TYPE, "status": STATUS, "start": START,
                "repeat.unit": REPEAT_UNIT, "repeat.mode": REPEAT_MODE,
                "weekday": "0=Sunday ... 6=Saturday",
                "dates": "YYYY-MM-DD local; timestamps ISO 8601 with UTC offset",
            },
        },
        "areas": areas,
        "tags": tags,
        "tasks": tasks,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="path to main.sqlite (default: the Things DB in this user's Group Containers)")
    ap.add_argument("--include-trashed", action="store_true", help="include trashed items (off by default)")
    ap.add_argument("--out", help="write here instead of stdout")
    args = ap.parse_args()

    db = args.db or (glob.glob(DEFAULT_GLOB) or [None])[0]
    if not db or not os.path.exists(db):
        sys.exit(f"Things database not found (looked at {args.db or DEFAULT_GLOB}); pass --db")

    data = export(db, args.include_trashed)
    text = json.dumps(data, indent=1, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        c = data["export"]["counts"]
        print(f"wrote {args.out}: {c}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
