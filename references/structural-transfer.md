# Structural transfer: executable planning and reading contracts

Different fields may use different names for related problem structures. Search those independent vocabularies, but do not assert common historical origin, mathematical equivalence or empirical transfer merely from similarity. Humanities, law and arts may transfer an argument, method, evaluative framework or process; preserve context and normative assumptions.

## Planner input

`discovery_plan.py` is deterministic, not a semantic model or crawler. The host derives the following from authorized project context. Required legacy input remains `question`; richer fields actually change query generation. Missing structural input yields `needs_host_input`, never invented evidence of cross-domain coverage.

```json
{
  "question": "质性研究中，编码规则改动后怎样追踪受影响的材料和解释？",
  "domain": "social_science",
  "project_id": "qualitative-study",
  "project_frame": {
    "bottleneck": "编码规则更新后难以追踪哪些解释需要重新审阅",
    "inputs": ["编码规则", "材料与解释之间的关联"],
    "outputs": ["待复核解释列表"],
    "constraints": ["保留研究者解释与语境"],
    "failure_modes": ["旧解释被误当成已经复核"],
    "mechanism_terms": ["codebook revision", "audit trail"],
    "evidence_refs": ["user-request:current-turn; hypothesis derived from the stated task"]
  },
  "mechanism_bridges": [{
    "bridge_id": "B1",
    "source_domain": "computing",
    "relation_type": "method_transfer",
    "status": "hypothesis",
    "shared_structure": "上游规则改变，需要追踪依赖它的下游产物",
    "target_problem": "定位需要人工复核的解释，而非自动判定解释真假",
    "search_terms": ["versioned provenance dependency tracking", "incremental computation invalidation"],
    "mapping": [{"source_role": "upstream dependency", "target_role": "编码规则", "relation": "变更触发下游关联产物复核"}],
    "assumptions": ["研究过程已有可追溯的关联记录"],
    "breaks_when": ["implicit dependencies missing provenance"],
    "target_benefit": "减少漏查，保留人工解释责任",
    "minimum_check": "用一次真实规则修改检查能否找出已知受影响的解释以及误报",
    "evidence_refs": []
  }]
}
```

This is an illustrative hypothesis, not a verified recommendation. Replace its project evidence locator with the actual authorized input location. The planner emits separate foreign-vocabulary queries and a boundary/failure query, not a target-keyword search labelled cross-disciplinary.

Other domains include `computing`, `health`, `life_science`, `social_science`, `financial_quant`, `law_policy`, `humanities`, `arts_design_media`, `experimental_science`, `business`, `multidisciplinary`. A bridge can name another discipline freely; recognized domains select their native ecosystems, others use cross-disciplinary indexes. The host should refine actual registry choices, not claim every ecosystem was searched.

`mechanism_bridges` require non-empty `mapping`, `assumptions`, `breaks_when`, benefit and minimum check. Relationship types are `formal_equivalence`, `conditional_approximation`, `method_transfer`, `analogy`. `source_supported` requires original evidence references; this is a declaration the host must check, not a mathematical proof performed by Python.

Optional `seed_relations` records contain `source_identity`, `relation`, `search_term`, `evidence_ref`; populate them from actual references, datasets, dependencies, implementations or successors. They produce relation-expansion queries. `known_leads` produce identity queries but remain user-known anchors, not novel successes.

Planner output includes `queries`, `mechanism_bridges`, `consumption`, `ranking_policy`, route status and budgets. A `query_id` represents a plan until a search tool actually executes it. Apply feedback only under the evidence rules in `research-radar-feedback-loop.md`; export actual ranking effects alongside query lineage.

## Cross-domain candidate evidence

Each recommended transfer candidate needs canonical identity plus:

- shared structure and explicit source-role/target-role/relation mappings;
- original-source evidence, version and what was actually read;
- assumptions that match, assumptions that fail and unresolved ones;
- project benefit and adaptation burden;
- a small falsifiable check, case comparison or interpretive review;
- separation between tentative analogy, supported correspondence and validated target behavior.

Do not penalize a source just because its name or discipline differs. Do not reward distance or cleverness alone. Same-looking equations, a shared word like memory/network, or missing citations do not establish or refute transfer.

## Reading ledger

Ordinary discovery does not need a ledger; skim-level cards say what was actually read. The ledger is required only before claiming that a source's mechanism was understood in full or migrated. It runs in four steps.

**1. Verify and inventory the source.** Obtain the originals as local UTF-8 Markdown or text, for example a PDF converted with any extractor, supplements, appendices, a README or the relevant code/config files. No PDF library is required. Then hash and section them:

```bash
python3 scripts/mechanism_transfer.py inventory \
  --material M1=paper.md --material M2=supplement.md --output inventory.json
```

Each heading starts one unit, and a preamble before the first heading is its own unit. Units carry a unique ordered ID (`M1#004`), heading, line range and sha256. Repeated headings such as two `Methods` stay separate. Headings inside code fences are ignored. Mentions such as `Table S1`, `Appendix A`, `Supplementary` or `附录` are indexed.

**2. Map components.** Write `reading-ledger.json` (`schema_version: 2`) with these fields:

- `inventory_ref` (path) and `inventory_sha256`;
- `materials`: `id` (matching the inventory), `source_ref`, pinned `version` (not `latest`/`main`), and `read_status` (`read`, `partial`, `unread`, `blocked`, `not_applicable` + `reason`). A material with nothing relevant needs `no_relevant_items_reason`;
- `items`: `id`, `material_id`, `source_version`, `unit_ids` (where the claim is), an optional verbatim `quote` (checked against those units), `claim`, `conditions`, `limitations`, and `decision` (`direct`, `adapt`, `reject`, `unverified`). `reject` needs a `reason`;
- `excluded_units`: `{unit_id: reason}` for every non-empty unit that no item maps;
- `supplement_links`: each indexed mention that is not a heading of an inventoried material resolves to `{"material_id": …}` or to `{"status": "unavailable", "reason": …}`. An unavailable supplement is recorded honestly, but it stays a gap and is listed in `unobtained_supplements`. Discovery can report partial reading, but a full-migration claim stays blocked until the supplement is obtained and inventoried.

**3. Target evidence.** `direct` and `adapt` items need:

- an existing local `target_ref` (design, code, protocol or argument document) and `target_behavior`;
- `verification` with `status=verified`;
- a local `evidence_ref` file plus its `evidence_sha256`;
- an observed `result`;
- a distinct `failure_case`.

For non-code work, the evidence file can be a case comparison, counterexample, expert review or argument audit.

**4. Unmigrated items.** `unverified` items are listed in `open_items` and block a completion claim. A plan may legitimately leave them open.

```bash
python3 scripts/mechanism_transfer.py --ledger reading-ledger.json --output reading-audit.json
```

The exit code is 0 when the gate passes, 1 when it is blocked (gaps listed) and 2 for malformed input (a readable `ERROR:`). The gate blocks when any of these hold:

- a unit is neither mapped nor excluded;
- an inventoried file is absent from the ledger;
- a supplement mention is unresolved;
- an original file or the inventory changed or went missing after hashing. The audit regenerates units, mentions and line counts from each original, so an edited and re-hashed inventory or a duplicate ID is caught;
- a `target_ref` is not an existing file, or the target or evidence file is empty or only a placeholder word. Length is not treated as truth, and non-empty binary evidence is accepted;
- a material with mapped items also declares `not_applicable` or `no_relevant_items_reason`. Its leftover units must be excluded one by one;
- a quote does not match its units;
- a version mismatches;
- a reason or evidence field is a placeholder (`x`, `ok`, `none`, `通过`, …).

The gate certifies hash-bound coverage of what was obtained and inventoried. It cannot see material that was never obtained, judge whether a claim was understood, or confirm that a cited result is true. Before claiming completion, compare the inventory and evidence with the originals. Formal `research_contract.py` gates still apply where a full research contract is used.
