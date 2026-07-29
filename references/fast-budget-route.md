# Fast Budget Route

Use this route only when the user or host gives a hard search budget, requests a compact/quick answer, runs a retrieval benchmark, or asks about one known source. It preserves source identity and relevance gates while reducing context and verification work. Open-ended requests for related papers, projects, methods, or project-moving ideas use the recovery route instead.

## Trigger

Select this route when any of the following is explicit:

- a maximum number of search calls, queries, opens, sources, tokens, or seconds;
- a request for a fast shortlist, smoke test, or benchmark result;
- a request where the user prefers useful discovery over a long literature review.

If the user asks for `deep`, `full`, `audit`, systematic review, or source-depth work, use the declared larger budget instead and record that change.

## Context budget

1. Load only this route plus the one discipline/ecosystem reference that is directly applicable. Load the recovery reference for open-ended discovery even when the user does not use the phrase “ordinary AI missed it.” Do not read every reference file in the package.
2. Keep a compact metadata ledger of up to 14 candidates, then verify and rank one list of at most four sources. Give every source a `direct`, `mechanism`, `validation`, `current`, or `adjacent` role. Each pool record contains canonical identity, source type, discovery lane, one-line relevance, one-line mechanism or implementation bridge, and one unresolved risk. Do not deeply read every pool candidate.
3. Do not paste raw search pages, full abstracts, repository READMEs, or repeated metadata into working context. Normalize and discard them after identity extraction.
4. Reserve enough context for final synthesis before the last search batch. A search that consumes the remaining response budget is a failed workflow even if it finds additional candidates.

## Search and verification budget

### Adaptive Fast Stop

The explicit `fast` profile uses at most two batched search calls, five query strings, one targeted open, and one coverage probe. After the first batch, stop when at least four identity-valid candidates cover three distinct source families and at least three discovery lanes have been attempted. Rank verified mechanism, validation, current, or adjacent neighbors in the same list when they offer more project-moving value than another direct match. The `standard` profile retains the larger three/eight/three ceiling for an explicitly expanded run; do not silently use it in a fast request.

For compatibility with earlier benchmark documentation, the expanded ceiling is also described as three batched web-search calls and eight query strings. That wording refers to `standard`, not the default `fast` profile.

If a search call exceeds the declared soft timeout, finish the current bounded work while marking that ecosystem as pending. Do not retry the same query. A hard timeout ends that path and becomes a visible coverage gap; it does not justify another broad search round.

Search lanes are scheduled by expected information gain:

1. direct problem/mechanism evidence;
2. one alternative, failure, or validation lane;
3. one artifact/ecosystem/current-work lane for repositories, datasets, successors, or recent work.

For a missed-source or baseline-comparison request, use the same unified ranked-list contract as every other route. Never hide a high-value mechanism neighbor merely because it is not directly deployable; label its role and limitation instead.

Do not run a full fixed sweep of every lane when the coverage vector is already complete. Verify the top candidates, explicit known leads, and ambiguous or high-risk identities only. A repository or dataset identity may be verified from its canonical landing page without reading its entire documentation.

## Compact output

Return the requested ranked sources plus a short coverage statement. When `discovery_trace` is required, keep it bounded:

- no more than eight query records;
- no more than six bridge paths;
- no more than seven gap rows;
- one sentence per contribution-map field;
- no more than five self-refutation bullets;
- one explicit `stop_evidence` sentence.

If the budget ends, return the verified shortlist and mark the remaining family or identity as a visible gap. Never continue searching merely to make the trace look complete.

## Safety and quality invariant

Fast mode changes search scheduling and context size, not the evidence rules. It must still normalize identities, reject duplicates and invented sources, separate direct fit from mechanism transfer, retain relevant-but-not-hot candidates, and expose unresolved evidence. A shorter answer is acceptable; a shorter audit trail is not an excuse for an unsupported claim.

For a user-provided constellation of several projects or papers, keep each item as a separate anchor, extract shared and contrasting mechanisms, and search for bridges between them. Do not infer a private preference profile or treat the user's examples as autonomous discoveries. For strong verified anchors, allow one bounded citation, dependency, successor, benchmark, or terminology bridge; record the hop and keep the two-anchor gate.

Before finalizing, produce a compact contribution record and self-refutation pass: expose empty contribution cells, repeated mechanism families, hard negatives, popularity-only candidates, and cross-domain transfer assumptions. If a material gap remains and the global budget allows, spend the single coverage probe on it; otherwise report the gap. Add `contribution_map`, `gap_matrix`, `next_query_reason`, `bridge_paths`, `self_refutation`, and `stop_evidence` to the trace when this loop is used. Evaluate `gap_coverage`, `family_coverage`, `unique_neighbor_rate`, and human-labelled `user_approved_novel@k` separately from known-lead recovery and nDCG.

When this active loop is used, the final structured answer must include `discovery_trace` with those fields. If the host cannot return that trace, mark `active_loop_trace_unavailable` and do not claim that the active loop was executed. Keep the existing query and source budgets; a longer query list is a budget violation, not improved discovery.

### Budgeted Progressive Discovery

The retrieval test showed that wider discovery can become counterproductive when the agent verifies candidates one by one. Treat search breadth and completion as joint objectives:

1. **Declare the budget first:** before the first search, reserve a query, source-open, verification, elapsed-time, and token budget. The lightweight neighbor budget is the explicit `fast` profile: two batched search calls, five query strings, one targeted open, and one coverage probe. Open-ended discovery uses the separate `recovery` profile. An explicitly expanded `standard`, `full`, or `deep` request must declare a larger budget rather than silently exceeding it.
2. **Batch for coverage:** each search call should contain several distinct queries from different lanes. Do not spend one web call per candidate, paper copy, or repository mirror. Do not repeat a failed query without recording a changed term or reason.
3. **Use progressive widening:** first collect compact candidates from exact/alias and mechanism/ecosystem lanes; stop immediately when the fast early-stop threshold is met. Otherwise use the second batch, then spend the single probe on the missing highest-value family. Stop when the probe is complete, the required families are covered, or the budget is exhausted.
4. **Verify selectively:** resolve identity and inspect evidence for the top candidates, explicit known leads, and genuinely ambiguous or high-risk items. A candidate that cannot materially change the decision stays pending or transfer-only instead of triggering another search round.
5. **Stop on the deadline:** if the remaining budget cannot support a complete response, return the best verified shortlist and a visible gap. A timeout or incomplete answer is a workflow failure to measure, not permission to keep expanding indefinitely.

For every web/search call, request the shortest available response format. Retain only title or owner, canonical URL or identifier, date/version, source type, and one mechanism/evidence sentence. Do not carry raw result pages, full abstracts, README bodies, or repeated metadata into the next call. If a tool has no response-length control, apply the same compact-field limit before continuing.

Always report `completed`, `budget_used`, `budget_remaining`, `known_lead_recovery`, `new_neighbor_count`, and `uncovered_known_leads` when this mode is evaluated. Optimize recovery per minute and per token, not recovery alone.

### Relevance-First Retrieval

When the user asks whether results are truly relevant, better than ordinary AI search, or connected to a named paper/repository, read [relevance-first-retrieval.md](relevance-first-retrieval.md). When the complaint is that ordinary search misses valuable sources rather than returning only irrelevant ones, also read [user-aligned-discovery.md](user-aligned-discovery.md) and [long-tail-neighbor-discovery.md](long-tail-neighbor-discovery.md). Freeze a target card before searching, keep lexical, decomposed, mechanism, artifact, failure, and current lanes separate, and fuse only after identity normalization. Keep a lexical lane inside the Skill; the no-Skill condition remains a separate A/B baseline.

Use a cheap two-anchor gate before deep reading, then rerank the shortlist on task, mechanism, modality/outcome, constraints, evidence depth, direct/transfer fit, and unresolved risk. Paper-to-repository links must be labelled `explicit_linked`, `metadata_linked`, `inferred_related`, or `unresolved`; stars, citations, tags, and repeated paths are discovery signals, not relevance evidence. Keep known-lead recovery separate from novel discovery. The references also define the ResearchArena-aligned discovery-versus-selection evaluation and the user-aligned missed-source recovery evaluation.

In the explicit fast pass, request short search results and inspect snippets or authoritative metadata first. Do not open full papers, repository trees, or long README pages for every candidate; reserve deep reading for the final shortlist or an explicit `source-depth`/`full` request. If a tool returns a large page, normalize the relevant identity and evidence fields immediately, then discard the raw page from working context. The fast two-batched-search, five-query, and one-open budget is the hard stop for fast requests; the recovery route has its own two/six/two budget plus a finalization reserve, and the standard three/eight/three ceiling applies only to a declared standard profile.
