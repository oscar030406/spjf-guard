"""Streaming parse of one CodeBench semester archive into the five per-semester tables.

This is the first stage of the pipeline and the only one whose input is not already a
table: a `.tar.gz` of one semester goes in, and `assessments`, `events`, `logins`,
`codemirror` and `users` come out.  Everything downstream -- the event cache, the
features, the overlays -- starts from these.

Two properties matter and are kept from the exploratory parser this is ported from
(`prechecks/codebench/parse_codebench.py`), because they are what make the result what it
is rather than merely how it was computed:

* **Nothing is extracted to disk.**  Every member is read from the gzip stream and either
  parsed or dropped, so a 2.5 GB semester costs no disk and one pass.
* **No source code and no keystrokes are kept.**  A submission contributes the length of
  its code in characters and lines, never the text; the editor log contributes a count of
  events per minute, never the keystrokes.  From `user.data` only the degree course id is
  read.

Timestamps in this dataset are not zero padded (`2016-11-3 9:05:03` occurs), which is why
the editor-log reader detects the width of each field instead of assuming it.
"""

from __future__ import annotations

import os
import re
import tarfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

SEPARATOR = b"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*"
RE_HEAD = re.compile(
    rb"==\s+(SUBMITION|TEST)\s+\((\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})\)"
)
RE_SECTION = re.compile(
    rb"(?m)^-- (CODE|EXECUTION TIME|OUTPUT|ERROR|GRADE|TEST CASE \d+):[ \t]*$"
)
RE_ERROR_TYPE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Interrupt|Warning|Exit))\s*:"
)
RE_LOGIN = re.compile(rb"(?m)^(\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})#user/(\w+)")
RE_KEY_VALUE = re.compile(r"^-{2,4} ([^:]+):\s*(.*)$")

EVENT_COLUMNS = [
    "semester", "class", "user", "assessment", "exercise", "ts", "kind",
    "grade", "exec_time", "code_len", "code_lines", "n_testcases",
    "has_error", "error_type",
]  # fmt: skip
TABLES = ("assessments", "events", "logins", "codemirror", "users")
"""The five tables one archive produces, in the layout `data.raw_parquet_dir` holds."""

DASH, COLON, SPACE = 45, 58, 32


def archive_name(semester: str, version: str = "1.81") -> str:
    """`2022-1` -> `cb_dataset_2022_1_v1.81.tar.gz`, the publisher's own naming."""
    return f"cb_dataset_{semester.replace('-', '_')}_v{version}.tar.gz"


def semester_of(archive: str | Path) -> str:
    """The semester tag an archive file name carries."""
    stem = Path(archive).name
    match = re.search(r"cb_dataset_(\d{4}_[A-Za-z0-9]+)_v", stem)
    if not match:
        raise ValueError(f"{stem} is not a CodeBench semester archive")
    return match.group(1).replace("_", "-")


def parse_assessment(raw: bytes) -> dict:
    """One assessment description file: its window, weight and exercise list."""
    fields: dict[str, str] = {}
    exercises: list[str] = []
    for line in raw.decode("utf-8", "replace").splitlines():
        found = RE_KEY_VALUE.match(line.strip())
        if not found:
            continue
        key, value = found.group(1).strip().lower(), found.group(2).strip()
        if key.startswith("exercise "):
            exercises.append(value)
        else:
            fields[key] = value
    return {
        "type": fields.get("type"),
        "weight": pd.to_numeric(fields.get("weight"), errors="coerce"),
        "start": fields.get("start"),
        "end": fields.get("end"),
        "n_exercises": pd.to_numeric(fields.get("total_exercises"), errors="coerce"),
        "exercise_ids": ",".join(exercises),
        "class_number": fields.get("class number"),
        "language": fields.get("language"),
    }


def parse_course_id(raw: bytes) -> str | None:
    """Only the degree course id is read from a user file; every other field is ignored."""
    text = raw.decode("utf-8", "replace")
    head = text.split("-- HIGH SCHOOL", 1)[0]
    found = re.search(r"course id:\s*(\S+)", head)
    return found.group(1) if found else None


def _characters(block: bytes) -> int:
    return len(block) if block.isascii() else len(block.decode("utf-8", "replace"))


def _error_type(body: bytes) -> str:
    lines = [ln for ln in body.decode("utf-8", "replace").strip().split("\n") if ln.strip()]
    if not lines:
        return "Empty"
    last = lines[-1].strip()
    found = RE_ERROR_TYPE.match(last)
    if found:
        return found.group(1)
    if last.lower().startswith("killed") or "time limit" in last.lower():
        return "TimeLimit"
    return "Other"


def _number(text: bytes) -> float | None:
    """A numeric section body, or None when the field is empty or not a number."""
    stripped = text.strip().rstrip(b"%")
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _one_execution(block: bytes, head) -> tuple:
    """One SUBMITION or TEST block: its sections, measured and then dropped."""
    fields: dict = {
        "code_len": 0,
        "code_lines": 0,
        "n_testcases": 0,
        "grade": None,
        "exec_time": None,
        "error_type": None,
        "has_error": False,
    }
    marks = list(RE_SECTION.finditer(block, head.end()))
    for index, mark in enumerate(marks):
        name = mark.group(1)
        stop = marks[index + 1].start() if index + 1 < len(marks) else len(block)
        body = block[mark.end() + 1 : stop]
        if name == b"CODE":
            body = body.rstrip(b"\n")
            fields["code_len"] = _characters(body)
            fields["code_lines"] = body.count(b"\n") + 1 if body else 0
        elif name == b"EXECUTION TIME":
            fields["exec_time"] = _number(body)
        elif name == b"GRADE":
            fields["grade"] = _number(body)
        elif name.startswith(b"TEST CASE"):
            fields["n_testcases"] += 1
        elif name == b"ERROR":
            fields["has_error"] = True
            fields["error_type"] = _error_type(body)
    return (
        head.group(2).decode(),
        "submit" if head.group(1) == b"SUBMITION" else "test",
        fields["grade"],
        fields["exec_time"],
        fields["code_len"],
        fields["code_lines"],
        fields["n_testcases"],
        fields["has_error"],
        fields["error_type"],
    )


def parse_executions(raw: bytes) -> list[tuple]:
    """One tuple per SUBMITION or TEST block of one execution log.

    The code body is measured and dropped: its length in characters and in lines is what
    the study uses, and keeping the text would make the derived tables a copy of the
    students' work.
    """
    out = []
    for block in raw.split(SEPARATOR):
        head = RE_HEAD.search(block)
        if head is not None:
            out.append(_one_execution(block, head))
    return out


def parse_codemirror_minutes(raw: bytes):
    """(minute key YYYYMMDDHHMM, count, lines seen), without keeping a keystroke.

    The widths of month, day and hour are read per line rather than assumed, because the
    dataset does not zero pad them.  A line whose leading timestamp does not parse is
    counted but not used, which is what `cm_line_coverage` reports.
    """
    if not raw:
        return None
    data = np.frombuffer(raw, dtype=np.uint8)
    newlines = np.flatnonzero(data == 10)
    starts = np.empty(newlines.size + 1, dtype=np.int64)
    starts[0] = 0
    starts[1:] = newlines + 1
    starts = starts[starts + 20 <= data.size]
    if starts.size == 0:
        return None

    def at(offset: int) -> np.ndarray:
        return data[starts + offset].astype(np.int64)

    d0, d1, d2, d3 = at(0), at(1), at(2), at(3)
    digits = (
        (d0 >= 48) & (d0 <= 57) & (d1 >= 48) & (d1 <= 57)
        & (d2 >= 48) & (d2 <= 57) & (d3 >= 48) & (d3 <= 57) & (at(4) == DASH)
    )  # fmt: skip
    year = (d0 - 48) * 1000 + (d1 - 48) * 100 + (d2 - 48) * 10 + (d3 - 48)

    month_width = np.where(at(6) == DASH, 1, 2)
    month = np.where(month_width == 1, at(5) - 48, (at(5) - 48) * 10 + (at(6) - 48))
    day_at = 5 + month_width + 1
    day_width = np.where(data[starts + day_at + 1] == SPACE, 1, 2)
    first = data[starts + day_at].astype(np.int64)
    second = data[starts + day_at + 1].astype(np.int64)
    day = np.where(day_width == 1, first - 48, (first - 48) * 10 + (second - 48))
    hour_at = day_at + day_width + 1
    hour_width = np.where(data[starts + hour_at + 1] == COLON, 1, 2)
    first = data[starts + hour_at].astype(np.int64)
    second = data[starts + hour_at + 1].astype(np.int64)
    hour = np.where(hour_width == 1, first - 48, (first - 48) * 10 + (second - 48))
    minute_at = hour_at + hour_width + 1
    minute = (data[starts + minute_at].astype(np.int64) - 48) * 10 + (
        data[starts + minute_at + 1].astype(np.int64) - 48
    )

    usable = digits & (
        (month >= 1) & (month <= 12) & (day >= 1) & (day <= 31)
        & (hour >= 0) & (hour <= 23) & (minute >= 0) & (minute <= 59)
        & (data[starts + day_at - 1] == DASH) & (data[starts + hour_at - 1] == SPACE)
        & (data[starts + minute_at - 1] == COLON) & (starts + minute_at + 2 <= data.size)
    )  # fmt: skip
    key = ((((year * 100 + month) * 100 + day) * 100 + hour) * 100 + minute)[usable]
    if key.size == 0:
        return None
    unique, counts = np.unique(key, return_counts=True)
    return unique, counts, int(starts.size)


def to_datetime(series: pd.Series, fmt: str) -> pd.Series:
    """Parse timestamps, falling back to per-element inference for the odd row."""
    out = pd.to_datetime(series, format=fmt, errors="coerce")
    bad = out.isna() & series.notna() & (series.astype(str).str.len() > 0)
    if bad.any():
        out.loc[bad] = pd.to_datetime(series[bad], format="mixed", errors="coerce")
    return out


class _Collected:
    """The rows one archive walk accumulates, before they become frames."""

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.logins: list[tuple] = []
        self.assessments: list[dict] = []
        self.users: list[dict] = []
        self.minute_keys: list[np.ndarray] = []
        self.minute_counts: list[np.ndarray] = []
        self.minute_meta: list[tuple] = []
        self.files = dict.fromkeys(
            ("executions", "codemirror", "logins", "assessments", "users", "other"), 0
        )
        self.bytes_read = 0
        self.exec_time_filled = [0, 0]
        self.codemirror_lines = [0, 0]
        self.semester: str | None = None


def _take_member(tar, member, collected: _Collected) -> None:
    """Route one archive member to its parser.  Nothing is written to disk."""
    parts = member.name.split("/")
    if len(parts) < 4:
        collected.files["other"] += 1
        return
    collected.semester = parts[0]
    class_id = parts[1]
    if parts[2] == "assessments":
        raw = tar.extractfile(member).read()
        collected.bytes_read += len(raw)
        collected.files["assessments"] += 1
        row = parse_assessment(raw)
        row.update(
            semester=collected.semester,
            assessment=os.path.splitext(parts[3])[0],
            **{"class": class_id},
        )
        collected.assessments.append(row)
        return
    if parts[2] != "users" or len(parts) < 5:
        collected.files["other"] += 1
        return
    _take_user_file(tar, member, collected, class_id, parts)


def _take_user_file(tar, member, collected: _Collected, class_id: str, parts: list) -> None:
    """One file under a user's directory: their record, logins, runs or editor log."""
    user, leaf, kind = parts[3], parts[-1], parts[4]
    if kind == "user.data":
        raw = tar.extractfile(member).read()
        collected.bytes_read += len(raw)
        collected.files["users"] += 1
        collected.users.append(
            {
                "semester": collected.semester,
                "class": class_id,
                "user": user,
                "course_id": parse_course_id(raw),
            }
        )
    elif kind == "logins.log":
        raw = tar.extractfile(member).read()
        collected.bytes_read += len(raw)
        collected.files["logins"] += 1
        for found in RE_LOGIN.finditer(raw):
            collected.logins.append(
                (
                    collected.semester,
                    class_id,
                    user,
                    found.group(1).decode(),
                    found.group(2).decode(),
                )
            )
    elif kind == "executions":
        raw = tar.extractfile(member).read()
        collected.bytes_read += len(raw)
        collected.files["executions"] += 1
        assessment, _, exercise = os.path.splitext(leaf)[0].partition("_")
        for row in parse_executions(raw):
            stamp, event_kind, grade, exec_time = row[0], row[1], row[2], row[3]
            if event_kind == "submit":
                collected.exec_time_filled[1] += 1
                if exec_time is not None:
                    collected.exec_time_filled[0] += 1
            collected.events.append(
                (collected.semester, class_id, user, assessment, exercise, stamp, event_kind)
                + (grade, exec_time)
                + row[4:]
            )
    elif kind == "codemirror":
        raw = tar.extractfile(member).read()
        collected.bytes_read += len(raw)
        collected.files["codemirror"] += 1
        parsed = parse_codemirror_minutes(raw)
        if parsed is not None:
            unique, counts, lines = parsed
            collected.codemirror_lines[0] += lines
            collected.codemirror_lines[1] += int(counts.sum())
            assessment, _, exercise = os.path.splitext(leaf)[0].partition("_")
            collected.minute_keys.append(unique)
            collected.minute_counts.append(counts)
            collected.minute_meta.append((class_id, user, assessment, exercise, unique.size))
    else:
        collected.files["other"] += 1


def _frames(collected: _Collected) -> dict[str, pd.DataFrame]:
    """The five tables, typed as the parquet on disk is typed."""
    semester = collected.semester
    assessments = pd.DataFrame(collected.assessments)
    if len(assessments):
        assessments["start"] = to_datetime(assessments["start"], "%Y-%m-%d %H:%M")
        assessments["end"] = to_datetime(assessments["end"], "%Y-%m-%d %H:%M")
        assessments = assessments[
            ["semester", "class", "assessment", "type", "weight", "start", "end",
             "n_exercises", "exercise_ids", "language"]
        ]  # fmt: skip

    events = pd.DataFrame(collected.events, columns=EVENT_COLUMNS)
    if len(events):
        events["ts"] = to_datetime(events["ts"], "%Y-%m-%d %H:%M:%S")
        for column in ("grade", "exec_time"):
            events[column] = pd.to_numeric(events[column], errors="coerce").astype("float32")
        for column in ("code_len", "code_lines", "n_testcases"):
            events[column] = pd.to_numeric(events[column], errors="coerce").astype("int32")
        events["kind"] = events["kind"].astype("category")
        events["error_type"] = events["error_type"].astype("category")

    logins = pd.DataFrame(collected.logins, columns=["semester", "class", "user", "ts", "kind"])
    if len(logins):
        logins["ts"] = to_datetime(logins["ts"], "%Y-%m-%d %H:%M:%S")
        logins["kind"] = logins["kind"].astype("category")

    columns = ["semester", "class", "user", "assessment", "exercise", "minute", "n_events"]
    if collected.minute_keys:
        keys = np.concatenate(collected.minute_keys)
        counts = np.concatenate(collected.minute_counts)
        repeats = np.array([meta[4] for meta in collected.minute_meta], dtype=np.int64)

        def spread(position: int) -> np.ndarray:
            values = np.array([meta[position] for meta in collected.minute_meta], dtype=object)
            return np.repeat(values, repeats)

        codemirror = pd.DataFrame(
            {
                "semester": semester,
                "class": spread(0),
                "user": spread(1),
                "assessment": spread(2),
                "exercise": spread(3),
                "minute": pd.to_datetime(
                    keys.astype(str), format="%Y%m%d%H%M", errors="coerce"
                ),
                "n_events": counts.astype("int32"),
            }
        )
    else:
        codemirror = pd.DataFrame(columns=columns)
    return {
        "assessments": assessments,
        "events": events,
        "logins": logins,
        "codemirror": codemirror,
        "users": pd.DataFrame(collected.users),
    }


def _statistics(collected: _Collected, tables: dict, seconds: float) -> dict:
    events, users = tables["events"], tables["users"]
    codemirror = tables["codemirror"]
    return {
        "semester": collected.semester,
        "seconds": round(seconds, 1),
        "uncompressed_mb": round(collected.bytes_read / 1e6, 1),
        "n_assessments": len(tables["assessments"]),
        "n_users": len(users),
        "n_classes": int(users["class"].nunique()) if len(users) else 0,
        "n_events": len(events),
        "n_submit": int((events["kind"] == "submit").sum()) if len(events) else 0,
        "n_test": int((events["kind"] == "test").sum()) if len(events) else 0,
        "n_logins": len(tables["logins"]),
        "n_cm_rows": len(codemirror),
        "cm_events": int(codemirror["n_events"].sum()) if len(codemirror) else 0,
        "exec_time_filled_share": round(
            collected.exec_time_filled[0] / max(1, collected.exec_time_filled[1]), 4
        ),
        "cm_line_coverage": round(
            collected.codemirror_lines[1] / max(1, collected.codemirror_lines[0]), 5
        ),
        "files_exec": collected.files["executions"],
        "files_cm": collected.files["codemirror"],
        "ev_ts_min": str(events["ts"].min()) if len(events) else "",
        "ev_ts_max": str(events["ts"].max()) if len(events) else "",
    }


def parse_archive(path: Path) -> tuple[dict[str, pd.DataFrame], dict]:
    """One semester archive to its five tables, plus what the pass saw.

    The archive is read once, as a stream; nothing is extracted and nothing is written.
    """
    started = time.time()
    collected = _Collected()
    with tarfile.open(path, "r|gz") as tar:
        for member in tar:
            if member.isfile():
                _take_member(tar, member, collected)
    if collected.semester is None:
        raise ValueError(f"{path} held no semester directory")
    tables = _frames(collected)
    return tables, _statistics(collected, tables, time.time() - started)


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path, semester: str) -> list[Path]:
    """The five tables, one parquet each, in the layout the rest of the package reads."""
    written = []
    for name in TABLES:
        folder = Path(out_dir) / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{semester}.parquet"
        tables[name].to_parquet(path, index=False)
        written.append(path)
    return written
