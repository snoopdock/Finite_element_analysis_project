# AE-02 verification scope

AE-02 source and fixture validation is **not** scientific proof of complete
repository code correctness. The evidence-verification guarantee applies to the
specific statically modeled, policy-classified import dependencies audited by
AE-01 and re-examined by AE-02. Pytest component/test-corpus evidence is
reported with denominators. No claim of measured precision/recall on real-world
defects is made.

The release `G9.2` validation profile is a GitHub dispatcher *transport* label,
not a continuation or renaming of previously completed graph-series milestones.
It is installed at `validation/profiles/G9.2.yaml`, and its test paths are
checked before packaging. All GitHub validation remains manual-only.

Adversarial checks include changed and renamed source files; consecutive
identical generations; changed import targets, moved occurrences and duplicate
imports; policy-only changes; incomplete successor scans; manipulated data and
resealed facts; unsafe symlinks and traversal generation identifiers; and CLI
failure status differentiation. G3's existing semantic graph snapshot/delta
system is reused for graph changes. Human acceptance/rejection requires an
explicit actor/evidence entry; no autonomous verdict promotion is authorized.
