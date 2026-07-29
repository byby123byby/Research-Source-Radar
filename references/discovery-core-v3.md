# Discovery Core v3

Use this route when the main failure is not false relevance but missed research-moving
papers, projects, methods, or evidence. v3 separates **candidate generation** from
**source audit**. The first stage should widen the search through independent
ecosystems; the second stage should remove identity, evidence, and transfer errors.

## Why v2 was not enough

The previous route described a 12-18 item candidate pool, but the host agent could
still stop after the first plausible search family. A larger number in a prompt is
not a candidate generator. v3 requires a material plan with explicit lanes,
ecosystems, query families, and a bounded candidate ledger before deep ranking.

## Two cores

### Discovery Core

Discovery Core may collect compact metadata, snippets, release signals, citation
edges, dependency edges, organization pages, conference artifacts, and technical
coverage. It may not treat any of them as evidence until Audit Core verifies them.

For each run:

1. freeze the research question, constraints, domain profile, cutoff, and known leads;
2. generate one plan from the matching domain ecosystems;
3. run at least three materially different lanes when the user asks for missed or
   new work: mechanism, artifact/ecosystem, and alternative/validation/failure;
4. add current-attention or adjacent-domain lanes only when they have a concrete
   bridge to the question;
5. normalize and deduplicate the union into a metadata candidate pool;
6. keep the raw lead, route, query, ecosystem, bridge, and unresolved risk for every
   candidate, including candidates later excluded.

The plan must expose an ecosystem-specific query template for each configured
adapter, not only a list of ecosystem names. If the host declares which adapters
are actually available, the plan records the remaining ecosystems as uncovered;
it never implies that an unavailable adapter was searched. A missing adapter is a
reported coverage gap, not a reason to silently substitute a second query against
the same index.

The default pool is 18-30 compact candidates. This is a metadata ceiling, not a
license to read 30 full papers. Deep review is limited to the top eight plus
explicit known leads and high-risk candidates.

### Audit Core

Audit Core runs after fusion and before any recommendation:

- verify the canonical locator and title/owner against authoritative metadata;
- collapse mirrors, forks, duplicate DOIs, preprint/published duplicates, and
  re-posted blog entries;
- require two concrete anchor matches and one mechanism or evidence bridge;
- label direct use, mechanism transfer, unresolved, and excluded separately;
- preserve a failed or unresolved candidate in the gap record rather than silently
  replacing it with a popular result.

Audit Core is allowed to reduce the pool. It must never manufacture a candidate to
fill a missing family.

## Source ecosystems are adapters, not a universal ranking

Select only ecosystems relevant to the domain. Typical adapters include:

| Domain | Candidate ecosystems | What they can reveal |
|---|---|---|
| Computing | GitHub/GitLab, package registries, Hugging Face, arXiv, conference artifacts | code, dependencies, model/dataset links, benchmarks, successors |
| Health | PubMed, Europe PMC, trial registries, guidelines, regulator pages | trials, corrections, safety and implementation evidence |
| Social science/business | OpenAlex, SSRN, IDEAS/RePEc, NBER, society pages, filings | working papers, measures, data, operational constraints |
| Humanities | library catalogs, H-Net, Humanities Commons, DH venues, institutional repositories | editions, archives, provenance, interpretive debates |
| Arts/design/media | museum records, exhibition catalogs, practice-research repositories, production credits | authorship, material process, documented practice, critical context |
| Methods/data | Zenodo, OSF, Figshare, Dataverse, standards bodies | versions, protocols, datasets, reuse and replication |

Attention signals are discovery-only. Stars, downloads, citations, editorial
selection, and reposts must remain separate from relevance and evidence quality.

## Candidate ledger

The minimum compact record is:

```json
{
  "candidate_id": "stable-run-local-id",
  "canonical_identity": "pending-or-resolved",
  "title_or_name": "displayed title",
  "source_type": "paper-or-repository-or-other",
  "discovered_via": ["mechanism", "artifact"],
  "ecosystems": ["arxiv", "github"],
  "anchor_matches": ["mechanism", "outcome"],
  "bridge_to_question": "one concrete sentence",
  "neighbor_family": "alternative|validation|failure|implementation|transfer",
  "attention": "none|observed|triangulated",
  "identity_status": "pending|verified|failed|unresolved",
  "direct_use_fit": "direct|partial|incompatible|unknown",
  "transfer_fit": "direct|adapt|weak|none",
  "duplicate_of": null,
  "exclusion_reason": null
}
```

`path_count`, stars, citation count, and model confidence are provenance or tie
signals. None can substitute for the two-anchor gate or authoritative identity.

## Selection and budget

Use a lexicographic order rather than one opaque score:

1. verified identity and direct task fit;
2. concrete mechanism, outcome, or evidence bridge;
3. family coverage and non-duplication;
4. authority and evidence depth;
5. transfer value and deployment fit;
6. freshness or attention as a tie-breaker.

Return one ranked list under the selected profile's `max_sources` limit in
`runtime-contract-v1.json`. Give each source an explicit role so direct work,
transferable mechanisms, validation, current work, and adjacent bridges remain
visible without creating competing output buckets.

The host should use the planner's `fast` profile for a fast run: two batched
search calls, five query records, one targeted open, and one gap probe. It may
stop after the first batch when four identity-valid candidates cover three
source families and the required lanes. A standard or deep run may declare a
larger budget, but it must record that deviation and its reason. Every run
reports candidates collected, candidates audited, budget used, budget remaining,
and uncovered ecosystems.

## Evaluation protocol

Do not evaluate v3 only with generic nDCG. Use a held-out lead set assembled from
sources the user explicitly supplied or later accepted, but never place that set in
the runtime prompt. Report:

- `known_lead_recovery@k`;
- `baseline_missed_recovery@k`;
- `user_approved_novel@k` after blinded review;
- mechanism-family coverage and hard-negative rate;
- identity-validity and completion;
- recovery per minute and per 10,000 tokens.

For a discipline-diverse smoke test, provide a frozen task file outside the
public Skill package. It should cover several fields and contain prompts,
constraints, source types, and evaluation focus. It is a task set, not a gold
answer list: blind human review is still required for user-approved novelty,
mechanism-family coverage, and hard-negative quality.

A v3 route may become the default only after repeated paired trials show better
known-lead or user-approved-novel recovery, no material primary-quality loss, and a
declared cost ceiling. A larger candidate list without a better decision is not a
successful upgrade.

## Boundary

This module cannot reproduce a private social-platform recommender or guarantee
exhaustive internet recall. Its contribution is to make independent discovery
routes explicit and test whether they recover valuable leads that a lexical-first
baseline misses.
