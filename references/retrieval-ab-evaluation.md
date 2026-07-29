# Retrieval Skill A/B Evaluation

## Contents

- [Research question](#research-question)
- [Conditions and isolation](#conditions-and-isolation)
- [Frozen task sets](#frozen-task-sets)
- [Outcomes](#outcomes)
- [Pooled blind judgment](#pooled-blind-judgment)
- [Analysis](#analysis)
- [Execution](#execution)
- [Interpretation boundary](#interpretation-boundary)
- [Release-audit separation](#release-audit-separation)

## Research Question

Under a fixed model, web-tool set, cutoff date, and execution budget, does loading `research-discovery-and-translation-audit` improve relevance, source validity, target-project constraint fit, and efficiency of research/open-source discovery compared with the same agent without the Skill?

The independent variable is target-Skill presence. The primary outcomes are `nDCG@10` and the number of valid, highly relevant sources. Invalid-source rate and completion are safety outcomes. Time and token-normalized useful-source yield are efficiency outcomes.

This is a benchmark of one frozen model/tool/Skill configuration. It is not a study of BLV users, does not measure accessibility benefit, and cannot establish exhaustive discovery.

## Discovery And Selection Must Be Reported Separately

Following the distinction used by ResearchArena, do not treat one aggregate relevance score as proof that the Skill discovers more work. Keep two questions separate:

- **Discovery:** did a condition recover the relevant candidate pool, including supplied known leads and candidates that were not named in the prompt?
- **Selection:** did it place highly relevant, identity-valid candidates near the top of the ranked list?

Known-lead recovery is a useful safety check but is not novel discovery. If a task contains named leads, record them separately from the pooled novel-candidate analysis. Preserve unresolved leads and hard negatives instead of replacing them with popular generic sources.

The current public runner keeps its frozen schema and primary metrics unchanged. A future benchmark revision may add declared aspect labels such as mechanism, implementation, evaluation, failure, and recent work, then report aspect coverage and duplicate rate. Do not retrofit those labels into an already scored run; create a new benchmark ID and rerun both conditions. ResearchArena is an evaluation precedent, not evidence that this Skill generalizes across models or disciplines.

## Conditions And Isolation

- `baseline`: a fresh temporary `CODEX_HOME` contains only a short-lived link to the existing authentication file. It contains no user Skills and does not load the user's normal configuration or project rules.
- `skill`: the same isolation is used, but the target Skill directory is copied into the temporary home's `skills/` directory.
- Both conditions use the same model, reasoning effort, prompt, response schema, internet availability, hard timeout, and source limit.
- The runner invokes the current Codex CLI's stable top-level `codex --search exec` option for live web retrieval. Do not silently replace it with an experimental feature flag; a CLI change creates a new benchmark version and must be reported.
- Every trial is ephemeral. Output from one trial is not provided to another.
- Trial order is randomized from a recorded seed. Repetition and condition remain in the execution manifest but are removed from the pooled judgment file.
- The runner never copies authentication into the experiment output. Its temporary home is removed after each trial.

The prompt says only to use any installed Skill that applies. It does not summarize the target Skill for the baseline. The common JSON response schema is intentionally narrow: ranked sources, queries, gaps, and constraint notes. Source validity and relevance are judged outside the model response.

## Frozen Task Sets

The evaluator must supply a versioned task set from outside this Skill package. Keep the task file, hidden gold labels, and scored outputs outside the public runtime package.

- Pilot and main trial counts are defined by the external task file.
- Categories should cover exact identity, ambiguous user-shared seeds, similar-work expansion, current landscape, and mechanism transfer when relevant.
- Task-specific constraints, dates, and evaluation criteria must remain visible in the external task file.

Do not change task wording, source limits, model, reasoning effort, timeout, or scoring rules after viewing condition results. A material change creates a new benchmark version.

## Discovery Core v3 Cross-domain Extension

The v3 extension targets the missed-source problem across disciplines. Provide its task file, manifests, pooled judgments, and scores outside the public Skill package, and keep them separate from any private or project-specific task set.

The v3 pilot's execution result is not a retrieval-quality result until its condition-blind pool has been judged. A completed run establishes only completion, runtime, and source-pool construction. Relevance, identity validity, constraint fit, and discovery recall require the same external judgment and scoring procedure described below.

## Outcomes

### Primary

- `ndcg_at_10`: graded ranking quality using relevance 0/1/2.
- `valid_high_relevance_sources`: retrieved sources judged both highly relevant and identity-valid.

### Safety And Secondary

- `invalid_source_rate`.
- `completion`.
- `precision_at_10`.
- `pooled_recall_at_20`.
- `direct_fit_sources`.

### Efficiency

- `valid_relevant_per_1k_tokens`.
- `valid_relevant_per_minute`.
- `wall_seconds`.
- `total_tokens`.

### Coverage And Compression Extension

The seed-neighbor policy should be evaluated with two additional observations when the implementation uses the adaptive coverage probe:

- whether the final candidate set covers the declared direct-use, alternative, validation, failure, and current-work categories;
- whether compact-context loading and any optional compressor reduce tokens without reducing identity validity or highly relevant sources.

The coverage probe is allowed at most one targeted gap query within the existing hard search budget. A compressor such as [LLMLingua](https://github.com/microsoft/LLMLingua) or a memory adapter such as [Mem0](https://github.com/mem0ai/mem0) must be tested as a separate adapter condition. It must not be silently enabled in the Skill condition, and its project-reported token savings must not be treated as evidence for this Skill.

Raw source count is not a success criterion. Duplicate, invented, weakly related, or constraint-incompatible sources cannot improve the primary outcomes.

## User-Aligned Discovery Evaluation

The generic v1 task set does not fully measure the user's motivating failure mode: a baseline may return reasonable sources while failing to surface projects or papers that the user would later recognize as valuable. A future benchmark revision must therefore add a separate discovery-recall track instead of changing the meaning of v1 nDCG.

### Frozen task design

- Build a declared reference set from sources the user explicitly supplied or accepted; do not infer it from private social-platform history.
- Create name-hidden tasks using the source's mechanism, problem, input, outcome, or rough description. The expected source name must not appear in the prompt.
- Add open discovery tasks with no expected name, plus hard negatives that share a broad topic but lack the target decision or mechanism.
- Include several domains when cross-disciplinary discovery is claimed.
- Run baseline, initial Skill, and upgraded Skill against the same prompt, model, tools, cutoff, source limit, timeout, and repetitions.

The reference set is an evaluation target, not a runtime preference profile and not proof that an expected source is universally best. Preserve user labels and reasons separately from the ordinary blind pooled judgment.

### Additional outcomes

Report these alongside the existing selection metrics:

- `known_lead_recovery@k`: expected sources recovered from a name-hidden clue;
- `baseline_missed_recovery@k`: expected sources found by the Skill but missed by baseline;
- `user_approved_novel@k`: newly discovered sources later accepted by the user as useful;
- `mechanism_family_coverage`: direct, alternative, validation, failure, and current families covered;
- `hard_negative_rate`: broad but low-value sources placed in the primary shortlist;
- `bridge_completeness`: new candidates with a concrete bridge to the seed.
- `completed_trial_rate`: valid final answers produced before the hard deadline;
- `recovery_per_minute` and `recovery_per_10k_tokens`: known-lead recovery normalized by execution cost.

Do not infer user approval from stars, clicks, an LLM judge, or a source's popularity. If the user has not labelled a candidate, report the endpoint as exploratory. A known-lead recovery is not independent discovery, and a longer candidate list is not evidence of improvement. A discovery condition that times out more often or spends materially more tokens must not be declared superior without reporting that cost.

The user-aligned track is the correct test for the claim “the Skill finds valuable sources that ordinary AI search tends to miss.” It does not replace identity verification, pooled relevance judgment, or the existing selection metrics. Create a new benchmark ID before running it; never retrofit these labels into an already scored v1 run.

## Pooled Blind Judgment

An exhaustive gold set is unavailable. Use pooled judgment:

1. Merge unique task-source pairs returned by both conditions.
2. Normalize GitHub, DOI, arXiv, and public URLs before deduplication. Merge paper or preprint copies with the same normalized bibliographic title so a DOI landing page and an author-hosted PDF cannot be counted twice.
3. Remove condition, repetition, rank, model prose, and trial identity, while retaining the original task constraints and evaluation focus.
4. Judge every pooled source against the original task, constraints, and evaluation focus.
5. Use `relevance`: 0 irrelevant, 1 relevant, 2 highly relevant.
6. Use `identity_valid`: `valid`, `invalid`, or `unresolved` after opening an authoritative source.
7. Use `constraint_fit`: 0 incompatible, 1 useful only by mechanism transfer, 2 directly compatible.

The primary analysis requires all pool rows to be judged. Automated model judging may be reported as exploratory only; the defensible result requires a human judgment pass blinded to condition. If two judges are available, preserve both raw files and report agreement before resolving disagreements.

## Analysis

The scorer first computes trial metrics. It then averages repetitions within task and condition, subtracts baseline from Skill, and bootstraps tasks rather than individual repeated trials. It reports the mean paired difference, 95% percentile bootstrap interval, and task win rate.

No p-value is a prerequisite for interpretation. Report effect direction, magnitude, interval, failures, and the frozen benchmark scope. If the interval crosses zero, describe the evidence as inconclusive for that endpoint. Do not select a different primary metric after seeing results.

## Execution

From the installed Skill root:

```bash
python3 scripts/retrieval_ab_benchmark.py validate-tasks \
  --tasks /path/to/frozen-task-set.json
```

Run the fail-closed contract check before preparing or executing live trials:

```bash
python3 scripts/preflight_retrieval_experiment.py \
  --skill-root "$HOME/.codex/skills/research-discovery-and-translation-audit" \
  --tasks /path/to/frozen-task-set.json
```

The preflight blocks live execution when the baseline and Skill schemas differ, source caps conflict, normalization differs, legacy output rules remain, or the runner and installed target Skill are different versions. A passing run emits a contract fingerprint. The live runner also writes that result to `preflight_report.json` beside the trial manifest.

Prepare a pilot outside the Skill package:

```bash
python3 scripts/retrieval_ab_benchmark.py prepare \
  --tasks /path/to/frozen-task-set.json \
  --phase pilot \
  --runs 2 \
  --seed 20260716 \
  --model gpt-5.6-sol \
  --reasoning-effort high \
  --max-wall-seconds 600 \
  --max-sources 6 \
  --output-dir /path/to/retrieval-ab-pilot
```

Execute pending trials only after reviewing the manifest. The explicit confirmation flag prevents accidental model/network spending:

```bash
python3 scripts/retrieval_ab_benchmark.py stage-treatment \
  --source-skill . \
  --output /path/to/holdout-clean-treatment \
  --holdout-gold /path/outside/the/treatment/hidden-gold.json

python3 scripts/retrieval_ab_benchmark.py run \
  --run-dir /path/to/retrieval-ab-pilot \
  --codex /path/to/codex \
  --source-codex-home "$HOME/.codex" \
  --target-skill /path/to/holdout-clean-treatment \
  --holdout-gold /path/outside/the/installed/skill/hidden-gold.json \
  --confirm-live-run
```

The runner treats account quota exhaustion as a batch-level infrastructure
blocker. It records the failed trial, stops immediately, and leaves later trials
pending so correlated quota failures do not contaminate the comparison. Ordinary
retrieval failures and timeouts remain visible trial-level outcomes. Do not score
a run until every preregistered pair has completed; retry only after the external
blocker has been resolved.

Known-lead recovery additionally requires a holdout-contamination check. Keep
gold labels outside the installed runtime package and pass them with
`--holdout-gold`; execution is blocked if a canonical hidden identifier appears
anywhere in the treatment Skill. A contaminated run measures memorization or
packaging leakage, not autonomous source discovery.

The shared query cap is derived from the active runtime profile rather than
written as a separate prompt constant. A recovery benchmark therefore gives both
conditions the same six-record ceiling. This prevents a baseline-oriented
eight-query instruction from contradicting the treatment's six-record recovery
contract.

The hidden known-lead scorer fails closed when any preregistered response is
missing, failed, or no longer matches its manifest identity. Partial pairs may be
inspected for debugging, but they cannot produce an effectiveness result.

Create the blind pool:

```bash
python3 scripts/retrieval_ab_benchmark.py pool \
  --run-dir /path/to/retrieval-ab-pilot \
  --tasks /path/to/frozen-task-set.json \
  --output /path/to/retrieval-ab-pilot/blind_judgments.json
```

After every row has been judged:

```bash
python3 scripts/retrieval_ab_benchmark.py score \
  --run-dir /path/to/retrieval-ab-pilot \
  --judgments /path/to/retrieval-ab-pilot/blind_judgments.json \
  --output /path/to/retrieval-ab-pilot/metrics.json \
  --report /path/to/retrieval-ab-pilot/report.md
```

## Interpretation Boundary

Software unit tests show that preparation, isolation, validation, pooling, and scoring behave as tested. They do not show that the Skill improves retrieval. A completed, judged A/B run is required for an effectiveness claim.

Pooled recall is recall within the judged union, not recall over all existing work. A positive result applies to the frozen model, date, tools, tasks, and budgets. A negative or inconclusive result should be retained; do not silently replace difficult tasks or discard failed trials.

## Release-Audit Separation

Research-source reverse audit remains part of this Skill because it shares the candidate ledger and source-to-outcome evidence chain. Software release assurance is a maintainer concern. Before the final public release, extract the generic release runner into a separately versioned `Agent Skill Release Assurance` package, keep `RELEASE_COMPLETENESS.json` as target metadata, rerun the complete release gate, then freeze and benchmark the final user-facing Skill. Do not split after collecting the definitive A/B result without rerunning the benchmark.
