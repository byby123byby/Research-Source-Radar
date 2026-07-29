<div align="center">

# Research Source Radar

**Use it to find papers, open-source projects, datasets, methods, and other sources that actually fit your project.**

[Quick Start](#quick-start) · [Core Capabilities](#core-capabilities) · [Output](#output) · [Source-to-Target Translation](#source-to-target-translation) · [Installation](#installation) · [简体中文](README.zh-CN.md)

</div>

Research Source Radar helps you find papers, open-source projects, datasets, and methods that actually fit your project. It starts from what the project is trying to solve, then looks for direct matches, related mechanisms, and useful alternatives instead of returning a keyword list.

## Quick Start

You do not need a structured form. Say:

> Use Research Source Radar to find papers, open-source projects, and other sources related to this project. Prioritize sources that could genuinely move it forward. My project is ...

If you already have sources that feel relevant, paste 1-n examples:

> These papers/projects seem relevant to me. Verify their identities, compare their mechanisms and boundaries, then find new sources based on those shared characteristics.

The Skill treats the examples as a visible, task-local preference hypothesis and separates them from genuinely new discoveries. One example creates a tentative hypothesis; several examples with consistent mechanisms make the current task's search and ranking more targeted.

## Core Capabilities

- **Direct problem matches:** papers, projects, datasets, standards, official documents, and methods that address the target directly.
- **Mechanism neighbors:** sources connected by state representation, update rules, training methods, metrics, data workflows, or validation rather than by name alone.
- **Cross-domain transfer:** connections across computing, life science, health, social science, quantitative finance, law and policy, humanities, arts, design, education, and multidisciplinary research.
- **Hot and recent discovery:** GitHub activity, community attention, recent papers, and technical coverage as a sidecar discovery lane, with the timing and evidence of attention stated separately rather than replacing direct problem search.
- **Long-tail recovery:** less popular sources with clear mechanisms, strong validation, or meaningful project value.
- **Source verification:** canonical papers, official project pages, repositories, dataset pages, standards, and other primary sources.
- **Actionable ranking:** direct use, adaptation, mechanism transfer, light reference, and unresolved status are kept separate so relevance is not treated as deep priority.

## Output

A normal run returns 10-20 candidates, defaulting to about 12. Each candidate card should include:

- **Source:** a directly usable canonical link or stable identifier;
- **What it is:** a short description of the paper, project, dataset, method, standard, or other source;
- **Why look now:** the concrete connection to the target project;
- **Time range:** approximate publication, release, update, or key-evaluation period;
- **Popularity and freshness:** when the source was popular or recently active, if applicable;
- **Mechanism tags:** the mechanism problem it addresses;
- **Target value:** directly usable, requires adaptation/reimplementation, mechanism reference, light reference, or unresolved;
- **Risks and limits:** evidence, implementation, data, platform, license, or transfer risks;
- **Research attention:** **夯 > 顶级 > 人上人 > NPC > 拉完了**.

This attention scale is not a simple relevance score:

- **夯:** read deeply first and prioritize migration or validation;
- **顶级:** high-priority deep reading;
- **人上人:** clear mechanism value for focused reference or adaptation;
- **NPC:** related but light reference only, not an average deep-reading priority;
- **拉完了:** not worth investing in for the current task.

## Source-to-Target Translation

When asked to borrow from a paper, open-source project, model, screenshot, or technical lead, the Skill builds a source capability inventory instead of extracting only a few familiar mechanisms:

1. Verify source identity and version.
2. Read relevant parts of the paper, README, implementation, configuration, evaluation, limitations, and version history.
3. List key mechanisms, assumptions, state variables, update rules, validation, failure handling, resource/platform constraints, and evaluation conclusions.
4. Map each item to the target project.
5. Mark each item directly usable, requires adaptation/reimplementation, deliberately not adopted, or not yet verified.
6. Give a reason for every non-adoption and point every claimed migration to target design, code, or tests.
7. Keep unexplained items open instead of declaring the translation complete.

The same workflow applies to biological methods, financial factors, legal frameworks, humanities theories, art tools, and other cross-disciplinary sources.

## Feedback and Preferences

You can say:

- “This source is mediocre”: lower only that candidate;
- “This batch is mediocre”: record a retrieval failure, diagnose the missing direction, and use a different search lane;
- “I want to see more of this mechanism”: expand that mechanism for the current task;
- “Do not recommend this type again”: lower similar types without blacklisting every related tag;
- “These are the sources I find relevant”: paste 1-n sources so the Skill can verify them and infer a current-task preference hypothesis.

If a whole batch misses the target, the Skill can ask a small number of focused questions, then search again around mechanisms, implementations, data, metrics, validation, or cross-domain transfer instead of turning one failed batch into a permanent preference.

## Installation

Install this directory as a Codex Skill:

```text
$CODEX_HOME/skills/research-discovery-and-translation-audit/
```

Native Agent Skills hosts may use the compatibility name `$research-discovery-and-translation-audit`; in ordinary use, simply say “use Research Source Radar.”

## Feedback and Collaboration

If you run into a problem, find a source-verification error, have a feature idea, or want support for another field, please open an [Issue](https://github.com/byby123byby/Research-Source-Radar/issues). Include the use case, input, actual output, and expected result when possible.

If this Skill is useful to you, a [Star on GitHub](https://github.com/byby123byby/Research-Source-Radar) is appreciated. If you are interested in research-source discovery, cross-disciplinary search, or Skill design, feel free to [contact me on GitHub](https://github.com/byby123byby) to exchange ideas or discuss collaboration.

## License

This project uses the [LICENSE](LICENSE) file in the repository root.
