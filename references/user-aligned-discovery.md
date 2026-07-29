# User-Aligned Discovery And Missed-Source Recovery

Use this reference when the user's complaint is not that the returned sources are wrong, but that ordinary AI search fails to surface the few papers or projects the user would have considered valuable. This is a discovery-recall problem: relevance and identity still matter, but the workflow must also search the neighboring mechanisms that a first-pass keyword search is likely to miss.

## Contents

- [What this solves](#what-this-solves)
- [Runtime protocol](#runtime-protocol)
- [Candidate ledger](#candidate-ledger)
- [Ranking and output](#ranking-and-output)
- [Evaluation protocol](#evaluation-protocol)
- [Boundaries](#boundaries)

## What This Solves

Separate four situations that are often conflated:

1. **Relevant result:** the source matches the current question.
2. **Known lead:** the user supplied or later identified the source as valuable.
3. **Recovered lead:** the Skill found a known lead from a name-hidden or mechanism-only prompt.
4. **New neighbor (`new_neighbor`):** the Skill found a source the user did not provide, with a traceable bridge to the seed.

A baseline can have good precision while still missing known leads and useful neighbors. Do not call those baseline results wrong, and do not call a user-supplied lead a new discovery. Report precision, known-lead recovery, and novel-neighbor discovery separately.

This protocol does not create a hidden preference profile or read social-platform history. It uses only leads explicitly present in the current request, a supplied research contract, or a source list the user deliberately provides for evaluation.

Model output does not produce automated “价值分” or “是否值得”的最终评分。最终有效性的判定仅基于用户的标签和随后人工复核；模型只能提供可复用的可追溯候选与归因证据。

## Runtime Protocol

### 1. Build A Lead Card

Before searching, extract a privacy-minimized card:

```text
anchor_seed: the current project, paper, question, or mechanism
known_leads: sources the user explicitly mentions as examples or expected finds
target_decision: what the user needs to decide or build
mechanism_fingerprint: inputs, mechanism, output, evidence, constraints
hard_negatives: broad results the user says are too generic or not useful
```

If the user supplies no known leads, leave the set empty. Do not invent remembered sources or infer a private recommendation history.

For each known lead, preserve its spelling, aliases, the reason it may matter, and its intended relation to the anchor. A lead can be an exact counterpart, implementation, alternative, validation method, failure case, or transferable mechanism.

### 2. Use Independent Discovery Lanes

Run compact queries in separate lanes. Batch related queries instead of making one expensive request per candidate.

1. **Exact and alias:** title, repository owner, package name, OCR/ASR variants, distinctive phrases.
2. **Mechanism:** the seed's mechanism expressed with competing terminology and neighboring field vocabulary.
3. **Artifact and ecosystem:** cited papers, code links, dependencies, organizations, successors, benchmarks, datasets, and implementations.
4. **Alternative and failure:** competing approaches, limitations, negative results, abandoned projects, corrections, and failed reproductions.
5. **Current and adjacent:** dated releases, recent papers, technical coverage, and one adjacent-domain query when it shares a concrete mechanism.

The seed-resolution query is not enough. A related-work pass must attempt at least one non-exact lane when the user asks what else may be useful. Record the lane and the exact query that produced every candidate.

### Budgeted Progressive Discovery

The goal is to recover valuable neighbors without turning the run into an unbounded source-by-source crawl. Use this default schedule unless the user explicitly requests a deep search:

| Stage | Work | Limit |
| --- | --- | --- |
| Fast coverage | exact/alias plus one mechanism/ecosystem batch | 2 batched searches, up to 6 query strings |
| Gap probe | one missing high-value family | 1 batched search, up to 2 query strings |
| Verification | seed, known leads, top candidates, and ambiguous claims | 3 targeted opens |

Each batch should contain several independent queries. Do not open every candidate or run a separate search for every title. Stop after the gap probe, when the high-value families are covered, or when the declared time/token budget is exhausted. Record `budget_used` and `budget_remaining`; a timeout is a failed completion, not a reason to launch another unbounded sweep.

For an explicit list of known leads, resolve those leads first and spend the remaining budget on new neighbors. For a name-hidden discovery task, do not pretend that the expected source set is known at runtime; evaluate it externally and report both recall and cost.

### 3. Expand Before Deep Reading

Use a two-stage process:

- **Coverage pass:** collect short metadata and snippets, normalize identities, and build a union of candidates from the active lanes. Do not deeply read every result.
- **Selection pass:** verify and inspect only the strongest candidates plus any unresolved known lead that could materially change the answer.

If a known lead is not found through the first route, try one alternate route: owner/title resolution, mechanism formulation, or independent citation/organization search. If it still cannot be found, record `uncovered_known_lead`; do not replace it with a popular generic source.

### 4. Preserve A Bridge For Every New Neighbor

Every newly discovered candidate needs a short, explicit bridge:

```text
discovered_via: exact | mechanism | artifact | alternative | failure | current | adjacent
bridge_to_anchor: which mechanism, task, input, outcome, or ecosystem link connects it
novelty: not in known_leads for this run
relation: direct_companion | alternative | validation | failure | transfer
```

A shared keyword, citation count, star count, or repeated search appearance is not a bridge. If the only bridge is a broad topic, move the candidate to background or transfer-only.

## Candidate Ledger

Keep these sets separate in the report and, when a contract is available, in its discovery record:

| Set | Meaning | Counts as discovery? |
| --- | --- | --- |
| `anchor_seed` | The source or question that started this run | No |
| `known_leads` | Sources explicitly supplied or expected by the user | No |
| `recovered_known_leads` | Known leads found through the current search | Recovery only |
| `new_candidates` | Sources not supplied by the user and found through a traceable route | Yes |
| `uncovered_known_leads` | Known leads not resolved within the declared budget | Gap |
| `hard_negatives` | Plausible-looking but weakly connected sources | No |

Do not merge a known lead into `new_candidates` merely because it was found through a different query. Do not remove an uncovered lead from the final report. The omission is part of the evaluation evidence.

## Ranking And Output

First guarantee coverage, then rank. The primary shortlist should contain the closest verified candidates, but it should not contain six near-duplicates from one mechanism family when an alternative or validation family is available.

Use this order:

1. verified high-relevance direct-use candidate;
2. verified relevant direct-use candidate;
3. verified high-relevance mechanism-transfer candidate;
4. verified relevant mechanism-transfer candidate;
5. unresolved or background candidate, clearly labelled and kept out of the primary claims.

Path diversity is a coverage signal and tie-breaker, not proof of relevance. A source may be useful even when its runtime cannot be deployed in the target environment, but the report must say `mechanism-transfer` rather than implying direct reuse.

The final answer must include:

- resolved anchor and mechanism fingerprint;
- known leads recovered and not recovered;
- primary new discoveries, with their bridge and discovery lane;
- hard negatives or generic results moved out of the primary list;
- covered and uncovered mechanism families;
- identity and evidence status;
- a bounded statement that the result is not an exhaustive internet search.

When the user says “this is the kind of project I meant,” add it to the current evaluation ledger and explain whether it was already present, recovered, or genuinely new. Do not silently rewrite the earlier result as if the Skill had found it originally.

## Evaluation Protocol

To test whether the Skill fixes the user's actual pain point, create a versioned user-aligned benchmark rather than reusing only generic topical relevance labels.

### Task construction

- Collect a declared set of user-provided high-value papers and projects.
- For each one, create a name-hidden prompt using its mechanism, problem, or rough description.
- Add open discovery prompts where no expected name is shown.
- Add hard negatives that are broadly related but not useful for the target decision.
- Include multiple domains when the Skill is claimed to be cross-disciplinary.

The expected source set is an evaluation reference, not a runtime preference profile. Keep it outside the prompt and do not let either condition read it.

### Metrics

Report both discovery and selection:

- `known_lead_recovery@k`: expected sources recovered from a name-hidden clue;
- `baseline_missed_recovery@k`: expected sources found by the Skill but missed by baseline;
- `user_approved_novel@k`: new candidates that the user later accepts as useful;
- `mechanism_family_coverage`: direct, alternative, validation, failure, and current families covered;
- `hard_negative_rate`: broad but low-value candidates in the primary shortlist;
- `completed_trial_rate`: trials that produce a valid final answer before the hard deadline;
- `recovery_per_minute` and `recovery_per_10k_tokens`: recovery normalized by completion cost;
- ordinary `nDCG`, precision, identity validity, token cost, and completion.

Do not infer user approval from clicks, stars, or an LLM judge. Record the user's label and short reason. If no user label is available, mark the endpoint exploratory.

### Interpretation

A Skill can lose generic nDCG and still solve a missed-source problem if it recovers high-value leads that the baseline misses. Conversely, a longer list or more unique URLs is not a success if the new candidates are not bridged, verified, or useful to the user's decision.

## Boundaries

- This protocol does not reproduce TikTok, Xiaohongshu, or WeChat recommendation graphs.
- User-provided leads establish an evaluation target, not proof that the sources are correct or useful for every project.
- A recovered known lead is not independent discovery.
- A candidate found through a mechanism bridge still requires authoritative identity and source-depth checks before it supports a claim.
- A small user-aligned benchmark can show progress for the user's discovery problem, but cannot prove universal superiority across models, domains, or dates.
