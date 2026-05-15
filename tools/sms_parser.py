#!/usr/bin/env python3
"""
短信解析器

支持格式：
1. Android SMS Backup & Restore 导出的 XML
2. CSV 格式导出
3. 纯文本格式

用法：
    python sms_parser.py --file sms_backup.xml --target "+8613800138000" --output output.txt
    python sms_parser.py --file sms.csv --target "小美" --output output.txt
"""

import re
import csv
import sys
import json
import argparse
from pathlib import Path
from xml.etree import ElementTree
from datetime import datetime, timezone


def parse_sms_xml(file_path: str, target: str, bidirectional: bool = False) -> list[dict]:
    """解析 Android SMS Backup & Restore 导出的 XML"""
    messages = []

    try:
        tree = ElementTree.parse(file_path)
        root = tree.getroot()
    except ElementTree.ParseError as e:
        print(f"错误：XML 解析失败: {e}", file=sys.stderr)
        return []

    for sms in root.iter("sms"):
        address = sms.get("address", "")
        body = sms.get("body", "")
        date_ms = sms.get("date", "")
        msg_type = sms.get("type", "")  # 1=received, 2=sent

        # 双向模式保留所有消息，否则只保留接收的
        if not bidirectional and msg_type != "1":
            continue

        if not bidirectional and target and target not in address:
            contact = sms.get("contact_name", "")
            if target not in contact:
                continue

        if not body.strip():
            continue

        timestamp = ""
        if date_ms:
            try:
                ts = int(date_ms) / 1000
                timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                pass

        # 双向模式下根据 type 判断发送人
        sender = sms.get("contact_name", address)
        if bidirectional and msg_type == "2":
            sender = "me"

        messages.append({
            "sender": sender,
            "content": body.strip(),
            "timestamp": timestamp,
        })

    return messages


def parse_sms_csv(file_path: str, target: str, bidirectional: bool = False) -> list[dict]:
    """解析 CSV 格式的短信导出"""
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
                row.get("昵称") or row.get("address") or row.get("number") or ""
            )
            content = (
                row.get("content") or row.get("body") or
                row.get("text") or row.get("message") or ""
            )
            timestamp = (
                row.get("timestamp") or row.get("date") or
                row.get("time") or ""
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


def parse_sms_txt(file_path: str, target: str, bidirectional: bool = False) -> list[dict]:
    """解析纯文本格式的短信记录"""
    messages = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="gbk", errors="replace") as f:
            lines = f.readlines()

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
        "不开心", "对不起", "分手", "在一起", "想见你",
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
        f"# 短信记录提取结果",
        f"目标人物：{target}",
        f"总消息数：{extracted['total_count']}",
        "",
        "---",
        "",
        "## 长消息（权重最高）",
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

    for msg in extracted["daily_messages"][:100]:
        ts = f"[{msg['timestamp']}] " if msg["timestamp"] else ""
        lines.append(f"{ts}{msg['content']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="解析短信导出文件")
    parser.add_argument("--file", required=True, help="输入文件路径（.xml / .csv / .txt）")
    parser.add_argument("--target", required=True, help="目标人物（手机号或姓名）")
    parser.add_argument("--output", default=None, help="输出文件路径")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="输出格式：md（默认）或 json")
    parser.add_argument("--bidirectional", action="store_true", help="保留双向对话（仅 json 格式时默认开启）")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"错误：文件不存在 {file_path}", file=sys.stderr)
        sys.exit(1)

    bidirectional = args.bidirectional or args.format == "json"
    suffix = file_path.suffix.lower()

    if suffix == ".xml":
        messages = parse_sms_xml(str(file_path), args.target, bidirectional=bidirectional)
    elif suffix == ".csv":
        messages = parse_sms_csv(str(file_path), args.target, bidirectional=bidirectional)
    else:
        messages = parse_sms_txt(str(file_path), args.target, bidirectional=bidirectional)

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
