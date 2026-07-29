# Missed-Source Recovery v5

Use this route by default for an open-ended research request asking for related papers, projects, methods, current work, alternatives, or ideas that could change the direction of the work. It also handles the explicit complaint that ordinary AI search returns plausible material but misses the valuable few. This route is deliberately broader than a fast shortlist. It optimizes recovery of high-value neighbors and known leads before token economy, within a fixed budget.

## One Ranked Result

Return one ranked list of at most six candidates. Give each candidate one role: `direct`, `mechanism`, `validation`, `current`, or `adjacent`. A role describes why the source is useful; it does not reserve a slot or lower the identity and evidence gates. The shared limits and budgets live in `runtime-contract-v1.json`.

## Required Coverage

Before stopping, attempt at least four distinct lanes, chosen from:

1. exact or decomposed problem terms;
2. mechanism and neighboring terminology;
3. implementation, dependency, dataset, or successor ecosystem;
4. evaluation, failure, limitation, correction, or replication;
5. dated current-work and independent technical attention;
6. one concrete adjacent-domain bridge.

For an open-ended request, decompose the target into capability atoms before searching. At least one query must be generated from a mechanism family that is not simply a restatement of the user's wording. Examples include temporal validity, consolidation or forgetting, entity linking, graph or lexical retrieval, workflow compilation, observation reduction, verification, or provenance. If the first batch returns only direct matches, the next batch must target the most valuable uncovered family; direct-match sufficiency is not a stop condition for recovery.

### Six-Slot Recall Plan

The six query records have distinct jobs. This prevents a superficially diverse trace from being six variants of the same broad query:

1. **Anchor:** resolve the task and its deployment boundary.
2. **Competing vocabulary:** use neighboring terminology rather than a synonym-only rewrite.
3. **Candidate reservoir:** query a domain-native index that reveals sibling work. Examples include a repository topic or curated collection, survey or review, benchmark/leaderboard, package or dataset ecosystem, conference/artifact list, bibliography, catalog, registry, archive finding aid, or professional-society list.
4. **Contrast/failure:** seek alternatives, limitations, successors, negative results, or abandoned paths.
5. **Anchor expansion:** after at least one identity-valid candidate is found, query a concrete relation around it: related/citing work, maintainers or lab, dependency, benchmark, dataset, alternative implementation, or successor. This slot must not merely repeat the original task terms.
6. **Coverage probe:** spend the final record on the highest-value uncovered family, or record the unavailable ecosystem and reason.

The reservoir is a discovery mechanism, not evidence. Each candidate it exposes must still pass canonical identity, two-anchor relevance, and mechanism/evidence checks. If an anchor cannot be resolved in time, mark the anchor-expansion slot unavailable and redirect only that one slot to the highest-value unrepresented family; record the reason in `gaps` and `stop_evidence`.

The query plan may use up to two batched search calls, six query records, two targeted opens, and one coverage probe. The coverage probe consumes one of the six query records; it is not an additional seventh query. `queries` must equal `budget_used.query_records`. Used plus actionable remaining capacity must never exceed the declared budget; dependent capacity may be zero once the query or time boundary makes it unusable. Stop after the first batch when five identity-valid candidates cover four source families and all required lanes attempted so far are represented. In a 300-second run, start no new discovery after 210 seconds and preserve at least 60 seconds for identity checks, deduplication, ranking, trace completion, and serialization. At the boundary, finalize from the verified ledger instead of trying to fill all six source slots. A slow or unavailable ecosystem becomes an explicit gap. Do not retry the same query without a recorded changed term and reason.

## Candidate Contract

Every candidate needs:

- canonical identity or an explicit unresolved status;
- two concrete anchors to the target card;
- one mechanism or evidence bridge;
- one reason it could change the project direction;
- direct-use versus transfer-only fit;
- the source family and discovery lane;
- one limitation or hard negative.

Popularity, stars, citations, or repeated mentions can prioritize a search path, but cannot satisfy the candidate contract. A user-supplied project is a recovery target, not a novel discovery.

## Required Trace

When this route is used, include `mode`, `route=recovery`, `attempted_families`, `covered_families`, `uncovered_families`, `budget_used`, `budget_remaining`, and `stop_evidence` in `discovery_trace`. Compute known-lead recovery and new-neighbor metrics outside the model response so the model cannot grade itself.

## Reranking

Use the following order after identity normalization:

1. identity and evidence validity;
2. uncovered-family value;
3. mechanism bridge and task fit;
4. project-moving potential and next experiment;
5. direct deployment fit;
6. freshness, maintenance, and risk.

This order intentionally differs from the ordinary fast route. A mechanism neighbor that cannot run directly can still rank highly when its transfer bridge is concrete. A directly deployable but repetitive source should not consume the list.

## Evaluation

Evaluate this route with a declared name-hidden recovery set and a separate blind review of new neighbors. Report direct-fit quality, known-lead recovery, novel-neighbor recovery, family coverage, identity validity, token cost, and elapsed time separately. Do not replace the recovery result with generic nDCG, and do not claim universal superiority from a small pilot.
