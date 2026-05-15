# ex-skill 改进总结

## 项目概述

`ex-skill` 是一个 Claude Code Skill，将前任的形象蒸馏为 AI 人格。用户提供聊天记录、照片、社交媒体等原材料，自动生成一个「像她一样说话」的 AI Skill，包含共同记忆（Memories）和人物性格（Persona）两部分。

---

## 当前功能

### 数据导入

| 来源 | 格式 | 双向对话 | 编码容错 |
|------|------|:--------:|:--------:|
| 微信聊天记录 | TXT / CSV / HTML / XLSX | 支持 | UTF-8 + GBK 降级 |
| iMessage | TXT / CSV / chat.db | 支持 | UTF-8 + GBK 降级 |
| 短信 | XML / CSV / TXT | 支持 | UTF-8 + GBK 降级 |
| 照片 | 文件夹扫描 | — | EXIF 提取（JPEG） |
| 社交媒体 | 微博 / 豆瓣 / 小红书 / Instagram | — | UTF-8 + GBK 降级 |
| 文件上传 | PDF / 图片 / MD / TXT | — | Claude 原生读取 |
| 直接粘贴 | 任意文本 | — | — |

所有解析器输出统一 JSON 格式：`{"sender": "her"/"me", "content": "...", "timestamp": "..."}`。

### 事件聚类流水线

```
聊天记录 → 解析器(JSON) → 时间分段 → Claude逐段提取事件 → 合并到 events.json → 分析跨事件模式 → 生成 memories.md
```

- **时间分段**：按消息间隔自动切分窗口，小窗口自动合并
- **事件提取**：每个窗口提取离散事件，包含时间线、细节、感官描述、情感意义
- **续集检测**：新事件自动判断是否为已有事件的延续，合并到同一事件
- **稳定 ID**：已有事件 ID 永不变，新增事件从最大 ID 递增
- **graph 结构**：一个事件可以是多个已有事件的续集

### 记忆系统（Part A）

| 模块 | 内容 |
|------|------|
| 关系概览 | 2-3 句叙事开头 |
| 关系弧线 | 按阶段划分的关系演变（高峰期 → 稳定期 → 磨合期 → ...） |
| 事件簿 | 所有事件的完整记录（时间线 + 细节 + 感官 + 情感），无上限 |
| 感官锚点 | 嗅觉/听觉/味觉/触觉/视觉的触发记忆，按类型去重 |
| 情感纹理 | 她在不同情绪下的行为模式 |
| 冲突地图 | 触发条件 → 升级路径 → 冷战特点 → 修复方式 |
| 共同梦想 | 未实现的计划和约定 |
| 未说出的 | 从对话中推断但未明言的情感 |
| Correction Log | 用户纠正的记录 |

### 人格系统（Part B）

7 层结构：

| 层级 | 内容 |
|------|------|
| Layer 0 | 硬规则（绝对不能做的事） |
| Layer 0.5 | 回复决策表（消息类型 × 情绪状态 → 回复行为） |
| Layer 1 | 身份（基本信息、关系状态） |
| Layer 2 | 表达风格（消息习惯、语气词、emoji 偏好） |
| Layer 3 | 情感逻辑（安全感需求、情绪表达方式） |
| Layer 4 | 关系行为（依赖模式、吵架模式、修复方式） |
| Layer 5 | 喜好与雷区 |
| Correction Log | 用户纠正的记录 |

### 进化机制

- **追加原材料**：新聊天记录 → 分段 → 提取事件 → 合并到 events.json → 增量更新 memories/persona
- **对话纠正**：说「她不会这样」→ 自动判断归属（memories 或 persona）→ 写入对应 Correction Log
- **版本管理**：每次更新自动存档，支持回滚和清理旧版本

### 管理命令

| 命令 | 说明 |
|------|------|
| `/create-ex` | 创建新前任 Skill |
| `/{slug}` | 调用完整 Skill |
| `/{slug}-memories` | 仅共同记忆 |
| `/{slug}-persona` | 仅人物性格 |
| `/list-exes` | 列出所有已创建的 Skill |
| `/update-ex {slug}` | 追加原材料或纠正 |
| `/ex-rollback {slug} {version}` | 回滚到历史版本 |
| `/delete-ex {slug}` | 删除 |

---

## 相比原项目的改进

### 1. 事件聚类（核心改进）

**原项目**：记忆系统只有简单的"关键节点总结"，预定义 8-15 个事件，每个事件是简短的文字描述。

**改进后**：
- 从聊天记录中自动提取离散事件，数量不设上限
- 每个事件包含：时间线（3-8 个节点）→ 整体叙事 → 具体细节 → 感官描述 → 情感意义
- 支持续集检测：新事件自动合并到已有事件
- 支持 graph 结构：一个事件可以关联多个已有事件
- 事件存储在 `events.json` 数据库中，支持增量追加

### 2. 解析器健壮性

**原项目**：解析器假设 UTF-8 编码，GBK 文件直接崩溃；CSV 不处理 BOM；sender 归一化逻辑不统一。

**改进后**：
- 所有解析器：UTF-8 优先，GBK 自动降级，不崩溃
- CSV 读取：使用 `utf-8-sig` 自动剥离 BOM
- Sender 归一化：三个解析器统一逻辑 `sender in ("me", "我")`
- 单方面消息：支持标注 `incomplete_dialogue`，区分事实和推断

### 3. 事件数据库稳定性

**原项目**：无事件数据库概念。

**改进后**：
- 事件 ID 稳定：已有事件 ID 永不变，新事件从最大 ID 递增
- 合并去重：timeline 用 `(time, detail)` tuple 去重，避免字符串拼接碰撞
- Schema 校验：`load_events` 验证列表类型、字典类型、id 字段，跳过无效条目并警告

### 4. 版本管理完整性

**原项目**：版本管理只备份 SKILL.md、memories.md、persona.md。

**改进后**：
- 备份包含 `events.json`，回滚不会丢失事件数据库
- 新增 `backup` action，支持独立备份操作
- 回滚前自动存档当前版本（带 `_before_rollback` 后缀）
- 修复潜在 NameError（`current_version` 未定义时的崩溃）

### 5. Correction 机制

**原项目**：Correction 只能写入 persona.md，且中英文标题不一致。

**改进后**：
- Correction 支持路由到 memories.md 或 persona.md
- 路由逻辑：事件/感官/偏好/冲突/情感 → memories.md；沟通/性格 → persona.md
- 标题统一为 `## Correction Log`，所有文件一致
- memories.md 模板包含 Correction Log 节

### 6. Skill 生成完整性

**原项目**：`skill_writer.py` 的 `slugify` 用下划线分隔，和文档规范不一致；meta.json 缺少 events 字段。

**改进后**：
- `slugify` 统一用 `-` 分隔（和 `intake.md` 规范一致）
- `create_skill` 自动从 events.json 读取事件数注入 meta.json
- SKILL.md 步骤编号修正（1-6，无重复）

### 7. Prompt 质量

**原项目**：事件提取 prompt 缺少单方面消息处理策略；memories 模板没有 incomplete_dialogue 处理。

**改进后**：
- `event_extractor.md`：完整的事件 JSON schema（含 `incomplete_dialogue` 字段）+ 单方面消息处理策略
- `memories_builder.md`：事件渲染模板区分完整对话和单方面消息（加警告标记）
- `correction_handler.md`：明确的路由表，区分 memories 和 persona 纠正
- 英文版 SKILL.md 补全窗口过多时的处理指引

### 8. 代码质量

**改进点**：
- 13 处文件读取统一添加编码降级
- 3 处 CSV 读取统一使用 `utf-8-sig`
- `merge_events` 返回值从单个 list 改为 `(list, int)` 元组，计数准确
- `load_events` 添加 schema 校验，防止坏数据导致整个流程崩溃
- 删除不维护的示例数据目录

### 9. 原始材料归档

**原项目**：`knowledge/` 目录只创建空文件夹，不归档任何原始材料。

**改进后**：
- 新增 `archive_source_files()` 函数，Skill 创建时自动归档原始材料
- 文本类文件（聊天记录、社交媒体导出）：复制到 `knowledge/chats/` 和 `knowledge/social/`
- 照片类：只在 `meta.json` 记录原始路径，不复制（避免占用大量磁盘空间）
- `meta.json` 的 `knowledge_sources` 字段自动记录归档信息（类型、原始路径、归档路径）
- 同名文件自动加数字后缀避免覆盖

### 10. XLSX 支持（WeFlow 格式）

**原项目**：微信解析器只支持 TXT/CSV/HTML。

**改进后**：
- 新增 `preview_xlsx()` 函数：预览 xlsx 前 15 行原始内容
- 新增 `parse_wechat_xlsx()` 函数：按指定表头行解析
- 两步法工作流：先 `--preview` 让 LLM 判断表头位置，再 `--header-row N` 正式解析
- 自动跳过 `消息类型 == "系统消息"` 的行
- 列名匹配优先级：WeFlow 专用列名 → 通用列名 fallback

### 11. 事件聚类优化

**原项目**：默认分段参数 `gap_hours=6`, `min_messages=10`，窗口太粗，导致每个窗口只提取一个事件。

**改进后**：
- 默认参数调整为 `gap_hours=2`, `min_messages=5`，窗口更细更聚焦
- 日期变化分段阈值从 2 小时改为 1 小时
- 每段最大消息数从 200 降到 150
- `event_extractor.md` 新增多事件提取指令，明确要求逐个识别所有事件
- 输出格式说明强化：多个事件必须返回 JSON 数组
- SKILL.md 修正窗口指引：窗口过多时应减小 gap-hours（而非增大）
- 新增 `density` 子命令：检查事件密度，自动警告过低情况

### 12. 回复逻辑优化

**原项目**：运行规则只有 3 句话概述（"Part B 判断 → Part A 提供记忆 → 保持风格"），无状态跟踪，无决策表。

**改进后**：
- `persona_builder.md` 新增 Layer 0.5（回复决策表）：消息类型 × 情绪状态 → 回复行为映射
- 新增不回复/延迟回复规则：明确已读不回、冷淡回复的触发条件
- `persona_analyzer.md` 新增第 5 维度（回复决策模式）：从聊天记录中提取不同情绪下的回复特征
- `skill_writer.py` 的 SKILL.md 模板重写运行规则：
  - 第 0 步：确定当前情绪状态（正常/开心/生气）
  - 第 1 步：查决策表判断回复行为
  - 第 2 步：检索记忆（情绪过滤：生气时不提甜蜜记忆）
  - 第 3 步：融合输出（情绪影响语气和 emoji）
- Persona 层级从 6 层变为 7 层：Layer 0 → Layer 0.5 → Layer 1-5

---

## 文件结构

```
ex-skill/
├── SKILL.md                     # Skill 入口（双语，完整工作流）
├── README.md                    # 项目说明
├── CHANGELOG.md                 # 本文件
├── prompts/
│   ├── intake.md                #   基础信息录入问题序列
│   ├── event_extractor.md       #   事件提取 prompt（含单方面消息策略）
│   ├── memories_analyzer.md     #   跨事件模式分析（6 维度）
│   ├── memories_builder.md      #   memories.md 生成模板（9 模块）
│   ├── persona_analyzer.md      #   性行为提取（含标签翻译表 + 回复决策模式）
│   ├── persona_builder.md       #   persona.md 7 层结构模板（含 Layer 0.5）
│   ├── merger.md                #   增量 merge 逻辑
│   └── correction_handler.md    #   对话纠正处理（双路由）
├── tools/
│   ├── wechat_parser.py         #   微信聊天记录解析
│   ├── imessage_parser.py       #   iMessage 解析
│   ├── sms_parser.py            #   短信解析
│   ├── photo_analyzer.py        #   照片 EXIF 元数据分析
│   ├── social_media_parser.py   #   社交媒体解析
│   ├── event_clusterer.py       #   事件聚类（segment/merge/list/summary/density）
│   ├── skill_writer.py          #   Skill 文件管理（含原始材料归档）
│   └── version_manager.py       #   版本管理（list/backup/rollback/cleanup）
├── exes/                        #   生成的前任 Skill（运行时创建）
├── requirements.txt
└── LICENSE
```
