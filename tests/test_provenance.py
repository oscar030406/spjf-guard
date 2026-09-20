"""The manifest has to catch exactly what it claims to catch.

Three cases decide it: an untouched directory is silent, a hand-edited table is named,
and a changed configuration makes the tables stale even when nobody touched them.
"""

from __future__ import annotations

import json

from spjf_guard.experiment import provenance


def _directory(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "main_table.csv").write_text("policy,p99\nFCFS,1.0\n", encoding="utf-8")
    (out / "main_cells.csv").write_text("overlay,level\n0,0\n", encoding="utf-8")
    config = tmp_path / "main.yaml"
    config.write_text("run:\n  output_dir: outputs\n", encoding="utf-8")
    manifest = provenance.write(
        out,
        produced_by="scripts/run_main.py",
        config_path=config,
        outputs=[out / "main_table.csv", out / "main_cells.csv"],
        inputs=[tmp_path / "primary_rep0.npz"],
        arguments={"pool": "primary"},
    )
    return out, config, manifest


def test_an_untouched_directory_has_no_complaints(tmp_path):
    _, _, manifest = _directory(tmp_path)
    assert provenance.verify(manifest) == []


def test_a_hand_edited_table_is_named(tmp_path):
    out, _, manifest = _directory(tmp_path)
    (out / "main_table.csv").write_text("policy,p99\nFCFS,0.5\n", encoding="utf-8")
    complaints = provenance.verify(manifest)
    assert len(complaints) == 1
    assert "main_table.csv" in complaints[0]


def test_a_deleted_table_is_named(tmp_path):
    out, _, manifest = _directory(tmp_path)
    (out / "main_cells.csv").unlink()
    assert any("main_cells.csv" in c for c in provenance.verify(manifest))


def test_a_changed_configuration_makes_the_tables_stale(tmp_path):
    _, config, manifest = _directory(tmp_path)
    config.write_text("run:\n  output_dir: elsewhere\n", encoding="utf-8")
    assert any("stale" in c for c in provenance.verify(manifest))


def test_an_absent_input_is_not_a_complaint(tmp_path):
    _, _, manifest = _directory(tmp_path)
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    assert recorded["inputs"][0]["present"] is False
    assert provenance.verify(manifest) == []
