# 中文研究雷达反馈闭环

评分来自用户，不能由模型的相关性判断代填。反馈的目的不是只存一个 JSON，而是改变同一项目下一轮的查询和可解释排序。发现阶段可以给模型建议优先级，但必须与用户真实评分分开。

## 保留原意

| 原始标签 | 作用 |
| --- | --- |
| 夯、顶级 | 值得深入，保留 5、4 的顺序 |
| 人上人、可借鉴机制 | 用于机制扩展，不自动变成深读或已实现 |
| NPC、相关但仅作参考 | 轻参考，不平均深入 |
| 拉完了、暂时没用 | 只影响该候选，不拉黑相同机制 |
| 不确定、可以看看、其他含糊表达 | 中性待核对，不当成正向 |
| 明确不想再推荐这类 | 仅按用户理由中明确的维度广泛降权 |

脚本只自动识别明确标签与保守的整句别名；复杂自然中文保存原话并归为 `uncertain`，不静默跳过，不从理由中的“夯”“迁移”推断强偏好。弱正向别名遇到明确保留语气时也保持不确定；原始口语标签及现有顺序保留在 `evidence.raw_label/ordinal`，不由理由补编排序。

## 不满意时怎样继续

用户说“一般，不是我想要的”，优先请他贴 1-n 个喜欢的论文、项目或其他来源；有必要时再问一个会改变搜索方向的短问题。建立可见的本轮偏好假设，说明共同机制和反例。不要自动写入长期画像，也不要把整批不满意变成广泛负反馈。

## 原始证据门禁

一份画像只服务其显式 `project.id`。只读取用户指定的画像，不从其他项目、社交账号或旧缓存猜偏好。删除画像后不保留外部派生缓存。

每个可消费的反馈包含 `candidate_id`、`title`、标准 `label`、原始 `reason`、来源描述 `tags`，以及 `evidence`：

- `project_id`、`candidate_id`、`candidate_title`：防止候选和项目错位；
- `source_ref.path` 与 `source_ref.sha256`：原始人工评审卡的稳定位置和内容快照，不是论文 URL；
- `source_identity.url/version`：被评价来源的精确版本；
- `raw_label/raw_reason`：原始判断，不补写理由；
- `verified_at`：来源核验时间；`confidence=user_explicit`：判断确实来自用户，而非模型打分；
- `status`：草案为 `unverified`，经用户确认且证据完整才是 `confirmed`；
- `scope`：`candidate` 或用户明确确认的 `dimension`；
- `confirmed_terms`：用户理由中实际出现并确认用于偏好的维度。不能把候选卡里模型生成的全部 tags 当成用户偏好。
- `dimension_confirmation.raw_scope/raw_terms`：直接来自原始人工卡片的“你的偏好范围／你的确认维度”。单独修改 JSON 的范围和维度不能通过门禁。

运行时会读取原始卡片，核对哈希、候选 ID/标题、原始标签/理由、URL 和版本。缺失或错位即隔离。`main`、`HEAD`、`latest`、`unverified` 不是可核实的固定版本。

积极维度必须在理由的肯定分句中出现。含否定或不确定词的分句不会仅因包含该子串而扩展；这是保守的词法检查，不是完整中文语义分析，“非侵入”等表述也可能被隔离。此时请用户在新的评审快照中澄清，模型不能替其改写原始判断。`uncertain` 不产生正向维度，只有 `avoid_similar` 才能按明确维度广泛降权。固定版本不会仅因论文年代较早而过期。

历史卡片如果没有来源版本，不得替用户改写原卡。保持历史证据不变，先做单独的可读修复提案与版本核对，再经用户确认建立新证据记录。旧 proposal 保留为 rejected artifact；不覆盖、不自动导入。本次工具升级不会自行修改任何已有私人画像。

## 本地操作

```bash
python3 scripts/radar_feedback.py init \
  --output profile.zh-CN.json --project-id my-project \
  --project-name '项目名称' --description '当前目标'

python3 scripts/radar_feedback.py render-review \
  --profile profile.zh-CN.json --candidates candidates.json --output review.md
```

用户在生成的卡片中填写标注与理由，反引号可省略。只评当前候选时，范围和维度可以留空；要让理由中的维度进入下一轮查询，用户需明确填写，例如：

```text
你的标注：可借鉴机制
你的理由：不是要截图优先，可审计的决策记录值得借鉴。
你的偏好范围：维度
你的确认维度：可审计
```

多个维度用顿号或逗号分隔。此示例不是用户真实评分，助手不得将示例或自行猜测的维度写入真实评审。随后从这份新快照提取，而不是手改提案 JSON：

```bash
python3 scripts/radar_feedback.py extract-review \
  --review review.md --candidates candidates.json --project-id my-project \
  --output feedback-proposal.json
```

候选 JSON 沿用原有卡片字段，新增可选的 `source_version`、`verified_at`、`time_note`。要启用反馈，来源版本和核验时间必须补齐；没有可靠日期时卡片明确写尚未核实，不编造。原始来源介绍、项目匹配理由、来源链接由 Skill 填好，只有评分和理由留给用户。

提取器同时生成 `feedback-proposal.review.zh-CN.md`，展示“原话 → 拟记录”、范围和维度。未知但非空标签保留为不确定；有理由或确认维度却无标注时明确报错。只提取已填写候选，不要求重填整张表，也不会写入画像。

仅在用户明确确认草案之后：

```bash
python3 scripts/radar_feedback.py record-feedback \
  --profile profile.zh-CN.json --feedback feedback-proposal.json --confirm
```

`record-feedback` 和 `replace-feedback` 必须显式 `--confirm`，即使旧提案已经标为 confirmed 也不自动导入。此参数代表操作者已获得真实用户确认，不是工具能验证人类身份的凭证；它不能绕过原始字段、哈希和来源版本核对。旧画像修复使用 `replace-feedback --archive <新归档路径> --confirm`，先让用户核对新提案，不重用旧推断。

旧 schema 1 画像和无 `evidence` 的反馈批次仍可读取；没有证据的历史记录保留并隔离，不能因兼容而启用。`refresh-guidance` 和 `show-guidance` 从合格原始事件重算，不信任旧派生缓存。公共消费接口仍为 `feedback_issue(event, project_id)`，维度仍在 `evidence.confirmed_terms/scope`。

含有效和无效候选的批次保持原子拒绝：错误列明候选 ID 和原因，画像不部分写入，替换校验失败也不创建归档。可补齐问题候选；或保留旧快照，把完整候选复制到新的评审文件，以新输出路径重新 `extract-review`，核对后再 `record-feedback --confirm`。不要删改旧提案证据来强行通过。

## 实际进入检索

```bash
python3 scripts/discovery_plan.py --input request.json \
  --profile profile.zh-CN.json --output discovery-plan.json
```

`request.json` 必须显式带同一个 `project_id`。也可以显式传入 `preference_events`，不能与 `--profile` 同时使用。

已核实积极反馈用用户确认的理由维度生成机制查询；没有维度时以该来源为扩展锚点，而不是猜喜欢它所有特征。`consumption` 记录对应 query ID 或未使用原因。`ranking_policy` 区分深入、机制参考、候选级降权和明确维度降权；宿主先做来源核验与项目匹配，再应用有界影响，并记录候选级效果。候选级影响按规范来源和版本匹配，不凭新一轮重复使用的编号。

三个状态始终分开：进入下一轮检索偏好、成为待验证机制假设、已实际实现到目标项目。用户的“可借鉴”本身不证明已经实现，也不证明发现质量已经提高。
