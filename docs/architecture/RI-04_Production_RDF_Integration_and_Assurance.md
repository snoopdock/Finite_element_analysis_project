# RI-04 — Production RDF Integration and Assurance

**Status:** Candidate for manual CI acceptance. RI-01/RI-02/RI-03 and the original G4 byte-level exporter remain authoritative.

## 1. Scientific source-bound dossier
`rdflib_production_integration.py` uses existing GE-04 and/or G7.3 reviewers. Only explicit editor-authored, version-bound section links may appear in a dossier. The code obtains the current/proposed source graph through `ri01.resolve_view`, builds the G4.6-verified RI-02 index, applies RI-03 cross-context checks, then joins bounded citation results to reviewed scientific entities. Missing post-change entities remain explicitly absent; they are not silently re-created. The output is deterministic and independent replay checks the **entire dossier and N-Quads bytes** against repository sources.

A graph relationship, citation, RDFS/OWL label, reasoner witness or RDF query does not prove scientific correctness. All approval and mutation authority fields are false.

## 2. Interoperability with an independent implementation
`rdflib_interoperability_campaign.py` parses the same detached, context-labelled N-Quads using **RDFLib and Oxigraph**. It compares all semantic terms (including data types, language tags and context IRIs), not merely quad counts or hashes. Plain string literals are normalized to `xsd:string`, the RDF 1.1 abstract term semantics. Blank nodes and default-graph records are prohibited in this detached format. Native Oxigraph is **required** by the acceptance workflow; a local RDFLib-only check explicitly reports `independently_verified=false`.

Oxigraph is an **optional verification dependency** (`pyoxigraph>=0.5,<0.6`, installed in the manual workflow), not a new canonical store or graph-engine backend.

## 3. Bounded deterministic benchmark campaign
The campaign generates deterministic synthetic scientific graph inputs containing concept hierarchies, propositions, repeated citations, and explicit relationships. Tested graph sizes and seeds are included in the output along with source/graph/quad hashes. Separate timing and tracemalloc samples cover RI-02 index construction, RI-03 fixed SPARQL queries, and cross-parser checks. Every campaign result is tied to the canonical input and independently replays semantic outputs.

**Important:** Timing samples themselves cannot be recomputed after the fact. Verification checks their numeric validity/statistical arithmetic, not their historical truth. `tracemalloc` tracks Python-managed allocations, not all native memory. Neither results nor comparisons can authorize automatic backend switching.

For additional scaling run manually with sizes `48,256,768`, seeds `20261013,20261014`, repeats `3`, subject to available GitHub runner memory/time. Typical acceptance should use the default smaller campaign first.

## 4. Security boundaries
- No arbitrary SPARQL: all executed queries originate in the RI-01/RI-02/RI-03 fixed catalogs.
- No SPARQL `SERVICE`, caller-originated graph patterns, remote contexts or automatic dereferencing.
- Query arguments are bound as RDF terms, not concatenated SPARQL source.
- Query rows, entities, report size, graph sizes, seeds and repeats are bounded.
- CI invokes each substantive CLI action in a separate Unix process with a wall-clock `timeout`; the workflow has an overall job timeout.
- Outputs must be new, detached paths outside the checked-out repository, created without following a pre-existing file.
- Independent verification rebuilds source relationships and checks every published byte.
- No repository writes, scientific approvals, fact substitutions or unreviewed document edits.

These controls are not a substitute for a container sandbox when running code from untrusted forks. Do not allow contributors to edit fixed query templates unnoticed; review patch source and restrict workflow permissions.

## 5. Dependency and workflow maintenance
The project already declares `rdflib>=7.0,<8.0`; RI-04 does **not** silently widen this dependency or modify the accepted G4 exporter. The manual workflow records installed versions, installs optional Oxigraph in a bounded range, executes `pip check`, and rejects pytest tests that return non-None. Checkout/setup-python/artifact actions use Node 24–compatible releases. RDFLib's internally emitted `Dataset.default_context` deprecations remain visible: they are upstream warnings and are not globally hidden.

Before future upgrading to RDFLib 8 or replacing canonical serialization, rerun G4.6 source-bound parity, G5 OWL conformance, RI-01 through RI-04, and complete regression.

## 6. Acceptance gates
1. Manual Validation Dispatcher with `G8.5`, full regression enabled, PASS.
2. Manual RI-04 workflow native modules present and no skipped G4 tests.
3. Independently parsed RDFLib/Oxigraph datasets agree exactly.
4. G7.3 explicit review dossier contains actual document-section triggers and no forged approval flag.
5. Campaign includes multiple sizes, multiple seeds, separately measured operations and replayed hashes.
6. Detached report verification, bounded query limits, untrusted input negative tests and upload PASS.

The current October 13 snapshot predates G4.5 and Oxigraph is not installed locally, so native G4/Oxigraph gates **cannot** be considered passed merely from local test skips.
