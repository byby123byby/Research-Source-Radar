# Active Discovery Loop

Use this reference when a normal multi-lane search still misses the few papers,
projects, or methods that could change the user's direction. The loop improves
candidate generation by choosing the next search from the current evidence and
uncovered contribution cells. It does not weaken identity, relevance, or source
verification gates.

## Why This Is Different

Fixed lanes provide useful coverage, but they can still spend the same budget on
well-indexed work and stop before an unusual mechanism or neighboring field is
found. The active loop treats discovery as a bounded decision process:

```text
target card -> contribution map -> search batch -> normalized candidates
             -> gap update -> next best lane -> comparison -> stop or revise
```

This adapts ideas from PaSa's multi-step academic search, OpenScholar's adaptive
retrieval and self-feedback, GeAR's graph expansion, and recent novelty-aware
retrieval work. These are workflow precedents, not evidence that this Skill
inherits their reported scores.

## Contribution Map

Before the first search, represent the target as a small map. Keep the wording
concrete and domain-neutral:

```text
problem: what decision or research obstacle matters?
inputs: data, users, artefacts, modalities, or observations
mechanism: what operation is expected to cause the improvement?
outputs: result, action, explanation, intervention, or measurement
constraints: deployment, cost, safety, access, ethics, or time limits
evidence: what would count as support, failure, or transfer evidence?
```

For a user-supplied constellation of several leads, preserve each lead as its
own anchor. Extract the shared mechanism and the meaningful differences; do not
average them into a hidden preference profile. Do not infer a private preference profile
from those examples or from social-platform history.

## Gap Matrix

Maintain a compact matrix with rows for discovery families and columns for the
contribution atoms. Use these families when applicable:

| Family | What it can expose |
| --- | --- |
| `direct` | same problem and mechanism in the target setting |
| `alternative` | a different implementation or inference route |
| `validation` | benchmark, audit, measurement, or falsification method |
| `failure` | limitation, negative result, correction, or abandoned route |
| `ecosystem` | repository, dependency, dataset, benchmark, or successor |
| `adjacent` | another discipline using the same mechanism under different names |
| `current` | recent work, release, or emerging terminology |

Each cell is one of `covered`, `uncertain`, `empty`, or `not_applicable`. A cell
is covered only by an identity-valid candidate with a concrete bridge and an
evidence note. A title, snippet, citation count, or model-generated guess is not
coverage.

## Choosing The Next Query

After every search batch:

1. Normalize identities and update the candidate ledger before deciding what to
   search next.
2. Mark cells supported by the new candidates and record which query/path
   produced the support.
3. Remove queries whose only output was a duplicate, generic result, or hard
   negative.
4. Select the next lane in this order: required empty family, uncertain cell
   with the clearest mechanism bridge, unresolved known lead, then an adjacent
   family with a concrete two-anchor bridge.
5. Prefer the query with the lowest expected verification cost when two lanes
   have comparable value. Do not use a single opaque relevance score to decide
   which source is relevant; this priority only schedules the next search.

The default recovery budget is two batched searches, six query strings, two
targeted opens, and one coverage probe. The active loop changes
the order and wording of those calls; it does not increase the budget. If the
same family produces no new identity-valid candidate after two materially
different formulations, mark it as a searched gap and move on.
The probe consumes one of the six query records and cannot create a seventh.

For a 300-second bounded run, stop creating new search work after 210 seconds
and reserve at least 60 seconds for verification, deduplication, ranking, trace
completion, and serialization. Finalize from the verified ledger at that
boundary; source-count ceilings are not fill targets.

## Graph Bridges Without A Graph Runtime

For the strongest verified anchors, perform at most one bounded bridge expansion
through the relations that are visible in authoritative sources:

```text
paper -> cited/follow-up paper -> method or benchmark
repository -> dependency/successor/organization -> related repository
method -> alternate field term -> adjacent-domain source
failure -> correction/negative result -> validation method
```

Record each hop as `bridge_type`, `from_id`, `to_id`, `source_locator`, and
`bridge_strength`. A path is a discovery route, not proof of relevance. Keep the
same two-anchor gate for the final shortlist, and label a one-anchor bridge as
transfer-only or exploratory.

## Contribution Comparison And Self-Refutation

Before finalizing the shortlist, create a short contribution record for each
selected candidate:

```text
candidate_id:
problem:
mechanism:
input_output:
reported_outcome:
evidence_type:
limitation:
bridge_to_anchor:
```

Then run a bounded self-refutation pass:

- Which candidate families are repeated without adding a different mechanism?
- Which contribution-map cells remain empty or are supported only by snippets?
- Is the top candidate merely popular, cited, or indexed by many paths?
- What is the strongest hard negative, and why is it excluded?
- Does any claimed cross-domain transfer confuse a shared mechanism with evidence
  that the outcome transfers?

If a material empty cell remains and the budget has room, use the single coverage
probe. Otherwise expose the gap. Do not invent a candidate to make the matrix
look complete.

## Output And Evaluation

Add these fields to the research trace when the active loop is used:

```text
contribution_map
gap_matrix
next_query_reason
bridge_paths
self_refutation
stop_evidence
```

Evaluate the loop separately from ordinary ranking:

- `gap_coverage`: proportion of applicable contribution cells with verified support;
- `family_coverage`: distinct direct, alternative, validation, failure, ecosystem,
  adjacent, and current families represented;
- `unique_neighbor_rate`: non-duplicate candidates with a concrete bridge;
- `user_approved_novel@k`: new candidates later accepted by the user or blinded
  reviewer;
- `hard_negative_rate`, completion, wall time, and tokens.

Known-lead recovery remains recovery, not autonomous discovery. Human or blinded
review is required for `user_approved_novel@k` and for judging whether a bridge is
actually useful. A positive automatic recovery result cannot establish that every
new candidate is valuable.

## Boundaries

Do not import a hosted graph database, reinforcement-learning trainer, or large
scientific corpus as a runtime dependency merely because a cited paper uses one.
The portable implementation is a structured trace plus bounded search planning.
Do not read private social-feed history. User-provided screenshots, video clues,
and projects are explicit seeds for the current run only.
