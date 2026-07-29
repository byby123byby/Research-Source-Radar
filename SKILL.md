---
name: research-discovery-and-translation-audit
description: Find and verify papers, repositories, datasets, standards, and grey literature; recover relevant long-tail and mechanism-neighbor sources across disciplines; translate mechanisms into a target project; and audit source identity, evidence, implementation, and claims. Use for open-ended research discovery, related papers/projects/methods, current or adjacent work, or when a user supplies a paper/project/screenshot/video lead.
---

# Research Discovery And Translation Audit

## Default Route

This Skill is a bounded discovery-and-audit workflow, not an exhaustive search promise. It separates:

1. **Discovery:** find direct matches, alternatives, mechanism neighbors, failure cases, artifacts, and recent work.
2. **Audit:** verify identity, evidence, implementation status, transfer fit, and claim boundaries.

### Natural-Language Entry

Users do not need to provide a structured research contract to start. Treat ordinary requests such as “用 Research Source Radar 帮我看看和这个项目相关的论文、开源项目和资料” or “帮我找找这个方向有什么值得看的项目” as a valid open-ended discovery request. Extract the project, question, known constraints, and source types from the current conversation. If the project context is already visible, do not ask the user to repeat it. If one missing detail would materially change the search, ask one short clarification; otherwise proceed with explicit assumptions.

The default user-facing response should be a Chinese candidate radar with a bounded list, not a request for the user to fill a form first. The Skill should internally create the scope card, discovery lanes, date window, and evidence requirements, then report those assumptions briefly with the results. A longer structured prompt is optional when the user wants tighter control, reproducibility, or an A/B evaluation.

Users may paste one or more sources they personally consider relevant: papers, repositories, datasets, screenshots, videos, or rough names. Resolve every source first, then build a visible **preference hypothesis** from the shared mechanisms, meaningful differences, evidence depth, deployment boundary, and stated reasons across the examples. One example produces a tentative single-anchor hypothesis; multiple examples can support a stronger mechanism constellation, but the Skill must not infer a preference from superficial shared keywords. Use the hypothesis to expand queries and order candidates for the current task, label its evidence and uncertainty, and keep the supplied examples out of novel-discovery counts. Do not persist or transfer the hypothesis unless the user explicitly confirms an export or project preference.

Use the smallest route that answers the request. For an open-ended request for related papers, projects, methods, current work, or ideas that could move a project forward, use the **recovery route automatically**. Use the **fast neighbor route** only when the user explicitly asks for a quick/short/smoke/benchmark answer or a single known-source lookup. Do not silently run a full literature review.

### Load References Progressively

Read only the references needed for the current request:

| Situation | Read |
|---|---|
| Fast shortlist, benchmark, or hard budget | `references/fast-budget-route.md`, then one applicable ecosystem/domain file |
| Open-ended papers/projects/method discovery, or ordinary search misses useful work | `references/missed-source-recovery-v5.md`, then one applicable ecosystem/domain file |
| Missed valuable sources or long-tail neighbors | `references/discovery-core-v3.md` and `references/user-aligned-discovery.md` |
| User supplies a paper, repository, screenshot, video, or uncertain name | `references/seed-to-neighbor-discovery.md` |
| Current, popular, recent, or cross-disciplinary work | `references/source-ecosystems-and-time-windows.md` and the relevant trend reference |
| User wants a Chinese research radar, explicit feedback learning, or a human review of discovered candidates | `references/research-radar-feedback-loop.md` |
| Explicit `deep`, `full`, or `audit` request | `references/operational-manual-v3.md` plus the applicable specialist references |
| Source authenticity or evidence contract | `references/contract-schema.md` and `scripts/research_contract.py` |
| Runtime budgets, source roles, and result limits | `references/runtime-contract-v1.json` |
| Release audit of this Skill | `references/audit-convergence.md` and `RELEASE_COMPLETENESS.json` |

Do **not** load `references/operational-manual-v3.md` during the default recovery or fast route. It contains the detailed legacy procedure and is intentionally deferred.

For large references, inspect headings first and load only the relevant section. Useful commands are:

```bash
rg -n '^#|^##|^###|two-anchor|budget|identity|ecosystem|failure|translation' references/<file>.md
sed -n '<start>,<end>p' references/<file>.md
```

## Hard Invariants

- Never promise that every relevant or latest source was found.
- Use one ranked `sources` list. The default recovery cap is 12; obey a smaller user or host cap. Give every source exactly one role: `direct`, `mechanism`, `validation`, `current`, or `adjacent`. Do not create a second exploration list.
- Treat `references/runtime-contract-v1.json` as the only source of truth for route budgets, source limits, roles, and normalization. Do not restate different numeric limits elsewhere.
- Before a live retrieval benchmark, require the fail-closed offline preflight. It must confirm runtime-contract validity, baseline/Skill schema parity, equal normalization, runner/target version parity, planner limits, and documentation parity before network or model spending begins.
- Treat a user-provided source as a relevance anchor, not as verified evidence, until its canonical identity resolves.
- Verify papers through authoritative DOI/Crossref, DataCite, arXiv, or PMID/NCBI metadata. Verify GitHub repositories through the GitHub API and pin a commit, tag, or release when the repository supports an implementation claim.
- Treat the source cap as a maximum, not a quota. Return fewer sources when identity cannot be verified within the bounded run. For papers, prefer the verified DOI, PMID, or arXiv locator in `sources`; a publisher page or search snippet is not a substitute when a registry identity exists. Put unresolved candidates in gaps rather than guessing or repairing an identifier from memory.
- Every presented candidate must include its canonical source URL or stable identifier directly in the card, together with the source type and verification status. A title without a link, a search-result page used as if it were the source, or a “请自行搜索” placeholder is not an acceptable candidate card. If the canonical source cannot be resolved, keep the item only in the unresolved/gap record.
- Keep topical relevance, direct-use fit, mechanism-transfer fit, research impact, evidence quality, freshness, popularity, deployment constraints, and research-attention priority as separate fields. A relevant source may be useful only as a light reference; do not average relevance into a deep-reading or migration recommendation.
- Require at least two concrete anchor matches before a candidate enters the primary shortlist. Broad topical similarity or popularity alone is not enough.
- Keep seed recovery separate from novel discovery. The supplied seed must not be counted as a newly discovered neighbor.
- Preserve unresolved, failed, excluded, and relevant-but-not-hot candidates in the gap record instead of silently replacing them.
- When the user explicitly opts in to feedback learning, store only visible labels, reasons, and tags in a user-chosen project profile. A profile is isolated to its explicitly named target project, study, or practice: never read, merge, or transfer it to another project unless the user explicitly requests a marked export or comparison. Use the profile to adjust query expansion and presentation order, not to bypass identity or evidence gates. Keep an exploration share and never infer a profile from private browsing or social feeds.
- When the user supplies 1-n examples as “the kind of source I want”, treat them as current-task positive anchors and produce a visible preference hypothesis before using it. Separate confirmed user statements, source-observed features, and model hypotheses. Use only confirmed statements and clearly labelled provisional hypotheses for query expansion and presentation order; never present the hypothesis as a fact about the user.
- Never treat stars, citations, downloads, reposts, or model confidence as evidence of relevance or correctness.
- Do not access private social-platform history. A screenshot, post, or video is a discovery lead only; verify the underlying public source independently.
- Never issue an empty search query. If a lane has no valid query, record the skipped lane and continue with the bounded plan.
- Do not execute untrusted repository code or install dependencies merely to inspect a source.

## Route Selection

- `neighbor`: named source/project or related-work request; default for a compact shortlist.
- `landscape`: current and foundational work around a research question.
- `translate`: map selected mechanisms into a project, experiment, policy, humanities, arts, or multidisciplinary setting.
- `refresh`: rerun a dated search for changes, successors, releases, corrections, or retractions.
- `audit`: reverse-check an existing report, implementation, evidence chain, or Skill.
- `full`: explicitly requested deep discovery plus translation and reverse audit.

If the user asks only for a named seed's identity or a compact known-source lookup, use the `neighbor`/fast route. If the user asks both for a named seed and “what is related,” or asks for papers, projects, methods, current work, alternatives, or what could move the project forward, activate the `recovery` route in `references/missed-source-recovery-v5.md` automatically. A special complaint such as “ordinary AI missed it” is not required; the semantic request itself is the trigger. Use fast only for an explicitly short, quick, smoke, benchmark, or single-source request.

## Fast Neighbor Workflow

1. **Freeze the target card:** question, seed, domain, date cutoff, constraints, preferred source types, and what would count as “moves the project forward.”
2. **Fingerprint the mechanism:** task, inputs/outputs, data or modality, core mechanism, deployment boundary, evidence level, and unknowns.
3. **Generate bounded lanes:** exact/direct, mechanism, alternative or failure, artifact/ecosystem, and current/adjacent only when a concrete bridge exists. Use the domain-native ecosystem rather than treating GitHub as universal.
4. **Batch search:** use the planner's `recovery` profile for ordinary open-ended discovery: at most two batched search calls, six query records, two targeted opens, and one coverage probe. The probe is one of the six query records, never a seventh query. Batch independent lanes; do not repeat broad searches. Use `fast` only for an explicitly short request, and use `standard` only when the user explicitly accepts an expanded run.
5. **Normalize early:** collapse mirrors, forks, duplicate DOI pages, reposts, and preprint/published duplicates. Keep one compact record per canonical source.
6. **Apply the two-anchor gate:** require two matches among task/domain, data/modality, mechanism, outcome, or explicit deployment bridge. Keep transfer-only candidates in the same ranking with a `mechanism` or `adjacent` role and a clear limitation.
7. **Verify selectively:** check the strongest shortlist, explicit seeds, ambiguous identities, and high-risk claims. Do not deep-read every candidate.
8. **Stop visibly:** after the first batch, stop if at least five identity-valid candidates cover four distinct source families and the required lanes are represented. Otherwise spend only the second batch or the single gap probe, then report completed lanes, budget used, covered and uncovered families, known-lead recovery, novel candidates, unresolved identities, and the next refresh trigger. Stop starting discovery work after 210 seconds in a 300-second run and reserve at least 60 seconds for identity checks, deduplication, ranking, and final output. At that boundary, finalize from the verified ledger even when fewer than 12 sources remain. A timeout is a visible gap, not a reason to retry the same query.

The default recovery pool is a separate 10-20 candidate ledger and a unified 12-source shortlist, with at least four discovery families attempted before stopping. The explicit fast pool is at most 14 compact metadata candidates and a four-source shortlist. The standard profile retains an 18-30 candidate pool and an eight-source shortlist for explicitly expanded runs. These are ceilings, not targets. A shorter verified answer is better than a padded list.

For recovery, first decompose the request into capability atoms rather than issuing one broad topical search. Attempt distinct query families for the task itself, its mechanism neighbors, implementation/ecosystem artifacts, validation or failure work, and current or community-curated work. Direct matches do not satisfy the exploration requirement by themselves.

Use the recovery query strategy emitted by `discovery_plan.py`: an anchor query, a competing-vocabulary query, a **candidate-reservoir** query, a contrast/failure query, an **anchor-expansion** query, and one coverage probe. A candidate reservoir is a domain-native place that exposes siblings: for computing this may be repository topics, curated collections, benchmark leaderboards, surveys, conference artifact lists, package ecosystems, or maintainer/release networks; in other domains it may be a review, bibliography, catalog, registry, archive finding aid, dataset portal, or methods handbook. The reservoir is only a lead generator: every returned candidate still needs canonical identity and the normal two-anchor gate. After the first identity-valid anchor, spend the anchor-expansion query on a real relation such as cited/related work, maintainer or lab, dependency, successor, benchmark, alternative implementation, or shared dataset. Do not spend both slots on another paraphrase of the user's original wording.

Do not stop merely because the identity and direct-fit thresholds are met: either cover at least four families or record the missing family and spend the bounded gap probe. This is the mechanism that makes a single Skill call search for less obvious project-moving work instead of only returning the most visible results.

### Recovery Output Contract

Return one usefulness-ranked list of at most 12 verified candidates. Roles make diversity visible without reserving fragile buckets: direct solutions, transferable mechanisms, validation or failure evidence, current work, and concrete adjacent-field bridges can compete in one ranking. Record attempted, covered, and uncovered families, budget use, and stop evidence in `discovery_trace`. Known-lead recovery and novel-neighbor counts belong to the external evaluator; do not ask the model to self-score them.

### Runtime Context Guard

For every web/search call in the fast route, request the shortest available response format. Keep only the canonical title or owner, URL or identifier, date/version, source type, and one mechanism/evidence sentence. Do not paste raw search pages, full abstracts, repository READMEs, or repeated metadata into the next query; normalize them into the compact ledger and discard the raw payload. Open a page only for a final candidate, an explicit seed, or an unresolved identity. If the tool has no short-response control, enforce the same field limit in the working ledger.

For the default recovery route, use `python3 scripts/discovery_plan.py ... --budget-profile recovery` when a deterministic plan is needed. The resulting plan exposes `early_stop` and `network_policy`: no same-query retry, a bounded soft/hard timeout pair, an exploration-slot reserve, and `record_gap_and_continue` on timeout. The host must not claim that an unavailable ecosystem was searched. Use `--budget-profile fast` only for an explicitly short request.

## Discovery Core v3

When the user says ordinary AI search returns plausible results but misses the few sources that would change the project, use the v5 recovery plan and its `discovery_plan.py` helper with `--budget-profile recovery`. The plan must expose:

- mechanism, artifact/ecosystem, alternative/validation/failure, current, and adjacent lanes as applicable;
- domain-native ecosystems and query templates;
- a contribution map and gap matrix;
- candidate provenance, bridge, family, identity status, direct/transfer fit, and unresolved risk;
- one bounded coverage probe rather than an unlimited synonym sweep;
- a unified ranked list with explicit roles and at least four attempted discovery families.

Run the deterministic planner when useful:

```bash
python3 scripts/discovery_plan.py --help
```

Do not claim that v3 was executed unless the final trace records the plan, lanes, queries, stop evidence, and uncovered ecosystems. Use `cross-domain-discovery-tasks-v1.json` for the frozen cross-domain evaluation; it is a task set, not a gold answer list.

## Chinese Research Radar

When the user asks to discover research opportunities, hot projects, or sources they would not have known to search for, present the result in Chinese unless the user requests another language. Treat popularity as a first-class candidate entrance alongside problem/mechanism, graph expansion, and cross-domain bridges. Do not let it replace identity, relevance, or evidence checks.

Keep a broad metadata ledger before selecting. Present candidates in four human-readable groups: `优先看`, `热门前沿`, `跨域启发`, and `持续关注`. Explain for every presented candidate what it is, why it is relevant now, the mechanism that could transfer, the direct-use versus adaptation boundary, the source URL, and the dated basis for any popularity statement. Do not pretend every watchlist candidate has had the same review depth as a verified priority source.

The visible source link is mandatory, not optional metadata. Put it immediately after the candidate title in the Chinese card. For a paper use DOI, PMID, or arXiv; for a repository use the canonical owner/repository URL; for a dataset, registry, standard, or policy use the authoritative landing page. Do not hide the only source in a bibliography at the end.

When the user opts in, use `references/research-radar-feedback-loop.md` and `scripts/radar_feedback.py` to create a visible Chinese project profile, render candidate cards, record the user's labels and reasons, and show the next-run guidance. The feedback loop must distinguish at least three attention states: explicit deep-priority, mechanism-reference, and relevant-but-light-reference. It may prioritize explicit deep-priority signals, use mechanism-reference signals for query expansion and a bounded secondary queue, and keep light-reference signals out of the deep-reading queue. It must not average all positive-looking labels, read social-account history, infer unstated preferences, silently remove feedback, or use feedback to bypass the normal identity and evidence gates. For effectiveness evaluation, show condition-blind Chinese cards to the user and use their labels to calculate `user_approved_novel@k`; do not let the model grade its own novelty.

If the user says the recommendations are “一般般”, treat it first as a quality diagnostic, not as a global preference. A candidate-specific “一般般” lowers only that candidate to light reference; a batch-level “整体一般般” records a result-quality issue without changing the project profile. Use an explicitly stated reason such as “太泛”“太具体”“没有机制”“来源不真实”“不能推动项目” to adjust the next discovery lane. If the user is willing to refine the miss, ask at most two short targeted questions, preferably one compact multiple-choice question about the desired value (mechanism, implementation, data/metrics, validation, or cross-domain transfer) and one about unwanted result types. Do not ask for a full research contract.

If the user says the results are generally not what they wanted, treat the run as a failed retrieval attempt and recover with minimal clarification rather than asking for a full re-specification. Preserve the failed candidate ledger and its reason, use the current project's explicit preference records and the user's new answers, diagnose whether the miss came from scope, vocabulary, source ecosystem, mechanism bridge, freshness, or actionability, then spend the bounded recovery route on a materially different lane. Ask no more than two short questions at this point; if the user does not answer, continue with the safest interpretation and state it. Do not turn the failed result set into a negative preference profile. Return what changed in the second search, which user preferences were applied, which gaps remain, and whether the failure is unresolved.

## Evidence And Translation

For every selected source, record:

- canonical identity and verification timestamp;
- discovery route and independent path evidence;
- topical relevance and mechanism bridge;
- direct-use and mechanism-transfer fit;
- authority, evidence depth, freshness, maintenance/license, and unresolved risk;
- `adopt`, `adapt`, `represented`, `defer`, `reject`, or `unverified` status;
- the positive test, failure test, provenance record, and claim boundary needed after translation.

Never label an adaptation as a reproduction. Do not turn a rationale into effectiveness evidence. Keep source identity, implementation behavior, and scientific validity as separate checks.

For formal source contracts, use the deterministic validator rather than relying on prose:

```bash
python3 scripts/research_contract.py verify-sources <contract>.json --write
python3 scripts/research_contract.py validate <contract>.json --base . --online
```

For this Skill or another release artifact, use the convergence audit twice without changing the scoped files:

```bash
python3 scripts/audit_release.py --strict-tools
python3 scripts/audit_release.py --strict-tools
```

Stop only at `PASS_CONVERGED`, and report the manifest scope, artifact hash, clean streak, and residual uncovered surfaces.

## Comparative Evaluation

Do not use unit tests or source-identity checks as evidence that this Skill is better than ordinary AI retrieval. For an A/B claim, use `scripts/retrieval_ab_benchmark.py` with a frozen task file, fresh isolated contexts, the same model/tools/cutoff/timeout/source cap, randomized paired trials, a condition-blind pooled judgment, and task-level bootstrap intervals.

Primary outcomes should include graded ranking quality, valid highly relevant sources, known-lead recovery, missed-source recovery, user-approved novelty, mechanism-family coverage, identity validity, and completion. Also report wall time, total tokens, relevant sources per minute, and relevant sources per 10,000 tokens. A larger list or higher popularity count is not an effectiveness result.

The current benchmark is a pilot. Do not claim superiority until repeated blinded trials show better discovery of user-valued sources without material relevance, completion, latency, or token regressions.

## Required Final Output

Return, in this order:

1. question, scope, date, profiles, ecosystems, and time windows;
2. coverage and stop evidence;
3. strongest direct-use and mechanism-transfer candidates with identity status;
4. source-depth limits, unread material, verification failures, and repository health;
5. mechanism/claim translation matrix;
6. adopted evidence and tests;
7. deferred, rejected, unverified, and uncovered items;
8. residual risks and refresh trigger;
9. bounded coverage statement.

Use this bounded statement:

> As of `<date>`, the search covered `<sources>` using the documented query families and eligibility rules. It identified `<n>` candidates, verified `<v>` identities, and deeply reviewed `<m>`. Remaining blind spots are `<gaps>`. This is a reproducible coverage claim, not proof that every relevant source was found.
