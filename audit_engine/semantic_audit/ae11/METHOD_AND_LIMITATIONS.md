# AE-11 — FEM Numerical Invariants, Mechanical Units, and Mesh-Refinement Evidence

## Scientific claim

A report marked `consistent_within_declared_checks` establishes only that the *specified*
linear-static FEM numerical facts satisfy **seven necessary, explicitly scoped** checks
against an unchanged, SHA-256-bound input. It is not a certificate that governing equations,
boundary physics, discretization, constitutive laws, material properties, or experimental data
are correct. The allowed unit tuples are `(N,m,N/m,J)`, `(kN,m,kN/m,kN*m)`, and
`(N,mm,N/mm,N*mm)`; the audit does **not** perform unit conversion.

## Seven tested properties

1. Global stiffness symmetry: `max |Kij - Kji| <= symmetry_abs`.
2. Free-DOF equilibrium: `max |(Ku-f)_i| <= residual_abs` for **free** DOFs only. Fixed-DOF
   residuals may be legitimate reaction forces and are not asserted to vanish.
3. Dirichlet boundary consistency: `max |u_fixed - prescribed| <= fixed_abs`.
4. Stable constrained operator: a positive LDLᵀ pivot test for the **symmetric free-free
   block**, not for the singular full rigid-body matrix. Eigenvalue scale, pivoting, and
   conditioning are not assessed. A matrix can be poorly conditioned even when this passes.
5. Strain-energy consistency: `|0.5 uᵀKu - declared_energy| <= energy_abs`. The declared
   energy is not independently measured or verified as physically correct.
6. Monotone refinement evidence: `error(h_next) <= error(h_previous) + tolerance`.
7. Observed convergence order: `ln(error_i/error_{i+1}) / ln(h_i/h_{i+1}) >= order_min`.
   All sampled errors and mesh sizes must be strictly positive and sizes decreasing.
   Observed rates do not establish an asymptotic limit or bound unknown true error.

The model requires an explicitly declared small-displacement linear-static, symmetric,
stable-constrained setting. The audit limits matrices to 80 degrees of freedom and
refinement series to 64 levels to make high-precision decimal assessment bounded.

## Provenance and architecture

Raw JSON evidence is read only within a symlink-restricted root; the manifest fixes its
SHA-256. Scientific quantities must be decimal **strings**, not binary JSON floats.
Audit observations are projected into the existing `SemanticGraph` as `FEMModel`,
`EvidenceArtifact` and `FEMNumericalCheck` entities with `EVIDENCED_BY` and `CHECKED_BY`
relationships. The canonical graph fingerprint and original source hash are sealed into a
content-addressed report. This is a graph of **audit observations**; the graph edges alone
do not establish independent scientific support. Native AE-10 claim/evidence verification
remains separately available and is not implicitly asserted to have run in AE-11.

Detached verification recomputes all checks from the declared bytes and compares the
entire canonical report before accepting the publication. The `LATEST.json` pointer is set
to `running` before publishing and to `failed` on errors; an old successful generation
is never advertised as current after failure. Existing historical generations remain
retained and independently identifiable.

## Limitations and trust assumptions

- Trusted local CI and Python interpreter; the file copy is not a sandbox against malicious code.
- User-declared tolerances are not independently validated against measurement uncertainty.
- Zero numerical defects detected does **not** mean mesh independence or software correctness.
- Decimal operations have 240-digit precision; extremely ill-conditioned matrices and
  underflow-like admissible values can require an independent higher-precision solver.
- Numerical residuals do not prove valid assembly; a jointly wrong matrix and solution may
  satisfy all algebraic checks.
- No transient, nonlinear, contact, eigenmode, plastic, shell or mixed-DOF physics supported.
- Repeated measurements, independent oracle datasets, and model verification are future work.
