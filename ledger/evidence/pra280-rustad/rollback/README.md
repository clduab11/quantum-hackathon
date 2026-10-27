# PRA-280: chemistry-only rollback, pra280-rustad → pra261-schur

Remedy 1 of the PRA-290 send-back. The procedure, archive delta and
boundaries are in `docs/reports/pra280-chemistry.md` (sections "Archive delta"
and "Rollback"). This directory holds the command and its rehearsal record.

| Item | Value |
| --- | --- |
| Source bundle | `pra280-rustad.zip`, submission-008, `8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21` |
| Target | `pra261-schur.zip`, submission-007, `9fcb5fe2e82d052568e2c5857965cf87cb51ab0dd1f107ae00c188f8e07b11d5` |
| Source pin | `main` `33c8f82cde158101615b40057eb039649efbdd66` (`git archive`, frozen lockfile) |
| Declared input | Gluzdov v8 `femoco_thc_r5.npz`, `809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5` |
| Output | `/home/cld-main/work/vqcc-data/pra280-rollback-20261027/rollback.zip`, `9fcb5fe2…07b11d5` (archive-identical to the target) |

- [Exact command](rehearsal-command.sh); [raw output](rehearsal.log);
  [exit status and timestamps](rehearsal-exit.json): exit 0, 39 s.
- [Complete before/after member hashes and delta](member-hashes.json):
  17 ANGLE members removed (`angle_k_8`–`angle_k_24`), 8 ANGLE members and
  `submission.npz` restored, nothing added; `dqi.kmb` and `invsqrt.kmb`
  byte-equal (`BYTE-EQUAL` lines in the raw output).
- [Target check](check-target.py): [before](target-before.log) exits 1 on
  `pra280-rustad.zip`; [after](target-after.log) exits 0 on the output.
- [Repeat refusal](repeat-refusal.log): exit 1 before any write; output
  hash unchanged.
- Repository checks on this branch: [uv sync](uv-sync.log),
  [pytest](pytest.log) (391 passed, 11 skipped), [registers](registers.log).

Binaries stay outside Git. This record grants no upload, merge or sign-off.
