<div align="center">

# Research Source Radar

**Use it to find papers, open-source projects, datasets, methods, and other sources that actually fit your project.**

[Quick Start](#quick-start) · [Core Capabilities](#core-capabilities) · [Output](#output) · [Source-to-Target Translation](#source-to-target-translation) · [Installation](#installation) · [简体中文](README.zh-CN.md)

</div>

Research Source Radar finds papers, open-source projects, datasets, and methods you can use in your project. It searches around your goals, current obstacles, and constraints, explains what each source helps with, and picks out the few worth reading closely.

## Quick Start

You do not need a structured form. Say:

> Use Research Source Radar to find papers, open-source projects, and other sources related to this project.

If the project context is already available, it starts there. Otherwise, add a sentence about what you are building or studying and where you are stuck.

If you already have useful examples, or the first batch misses the mark, paste one or more sources:

> These papers and projects are closer to what I want. Find what they have in common, then look for more like them.

It verifies the sources and explains the preferences it infers so you can correct them. Your examples stay separate from new discoveries; sources you already know do not count as new finds.

## Core Capabilities

- **Search around the project:** find papers, repositories, data, methods, standards, and official materials that address the problem, not just the same keywords.
- **Follow methods to reusable materials:** look beyond a paper for implementations, data, templates, updated versions, and follow-up work. Explain what you can reuse instead of rebuilding.
- **Find methods across disciplines:** search for similar problem structures even when terminology differs. Explain what corresponds, which assumptions differ, and how to test whether the transfer works.
- **Search both popular and overlooked work:** recent papers, project activity, and community attention have their own search routes, alongside less popular but useful sources. Popularity claims include dates and evidence.
- **Check original sources:** link to original papers, official repositories, dataset pages, and standards. Distinguish versions and avoid counting multiple links to one work as separate discoveries.
- **Prioritize a few:** explain the best 3-5 sources first, then provide the remaining candidates. Being related does not automatically make a source worth a deep dive.

Use it for computing, life sciences, health, social sciences, quantitative finance, law and policy, humanities, arts, design, education, and interdisciplinary projects. Source types and evidence standards follow the field; not every discipline needs a GitHub repository.

## Output

A normal run returns 10-20 candidates, defaulting to about 12. If too few suitable sources are available, it explains the gap rather than padding the list. The most useful sources come first, followed by filled candidate cards with:

- **Source:** a directly usable canonical link or stable identifier;
- **What it is:** a short description of the paper, project, dataset, method, standard, or other source;
- **Why look now:** the concrete connection to the target project;
- **Dates:** first publication, version or edition, and verification date recorded separately; if the original source provides only a year, no month or day is invented;
- **Popularity and freshness:** the date or interval of observed attention and its evidence, separate from publication dates; no unsupported trending labels;
- **Mechanism tags:** the mechanism problem it addresses;
- **Target value:** directly usable, requires adaptation/reimplementation, mechanism reference, light reference, or unresolved, with the work it saves and a concrete next step;
- **Implementations and follow-up work:** available code, data, templates, newer versions, or successors, with missing or inaccessible materials noted;
- **Risks and limits:** evidence, implementation, data, platform, license, or transfer risks;
- **Recommended effort and actual reading depth:** how closely it deserves to be read, separate from what was actually inspected.

You can give feedback using **夯 > 顶级 > 人上人 > NPC > 拉完了**. AI recommendations stay separate from your ratings; the Skill does not fill in scores on your behalf:

- **夯:** read deeply first and prioritize migration or validation;
- **顶级:** high-priority deep reading;
- **人上人:** clear mechanism value for focused reference or adaptation;
- **NPC:** related but light reference only, not an average deep-reading priority;
- **拉完了:** not worth investing in for the current task.

## Source-to-Target Translation

When asked to borrow from a paper, open-source project, model, screenshot, or technical lead, the Skill builds a source capability inventory instead of extracting only a few familiar mechanisms:

1. Verify source identity and version.
2. Inventory the full paper, supplements, README, relevant implementation, configuration, evaluations, limitations, and version history. Record what was read and what remains unread or inaccessible.
3. List key mechanisms, assumptions, state variables, update rules, validation, failure handling, resource/platform constraints, and evaluation conclusions.
4. Map each item to the target project.
5. Mark each item directly usable, requires adaptation/reimplementation, deliberately not adopted, or not yet verified.
6. Explain every non-adoption. Keep planned adoption separate from completed implementation; implemented items need target behavior mappings and verification results, not just a file or test name.
7. Keep unexplained items open instead of declaring the translation complete.

The same workflow applies to biological methods, financial factors, legal frameworks, humanities theories, art tools, and other cross-disciplinary sources.

## Feedback and Preferences

You can say:

- “This source is mediocre”: lower only that candidate;
- “This batch is mediocre”: record a retrieval failure, diagnose the missing direction, and use a different search lane;
- “I want to see more of this mechanism”: expand that mechanism for the current task;
- “Do not recommend this type again”: lower similar types without blacklisting every related tag;
- “These are the sources I find relevant”: paste 1-n sources so the Skill can verify them and infer a current-task preference hypothesis.

If a whole batch misses the target, the Skill asks one or two focused questions or invites you to share examples, then searches in a different direction. No lengthy questionnaire is required.

Saved preferences must trace back to your original labels and reasons, and only affect later searches and ranking after your confirmation. They stay in visible, deletable, project-local files, isolated from other projects. Tentative interest is not treated as strong approval, and "not useful now" does not exclude every related topic.

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
