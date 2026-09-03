# Finite Element Analysis Project

This project is an automated pipeline that finds academic sources about the Finite Element Method (FEM), extracts facts and equations, writes clear guideline sections using LLMs, and builds a LaTeX guideline.

The goal is to make a precise, evidence-backed technical guideline for FEM that can be checked by humans and, when enabled, by formal tools.

---

## What the pipeline does

Each run of the pipeline goes through four phases:

1. RESEARCH — Search arXiv and Wikipedia for new papers and pages, collect them as evidence. (No LLM calls.)
2. EXTRACT — Read new sources and pull out concepts, formulas, and rules into a structured knowledge base. (One LLM call per extraction job.)
3. WRITE — Use the knowledge base to make section outlines and write paragraphs. Each paragraph must include allowed citations. (A few LLM calls.)
4. ASSEMBLE — Join sections and produce a LaTeX file for the full guideline. (No LLM calls.)

This loop runs repeatedly. The pipeline keeps state so it does not re-read the same sources.

---

## Key ideas and terms (plain)

- Evidence: papers, web pages, and passages that support a claim.
- Knowledge base: structured facts and formulas extracted from evidence.
- Section: a unit of the guideline (title + paragraphs).
- Paragraph: a short, focused block of text that must cite evidence.
- OAA loop: Observe-Analyze-Adjust loop that checks section quality and decides actions.
- Eta score: a number that ranks sections by how much work they need. It uses leverage, instability, and anomaly.
- Formal layer: optional tools (SAT/SMT/CP-SAT/Lean) that can check math claims.

---

## Phase details and costs

Phase | Input | Output | LLM calls
---|---:|---|---:
RESEARCH | seed queries | evidence.json | 0
EXTRACT | new sources | research.json / knowledge base | 1 per extraction job
WRITE | knowledge base | sections.json | 1–5 (small number)
ASSEMBLE | sections.json | guideline.tex | 0

The config controls how many LLM calls and tokens are used. See `config.yaml`.

---

## How the pipeline chooses work

Each section gets a score eta = w_L * L + w_U * U + w_A * A.

- L (Leverage): how many other sections depend on this one.
- U (Instability): how recently the section failed checks.
- A (Anomaly): whether the section failed a quality check in the last cycle.

Weights are in config.yaml (defaults: w_L=0.4, w_U=0.4, w_A=0.2). Sections are sorted by eta and the pipeline rewrites the top set until they cover a fraction theta of total eta (default theta = 0.75).

This is inspired by adaptive work allocation used in numerical methods such as adaptive mesh refinement (Dörfler, 1996).

---

## Finding missing knowledge

The pipeline runs two tracks:

- Context-free track: fetch a reference taxonomy by scraping headings from relevant Wikipedia pages (no LLM). This gives a list of topics a guideline should cover.
- Context-aware track: compare the taxonomy to the current knowledge base using an LLM to find missing or weakly covered topics. The LLM returns search queries for missing topics.

This two-track approach balances external reference structure and the pipeline's internal state.

---

## Writing rules and checks

- Paragraphs must cite allowed evidence IDs. If a paragraph cites outside the allowed list, the citation is removed.
- Repetition check: new paragraph is compared to earlier paragraphs in the same section. If word overlap (Jaccard similarity) > 50%, the paragraph is rejected.
- Minimum paragraph/section lengths and merge/split rules are in config.yaml (e.g., sections below 300 words are flagged for expansion).
- Structural changes are limited: one split or merge per section per cycle to avoid cascades.

These rules aim to keep writing precise, traceable, and non-repetitive.

---

## Quality checks (OAA loop)

Observe: measure word counts, number of citations, and overlap between sections.
Analyze: compare measures to thresholds (too short, uncited, redundant).
Adjust: decide to split, merge, or do nothing for each flagged section.

The loop uses a hysteresis window (default 2 cycles) so sections marked stable are not flipped immediately.

References: Wiener (1948) on control loops; Kephart & Chess (2003) on autonomic systems.

---

## Formal verification (not active by default, it will be worked on in near future)

When enabled, the pipeline can route mathematical claims to solver tools:

- SAT/SMT solvers for satisfiability checks.
- CP-SAT or MILP solvers for optimization/existence questions (OR-Tools).
- Lean 4 for universal proofs (theorem proving).

The formal layer is disabled by default. To use it you must install the external tools and enable `semantic_verification.enabled` in config.yaml. The README lists references for these tools.

---

## Repository layout (short)

- main.py — pipeline entry point.
- config.yaml — runtime parameters and weights.
- core/ — pipeline sequencing, state, and graph code.
- research/ — data acquisition (arXiv, Wikipedia, Semantic Scholar, OCR helpers).
- processing/ — LLM response parsing and LaTeX builder.
- analysis/ — scoring, OAA loop, retrieval attention, and checks.
- writing/ — writer, section merger, and splitter.
- formal/ — solver adapters and Lean project (not active by default, it will be worked on in near future).
- specs/ — YAML contracts and invariants.
- scripts/ — audit scripts to check invariants and stages.
- state/ and output/ — runtime state and generated files.

---

## How to run (local)

1. Create a Python 3.11 virtual environment and install deps:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Set Cloudflare credentials (default provider requires these):

```bash
export CLOUDFLARE_ACCOUNT_ID="your_account_id"
export CLOUDFLARE_API_TOKEN="your_api_token"
```

3. Run one cycle:

```bash
python main.py --config config.yaml
```

Notes:
- If you do not want to use real LLMs, make a mock provider and set it in the code or use a dev config with `max_llm_calls_per_run: 0`.
- The GitHub Actions workflow runs the pipeline on a schedule; set secrets in the repository settings if you enable it.

---

## Development and testing

- Tests: small pytest tests are in `tests/`. Add tests for WritingIndicator, OAALoop, and ConvergenceDetector before changing scoring.
- Add small evidence fixtures for deterministic tests (see `audits/fixtures`).
- Consider making a Dockerfile or devcontainer that installs optional tools (Lean 4, OR-Tools) to reproduce the formal layer locally.

---

## Limits and risks (brief)

- LLM text can be wrong or miss citations. Always check output before using it in real documents.
- Formal checks need careful encoding. A wrong encoding can give misleading results.
- The pipeline depends on external services (Cloudflare models, arXiv, Wikipedia). Network or API changes can break runs.

---

## Configuration

Edit `config.yaml` for weights, thresholds, budgets, and which models to use. The file contains defaults and comments.

---

## Selected references and further reading

- Parnas, D. L. (1972). "On the criteria to be used in decomposing systems into modules." Communications of the ACM, 15(12), 1053–1058.
- Meyer, B. (1988). Object-Oriented Software Construction. Prentice Hall.
- Dörfler, W. (1996). "A convergent adaptive algorithm for Poisson's equation." SIAM Journal on Numerical Analysis, 33(3), 1106–1124.
- Wiener, N. (1948). Cybernetics: Or Control and Communication in the Animal and the Machine. MIT Press.
- Kephart, J. O., and Chess, D. M. (2003). "The vision of autonomic computing." IEEE Computer, 36(1), 41–50.
- Biere, A., Heule, M., van Maaren, H., and Walsh, T. (eds.). (2021). Handbook of Satisfiability (2nd ed.). IOS Press.
- Google OR-Tools CP-SAT docs: https://developers.google.com/optimization/cp
- Lean 4 documentation: https://lean-lang.org/
