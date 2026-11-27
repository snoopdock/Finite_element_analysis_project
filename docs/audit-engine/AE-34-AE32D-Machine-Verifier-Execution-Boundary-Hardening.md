# AE-34 — AE-32D Machine-Verifier Execution-Boundary Hardening

**Status:** Implemented; targeted boundary tests and exact-head repository CI passed  
**Branch:** `stage1/section-uuids`  
**Validated source:** `4b028d50bea9e62e3aa8bab1077eb3e19b8bbcc8`  
**Change class:** Workflow input restriction, fixture path confinement, subprocess environment reduction, adversarial tests  
**Application scope:** Audit Engine code-audit tooling only

## 1. Finding

The original manual workflow accepted `fixture_path` as a free-form string and passed it to `tools/ae32d_machine_verify_candidate.py` as `--fixture`.

The verifier then:

1. resolved the supplied path;
2. checked whether a small set of expected filenames existed;
3. parsed those files; and
4. executed `main.py` with that directory as the subprocess working directory.

There was no requirement that the selected directory be the declared provider-interface fixture, remain beneath the checked-out repository, or avoid symlinked path components. The subprocess also inherited the complete parent environment.

This created an unnecessary arbitrary-code execution surface in a GitHub Actions job. The workflow had `contents: read`, disabled checkout credential persistence, and declared no application secrets; this record does not claim that a credential was exfiltrated. The defect was that the workflow allowed the execution target and its process environment to be broader than the stated machine-verification task required.

## 2. Decision and corrective implementation

The machine verifier now accepts only the one declared fixture:

`tests/semantic_audit/fixtures/ae32c_provider_interface_incident`

### 2.1 Remove caller-controlled executable paths

- Removed the `fixture_path` workflow-dispatch input.
- Removed the verifier's `--fixture` command-line argument.
- The repository root is derived from the verifier's own checked-out location.
- The fixture path is a constant relative to that root; callers cannot substitute another directory.

### 2.2 Constrain filesystem resolution

The verifier now:

- rejects a symlink supplied as the repository root;
- resolves the fixed fixture beneath the repository root;
- rejects symlinked components along the fixture path;
- checks every required file component with `lstat`;
- rejects symlinked required files and non-regular file targets;
- performs all these checks before the runtime reproduction step.

The verifier does not follow fixture symlinks to obtain executable source.

### 2.3 Reduce subprocess authority

The controlled runtime reproduction now uses:

- the current Python interpreter in isolated mode (`-I`) and bytecode-disabled mode (`-B`);
- an explicit fixture-directory import path, rather than ambient `PYTHONPATH`;
- a minimal environment allowlist containing only basic process-launch variables (`PATH`, and platform path/temp variables where present);
- no inherited GitHub token, provider credential, or arbitrary parent-process secret environment variable;
- `stdin=DEVNULL`, captured output, closed file descriptors, and a 15-second timeout;
- explicit timeout and launch-failure statuses.

The isolated Python process is still not an operating-system sandbox. Its filesystem and network capabilities remain those of the hosted runner. The remaining trust boundary is stated explicitly in the report and in Section 5 below.

### 2.4 Separate automatic boundary tests from manual execution

The workflow now has two modes:

- **Push to Stage1:** runs only the fixed-fixture boundary tests. It does not execute the repository's provider-interface fixture.
- **Manual dispatch:** runs the same boundary tests and, only when the operator acknowledges the machine-verification limitation, executes the one fixed fixture and emits the machine-verification artifact.

This keeps the automated push gate from turning arbitrary fixture edits into automatic runtime execution.

## 3. Adversarial regression tests

New test module:

`tests/semantic_audit/test_ae32d_machine_verification_boundary.py`

The six tests cover:

1. the fixed fixture path and expected controlled runtime failure;
2. rejection of a symlink at the fixture-directory boundary;
3. rejection of a symlinked required source file before execution;
4. rejection of a symlinked repository root;
5. absence of GitHub token and arbitrary secret variables from the runtime subprocess environment, plus isolated-mode and timeout arguments;
6. rejection of the removed caller-supplied `--fixture` argument.

The runtime test creates its own small temporary fixture. It does not execute an arbitrary caller-selected repository directory.

## 4. Exact-source validation

### 4.1 Boundary workflow

- **Workflow:** [46001305945](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46001305945)
- **Source:** `4b028d50bea9e62e3aa8bab1077eb3e19b8bbcc8`
- **Conclusion:** success
- **Boundary tests:** 6 passed
- **Failures/errors:** 0

The push-triggered run intentionally skipped the manual fixed-fixture execution step. The six tests include a controlled temporary-fixture runtime reproduction; the actual checked-out provider-interface fixture was not executed by this push run.

### 4.2 Exact-head source and graph regression

- **Workflow:** [46001305989](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46001305989)
- **Source:** `4b028d50bea9e62e3aa8bab1077eb3e19b8bbcc8`
- **Conclusion:** success

The source/graph workflow passed its source-manifest tests, immutable Git-object source-provider tests, LFS payload provenance tests, recursive submodule/LFS accounting tests, graph snapshot identity/coverage tests, rule/finding provenance tests, publication state-machine tests, trusted artifact tests, graph snapshot capture, recursive accounting, and post-projection source verification.

This broad regression validates the exact branch head containing AE-34; it does not turn the AE-32D candidate into an adjudicated benchmark case.

## 5. Assurance limits and non-claims

- Python isolated mode is not a container, seccomp policy, network namespace, or other OS-level sandbox.
- The runtime process can still use filesystem and network capabilities available to the hosted runner. The workflow deliberately has no application secrets and grants only `contents: read`.
- The fixed fixture is code from the checked-out revision. The manual workflow reports that exact source revision; it does not relabel a current-branch execution as a reproduction of the older frozen candidate commit.
- The verifier's result is a narrow machine check of one controlled fixture. It is not independent human adjudication, a general audit-quality score, or benchmark acceptance.
- The provider-interface candidate remains `pending_adjudication` and `primary_benchmark_eligible=false`. Two independent human reviews and a recorded adjudication are still required before primary scoring.

## 6. Repository state

All changes were made on `stage1/section-uuids`. The `main` branch was not modified. No new branch was created.

**Decision:** the arbitrary fixture-path execution surface is closed for the declared workflow interface. The manual verifier is constrained to one fixed fixture and a reduced subprocess environment. This is a bounded workflow hardening result, not a claim that the fixture process is OS-sandboxed or that AE-32D ground truth has been adjudicated.
