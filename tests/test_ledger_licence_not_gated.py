"""G5 does not gate on a parent's licence label (board directive on PRA-273, D-PRA273-01).

The label stays a record for the end-of-hackathon credits and licensure pass. The one exception is
`reference-only` (AGENTS.md R10), covered by `test_g5_rejects_reference_only_provenance` in
`test_ledger_gates.py`. Every other G5 check runs unchanged."""
from __future__ import annotations

import pytest
from conftest import git

from ledger.gates.runner import GATE_IDS, run_pipeline
from ledger.run_manifest import (
    LICENCES,
    NEVER_SHIPPED_LICENCES,
    ManifestError,
    Provenance,
    TaskRecord,
    create_manifest,
)


def _pipeline(ws, manifest):
    return run_pipeline(manifest, ws.zip_path, ws.config, queue_dir=ws.queue_dir, **ws.context())


def test_only_reference_only_is_never_shipped():
    assert NEVER_SHIPPED_LICENCES == {"reference-only"}
    assert "no-licence" in LICENCES


@pytest.mark.parametrize("licence", sorted(set(LICENCES) - NEVER_SHIPPED_LICENCES))
def test_g5_passes_every_recorded_licence(workspace, fakes, licence):
    manifest = workspace.candidate(licence=licence)
    records = _pipeline(workspace, manifest)
    assert [(r.gate, r.status) for r in records] == [(g, "PASS") for g in GATE_IDS], records
    assert (workspace.queue_dir / "cand-001.zip").exists()


def test_g5_still_rebuilds_a_no_licence_parent(workspace, fakes):
    """Dropping the licence gate waives nothing else: generator drift still fails G5."""
    gen = workspace.repo / "gen.py"
    gen.write_text(gen.read_text().replace('"generated "', '"changed "'))
    git(workspace.repo, "commit", "-qam", "generator drift")
    manifest = workspace.candidate(licence="no-licence")
    records = _pipeline(workspace, manifest)
    assert records[-1].gate == "G5" and records[-1].status == "FAIL"
    assert "rebuild differs for" in records[-1].reason
    assert not (workspace.queue_dir / "cand-001.zip").exists()


def test_no_licence_parent_still_needs_its_url():
    tasks = {t: TaskRecord(task=t, provenance=Provenance(licence="own")) for t in
             ("invsqrt", "dqi", "dfthcsos")}
    tasks["dqi"].provenance = Provenance(licence="no-licence")
    with pytest.raises(ManifestError, match="needs a parent_url"):
        create_manifest(candidate_id="c", tasks=tasks)
    tasks["dqi"].provenance = Provenance(licence="no-licence",
                                         parent_url="https://github.com/jday96314/QuantumAI")
    create_manifest(candidate_id="c", tasks=tasks)
