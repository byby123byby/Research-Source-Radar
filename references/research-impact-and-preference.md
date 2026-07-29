# Research Impact And Preference Memory

Use this reference when the user cares more about sources that could move a
research project than about components that can be installed immediately. It
defines the distinction between research value and deployment fit, and provides
an opt-in memory contract for the user's explicit feedback.

## Three Separate Decisions

Do not collapse these decisions into one average score:

1. **Relevance:** does the source have a concrete bridge to the current question or project?
2. **Research attention:** should the user spend substantial reading or experimental effort on it now?
3. **Deployment/translation fit:** can a mechanism be used directly, adapted, represented, or only observed?

Many candidates can be relevant while only a few deserve deep investigation. A label such as “可以看看” or “值得看看” should normally remain a light reference unless the user's reason contains an explicit stronger signal such as “值得深入”“夯”“多推荐”“好好看看” or “值得迁移”. The model must preserve the original wording and must not upgrade a light reference into a deep-priority preference.

## Two Independent Rankings

Do not collapse these into one score.

### Research-impact ranking

Ask whether the source could solve a current project obstacle, introduce a new
algorithm or evaluation method, expose a limitation or alternative, create a
meaningful cross-domain connection, or change the project's question,
architecture, experiment, or claim boundary. For every deep-priority item,
write a short `project_shift` and a falsifiable next experiment. A source may
rank highly here even when it cannot run in the target environment. A merely
relevant or light-reference item should have a cheaper action such as “skim the
relevant section” or “retain as a query neighbor”, not a full migration plan.

### Deployment-fit ranking

Separately record whether the source is directly usable under the target's
runtime, platform, license, data, safety, and maintenance constraints. A source
with poor deployment fit is not automatically irrelevant; label it
`mechanism_transfer` or `exploratory` and state the adaptation cost.

When these rankings conflict, show the conflict. A high-impact transfer source
may precede an incremental direct-use component in the research-impact section,
while the direct-use section preserves the practical implementation order.

## Default Result Mix

When the evidence and source budget permit, organize ten selected items as:

```text
3 high-potential research movers
3 mechanism-transfer sources
2 recent or emerging exploratory sources
1 direct-use implementation
1 failure, alternative, or validation source
```

This is a presentation budget, not a guarantee. If a category is empty, report
the gap rather than filling it with a generic result. Recent or popular work may
enter the exploratory section with weaker evidence, but it must never be
presented as validated merely because it is receiving attention.

## Popular And Emerging Signals

When the user asks for hot or recent GitHub projects, inspect time-bounded
signals such as unusual star or contributor growth, substantive releases,
adoption in packages or models, independent technical coverage, conference
demos, and maintainer or practitioner explanations. Prefer changes over
cumulative totals. Require at least two independent source groups before using
`popular`, `emerging`, or `fast_growing` as a report label.

Treat these signals as candidate-generation evidence only. Verify the canonical
repository, pinned revision, license, maintenance state, implementation claims,
and research evidence independently. A technical blog or news item can reveal a
source that ordinary search missed; it cannot prove that the method works.

## Explicit Preference Ledger

Preference memory is opt-in and auditable. Do not infer it from private browsing,
social recommendations, or unspoken reactions. Store only user-visible records:

The core Skill is stateless by default. A project or global record may be
persisted only when the user explicitly opts in and the host provides a visible
ledger file or research contract. If that storage is unavailable, apply the
record to the current run and report `not_persisted`; do not imply that a later
session will remember it.

```text
preference_id:
scope: current_task | project | user_global
kind: positive | negative | priority | excluded
target: source, mechanism, family, or failure mode
reason: the user's stated reason
evidence: user_message or task_id
created_at:
expires_at: optional
confidence: explicit | inferred_from_explicit_feedback
```

Apply this lifecycle:

- “这个有价值/以后按这个找” creates a project or global positive record;
- “这次可以” affects only the current task;
- “不要再推荐这种” creates a negative record with the reason;
- deletion, correction, and export must be supported;
- older inferred records decay or become review-needed; explicit records do not
  silently change;
- a preference can change ranking and query expansion, but cannot bypass source
  identity, evidence, safety, or two-anchor gates.

Keep project memory separate from user-global memory. A preference for temporal
knowledge graphs in one project must not automatically become a preference for
every unrelated research question.

## User-Aligned Research Rationale

Projects or papers supplied by the user should be represented as a **mechanism
constellation**: shared mechanisms, meaningful differences, and the project
problems they may address. They are known anchors for that run, not autonomous
discovery credit. The Skill should then search for bridge candidates,
alternatives, validation methods, failures, and newer work around that
constellation.

## Required Candidate Record

For each high-potential or exploratory candidate, add:

```text
research_impact: high | medium | low | exploratory
research_attention: deep_priority | mechanism_reference | light_reference | unresolved
project_shift: what could change in the project
mechanism_transfer: direct | adapt | represented | exploratory
deployment_fit: direct | partial | incompatible | unknown
next_experiment: a test that could falsify the proposed value
popularity_signal: none | observed | triangulated
```

Do not call a candidate “valuable” solely because it matches the user's prior
examples. The user or a blinded reviewer must still evaluate genuinely new
candidates.
