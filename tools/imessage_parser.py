#!/usr/bin/env python3
"""
iMessage 解析器

支持格式：
1. macOS chat.db 直接读取（需要 Full Disk Access 权限）
2. iMazing / PhoneView 等工具导出的 txt/csv 文件
3. 手动整理的 txt 格式

用法：
    python imessage_parser.py --file messages.txt --target "+8613800138000" --output output.txt
    python imessage_parser.py --direct --target "小美" --output output.txt
"""

import re
import csv
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone


CHAT_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"

# iMessage stores timestamps as nanoseconds since 2001-01-01
APPLE_EPOCH_OFFSET = 978307200  # seconds between Unix epoch and 2001-01-01


def parse_chat_db(target: str, limit: int = 5000, bidirectional: bool = False) -> list[dict]:
    """直接从 macOS chat.db 读取 iMessage"""
    if not CHAT_DB_PATH.exists():
        print(f"错误：找不到 chat.db：{CHAT_DB_PATH}", file=sys.stderr)
        print("提示：需要 Full Disk Access 权限才能读取 iMessage 数据库", file=sys.stderr)
        return []

    messages = []
    try:
        conn = sqlite3.connect(str(CHAT_DB_PATH))
        cursor = conn.cursor()

        if bidirectional:
            query = """
            SELECT
                m.text,
                m.date,
                m.is_from_me,
                h.id AS handle_id
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.text IS NOT NULL
                AND m.text != ''
                AND (h.id LIKE ? OR h.id LIKE ?)
            ORDER BY m.date DESC
            LIMIT ?
            """
        else:
            query = """
            SELECT
                m.text,
                m.date,
                m.is_from_me,
                h.id AS handle_id
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.text IS NOT NULL
                AND m.text != ''
                AND m.is_from_me = 0
                AND (h.id LIKE ? OR h.id LIKE ?)
            ORDER BY m.date DESC
            LIMIT ?
            """

        cursor.execute(query, (f"%{target}%", f"%{target}%", limit))
        rows = cursor.fetchall()

        for text, date_val, is_from_me, handle_id in rows:
            # Convert Apple timestamp to datetime
            if date_val and date_val > 1e15:
                # Nanoseconds
                ts = date_val / 1e9 + APPLE_EPOCH_OFFSET
            elif date_val:
                ts = date_val + APPLE_EPOCH_OFFSET
            else:
                ts = 0

            timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if ts else ""

            # 双向模式下根据 is_from_me 判断发送人
            if bidirectional and is_from_me:
                sender = "me"
            else:
                sender = handle_id or target

            messages.append({
                "sender": sender,
                "content": text.strip(),
                "timestamp": timestamp,
            })

        conn.close()
        messages.reverse()  # Chronological order

    except sqlite3.OperationalError as e:
        print(f"错误：无法读取 chat.db: {e}", file=sys.stderr)
        print("提示：请在 系统设置 → 隐私与安全性 → Full Disk Access 中授权终端", file=sys.stderr)

    return messages


def parse_txt(file_path: str, target: str, bidirectional: bool = False) -> list[dict]:
    """解析 txt 格式的 iMessage/短信导出"""
    messages = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="gbk", errors="replace") as f:
            lines = f.readlines()

    # 匹配格式：2024-01-01 10:00 sender: content
    pattern = re.compile(
        r"^(?P<time>\d{4}[-/]\d{1,2}[-/]\d{1,2}[\s\d:]*)\s+(?P<sender>.+?)[:：]\s*(?P<content>.+)$"
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = pattern.match(line)
        if m:
            sender = m.group("sender").strip()
            content = m.group("content").strip()
            timestamp = m.group("time").strip()

            if not bidirectional and target and target not in sender:
                continue
            if not content:
                continue

            messages.append({
                "sender": sender,
                "content": content,
                "timestamp": timestamp,
            })

    return messages


def parse_csv(file_path: str, target: str, bidirectional: bool = False) -> list[dict]:
    """解析 CSV 格式的导出文件"""
    messages = []

    try:
        f = open(file_path, "r", encoding="utf-8-sig")
        f.read(1)
        f.seek(0)
    except UnicodeDecodeError:
        f = open(file_path, "r", encoding="gbk", errors="replace")
    with f:
        reader = csv.DictReader(f)
        for row in reader:
            sender = (
                row.get("sender") or row.get("from") or
                row.get("昵称") or row.get("Sender") or row.get("From") or ""
            )
            content = (
                row.get("content") or row.get("text") or
                row.get("Content") or row.get("Text") or
                row.get("message") or row.get("Message") or ""
            )
            timestamp = (
                row.get("timestamp") or row.get("time") or
                row.get("Date") or row.get("date") or ""
            )

            if not bidirectional and target and target not in str(sender):
                continue
            if not content.strip():
                continue

            messages.append({
                "sender": str(sender),
                "content": str(content).strip(),
                "timestamp": str(timestamp),
            })

    return messages


def normalize_timestamp(ts: str) -> str:
    """归一化时间戳为 YYYY-MM-DD HH:MM:SS 格式"""
    if not ts:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", ts):
        return ts
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", ts):
        return ts + ":00"
    ts = ts.replace("/", "-")
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", ts):
        return ts + ":00"
    return ts


def normalize_sender(sender: str, target: str) -> str:
    """归一化发送人为 her/me"""
    if sender in ("me", "我"):
        return "me"
    if target in sender:
        return "her"
    return "me"


def check_sender_mapping(messages: list[dict], target: str):
    """检测 sender 映射是否清晰，不清晰时输出警告"""
    unique_senders = set(msg["sender"] for msg in messages)
    has_wo = "我" in unique_senders or "me" in unique_senders
    has_target = any(target in s for s in unique_senders)

    if len(unique_senders) > 2:
        print(f"⚠️ 检测到 {len(unique_senders)} 个不同的发送人：{unique_senders}", file=sys.stderr)
        print(f"   预期只有 2 个：'我' 和 '{target}'", file=sys.stderr)
        print(f"   请检查输出的 JSON 中 sender 字段是否正确（应只有 'her' 和 'me'）", file=sys.stderr)
    elif not has_wo and not has_target:
        print(f"⚠️ 未检测到 '我'/'me' 或 '{target}'，发送人：{unique_senders}", file=sys.stderr)
        print(f"   请确认聊天记录中的昵称是否正确", file=sys.stderr)


def format_json_output(target: str, messages: list[dict]) -> str:
    """格式化为 JSON 输出，保留双向对话"""
    check_sender_mapping(messages, target)
    output = []
    for msg in messages:
        output.append({
            "sender": normalize_sender(msg["sender"], target),
            "content": msg["content"],
            "timestamp": normalize_timestamp(msg["timestamp"]),
        })
    return json.dumps(output, ensure_ascii=False, indent=2)


def extract_key_content(messages: list[dict]) -> dict:
    """分类提取消息"""
    long_messages = []
    emotional_messages = []
    daily_messages = []

    emotional_keywords = [
        "想你", "爱你", "喜欢", "讨厌", "生气", "难过", "开心",
        "不开心", "对不起", "分手", "在一起", "想见你", "好想",
        "miss", "love", "sorry", "happy", "sad",
    ]

    for msg in messages:
        content = msg["content"]
        if len(content) > 50:
            long_messages.append(msg)
        elif any(kw in content for kw in emotional_keywords):
            emotional_messages.append(msg)
        else:
            daily_messages.append(msg)

    return {
        "long_messages": long_messages,
        "emotional_messages": emotional_messages,
        "daily_messages": daily_messages,
        "total_count": len(messages),
    }


def format_output(target: str, extracted: dict) -> str:
    """格式化输出"""
    lines = [
        f"# iMessage 聊天记录提取结果",
        f"目标人物：{target}",
        f"总消息数：{extracted['total_count']}",
        "",
        "---",
        "",
        "## 长消息（心情/想法类，权重最高）",
        "",
    ]

    for msg in extracted["long_messages"]:
        ts = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
        lines.append(f"{ts}{msg['content']}")
        lines.append("")

    lines += ["---", "", "## 情感类消息", ""]

    for msg in extracted["emotional_messages"]:
        ts = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
        lines.append(f"{ts}{msg['content']}")
        lines.append("")

    lines += ["---", "", "## 日常沟通（风格参考）", ""]

    for msg in extracted["daily_messages"][:200]:
        ts = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
        lines.append(f"{ts}{msg['content']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="解析 iMessage 聊天记录")
    parser.add_argument("--file", help="输入文件路径（.txt / .csv）")
    parser.add_argument("--direct", action="store_true", help="直接读取本机 chat.db")
    parser.add_argument("--target", required=True, help="目标人物（姓名或手机号）")
    parser.add_argument("--output", default=None, help="输出文件路径")
    parser.add_argument("--limit", type=int, default=5000, help="最大消息数（direct 模式）")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="输出格式：md（默认）或 json")
    parser.add_argument("--bidirectional", action="store_true", help="保留双向对话（仅 json 格式时默认开启）")

    args = parser.parse_args()

    bidirectional = args.bidirectional or args.format == "json"

    if args.direct:
        messages = parse_chat_db(args.target, args.limit, bidirectional=bidirectional)
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"错误：文件不存在 {file_path}", file=sys.stderr)
            sys.exit(1)

        if file_path.suffix.lower() == ".csv":
            messages = parse_csv(str(file_path), args.target, bidirectional=bidirectional)
        else:
            messages = parse_txt(str(file_path), args.target, bidirectional=bidirectional)
    else:
        print("错误：需要 --file 或 --direct 参数", file=sys.stderr)
        sys.exit(1)

    if not messages:
        print(f"警告：未找到消息", file=sys.stderr)

    if args.format == "json":
        output = format_json_output(args.target, messages)
    else:
        extracted = extract_key_content(messages)
        output = format_output(args.target, extracted)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"已输出到 {args.output}，共 {len(messages)} 条消息", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
