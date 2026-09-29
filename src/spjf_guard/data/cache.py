"""The parsed-event cache stage: per-semester parquet files to one `ev.parquet`.

This is the last stage the study used to take from the exploratory scripts.  It reads
only the per-semester parquet already extracted from the archives (the archive parse
itself is not here, and is not part of a reproduction run), joins the code features and
the assessment windows onto the events, and writes one frame sorted by timestamp.

Which semesters are read is an argument, never a constant: the sealed terms are refused
by `sealed.guard_semesters` before a single file is opened, so building the cache for the
sealed run is the same call with the sealed list and `--unseal`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from spjf_guard.data import sealed

EVENT_KEY = ["semester", "class", "user", "assessment", "exercise", "blk_i"]
"""The stable identity of a submission block, and the key the code features join on."""

ASSESSMENT_COLUMNS = {
    "start": "a_start",
    "end": "a_end",
    "type": "a_type",
    "weight": "a_weight",
    "n_exercises": "a_nex",
}
SORT_COLUMN = "ts"


def semester_file(root: Path, kind: str, semester: str) -> Path:
    return Path(root) / kind / f"{semester}.parquet"


def files_for(root: Path, semesters) -> list[Path]:
    """Every file the build would open, in the order it would open them."""
    return [
        semester_file(root, kind, s)
        for s in semesters
        for kind in ("events", "code_features", "assessments")
    ]


def sealed_inputs(archive_dir: Path, raw_dir: Path, semesters) -> list[Path]:
    """Every sealed file the pipeline can reach: the publisher's archives and the tables
    parsed out of them.

    One list with one definition.  It used to be assembled twice -- nine files in the
    draft lock, twelve at the freeze -- so the document a person reads before freezing
    described a different set from the one that was frozen.
    """
    from spjf_guard.data.archive import archive_name

    return [Path(archive_dir) / archive_name(s) for s in semesters] + files_for(
        raw_dir, semesters
    )


def _one_semester(root: Path, semester: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    events = pd.read_parquet(semester_file(root, "events", semester))
    events["blk_i"] = (
        events.groupby(["class", "user", "assessment", "exercise"], observed=True)
        .cumcount()
        .astype("int32")
    )
    return (
        events,
        pd.read_parquet(semester_file(root, "code_features", semester)),
        pd.read_parquet(semester_file(root, "assessments", semester)),
    )


def build_events(
    raw_dir: Path,
    semesters,
    remote_semesters=(),
    project_root: Path | None = None,
    unseal: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """The joined event frame and a report of what it was built from.

    `blk_i` counts a record's position among the submissions of the same
    (class, user, assessment, exercise), which is what makes a record's identity stable
    under a rebuild and is what the deterministic jitter key hashes.
    """
    semesters = list(semesters)
    if project_root is not None:
        sealed.guard_semesters(semesters, project_root, unseal=unseal)
    events, features, assessments = [], [], []
    for semester in semesters:
        one = _one_semester(Path(raw_dir), semester)
        events.append(one[0])
        features.append(one[1])
        assessments.append(one[2])
    frame = pd.concat(events, ignore_index=True)
    feature_frame = pd.concat(features, ignore_index=True).drop(columns=["kind"])
    feature_frame = feature_frame.rename(columns={"code_len": "code_len_cf"})
    assessment_frame = pd.concat(assessments, ignore_index=True).rename(
        columns=ASSESSMENT_COLUMNS
    )
    frame = frame.merge(feature_frame, on=EVENT_KEY, how="left")
    matched = float((frame["code_len"] == frame["code_len_cf"]).mean())
    frame = frame.drop(columns=["code_len_cf"])
    frame = frame.merge(
        assessment_frame[
            [
                "semester",
                "class",
                "assessment",
                "a_type",
                "a_weight",
                "a_start",
                "a_end",
                "a_nex",
            ]
        ],
        on=["semester", "class", "assessment"],
        how="left",
    )
    frame["remote"] = frame["semester"].isin(list(remote_semesters))
    frame = frame.sort_values(SORT_COLUMN, kind="mergesort").reset_index(drop=True)
    report = {
        "semesters": semesters,
        "rows": int(len(frame)),
        "code_feature_match": round(matched, 6),
        "columns": int(frame.shape[1]),
    }
    return frame, report


def write_events(frame: pd.DataFrame, cache_dir: Path, name: str = "ev.parquet") -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / name
    frame.to_parquet(path, index=False)
    return path


def compare_frames(ours: pd.DataFrame, theirs: pd.DataFrame, semesters=None) -> list[dict]:
    """Column by column, on the rows of `semesters`: equal, or how they differ.

    Comparison is by value on the sorted frame, not by position, because two builds may
    order ties differently without disagreeing about anything.
    """
    if semesters is not None:
        ours = ours[ours["semester"].isin(list(semesters))]
        theirs = theirs[theirs["semester"].isin(list(semesters))]
    order = EVENT_KEY + [SORT_COLUMN]
    a = ours.sort_values(order, kind="mergesort").reset_index(drop=True)
    b = theirs.sort_values(order, kind="mergesort").reset_index(drop=True)
    out = []
    for column in sorted(set(a.columns) | set(b.columns)):
        row: dict = {"column": column, "rows": int(len(a))}
        if column not in a.columns or column not in b.columns:
            row["status"] = "only in ours" if column in a.columns else "only in theirs"
            out.append(row)
            continue
        if len(a) != len(b):
            row["status"] = f"row counts differ: {len(a)} against {len(b)}"
            out.append(row)
            continue
        left, right = a[column], b[column]
        if left.dtype.kind == "f" and right.dtype.kind == "f":
            same = ((left - right).abs() <= 1e-9) | (left.isna() & right.isna())
        else:
            same = (left == right) | (left.isna() & right.isna())
        differing = int((~same).sum())
        row["status"] = "equal" if differing == 0 else f"{differing} rows differ"
        row["differing"] = differing
        out.append(row)
    return out
