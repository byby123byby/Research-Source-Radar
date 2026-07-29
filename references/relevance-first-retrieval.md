# Relevance-First Retrieval

Use this reference when the user cares about “truly related”, “better than a normal AI search”, paper-to-repository links, or a comparative A/B result. The objective is not to maximize the number of links. It is to improve the quality and coverage of the ranked shortlist while keeping identity and evidence checks separate.

## 1. Freeze A Target Card

Before searching, write a compact target card:

- research decision or question;
- domain/application and target population or environment;
- research task or desired outcome;
- input/data modality;
- core mechanism or workflow;
- deployment, safety, licensing, cost, and time constraints;
- required evidence type;
- explicit non-goals and hard negatives.

Do not rank a candidate against a vague topic label. A source should be judged against the target card and the user's seed, not against the broad field name.

## 2. Keep Discovery Lanes Separate

Run only the lanes that fit the target card, and retain `discovered_via` for every candidate:

1. **Lexical/exact lane:** exact names, titles, aliases, author names, DOI, repository owner, and distinctive phrases. This is the anchor lane and must remain available even when an embedding or agent search is used.
2. **Decomposition lane:** split the question into bounded subquestions such as mechanism, target task, evaluation, failure mode, and deployment constraint. Search each subquestion separately.
3. **Mechanism lane:** search the mechanism with domain synonyms and competing terminology, not only the seed's name.
4. **Artifact/bridge lane:** search for code, dataset, benchmark, implementation, citation, DOI, repository links, and reproducibility statements.
5. **Failure lane:** search limitations, negative results, corrections, ablations, and competing methods.
6. **Current lane:** use a dated freshness route only when recency matters. Popularity remains a discovery signal, never a relevance label.

Do not concatenate these results into one raw list. First normalize identities, remove mirrors and duplicates, then fuse the candidate sets with transparent rank fusion such as reciprocal rank fusion. Path count is provenance and a tie-breaker only; repeated indexing or popularity cannot repair a weak mechanism match.

In the fast pass, ask search tools for short result payloads and retain only snippets, canonical identity fields, and the evidence needed for the next gate. Do not open the full body of every paper or repository README. Full source reading belongs to the final shortlist or an explicit deep/source-depth request; otherwise large tool payloads can overwhelm the context without improving the ranking decision.

## 3. Rank In Two Stages

### Stage 1: Cheap relevance gate

Reject or move to transfer-only when a candidate has no verified identity, shares only a broad keyword, or fails the two-anchor rule. The two anchors should come from the target card: for example, domain plus task, task plus modality, mechanism plus outcome, or mechanism plus target ecosystem. Preserve unresolved candidates as gaps rather than silently promoting them.

### Stage 2: Focused source rerank

Read only the shortlist and score these dimensions separately:

- task and problem fit;
- mechanism fit;
- input/data and outcome fit;
- constraint and deployment fit;
- evidence depth and authority;
- direct-use versus mechanism-transfer fit;
- freshness, maintenance, license, and safety;
- unresolved ambiguity or contradiction.

Use a lexicographic decision before any aggregate score: verified high-relevance direct use, verified relevant direct use, verified high-relevance transfer, then verified relevant transfer. A citation count, star count, or model-generated similarity score cannot override a failed relevance gate.

## 4. Paper-to-Repository Evidence

Use a separate relation field for paper/repository links:

| Relation status | Evidence | Use |
|---|---|---|
| `explicit_linked` | paper code link, repository DOI/title link, or official artifact statement | supports a direct artifact relation after identity verification |
| `metadata_linked` | matching title/authors/organization plus consistent version or benchmark | useful supporting evidence; inspect the source body |
| `inferred_related` | shared topic, method, tags, citations, stars, or embedding proximity | discovery only; cannot prove the repository implements the paper |
| `unresolved` | plausible match without authoritative confirmation | keep out of evidence claims and report as a gap |

Paper2Repo is useful here as a design precedent: it models paper-repository neighborhoods and explicit bridge links, but its historical co-star graph, CS-only data, and distant supervision are not proof of relevance for a new task. Adapt the bridge-evidence distinction; do not import its old training stack as a runtime dependency.

## 5. Compare Approaches Before Recommending One

For implementation-oriented work, make an approach card for each serious candidate:

```text
approach:
source_identity:
problem_and_inputs:
mechanism:
reported_outcome:
evidence_type:
limitations:
target_fit:
adaptation_cost:
verification_needed:
```

Paper Lantern is a useful workflow precedent for collecting multiple approaches, implementation details, benchmarks, and failure modes before coding. Its public benchmark is coding-centric and mainly self-reported; it is not evidence that its hosted research interface improves paper relevance. Treat it as a process pattern, not as a ranking authority.

## 6. Separate Discovery From Selection In Evaluation

When claiming that the Skill is better than an unskilled baseline, evaluate at least two stages:

- **Discovery:** did the condition recover the relevant pool, including novel candidates and supplied known leads?
- **Selection:** did it rank highly relevant and identity-valid candidates near the top?

Keep known-lead recovery separate from novel discovery: recovering a project the user named proves recovery, not independent discovery. Judge the pooled union blindly, retain hard negatives and failed trials, and report task-level paired differences with intervals.

ResearchArena is the main evaluation precedent: it separates discovery recall/precision from selection metrics and shows why a strong language model can still underperform a simpler lexical or embedding baseline. Preserve a lexical lane inside the Skill and keep the no-Skill baseline condition unchanged.

For a stronger benchmark extension, add declared aspect labels such as `mechanism`, `implementation`, `evaluation`, `failure`, and `recent_work`, then report aspect coverage and duplicate rate alongside nDCG, pooled recall, and precision. Do not retrofit these labels into an already scored run; create a new versioned benchmark.

## 7. Use The Four Sources Correctly

- **ResearchArena:** evaluation design and discovery/selection separation; not a runtime dependency.
- **Paper2Repo:** paper-to-code bridge evidence and artifact-neighborhood ideas; not a relevance oracle.
- **paper-search:** OpenAlex, Semantic Scholar, Unpaywall, and GitHub transport plus DOI deduplication; not a relevance or evidence gate. Citation sorting must remain secondary.
- **Paper Lantern:** approach-comparison and research-before-implementation workflow; not a peer-reviewed relevance result or a required hosted service.

Primary sources inspected: [ResearchArena paper](https://arxiv.org/abs/2406.10291), [ResearchArena repository](https://github.com/cxcscmu/ResearchArena), [Paper2Repo paper](https://arxiv.org/abs/2004.06059), [Paper2Repo repository](https://github.com/hrukalive/WWW2020_paper2repo), [paper-search repository](https://github.com/Csed-dev/paper-search), [paper-search package](https://pypi.org/project/paper-search/), and [Paper Lantern's public challenge repository](https://github.com/paperlantern-ai/paper-lantern-challenges).

## Stop Rule

Stop when the declared search lanes and one targeted coverage probe are complete, the identity gate has been applied, and remaining gaps are recorded. A longer list is not evidence of a better result. The final report must state which candidates were directly relevant, which were transfer-only, which were hard negatives, and which could not be verified.
