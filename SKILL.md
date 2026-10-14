---
name: research-discovery-and-translation-audit
description: Find papers, open-source projects, datasets and methods that fit a user's project, including overlooked sources and transferable methods from other disciplines. Use for related-source discovery, user-supplied research leads, feedback-guided search, or source-to-project translation.
---

# Research Source Radar

Find sources that can move the user's project forward, not just sources with similar titles. Use the user's language; default to Chinese for Chinese requests.

## Start from an ordinary request

“用 Research Source Radar 帮我看看这个项目相关的论文、开源项目和资料” is sufficient. Infer the target, bottleneck, constraints and known sources from the conversation and authorized project material. Do not make the user fill out a research form. Ask at most one or two short questions only when the answer changes the search substantially. Mark inferred context as provisional.

Open-ended discovery uses `references/missed-source-recovery-v5.md`. A named-source identity lookup or explicitly quick request may use `fast`. Deep reading is selective, not mandatory for every candidate.

## Build and execute a project-specific plan

Read `references/structural-transfer.md` for the executable input contract. Populate the JSON internally; the user does not need to write it.

```bash
python3 scripts/discovery_plan.py --input request.json --output discovery-plan.json
```

1. Describe the bottleneck, input/output roles, constraints, failure modes and mechanism vocabulary in `project_frame`, with evidence references. Do not reduce a Chinese question to its few English tokens.
2. Cover direct problems, mechanism neighbors, structural transfer, recent/popular signals and long-tail relations. Use domain-native sources: code hosting is not a universal research index. Include validation/failure searches.
3. Build `mechanism_bridges` for other fields, including computing projects. Different names and no shared citations do not disqualify a source. The bridge must specify role/relationship mappings, assumptions, break conditions, project benefit and a minimal check. The planner searches foreign vocabulary without requiring the target project's words.
4. Execute a diverse selection from the query backlog within the shared per-round budget, honouring the plan's `usefulness_policy.per_round_minimums` so direct matches cannot crowd out reuse, recent signals and long-tail relations. After a source is resolved, add actual citation, implementation, dataset, dependency or successor relations with evidence. Record executed query IDs; a generated query is not a performed search.
5. Ask "who already built or updated this?" before recommending work. The `reuse` lane searches maintained implementations and current versions from the frame. After round one, pass the 3-5 strongest method, standard or dataset anchors as `foundation_sources` and rerun. Then run the one-hop checks: recent citing work, current version or extension, author/maintainer implementation. Record each as found, none_found or blocked. Age never excludes a source; an older anchor needs this successor check. Details: `references/usefulness-first-discovery.md`.
6. Maintain one identity-normalized candidate ledger, then rank for project benefit, fit, evidence and adaptation cost. Group a method paper, its implementation and its successor versions as one lineage entry instead of letting near-duplicates fill the list. Popularity is a discovery entrance, not correctness. Avoid fixed result quotas per discipline or route.

Runtime limits come only from `references/runtime-contract-v1.json`. Its default result size is 12, with user-adjustable output up to 20. Return fewer rather than fabricate. The metadata pool is separate from the displayed list. Discovery has a bounded round/resource budget, not a default global elapsed-time deadline. Per-request timeouts still prevent hanging; slow or blocked routes remain visible gaps. A resource stop is not evidence of saturation.

## Verify identity and useful fit

Every presented candidate needs a canonical, directly clickable source: DOI/arXiv/PMID or authoritative publication record, canonical repository, official dataset/standard/archive/policy page. Resolve ambiguous names; pin the relevant version for implementation and transfer claims. Social posts, screenshots, videos, snippets and curated lists are leads, not original evidence. When a proof, preprint, mirror or index record disagrees with the formal record (DOI, pages, dates), resolve the registry or publisher record and cite that. Hand the conflict to the user only when the formal record cannot be reached.

Require at least two concrete target anchors. For a cross-domain source these can be a supported structural correspondence and a target constraint/outcome match; matching domain names is not required. Distinguish formal equivalence, conditional approximation, method transfer and tentative analogy. Similar words or equations are not enough. An analogy may be a labelled exploration lead, never a proven transfer.

Keep direct usability, mechanism value, evidence strength, freshness, popularity and deep-reading priority separate. Rejecting a source for direct deployment does not erase a useful mechanism. Technical elegance alone is not a reason to recommend it: identify the user's actual benefit and a next action.

## Feedback must reach the next search

When the user dislikes a batch, first invite 1-n sources they do like, with at most one additional targeted question. Resolve those examples and show a provisional preference hypothesis. Use it for this task; do not silently persist it or infer a negative profile from a disappointing batch.

For explicit local feedback, read `references/research-radar-feedback-loop.md`. Profiles are opt-in, project-bound, visible and deletable. Never auto-discover another project's profile or read private social history.

```bash
python3 scripts/discovery_plan.py --input request.json --profile profile.zh-CN.json --output discovery-plan.json
```

The request's `project_id` must match the profile. The planner checks original feedback evidence, emits per-input `consumption`, and carries bounded `ranking_policy` effects. Apply these effects only after identity and target-fit gates. Record actual candidate-level effects with the event reference; do not claim feedback improved results just because it was loaded. Match candidate-only feedback by canonical identity and source version, not a recycled display ID. Preserve unrelated exploration candidates and keep user-known seeds out of novelty claims.

Preserve `夯 > 顶级 > 人上人 > NPC > 拉完了`: deep priority, mechanism reference, light reference and candidate-only rejection remain distinct. Only explicit `avoid_similar` with user-grounded dimensions can broadly downweight. Uncertain language cannot become strong positive evidence. Legacy records without provenance are quarantined, not automatically repaired. Never substitute model scores for user judgments.

## Read deeply without losing the important parts

For selected sources or a translation request, use `references/seed-to-neighbor-discovery.md` and the reading-ledger contract in `references/structural-transfer.md`. Inventory original materials first: full text, supplements, relevant implementation/configuration, evaluations, limits and versions. For other disciplines use the actual method, evidence, context and argument structure, not a forced software analogy.

```bash
python3 scripts/mechanism_transfer.py inventory --material M1=paper.md --material M2=supplement.md --output inventory.json
python3 scripts/mechanism_transfer.py --ledger reading-ledger.json --output reading-audit.json
```

Map critical mechanisms, claims, assumptions, state/update rules, failure handling and resource/ethical constraints. Decisions are direct use, adaptation, intentional rejection or unverified. Rejection needs a reason. Planned adoption is not implementation: adopted items need target behavior mappings and verification evidence, including a failure case. A path or test name alone is insufficient. Unread materials, stale versions and unresolved items block completion claims. A passing structural check still requires checking original evidence for unlisted content; it cannot prove semantic completeness.

For formal source/implementation contracts, the existing `scripts/research_contract.py` verifier remains available. Never run third-party repository code just to inspect it.

## Deliver filled, source-backed cards

Return one usefulness-ranked list, with role labels rather than competing grouped rankings. Open with the top 3-5: for each, say why it is worth investing in and which concrete piece of project work it saves (an estimator not to re-implement, a checklist not to rebuild, a dataset not to collect). Each Chinese card includes:

- 来源链接、来源类型与核验状态（正式记录优先）；
- 是什么，以及为何匹配这个项目的具体卡点；
- 可借鉴内容、直接可用还是需要适配、风险和下一步；
- 现成实现/更新版本/后继：找到、未找到或受阻，各附依据；
- 时间分四项：首次发表、版本/版次、本次观测日、热度事件及依据。不编造未知时间，也不把发布或维护公告当热度；
- 跨域候选的目标卡点、共同结构、角色对应、不成立条件与最小验证；
- 建议投入程度与实际阅读深度，各为独立字段，不写进其他字段的开头；不代填用户评分。

Briefly report executed routes, remaining gaps and stop reason. Show a migration matrix only when deep reading/translation was performed; do not burden a simple discovery request with a release audit. Distinguish entered retrieval preferences, proposed mechanism hypotheses and actual target implementation.

## Development is separate from ordinary use

Do not run release audits or A/B harnesses in every discovery call. On an explicit evaluation request, use equal model/tool conditions, frozen candidate snapshots, blinded Chinese cards and held-out user judgments. Separate discovery usefulness, preference fit and reading omissions. Record token cost and slow-network failures separately; unit-test success does not demonstrate retrieval superiority. Do not claim complete coverage or proven superiority without evidence.

Use `references/token-efficient-execution.zh-CN.md` only when cost control is relevant. Preserve identities, exact dates, original feedback, source evidence, limitations and transfer mappings when shortening context.
