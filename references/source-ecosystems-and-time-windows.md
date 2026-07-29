# Source Ecosystems And Time Windows

Use this protocol when a request spans disciplines, asks for recent or
popular work, or asks why a normal AI search did not surface a user-discovered
paper or project. GitHub is one discovery ecosystem, not a universal research
ranking.

**Recall protection rule:** attention discovery is a sidecar route. It may add
candidates to the pool, but it may not replace, narrow, or reweight the core
problem, mechanism, citation, alternative, failure, or foundational searches.
The core routes must run even when no source is currently popular.

## 1. Select The Ecosystem Profile

Choose a primary domain profile and the source ecosystems that match its
evidence culture. Add a secondary profile when the question crosses fields.
Do not search every platform by default: activate only the ecosystems that can
answer the question and record unavailable or inaccessible ones as gaps.

| Research setting | Discovery ecosystems | Native attention or activity signals |
|---|---|---|
| Computing and software | GitHub, GitLab, Codeberg, package registries, release pages, conference artifacts | star or contributor change, substantive releases, dependents, package adoption, issue activity, benchmark use |
| AI models and datasets | Hugging Face, model registries, dataset registries, arXiv, OpenAlex, conference pages | paper/model/dataset trending, downloads, likes, versions, benchmark visibility, external technical coverage |
| General scholarship | OpenAlex, Crossref, Semantic Scholar, preprint servers, institutional repositories | field-aware citations, downloads where available, recency, related concepts, correction or retraction status |
| Humanities and digital humanities | H-Net, Humanities Commons, Digital Humanities Now, DH journals, society and conference pages, library and institutional repositories | editorial selection, reviews and discussion, conference appearance, repository views/downloads, provenance and archival status |
| Economics and social science | IDEAS/RePEc, SSRN, NBER, SocArXiv, discipline indexes and society pages | downloads, abstract views, citations, working-paper recency, discussion and conference visibility |
| Health and biomedicine | PubMed, Europe PMC, bioRxiv/medRxiv, trial registries, guidelines, regulator and professional-body pages | publication recency, trial status, guideline updates, corrections/retractions, field citations |
| Experimental science and engineering | discipline repositories, standards bodies, protocols, apparatus documentation, datasets, institutional pages | protocol reuse, version updates, replication, calibration and dataset activity |
| Law, policy and regulation | legislation and court portals, government pages, official guidance, SSRN, legal repositories and professional bodies | effective-date changes, decisions, consultation activity, downloads and authoritative updates |
| Arts, design and media | museum and institutional records, exhibition catalogues, artist/designer archives, practice-research repositories, societies | exhibition or programme selection, documented practice, provenance, catalogue/repository activity and critical discussion |
| Research data and methods | Zenodo, Figshare, OSF, Dataverse, Kaggle, institutional data repositories | DOI records, versions, downloads, reuse/citations, dataset updates, method replication |

This table is a routing map, not a quality ranking. A platform's native
attention signal is useful for discovery only. Stars, downloads, editorial
selection, citations, and conference appearance are not comparable units and
must not be combined into one universal popularity score.

## 2. Use Separate Time Horizons

The contract must distinguish time-bounded attention from durable importance.
Unless the user specifies otherwise, use these separate buckets:

| Bucket | Suggested window | Use |
|---|---:|---|
| `rapid_attention` | 7 days | newly visible releases, announcements, demos, or discussions |
| `recent_activity` | 30 days | active releases, coverage, adoption, or conference/news activity |
| `recent_6m` | 180 days | the default answer to “recently” or “in the last six months” |
| `foundational` | no fixed window | older work whose mechanism, theory, dataset, or evidence remains important |

The windows are not interchangeable. A source can be both old and highly
relevant, or recent and merely fashionable. Report recent candidates and
foundational candidates in separate sections. Record the cutoff date and the
actual observation date; never write a static “latest” timestamp into a
contract.

For a request that says only “recent” or “hot,” the default is `recent_6m`
plus a `foundational` lane. Add the 7-day and 30-day lanes when the request
explicitly asks for daily/weekly activity or fast growth. A refresh should
reuse the prior windows and compare the dated snapshots rather than silently
changing the definition.

The `foundational` lane is not optional merely because a trend route is
available. A small repository, an older paper, a negative result, a local
language source, or a method with little online attention may be more useful
than a highly visible project. Preserve it when it passes the relevance or
mechanism-transfer gate, and label it `relevant_but_not_hot` when it has no
attention evidence.

## 3. Record Native Signals Without Overclaiming

Each attention observation should record:

```text
ecosystem_profile
source_class
signal_type
candidate_id
observed_at
observation_window
independence_group
value
evidence
evidence_policy: discovery_only
```

Use a signal to decide what deserves inspection, not to establish quality,
correctness, novelty, safety, or effectiveness. Require at least two
independent source groups before using labels such as `popular`, `emerging`,
`fast_growing`, or `widely_discussed`. Correlated reposts, mirrors, and feeds
derived from the same ranking count as one group.

Keep these judgments separate:

- `relevance`: does it address the user's task or problem?
- `mechanism_transfer`: can its method, theory, data structure, or evaluation
  be adapted?
- `attention`: is there a dated signal that it is receiving notice?
- `authority`: can its identity and provenance be verified?
- `evidence_depth`: were the relevant methods, artifacts, limitations, and
  tests actually inspected?

An item can therefore be `relevant_but_not_hot`, `hot_but_transfer_only`, or
`hot_and_relevant_pending_review`. Never promote it to a primary recommendation
because of attention alone.

The primary shortlist must contain the best verified candidates from the core
relevance routes before trend-only candidates are considered. Trend signals may
break ties between otherwise comparable candidates, but they cannot demote a
strong relevant-but-quiet source or promote a popularity-only source into the
primary shortlist.

## 4. Cross-Disciplinary And Grey-Literature Rules

For multidisciplinary work, run the vocabulary and source routes separately
before synthesis. Preserve the source's own standards: an engineering
artifact, a humanities interpretation, a clinical study, and a legal source
cannot share one evidence threshold.

Technical blogs, newsletters, community posts, short-video descriptions, and
social posts are discovery leads. Resolve the underlying project, paper,
dataset, artwork, archive, or official record through an authoritative source
before treating it as evidence. Preserve the lead and its uncertain wording so
that a missing source is visible rather than silently replaced.

If a paywalled, private, personalized, or unavailable platform could change
the result, record it as an uncovered source class. Do not claim that the
platform was searched, and do not infer a private recommendation graph from
the user's feed.

## 5. Required Reporting

Every current or cross-disciplinary run should report:

1. selected domain profiles and source ecosystems;
2. time horizons and exact cutoff dates;
3. source classes searched and unavailable;
4. native attention signals and their independence groups;
5. direct relevance, mechanism-transfer fit, and authority separately;
6. recent, foundational, transfer-only, popularity-only, and unresolved
   sections;
7. the remaining coverage gap and the next refresh trigger.

The report should also state whether the core routes were completed separately
from the trend route. If a budget prevented the foundational or failure route,
record that as an explicit gap instead of claiming that the trend sweep was
complete.

This is a coverage protocol, not a completeness guarantee. The result should
make it possible to reproduce where the candidates came from and why a source
was included, deferred, or excluded.
