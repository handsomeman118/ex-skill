#!/usr/bin/env python3
"""
Skill 文件写入器

负责将生成的 memories.md、persona.md 写入到正确的目录结构，
并生成 meta.json 和完整的 SKILL.md。

用法：
    python3 skill_writer.py --action create --slug xiaomei --meta meta.json \
        --memories memories_content.md --persona persona_content.md \
        --base-dir ./exes

    python3 skill_writer.py --action update --slug xiaomei \
        --memories-patch memories_patch.md --persona-patch persona_patch.md \
        --base-dir ./exes

    python3 skill_writer.py --action list --base-dir ./exes
"""

from __future__ import annotations

import json
import shutil
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


SKILL_MD_TEMPLATE = """\
---
name: ex_{slug}
description: {name}，{identity}
user-invocable: true
---

# {name}

{identity}

---

## PART A：共同记忆

{memories_content}

---

## PART B：人物性格

{persona_content}

---

## 运行规则

接收到任何消息时，按以下流程回复：

### 第 0 步：确定当前情绪状态

- 如果是对话第一条消息：状态为「正常」
- 如果有上一轮对话：根据 PART B 的 Layer 0.5 回复决策表，结合上一轮内容和你的回复，判断当前情绪状态
- 情绪状态分三档：正常 / 开心 / 生气（含冷战）

### 第 1 步：判断回复行为

查 PART B 的 Layer 0.5 回复决策表，根据「消息类型 × 当前情绪状态」确定回复行为：

- **正常回复** → 继续第 2 步
- **冷淡回复**（一个字/敷衍）→ 用 Layer 2 的冷淡风格直接输出，跳过第 2 步
- **已读不回** → 输出「……」或不回复
- **延迟回复暗示** → 输出「嗯」「哦」「在忙」

### 第 2 步：检索相关记忆

- 查 PART A 的事件簿、感官锚点、情感纹理
- 规则：如果当前情绪是生气/冷战，即使记忆中有甜蜜事件，也不主动提及（除非用户主动道歉，才参考冲突地图的修复方式）
- 规则：如果当前情绪是开心，可以主动关联甜蜜记忆和共同梦想

### 第 3 步：融合输出

- 用 Layer 2 的表达风格输出
- 情绪状态影响语气：开心时多用 emoji，生气时少用或不用
- 记忆引用要符合当前情绪：生气时不会说"还记得我们那次旅行吗"
- **PART B 的 Layer 0 规则永远优先，任何情况下不得违背**
"""


def slugify(name: str) -> str:
    """
    将姓名转为 slug。
    优先尝试 pypinyin（如已安装），否则 fallback 到简单处理。
    """
    try:
        from pypinyin import lazy_pinyin
        parts = lazy_pinyin(name)
        slug = "-".join(parts)
    except ImportError:
        import unicodedata
        result = []
        for char in name.lower():
            if char.isascii() and (char.isalnum() or char in ("-", "_")):
                result.append(char)
            elif char == " ":
                result.append("-")
        slug = "".join(result)

    import re
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug if slug else "ex"


def build_identity_string(meta: dict) -> str:
    """从 meta 构建身份描述字符串"""
    profile = meta.get("profile", {})
    parts = []

    duration = profile.get("duration", "")
    how_met = profile.get("how_met", "")
    time_since = profile.get("time_since_breakup", "")
    occupation = profile.get("occupation", "")

    if duration:
        parts.append(f"在一起 {duration}")
    if how_met:
        parts.append(how_met)
    if time_since:
        parts.append(f"分手 {time_since}")

    identity = "，".join(parts) if parts else "前任"

    if occupation:
        identity += f"，{occupation}"

    mbti = profile.get("mbti", "")
    if mbti:
        identity += f"，MBTI {mbti}"

    return identity


def archive_source_files(source_files: dict, skill_dir: Path) -> list[dict]:
    """归档原始材料到 knowledge/ 目录。

    Args:
        source_files: {"chats": [路径列表], "social": [路径列表], "photos": [路径列表]}
        skill_dir: Skill 目录路径

    Returns:
        knowledge_sources 列表，供写入 meta.json
        - chats/social: 类型为 "archived"，记录归档后的相对路径
        - photos: 类型为 "linked"，只记录原始路径（不复制）
    """
    knowledge_sources = []

    # 文本类文件：复制到 knowledge/ 对应子目录
    for category in ("chats", "social"):
        files = source_files.get(category, [])
        for fpath in files:
            src = Path(fpath)
            if not src.exists():
                print(f"警告：文件不存在，跳过归档：{src}", file=sys.stderr)
                continue
            dest_dir = skill_dir / "knowledge" / category
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            # 同名文件加数字后缀
            if dest.exists():
                stem = src.stem
                suffix = src.suffix
                idx = 1
                while dest.exists():
                    dest = dest_dir / f"{stem}_{idx}{suffix}"
                    idx += 1
            shutil.copy2(str(src), str(dest))
            knowledge_sources.append({
                "type": "archived",
                "category": category,
                "original": str(src),
                "archived": str(dest.relative_to(skill_dir)),
            })

    # 照片类：只记录路径，不复制
    for fpath in source_files.get("photos", []):
        src = Path(fpath)
        knowledge_sources.append({
            "type": "linked",
            "category": "photos",
            "path": str(src),
        })

    return knowledge_sources


def create_skill(
    base_dir: Path,
    slug: str,
    meta: dict,
    memories_content: str,
    persona_content: str,
    source_files: Optional[dict] = None,
) -> Path:
    """创建新的前任 Skill 目录结构"""

    skill_dir = base_dir / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    (skill_dir / "versions").mkdir(exist_ok=True)
    (skill_dir / "knowledge" / "chats").mkdir(parents=True, exist_ok=True)
    (skill_dir / "knowledge" / "photos").mkdir(parents=True, exist_ok=True)
    (skill_dir / "knowledge" / "social").mkdir(parents=True, exist_ok=True)

    # 归档原始材料
    if source_files:
        archived = archive_source_files(source_files, skill_dir)
        if archived:
            meta["knowledge_sources"] = archived

    # 写入 memories.md
    (skill_dir / "memories.md").write_text(memories_content, encoding="utf-8")

    # 写入 persona.md
    (skill_dir / "persona.md").write_text(persona_content, encoding="utf-8")

    # 生成并写入 SKILL.md
    name = meta.get("name", slug)
    identity = build_identity_string(meta)

    skill_md = SKILL_MD_TEMPLATE.format(
        slug=slug,
        name=name,
        identity=identity,
        memories_content=memories_content,
        persona_content=persona_content,
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # 写入 memories-only skill
    memories_only = (
        f"---\nname: ex_{slug}_memories\n"
        f"description: {name} 的共同记忆（仅 Memories，无 Persona）\n"
        f"user-invocable: true\n---\n\n{memories_content}\n"
    )
    (skill_dir / "memories_skill.md").write_text(memories_only, encoding="utf-8")

    # 写入 persona-only skill
    persona_only = (
        f"---\nname: ex_{slug}_persona\n"
        f"description: {name} 的人物性格（仅 Persona，无共同记忆）\n"
        f"user-invocable: true\n---\n\n{persona_content}\n"
    )
    (skill_dir / "persona_skill.md").write_text(persona_only, encoding="utf-8")

    # 写入 meta.json
    now = datetime.now(timezone.utc).isoformat()
    meta["slug"] = slug
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    meta["version"] = "v1"
    meta.setdefault("corrections_count", 0)

    # 自动注入 events 字段
    events_path = skill_dir / "events.json"
    if events_path.exists():
        try:
            events = json.loads(events_path.read_text(encoding="utf-8"))
            meta["events"] = {
                "count": len(events),
                "last_clustered_at": now,
            }
        except Exception:
            pass
    else:
        meta.setdefault("events", {"count": 0, "last_clustered_at": None})

    (skill_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return skill_dir


def update_skill(
    skill_dir: Path,
    memories_patch: Optional[str] = None,
    persona_patch: Optional[str] = None,
    correction: Optional[dict] = None,
) -> str:
    """更新现有 Skill，先存档当前版本，再写入更新"""

    meta_path = skill_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    current_version = meta.get("version", "v1")
    try:
        version_num = int(current_version.lstrip("v").split("_")[0]) + 1
    except ValueError:
        version_num = 2
    new_version = f"v{version_num}"

    # 存档当前版本
    version_dir = skill_dir / "versions" / current_version
    version_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("SKILL.md", "memories.md", "persona.md"):
        src = skill_dir / fname
        if src.exists():
            shutil.copy2(src, version_dir / fname)

    # 应用 memories patch
    if memories_patch:
        current_memories = (skill_dir / "memories.md").read_text(encoding="utf-8")
        new_memories = current_memories + "\n\n" + memories_patch
        (skill_dir / "memories.md").write_text(new_memories, encoding="utf-8")

    # 应用 persona patch 或 correction
    if persona_patch or correction:
        current_persona = (skill_dir / "persona.md").read_text(encoding="utf-8")

        if correction:
            correction_line = (
                f"\n- [{correction.get('scene', '通用')}] "
                f"不应该 {correction['wrong']}，应该 {correction['correct']}"
            )
            target = "## Correction Log"
            if target in current_persona:
                insert_pos = current_persona.index(target) + len(target)
                rest = current_persona[insert_pos:]
                skip = "\n\n（暂无记录）"
                if rest.startswith(skip):
                    rest = rest[len(skip):]
                new_persona = current_persona[:insert_pos] + correction_line + rest
            else:
                new_persona = (
                    current_persona
                    + f"\n\n## Correction Log\n{correction_line}\n"
                )
            meta["corrections_count"] = meta.get("corrections_count", 0) + 1
        else:
            new_persona = current_persona + "\n\n" + persona_patch

        (skill_dir / "persona.md").write_text(new_persona, encoding="utf-8")

    # 应用 memories correction（correction target 为 memories 时）
    if correction and correction.get("target") == "memories":
        current_memories = (skill_dir / "memories.md").read_text(encoding="utf-8")
        correction_line = (
            f"\n- [{correction.get('scene', '通用')}] "
            f"不应该 {correction['wrong']}，应该 {correction['correct']}"
        )
        target = "## Correction Log"
        if target in current_memories:
            insert_pos = current_memories.index(target) + len(target)
            rest = current_memories[insert_pos:]
            skip = "\n\n（暂无记录）"
            if rest.startswith(skip):
                rest = rest[len(skip):]
            new_memories = current_memories[:insert_pos] + correction_line + rest
        else:
            new_memories = (
                current_memories
                + f"\n\n## Correction Log\n{correction_line}\n"
            )
        (skill_dir / "memories.md").write_text(new_memories, encoding="utf-8")

    # 重新生成 SKILL.md
    memories_content = (skill_dir / "memories.md").read_text(encoding="utf-8")
    persona_content = (skill_dir / "persona.md").read_text(encoding="utf-8")
    name = meta.get("name", skill_dir.name)
    identity = build_identity_string(meta)

    skill_md = SKILL_MD_TEMPLATE.format(
        slug=skill_dir.name,
        name=name,
        identity=identity,
        memories_content=memories_content,
        persona_content=persona_content,
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # 更新 meta
    meta["version"] = new_version
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return new_version


def list_exes(base_dir: Path) -> list:
    """列出所有已创建的前任 Skill"""
    exes = []

    if not base_dir.exists():
        return exes

    for skill_dir in sorted(base_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        meta_path = skill_dir / "meta.json"
        if not meta_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        exes.append({
            "slug": meta.get("slug", skill_dir.name),
            "name": meta.get("name", skill_dir.name),
            "identity": build_identity_string(meta),
            "version": meta.get("version", "v1"),
            "updated_at": meta.get("updated_at", ""),
            "corrections_count": meta.get("corrections_count", 0),
        })

    return exes


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill 文件写入器")
    parser.add_argument("--action", required=True, choices=["create", "update", "list"])
    parser.add_argument("--slug", help="前任 slug（用于目录名）")
    parser.add_argument("--name", help="前任昵称")
    parser.add_argument("--meta", help="meta.json 文件路径")
    parser.add_argument("--memories", help="memories.md 内容文件路径")
    parser.add_argument("--persona", help="persona.md 内容文件路径")
    parser.add_argument("--memories-patch", help="memories.md 增量更新内容文件路径")
    parser.add_argument("--persona-patch", help="persona.md 增量更新内容文件路径")
    parser.add_argument(
        "--base-dir",
        default="./exes",
        help="前任 Skill 根目录（默认：./exes）",
    )
    parser.add_argument(
        "--source-files",
        help="原始材料 JSON 文件路径，格式：{\"chats\": [...], \"social\": [...], \"photos\": [...]}",
    )

    args = parser.parse_args()
    base_dir = Path(args.base_dir).expanduser()

    if args.action == "list":
        exes = list_exes(base_dir)
        if not exes:
            print("暂无已创建的前任 Skill")
        else:
            print(f"已创建 {len(exes)} 个前任 Skill：\n")
            for e in exes:
                updated = e["updated_at"][:10] if e["updated_at"] else "未知"
                print(f"  [{e['slug']}]  {e['name']} — {e['identity']}")
                print(f"    版本: {e['version']}  纠正次数: {e['corrections_count']}  更新: {updated}")
                print()

    elif args.action == "create":
        if not args.slug and not args.name:
            print("错误：create 操作需要 --slug 或 --name", file=sys.stderr)
            sys.exit(1)

        meta: dict = {}
        if args.meta:
            meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
        if args.name:
            meta["name"] = args.name

        slug = args.slug or slugify(meta.get("name", "ex"))

        memories_content = ""
        if args.memories:
            memories_content = Path(args.memories).read_text(encoding="utf-8")

        persona_content = ""
        if args.persona:
            persona_content = Path(args.persona).read_text(encoding="utf-8")

        source_files = None
        if args.source_files:
            source_files = json.loads(Path(args.source_files).read_text(encoding="utf-8"))

        skill_dir = create_skill(base_dir, slug, meta, memories_content, persona_content, source_files=source_files)
        print(f"✅ Skill 已创建：{skill_dir}")
        print(f"   触发词：/{slug}")

    elif args.action == "update":
        if not args.slug:
            print("错误：update 操作需要 --slug", file=sys.stderr)
            sys.exit(1)

        skill_dir = base_dir / args.slug
        if not skill_dir.exists():
            print(f"错误：找不到 Skill 目录 {skill_dir}", file=sys.stderr)
            sys.exit(1)

        memories_patch = Path(args.memories_patch).read_text(encoding="utf-8") if args.memories_patch else None
        persona_patch = Path(args.persona_patch).read_text(encoding="utf-8") if args.persona_patch else None

        new_version = update_skill(skill_dir, memories_patch, persona_patch)
        print(f"✅ Skill 已更新到 {new_version}：{skill_dir}")


if __name__ == "__main__":
    main()
