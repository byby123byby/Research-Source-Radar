# Long-Tail Neighbor Discovery

Use this reference when the user says that ordinary AI search returns plausible sources but misses the few projects, papers, or methods that would change their research direction. This is a candidate-generation and coverage problem. Do not fix it by weakening identity or relevance checks, and do not claim that an unseen candidate is valuable before the user or a blinded reviewer labels it.

## The Target Failure Mode

Ordinary retrieval is usually strong at direct lexical matches and well-indexed canonical work. It is weaker at work that is connected through a mechanism, an implementation ecosystem, a failure mode, or a neighboring discipline. A useful long-tail run therefore asks two separate questions:

1. Which sources directly answer the stated research question?
2. Which less-obvious sources implement, validate, criticize, or transfer a mechanism needed by that question?

The second question is a discovery hypothesis, not a relevance guarantee. Keep it visibly separate from the primary shortlist.

## Build A Mechanism Bridge

Decompose the anchor into six atoms before searching:

- **problem:** the decision or research task;
- **actor and setting:** who uses it and under what deployment conditions;
- **input and output:** data, modality, action, or observable outcome;
- **mechanism:** the operation that makes the result possible;
- **constraint:** latency, privacy, platform, safety, cost, or study boundary;
- **evidence:** what would demonstrate that the mechanism works.

Generate a small synonym set for each atom. Do not search every Cartesian combination. Use the atoms to create one query for each independent lane, then retain the atom pair that connects every candidate back to the anchor.

## Discovery Lanes

After the direct and alias lanes, use at most one compact query per lane that is materially useful for the task:

1. **Mechanism neighbor:** the same operation under different field terminology.
2. **Artifact ecosystem:** repositories, dependencies, authors, organizations, benchmarks, datasets, successors, and explicit paper-to-code links.
3. **Alternative or failure:** competing methods, limitation papers, failed reproductions, negative results, corrections, and abandoned implementations.
4. **Validation neighbor:** evaluation tools, safety methods, audit frameworks, or measurement protocols that test the same outcome.
5. **Current attention:** dated releases, technical coverage, demos, and recent work. Treat attention as a discovery signal only.
6. **Cross-domain transfer:** one adjacent discipline only when it shares a concrete mechanism, input/output pattern, or evidence model. Do not use a broad topic such as "AI" or "accessibility" as the bridge.

For a source first seen in a short video, blog, newsletter, or social post, use the post only as a lead. Resolve the actual paper, repository, product, or report through authoritative metadata before treating it as evidence.

## Candidate Ledger And Novelty Gate

Every candidate should retain:

```text
candidate_id
canonical_identity
discovered_via
bridge_to_anchor
neighbor_family
relation: direct | mechanism | ecosystem | validation | failure | transfer
novelty_status: supplied | recovered | new_for_run | unresolved
identity_status
evidence_status
direct_use_fit
transfer_fit
duplicate_of
```

Apply the following gates before a candidate enters the primary shortlist:

1. It has a canonical identity or is explicitly marked pending.
2. It shares at least two anchors with the seed: domain/setting, task, input/output, mechanism, evidence, or ecosystem.
3. It has a concrete bridge, not only a keyword, popularity signal, citation count, or repeated indexing.
4. It is not a mirror, fork, duplicate DOI landing page, or already supplied lead.
5. Its direct-use or transfer boundary is explicit.

If a candidate fails only the direct-use constraint but has a strong mechanism bridge, keep it in the transfer section rather than discarding it or presenting it as deployable.

## Family-Diverse Selection

Use family coverage before final ranking. In a shortlist of up to eight sources, try to reserve space for:

- one direct counterpart or implementation;
- one mechanism alternative;
- one validation, failure, or criticism source;
- one current or adjacent source;
- one cross-domain transfer only when its bridge is concrete.

Do not force empty families. Report them as uncovered. Do not allow popularity or path count to fill all slots from one family. Between candidates with similar identity, evidence, and fit, prefer the candidate that covers an unrepresented family; this is a diversity tie-breaker, not a relevance override.

## What Counts As Success

Keep the following outcomes separate:

- **recovered known lead:** a supplied or externally held-out lead was found;
- **new neighbor:** a source not supplied in the current run was found with a traceable bridge;
- **user-approved novel:** a new neighbor was later accepted by the user as useful;
- **exploratory:** a new neighbor has not yet received a user or blinded expert label.

Known-lead recovery can show that the Skill reaches a target that baseline missed. It cannot prove autonomous discovery. Autonomous or user-aligned discovery must be assessed using blind pooled review, with the condition hidden and the original decision context retained.

## Cross-Disciplinary Safeguard

For non-computing work, translate the mechanism before translating the implementation. For example, a graph memory system may transfer to a longitudinal clinical record, a historical archive, or a policy evidence map only if the relation type, time semantics, provenance requirement, and outcome evidence are comparable. State what does not transfer: population, ethics, data-generating process, measurement validity, or regulatory context. Never use a software repository as evidence for a human, clinical, artistic, or policy outcome without domain-appropriate evidence.

## Evaluation And Anti-Contamination

Use a frozen prompt and equal budgets for baseline and Skill. For each condition record:

- known-lead recovery at `k`;
- baseline-missed recovery at `k`;
- new-neighbor family coverage;
- bridge completeness;
- hard-negative rate;
- user-approved novel sources after blinded review;
- completion rate, wall time, and tokens.

Do not put the hidden gold list, a private preference profile, or the user's later correction into the runtime prompt. A current-run supplied lead is a recovery target, not a discovery credit. If a run times out, count it as incomplete and report the cost; do not silently replace it with a shorter result.
