# GitHub Hot-and-Similar Discovery

Use this reference when the user asks for GitHub daily or weekly trending
projects, high-star alternatives, fast-growing repositories, or projects that
are similar to a supplied repository. This route generates candidates; it is
not a quality or relevance shortcut.

## Four Discovery Lanes

Run the lanes separately and preserve `discovered_via` for each candidate:

1. **Global trend lane:** inspect the official GitHub daily and weekly
   trending pages for the requested language when possible. These global lists
   are often dominated by generic infrastructure, so do not stop there.
2. **Topic and mechanism lane:** search GitHub repositories using the seed's
   task, input modality, mechanism, and ecosystem terms. Use `topic:` terms,
   exact aliases, and mechanism phrases; inspect both star-sorted and
   recently-updated or recently-pushed results.
3. **High-star and velocity lane:** query repositories with strong cumulative
   stars and separately inspect recent release or contributor activity. A
   current star count is not a velocity measurement. Use `fast_growing` only
   when dated snapshots, repository activity, or an independent trend report
   supports a change over time.
4. **Independent attention lane:** search maintainer release notes, papers,
   conference demos, substantive technical articles, newsletters, and
   community curation. Reposts of one announcement belong to one
   `independence_group`.

For a seed constellation, apply these lanes to the shared mechanism and to
each anchor with a distinct role. Do not search only the literal project name:
a project may be popular under a product name while its mechanism uses
different research vocabulary.

## Similarity Gate

A hot repository enters the primary shortlist only when it shares at least two
of the following with the seed or target:

- domain or application;
- research task or user problem;
- input/output modality;
- core mechanism or algorithm;
- software ecosystem or execution setting.

Stars, ranking position, a single keyword, and repeated search appearance do
not count as a similarity anchor. A candidate that is interesting only because
it is popular goes to `popularity_only` or `transfer_only`, with missing
anchors recorded.

## Attention Evidence

Store a compact signal record for every trend lead:

```text
signal_id
candidate_id
source_url
source_kind: github_trending | github_metadata | release | paper | blog |
             newsletter | community | benchmark | other
independence_group
observed_at
observation_window
value: stars | star_delta | contributors | release | mention | rank | other
claim
evidence_policy: discovery_only
```

Use at least two independent source groups before writing `popular`,
`emerging`, or `fast_growing`. GitHub trending and GitHub repository metadata
are the same platform group; they do not establish independent confirmation by
themselves. Keep cumulative stars, recent change, and external discussion as
separate fields rather than blending them into one opaque score.

## Ranking And Reporting

Rank candidates in this order:

1. identity validity and repository status;
2. task/mechanism match and two-anchor coverage;
3. research impact and a concrete project-shift hypothesis;
4. evidence depth, maintenance, license, and safety;
5. freshness and attention signals as tie-breakers among comparable items.

Return separate sections for `high_relevance`, `hot_but_transfer_only`,
`emerging_exploration`, and `popularity_only_or_excluded`. For each selected
item report the canonical `owner/repository`, pinned commit, tag, or release,
observed star or activity fields, signal sources, shared anchors, the
transferable mechanism, deployment fit, and a falsifiable next experiment.
Never present a repository as valuable solely because it has many stars.

## Stop And Gaps

Stop after the normal bounded search budget, after one targeted coverage probe,
or when all requested families are represented. Record which lanes ran and
which did not. If a GitHub trending page was unavailable or showed no relevant
candidate, record that fact and continue with topic, mechanism, release, and
independent-coverage lanes. Do not claim that the current GitHub top list is a
complete view of the field.

