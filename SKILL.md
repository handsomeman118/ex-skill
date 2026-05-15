---
name: create-ex
description: "Distill an ex-girlfriend into an AI Skill. Import WeChat/iMessage/SMS/photos, generate Memories + Persona, with continuous evolution. | 把前任蒸馏成 AI Skill，导入微信/iMessage/短信/照片，生成共同记忆 + Persona，支持持续进化。"
argument-hint: "[ex-name-or-slug]"
version: "1.0.0"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash
---

> **Language / 语言**: This skill supports both English and Chinese. Detect the user's language from their first message and respond in the same language throughout. Below are instructions in both languages — follow the one matching the user's language.
>
> 本 Skill 支持中英文。根据用户第一条消息的语言，全程使用同一语言回复。下方提供了两种语言的指令，按用户语言选择对应版本执行。

# 前任.skill 创建器（Claude Code 版）

## 触发条件

当用户说以下任意内容时启动：
- `/create-ex`
- "帮我创建一个前任 skill"
- "我想蒸馏一个前任"
- "新建前任"
- "给我做一个 XX 的 skill"

当用户对已有前任 Skill 说以下内容时，进入进化模式：
- "我有新聊天记录" / "追加"
- "这不对" / "她不会这样" / "她应该是"
- `/update-ex {slug}`

当用户说 `/list-exes` 时列出所有已生成的前任。

---

## 工具使用规则

本 Skill 运行在 Claude Code 环境，使用以下工具：

| 任务 | 使用工具 |
|------|---------|
| 读取 PDF 文档 | `Read` 工具（原生支持 PDF） |
| 读取图片截图 | `Read` 工具（原生支持图片） |
| 读取 MD/TXT 文件 | `Read` 工具 |
| 解析微信聊天记录（TXT/CSV/HTML/XLSX） | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py` |
| 解析 iMessage | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/imessage_parser.py` |
| 解析短信 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/sms_parser.py` |
| 事件聚类 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py` |
| 分析照片元数据 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/photo_analyzer.py` |
| 解析社交媒体导出 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/social_media_parser.py` |
| 写入/更新 Skill 文件 | `Write` / `Edit` 工具 |
| 版本管理 | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py` |
| 列出已有 Skill | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action list` |

**基础目录**：Skill 文件写入 `./exes/{slug}/`（相对于本项目目录）。
如需改为全局路径，用 `--base-dir ~/.openclaw/workspace/skills/exes`。

---

## 主流程：创建新前任 Skill

### Step 1：基础信息录入（3 个问题）

参考 `${CLAUDE_SKILL_DIR}/prompts/intake.md` 的问题序列，只问 3 个问题：

1. **昵称/代号**（必填）
2. **基本信息**（一句话：在一起多久、怎么认识的、分手多久、她做什么的，想到什么写什么）
   - 示例：`在一起三年 大学同学 分手一年 她做设计`
3. **性格画像**（一句话：MBTI、星座、依恋类型、恋爱标签、你对她的印象）
   - 示例：`ENFP 双子座 焦虑型 爱撒娇 翻旧账 嘴上说不在意其实比谁都在意`

除昵称外均可跳过。收集完后汇总确认再进入下一步。

### Step 2：原材料导入

询问用户提供原材料，展示多种方式供选择：

```
原材料怎么提供？

  [A] 微信聊天记录
      导出的 txt/html 文件（WechatExporter 等工具导出）

  [B] iMessage / 短信
      从 Mac 的 chat.db 或导出文件

  [C] 照片
      指定一个文件夹，自动提取时间线（EXIF 元数据）

  [D] 社交媒体
      微博/豆瓣/小红书/Instagram 导出

  [E] 上传其他文件
      PDF / 图片截图 / 任意文本

  [F] 直接粘贴内容
      把文字复制进来

可以混用，也可以跳过（仅凭手动信息生成）。
```

---

#### 方式 A：微信聊天记录

```bash
python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py --file {path} --target "{name}" --format json --output /tmp/wechat_out.json
```
然后 `Read /tmp/wechat_out.json`

支持格式：
- WechatExporter 导出的 txt 文件（格式：`{时间} {发送人}: {内容}`）
- WechatExporter 导出的 html 文件
- 其他微信备份工具导出的 txt/csv
- WeFlow 等工具导出的 xlsx 文件

**xlsx 文件处理流程**（需要两步）：

1. 先预览前 15 行，判断表头位置：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py --file {path} --preview
```
2. 根据预览结果指定表头行号，正式解析：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py --file {path} --target "{name}" --header-row {N} --format json --output /tmp/wechat_out.json
```

---

#### 方式 B：iMessage / 短信

**iMessage**（macOS）：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/imessage_parser.py --file {path} --target "{phone_or_name}" --format json --output /tmp/imessage_out.json
```

直接读取本机 chat.db（需要 Full Disk Access 权限）：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/imessage_parser.py --direct --target "{phone_or_name}" --format json --output /tmp/imessage_out.json
```

**短信**：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/sms_parser.py --file {path} --target "{phone_or_name}" --format json --output /tmp/sms_out.json
```

---

#### 方式 C：照片

```bash
python3 ${CLAUDE_SKILL_DIR}/tools/photo_analyzer.py --dir {photo_directory} --output /tmp/photo_timeline.txt
```
然后 `Read /tmp/photo_timeline.txt` 获取时间线。

具体照片的内容由用户选择后通过 `Read` 工具直接查看（Claude 原生支持图片）。

---

#### 方式 D：社交媒体

```bash
python3 ${CLAUDE_SKILL_DIR}/tools/social_media_parser.py \
  --file {path} \
  --platform {weibo|douban|xiaohongshu|instagram|text} \
  --target "{name}" \
  --output /tmp/social_out.txt
```
然后 `Read /tmp/social_out.txt`

---

#### 方式 E：上传文件

- **PDF / 图片**：`Read` 工具直接读取
- **Markdown / TXT**：`Read` 工具直接读取

---

#### 方式 F：直接粘贴

用户粘贴的内容直接作为文本原材料，无需调用任何工具。

---

如果用户说"没有文件"或"跳过"，仅凭 Step 1 的手动信息生成 Skill。

### Step 3：事件聚类

如果有聊天记录 JSON 文件，先进行事件聚类：

**3a. 分段**：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py segment --input /tmp/wechat_out.json --output /tmp/windows.json
```

**3b. 逐段提取事件**：
- `Read /tmp/windows.json` 获取所有时间窗口
- 窗口数量多（>20）是正常的，每个窗口消息更少，事件提取更准确
- 如果窗口数量过多（>50），可以略微增大 `--gap-hours`（如 3 或 4）重新分段
- 参考 `${CLAUDE_SKILL_DIR}/prompts/event_extractor.md`，对每个窗口提取事件
- **重要：每个窗口应提取所有可识别的事件**，不要只提取一个概括性事件
- 每个窗口处理时，先读取已有事件摘要：`python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py summary --base-dir exes/{slug}`
- 将每个窗口提取的事件追加到 `/tmp/new_events.json`（所有窗口共用一个文件，不是每个窗口一个文件）
- 如果某个窗口提取失败（返回非 JSON 或无事件），跳过该窗口并记录 window_id，最后告知用户跳过了哪些窗口

**3c. 合并事件**：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py merge --events /tmp/new_events.json --base-dir exes/{slug}
```

**3d. 事件密度检查**：
合并后检查事件密度：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py density --windows /tmp/windows.json --base-dir exes/{slug}
```
如果平均每个窗口 < 1.5 个事件，说明提取过于保守，需要：
1. 检查事件提取结果，确认是否有遗漏
2. 考虑减小 `--gap-hours` 重新分段，让每个窗口更聚焦

**3d. 确认事件列表**：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py list --base-dir exes/{slug}
```
向用户展示事件列表，用户可选择合并/拆分/删除事件。

### Step 4：分析事件数据库

将事件数据库和用户填写的基础信息汇总，按以下两条线分析：

**线路 A（Memories Skill）**：
- 参考 `${CLAUDE_SKILL_DIR}/prompts/memories_analyzer.md` 中的提取维度
- 从 events.json 中提炼：关系弧线、感官锚点、情感模式、冲突地图、共同梦想、未说出的

**线路 B（Persona）**：
- 参考 `${CLAUDE_SKILL_DIR}/prompts/persona_analyzer.md` 中的提取维度
- 将用户填写的标签翻译为具体行为规则（参见标签翻译表）
- 从事件中提取：表达风格、情感逻辑、关系行为

### Step 5：生成并预览

参考 `${CLAUDE_SKILL_DIR}/prompts/memories_builder.md` 生成 Memories Skill 内容（从 events.json + 分析结果生成）。
参考 `${CLAUDE_SKILL_DIR}/prompts/persona_builder.md` 生成 Persona 内容（7 层结构：Layer 0 硬规则 → Layer 0.5 回复决策表 → Layer 1-5）。

向用户展示摘要（各 5-8 行），询问：
```
共同记忆摘要：
  - 在一起：{duration}
  - 事件数量：{N} 个
  - 关系弧线：{阶段概述}
  - 感官锚点：{N} 个
  ...

Persona 摘要：
  - 核心性格：{xxx}
  - 回复风格：{正常/开心/生气时的回复差异}
  - 不回复场景：{已读不回/冷淡回复的触发条件}
  - 吵架模式：{xxx}
  ...

确认生成？还是需要调整？
```

### Step 6：写入文件

用户确认后，执行以下写入操作：

**1. 准备原始材料归档列表**

将 Step 2 中用户提供的原始文件路径整理为 JSON，按类别分组：
- `chats`：微信/iMessage/短信等聊天记录文件
- `social`：社交媒体导出文件
- `photos`：照片文件夹路径（只记录路径，不复制）

```json
{
  "chats": ["/path/to/wechat.txt", "/path/to/imessage.csv"],
  "social": ["/path/to/weibo.html"],
  "photos": ["/path/to/photos/"]
}
```

保存为 `/tmp/source_files.json`。

**2. 写入所有文件**（用 Bash 调用 skill_writer.py）：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action create \
  --slug {slug} --name "{name}" \
  --meta /tmp/meta.json \
  --memories /tmp/memories.md \
  --persona /tmp/persona.md \
  --source-files /tmp/source_files.json \
  --base-dir ./exes
```

其中 `/tmp/meta.json` 包含：
```json
{
  "name": "{name}",
  "slug": "{slug}",
  "profile": {
    "duration": "{duration}",
    "how_met": "{how_met}",
    "time_since_breakup": "{time_since}",
    "occupation": "{occupation}",
    "gender": "女",
    "mbti": "{mbti}"
  },
  "tags": {
    "personality": [...],
    "attachment": "{attachment_style}"
  },
  "impression": "{impression}",
  "corrections_count": 0,
  "events": {
    "count": 10,
    "last_clustered_at": "2024-01-01T00:00:00Z"
  }
}
```

`skill_writer.py` 会自动：
- 创建目录结构（`versions/`、`knowledge/chats/`、`knowledge/photos/`、`knowledge/social/`）
- 归档文本类原始材料（复制到 `knowledge/` 对应子目录）
- 记录照片路径（只在 `meta.json` 的 `knowledge_sources` 中记录，不复制文件）
- 生成 `memories_skill.md` 和 `persona_skill.md`
- 生成 `SKILL.md`（合并 memories.md + persona.md + 运行规则）

告知用户：
```
✅ 前任 Skill 已创建！

文件位置：exes/{slug}/
触发词：/{slug}（完整版）
        /{slug}-memories（仅共同记忆）
        /{slug}-persona（仅人物性格）

如果用起来感觉哪里不对，直接说"她不会这样"，我来更新。
```

---

## 进化模式：追加文件

用户提供新文件或文本时：

1. 按 Step 2 的方式读取新内容（JSON 格式）
2. 事件聚类（按 Step 3 的流程）：
   - 分段 → 逐段提取事件 → 合并到 events.json
3. 用 `Read` 读取现有 `exes/{slug}/memories.md` 和 `persona.md`
4. 参考 `${CLAUDE_SKILL_DIR}/prompts/merger.md` 分析增量内容
5. 存档当前版本（用 Bash）：
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py --action backup --slug {slug} --base-dir ./exes
   ```
6. 用 `Edit` 工具更新 memories.md 和 persona.md
7. 重新生成 `SKILL.md`（合并最新 memories.md + persona.md）
8. 更新 `meta.json` 的 version 和 updated_at

---

## 进化模式：对话纠正

用户表达"不对"/"她不会这样"时：

1. 参考 `${CLAUDE_SKILL_DIR}/prompts/correction_handler.md` 识别纠正内容
2. 判断属于 Memories（时间/地点/偏好）还是 Persona（性格/沟通）
3. 生成 correction 记录
4. 用 `Edit` 工具追加到对应文件的 `## Correction Log` 节
5. 重新生成 `SKILL.md`

---

## 管理命令

`/list-exes`：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action list --base-dir ./exes
```

`/ex-rollback {slug} {version}`：
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py --action rollback --slug {slug} --version {version} --base-dir ./exes
```

`/delete-ex {slug}`：
确认后执行：
```bash
rm -rf exes/{slug}
```

---
---

# English Version

# Ex.skill Creator (Claude Code Edition)

## Trigger Conditions

Activate when the user says any of the following:
- `/create-ex`
- "Help me create an ex skill"
- "I want to distill an ex"
- "New ex"
- "Make a skill for XX"

Enter evolution mode when the user says:
- "I have new chat logs" / "append"
- "That's wrong" / "She wouldn't do that" / "She should be"
- `/update-ex {slug}`

List all generated exes when the user says `/list-exes`.

---

## Tool Usage Rules

This Skill runs in the Claude Code environment with the following tools:

| Task | Tool |
|------|------|
| Read PDF documents | `Read` tool (native PDF support) |
| Read image screenshots | `Read` tool (native image support) |
| Read MD/TXT files | `Read` tool |
| Parse WeChat chat exports (TXT/CSV/HTML/XLSX) | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py` |
| Parse iMessage | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/imessage_parser.py` |
| Parse SMS | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/sms_parser.py` |
| Event clustering | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py` |
| Analyze photo metadata | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/photo_analyzer.py` |
| Parse social media exports | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/social_media_parser.py` |
| Write/update Skill files | `Write` / `Edit` tool |
| Version management | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py` |
| List existing Skills | `Bash` → `python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action list` |

**Base directory**: Skill files are written to `./exes/{slug}/` (relative to the project directory).
For a global path, use `--base-dir ~/.openclaw/workspace/skills/exes`.

---

## Main Flow: Create a New Ex Skill

### Step 1: Basic Info Collection (3 questions)

Refer to `${CLAUDE_SKILL_DIR}/prompts/intake.md` for the question sequence. Only ask 3 questions:

1. **Nickname / Codename** (required)
2. **Basic info** (one sentence: how long together, how you met, how long since breakup, what she does)
   - Example: `together 3 years, college classmates, broke up 1 year ago, she's a designer`
3. **Personality profile** (one sentence: MBTI, zodiac, attachment style, relationship traits, your impression)
   - Example: `ENFP Gemini anxious attachment, clingy, brings up old arguments, says she doesn't care but cares the most`

Everything except the nickname can be skipped. Summarize and confirm before moving to the next step.

### Step 2: Source Material Import

Ask the user how they'd like to provide materials:

```
How would you like to provide source materials?

  [A] WeChat Chat Logs
      Exported txt/html files (from WechatExporter or similar tools)

  [B] iMessage / SMS
      From Mac's chat.db or exported files

  [C] Photos
      Specify a folder, auto-extract timeline (EXIF metadata)

  [D] Social Media
      Weibo/Douban/Xiaohongshu/Instagram exports

  [E] Upload Files
      PDF / screenshots / any text

  [F] Paste Text
      Copy-paste text directly

Can mix and match, or skip entirely (generate from manual info only).
```

---

#### Option A: WeChat Chat Logs

```bash
python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py --file {path} --target "{name}" --format json --output /tmp/wechat_out.json
```
Then `Read /tmp/wechat_out.json`

Supported formats:
- WechatExporter txt files (format: `{timestamp} {sender}: {content}`)
- WechatExporter html files
- Other WeChat backup tools: txt/csv
- WeFlow and similar tools: xlsx

**XLSX file workflow** (two steps):

1. Preview first 15 rows to identify the header position:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py --file {path} --preview
```
2. Parse with the identified header row:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/wechat_parser.py --file {path} --target "{name}" --header-row {N} --format json --output /tmp/wechat_out.json
```

---

#### Option B: iMessage / SMS

**iMessage** (macOS):
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/imessage_parser.py --file {path} --target "{phone_or_name}" --format json --output /tmp/imessage_out.json
```

Direct access to local chat.db (requires Full Disk Access):
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/imessage_parser.py --direct --target "{phone_or_name}" --format json --output /tmp/imessage_out.json
```

**SMS**:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/sms_parser.py --file {path} --target "{phone_or_name}" --format json --output /tmp/sms_out.json
```

---

#### Option C: Photos

```bash
python3 ${CLAUDE_SKILL_DIR}/tools/photo_analyzer.py --dir {photo_directory} --output /tmp/photo_timeline.txt
```
Then `Read /tmp/photo_timeline.txt` for the timeline.

Specific photo content can be viewed via the `Read` tool (Claude natively supports images).

---

#### Option D: Social Media

```bash
python3 ${CLAUDE_SKILL_DIR}/tools/social_media_parser.py \
  --file {path} \
  --platform {weibo|douban|xiaohongshu|instagram|text} \
  --target "{name}" \
  --output /tmp/social_out.txt
```

---

#### Option E: Upload Files

- **PDF / Images**: `Read` tool directly
- **Markdown / TXT**: `Read` tool directly

---

#### Option F: Paste Text

User-pasted content is used directly as text material. No tools needed.

---

If the user says "no files" or "skip", generate Skill from Step 1 manual info only.

### Step 3: Event Clustering

If chat log JSON files exist, perform event clustering first:

**3a. Segment**:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py segment --input /tmp/wechat_out.json --output /tmp/windows.json
```

**3b. Extract events per window**:
- `Read /tmp/windows.json` to get all time windows
- Having many windows (>20) is normal — fewer messages per window means more accurate extraction
- If there are too many windows (>50), slightly increase `--gap-hours` (e.g., 3 or 4) and re-segment
- Refer to `${CLAUDE_SKILL_DIR}/prompts/event_extractor.md` to extract events from each window
- **Important: extract ALL identifiable events from each window**, not just one summary event
- For each window, first read existing events: `python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py summary --base-dir exes/{slug}`
- Append each window's extracted events to `/tmp/new_events.json` (all windows share one file, not one file per window)
- If a window extraction fails (returns non-JSON or no events), skip that window and record the window_id; inform the user which windows were skipped at the end

**3c. Merge events**:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py merge --events /tmp/new_events.json --base-dir exes/{slug}
```

**3d. Event density check**:
After merging, check event density:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py density --windows /tmp/windows.json --base-dir exes/{slug}
```
If average events per window < 1.5, extraction was too conservative:
1. Review extracted events for gaps
2. Consider reducing `--gap-hours` to make windows more focused

**3e. Confirm event list**:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/event_clusterer.py list --base-dir exes/{slug}
```
Show events to user, who can merge/split/delete.

### Step 4: Analyze Events Database

Combine events database and user-provided info, analyze along two tracks:

**Track A (Memories Skill)**:
- Refer to `${CLAUDE_SKILL_DIR}/prompts/memories_analyzer.md` for extraction dimensions
- From events.json extract: relationship arc, sensory anchors, emotional patterns, conflict map, shared dreams, the unspoken

**Track B (Persona)**:
- Refer to `${CLAUDE_SKILL_DIR}/prompts/persona_analyzer.md` for extraction dimensions
- Translate user-provided tags into concrete behavior rules (see tag translation table)
- Extract from events: communication style, emotional logic, relationship behavior

### Step 5: Generate and Preview

Use `${CLAUDE_SKILL_DIR}/prompts/memories_builder.md` to generate Memories Skill content (from events.json + analysis results).
Use `${CLAUDE_SKILL_DIR}/prompts/persona_builder.md` to generate Persona content (7-layer structure: Layer 0 hard rules → Layer 0.5 reply decision matrix → Layer 1-5).

Show the user a summary (5-8 lines each), ask:
```
Memories Summary:
  - Together: {duration}
  - Events: {N}
  - Relationship arc: {phases overview}
  - Sensory anchors: {N}
  ...

Persona Summary:
  - Core personality: {xxx}
  - Reply style: {normal/happy/angry differences}
  - Non-reply triggers: {conditions for cold silence}
  - Conflict pattern: {xxx}
  ...

Confirm generation? Or need adjustments?
```

### Step 6: Write Files

After user confirmation, execute the following:

**1. Prepare source file archive list**

Organize the original files from Step 2 into a JSON grouped by category:
- `chats`: WeChat/iMessage/SMS chat log files
- `social`: Social media export files
- `photos`: Photo folder paths (path only, no copying)

```json
{
  "chats": ["/path/to/wechat.txt", "/path/to/imessage.csv"],
  "social": ["/path/to/weibo.html"],
  "photos": ["/path/to/photos/"]
}
```

Save as `/tmp/source_files.json`.

**2. Write all files** (Bash via skill_writer.py):
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action create \
  --slug {slug} --name "{name}" \
  --meta /tmp/meta.json \
  --memories /tmp/memories.md \
  --persona /tmp/persona.md \
  --source-files /tmp/source_files.json \
  --base-dir ./exes
```

`skill_writer.py` automatically:
- Creates directory structure (`versions/`, `knowledge/chats/`, `knowledge/photos/`, `knowledge/social/`)
- Archives text source materials (copies to `knowledge/` subdirectories)
- Records photo paths (only in `meta.json` `knowledge_sources`, no file copying)
- Generates `memories_skill.md` and `persona_skill.md`
- Generates `SKILL.md` (merges memories.md + persona.md + runtime rules)

Inform user:
```
✅ Ex Skill created!

Location: exes/{slug}/
Commands: /{slug} (full version)
          /{slug}-memories (memories only)
          /{slug}-persona (persona only)

If something feels off, just say "she wouldn't do that" and I'll update it.
```

---

## Evolution Mode: Append Files

When user provides new files or text:

1. Read new content using Step 2 methods (JSON format)
2. Event clustering (follow Step 3 flow):
   - Segment → Extract events per window → Merge into events.json
3. `Read` existing `exes/{slug}/memories.md` and `persona.md`
4. Refer to `${CLAUDE_SKILL_DIR}/prompts/merger.md` for incremental analysis
5. Archive current version (Bash):
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py --action backup --slug {slug} --base-dir ./exes
   ```
6. Use `Edit` tool to update memories.md and persona.md
7. Regenerate `SKILL.md` (merge latest memories.md + persona.md)
8. Update `meta.json` version and updated_at

---

## Evolution Mode: Conversation Correction

When user expresses "that's wrong" / "she wouldn't do that":

1. Refer to `${CLAUDE_SKILL_DIR}/prompts/correction_handler.md` to identify correction content
2. Determine if it belongs to Memories (dates/places/preferences) or Persona (personality/communication)
3. Generate correction record
4. Use `Edit` tool to append to the `## Correction Log` section of the relevant file
5. Regenerate `SKILL.md`

---

## Management Commands

`/list-exes`:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/skill_writer.py --action list --base-dir ./exes
```

`/ex-rollback {slug} {version}`:
```bash
python3 ${CLAUDE_SKILL_DIR}/tools/version_manager.py --action rollback --slug {slug} --version {version} --base-dir ./exes
```

`/delete-ex {slug}`:
After confirmation:
```bash
rm -rf exes/{slug}
```
