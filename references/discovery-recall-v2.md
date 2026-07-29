# Discovery Recall v2

Use this route when ordinary retrieval returns plausible material but misses papers, repositories, datasets, tools, standards, or methods that could change the project direction. The active output and budget contract is `runtime-contract-v1.json`; this reference defines retrieval behavior only.

## Separate Discovery From Selection

Build a compact metadata candidate pool before selecting the final ranked list. The candidate pool protects mechanism, failure, implementation, and adjacent-domain leads from being crowded out by early lexical matches. It is not permission to read every paper or repository in full.

## Anchor Card

Freeze five axes:

1. problem or decision;
2. mechanism or operation;
3. input, output, or observable outcome;
4. evidence, evaluation, or failure mode;
5. ecosystem, deployment setting, or constraint.

Search restrained pairs of axes. Every selected candidate must retain its two strongest anchors and one concrete bridge.

## Candidate Lanes

Keep these paths separate until identity normalization:

- lexical identity and aliases;
- mechanism terminology;
- artifacts, dependencies, successors, datasets, and benchmarks;
- failures, validation, corrections, audits, and alternatives;
- dated attention and curation signals;
- one adjacent discipline when the mechanism bridge is concrete.

Use domain-native ecosystems. GitHub is not a universal source for health, social science, humanities, arts, or policy work.

## Delayed Commitment

For each candidate retain canonical identity, discovery paths, anchor matches, family, bridge, identity status, evidence hint, direct-use fit, mechanism-transfer fit, and duplicate relation. Collapse mirrors, forks, duplicate DOI pages, and preprint/published duplicates before ranking.

Run the authoritative identity gate on every selected source. A real URL paired with the wrong title or owner is an identity mismatch. Remove or mark it unresolved; never repair it from memory.

## Unified Selection

Rank one result list in this order:

1. verified identity and task fit;
2. concrete mechanism, outcome, or evidence bridge;
3. evidence authority and depth;
4. project-moving value and a testable next experiment;
5. deployment fit or explicit transfer value;
6. family coverage and non-duplication;
7. freshness or attention as a tie-breaker only.

Give every selected source one role from the runtime contract. A mechanism or adjacent source competes in the same ranking and must state why adaptation is needed. Do not reserve result slots through a second list.

## Feedback And Evaluation

Record user feedback as `accepted_useful`, `already_known`, `not_relevant`, or `needs_more_evidence` with a reason. Only explicit, reasoned acceptance may count toward `user_approved_novel@k`.

Measure known-lead recovery, user-approved novelty, family coverage, hard-negative rate, identity validity, completion, latency, and tokens outside the model response. Promote a route only when repeated blinded trials improve user-valued discovery without material ranking-quality, completion, latency, or token regression.
