#!/usr/bin/env python3
"""
事件聚类工具

将聊天记录按时间分段，配合 Claude 提取事件，存入事件数据库。
支持增量追加：新事件自动检测是否为已有事件的续集。

用法：
    # 将消息分段（供 Claude 逐段分析）
    python event_clusterer.py segment --input messages.json --output /tmp/windows.json

    # 将 Claude 提取的事件合并到数据库
    python event_clusterer.py merge --events new_events.json --base-dir ./exes/xiao-mei

    # 列出已有事件
    python event_clusterer.py list --base-dir ./exes/xiao-mei

    # 导出事件摘要（供 Claude 做续集检测时参考）
    python event_clusterer.py summary --base-dir ./exes/xiao-mei
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta


def load_messages(input_path: str) -> list[dict]:
    """加载解析器输出的 JSON 消息"""
    with open(input_path, "r", encoding="utf-8") as f:
        messages = json.load(f)

    # 按时间排序
    def sort_key(msg):
        ts = msg.get("timestamp", "")
        if not ts:
            return ""
        return ts

    messages.sort(key=sort_key)
    return messages


def segment_messages(messages: list[dict], gap_hours: float = 2.0, min_messages: int = 5) -> list[dict]:
    """
    将消息按时间分段。

    分段逻辑：
    - 两条消息间隔 > gap_hours 小时 → 新段
    - 日期变化且间隔 > 1 小时 → 新段
    - 每段最多 150 条消息（防止过长）
    - 分段后，消息数 < min_messages 的小段合并到前一段

    返回：[{"window_id": 0, "start": "...", "end": "...", "messages": [...]}]
    """
    if not messages:
        return []

    windows = []
    current_window = []
    gap = timedelta(hours=gap_hours)

    for i, msg in enumerate(messages):
        if not current_window:
            current_window.append(msg)
            continue

        prev_ts = current_window[-1].get("timestamp", "")
        curr_ts = msg.get("timestamp", "")

        if not prev_ts or not curr_ts:
            current_window.append(msg)
            continue

        try:
            prev_dt = datetime.strptime(prev_ts[:19], "%Y-%m-%d %H:%M:%S")
            curr_dt = datetime.strptime(curr_ts[:19], "%Y-%m-%d %H:%M:%S")
            diff = curr_dt - prev_dt

            # 检查是否需要分段
            should_split = False
            if diff > gap:
                should_split = True
            elif diff > timedelta(hours=1) and prev_dt.date() != curr_dt.date():
                should_split = True
            elif len(current_window) >= 150:
                should_split = True

            if should_split:
                windows.append(current_window)
                current_window = [msg]
            else:
                current_window.append(msg)
        except ValueError:
            current_window.append(msg)

    if current_window:
        windows.append(current_window)

    # 合并小窗口到前一个窗口
    if min_messages > 1 and len(windows) > 1:
        merged = [windows[0]]
        for w in windows[1:]:
            if len(w) < min_messages:
                merged[-1].extend(w)
            else:
                merged.append(w)
        windows = merged

    # 格式化输出
    result = []
    for i, window in enumerate(windows):
        start_ts = window[0].get("timestamp", "")
        end_ts = window[-1].get("timestamp", "")
        result.append({
            "window_id": i,
            "start": start_ts,
            "end": end_ts,
            "message_count": len(window),
            "messages": window,
        })

    return result


def load_events(base_dir: str) -> list[dict]:
    """加载已有事件数据库"""
    events_path = Path(base_dir) / "events.json"
    if not events_path.exists():
        return []
    with open(events_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"警告：events.json 内容不是列表（类型：{type(data).__name__}），返回空列表", file=sys.stderr)
        return []

    valid = []
    for i, evt in enumerate(data):
        if not isinstance(evt, dict):
            print(f"警告：events.json 第 {i} 条不是字典，已跳过", file=sys.stderr)
            continue
        if "id" not in evt:
            print(f"警告：events.json 第 {i} 条缺少 \"id\" 字段，已跳过", file=sys.stderr)
            continue
        valid.append(evt)

    if len(valid) < len(data):
        print(f"警告：{len(data) - len(valid)} 条无效事件被跳过", file=sys.stderr)

    return valid


def save_events(base_dir: str, events: list[dict]):
    """保存事件数据库"""
    events_path = Path(base_dir) / "events.json"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def generate_event_summary(events: list[dict]) -> str:
    """生成事件摘要，供 Claude 做续集检测时参考"""
    if not events:
        return "暂无已有事件。"

    lines = ["已有事件摘要：", ""]
    for evt in events:
        eid = evt.get("id", "?")
        title = evt.get("title", "未知")
        tr = evt.get("time_range", {})
        start = tr.get("start", "?")
        end = tr.get("end", "?")
        tags = ", ".join(evt.get("tags", []))
        related = ", ".join(evt.get("related_events", []))
        summary = evt.get("what_happened", "")[:80]

        lines.append(f"[{eid}] {title}")
        lines.append(f"  时间：{start} ~ {end}")
        lines.append(f"  摘要：{summary}")
        if tags:
            lines.append(f"  标签：{tags}")
        if related:
            lines.append(f"  关联：{related}")
        lines.append("")

    return "\n".join(lines)


def merge_events(existing: list[dict], new_events: list[dict]) -> tuple[list[dict], int]:
    """
    合并新事件到已有事件列表。

    规则：
    - new_events 中如果有 id 与已有事件相同 → 更新已有事件（追加 timeline/details）
    - 如果 id 不存在 → 新增事件

    返回：(合并后的事件列表, 被更新的事件数量)
    """
    existing_map = {evt["id"]: evt for evt in existing}
    merge_count = 0

    for new_evt in new_events:
        eid = new_evt.get("id", "")

        if eid in existing_map:
            merge_count += 1
            # 合并：追加 timeline 和 important_details
            old = existing_map[eid]

            # 合并 timeline（去重）
            old_times = {(t.get("time", ""), t.get("detail", "")) for t in old.get("timeline", [])}
            for item in new_evt.get("timeline", []):
                key = (item.get("time", ""), item.get("detail", ""))
                if key not in old_times:
                    old.setdefault("timeline", []).append(item)

            # 合并 important_details（去重）
            old_details = set(old.get("important_details", []))
            for detail in new_evt.get("important_details", []):
                if detail not in old_details:
                    old.setdefault("important_details", []).append(detail)

            # 合并 sensory（去重）
            old_sensory = set(old.get("sensory", []))
            for s in new_evt.get("sensory", []):
                if s not in old_sensory:
                    old.setdefault("sensory", []).append(s)

            # 更新 what_happened（如果新的更长）
            new_desc = new_evt.get("what_happened", "")
            old_desc = old.get("what_happened", "")
            if len(new_desc) > len(old_desc):
                old["what_happened"] = new_desc

            # 更新 emotional（如果新的更长）
            new_emo = new_evt.get("emotional", "")
            old_emo = old.get("emotional", "")
            if len(new_emo) > len(old_emo):
                old["emotional"] = new_emo

            # 合并 related_events（去重）
            old_related = set(old.get("related_events", []))
            for r in new_evt.get("related_events", []):
                if r not in old_related and r != eid:
                    old.setdefault("related_events", []).append(r)

            # 合并 tags（去重）
            old_tags = set(old.get("tags", []))
            for t in new_evt.get("tags", []):
                if t not in old_tags:
                    old.setdefault("tags", []).append(t)

            # 合并 source_messages（去重）
            old_sources = set(old.get("source_messages", []))
            for s in new_evt.get("source_messages", []):
                if s not in old_sources:
                    old.setdefault("source_messages", []).append(s)

            # 更新 time_range
            new_start = new_evt.get("time_range", {}).get("start", "")
            new_end = new_evt.get("time_range", {}).get("end", "")
            if new_start and new_start < old.get("time_range", {}).get("start", "z"):
                old["time_range"]["start"] = new_start
            if new_end and new_end > old.get("time_range", {}).get("end", ""):
                old["time_range"]["end"] = new_end

        else:
            # 新增事件
            existing_map[eid] = new_evt

    # 按时间排序
    result = list(existing_map.values())
    result.sort(key=lambda e: e.get("time_range", {}).get("start", ""))

    # 保持已有事件 id 不变，只给新事件分配 id
    existing_ids = {evt["id"] for evt in existing}
    max_num = 0
    for eid in existing_ids:
        if eid.startswith("evt_"):
            try:
                max_num = max(max_num, int(eid[4:]))
            except ValueError:
                pass

    for evt in result:
        if evt["id"] not in existing_ids:
            max_num += 1
            evt["id"] = f"evt_{max_num:03d}"

    return result, merge_count


def do_segment(args):
    """执行分段"""
    messages = load_messages(args.input)
    windows = segment_messages(messages, gap_hours=args.gap_hours, min_messages=args.min_messages)

    output = {
        "total_messages": len(messages),
        "total_windows": len(windows),
        "windows": windows,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"已分段：{len(messages)} 条消息 → {len(windows)} 个窗口，输出到 {args.output}", file=sys.stderr)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


def do_merge(args):
    """执行事件合并"""
    # 加载新事件
    with open(args.events, "r", encoding="utf-8") as f:
        new_events = json.load(f)

    # 确保是列表
    if isinstance(new_events, dict):
        new_events = [new_events]

    existing = load_events(args.base_dir)
    merged, updated_count = merge_events(existing, new_events)
    save_events(args.base_dir, merged)

    new_count = len(merged) - len(existing)
    print(f"合并完成：新增 {new_count} 个事件，更新 {updated_count} 个事件，共 {len(merged)} 个事件", file=sys.stderr)


def do_list(args):
    """列出已有事件"""
    events = load_events(args.base_dir)
    if not events:
        print("暂无事件。", file=sys.stderr)
        return

    print(f"共 {len(events)} 个事件：\n")
    for evt in events:
        eid = evt.get("id", "?")
        title = evt.get("title", "未知")
        tr = evt.get("time_range", {})
        start = tr.get("start", "?")
        end = tr.get("end", "?")
        tags = ", ".join(evt.get("tags", []))
        detail_count = len(evt.get("important_details", []))
        timeline_count = len(evt.get("timeline", []))

        print(f"  [{eid}] {title}")
        print(f"    {start} ~ {end}")
        print(f"    {timeline_count} 个时间点, {detail_count} 个细节")
        if tags:
            print(f"    标签：{tags}")
        related = evt.get("related_events", [])
        if related:
            print(f"    关联事件：{', '.join(related)}")
        print()


def do_summary(args):
    """导出事件摘要"""
    events = load_events(args.base_dir)
    summary = generate_event_summary(events)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(summary)
        print(f"摘要已输出到 {args.output}", file=sys.stderr)
    else:
        print(summary)


def do_density(args):
    """检查事件密度：事件数 / 窗口数"""
    events = load_events(args.base_dir)
    event_count = len(events)

    with open(args.windows, "r", encoding="utf-8") as f:
        windows_data = json.load(f)
    window_count = windows_data.get("total_windows", len(windows_data.get("windows", [])))

    if window_count == 0:
        print("无窗口数据", file=sys.stderr)
        return

    density = event_count / window_count

    print(f"窗口数：{window_count}")
    print(f"事件数：{event_count}")
    print(f"事件密度：{density:.2f} 事件/窗口")

    if density < 1.0:
        print(f"\n⚠️ 事件密度过低！每个窗口平均不到 1 个事件。", file=sys.stderr)
        print(f"建议：", file=sys.stderr)
        print(f"  1. 检查事件提取是否过于保守（每个窗口应提取所有可识别事件）", file=sys.stderr)
        print(f"  2. 考虑减小 --gap-hours 让窗口更聚焦", file=sys.stderr)
    elif density < 1.5:
        print(f"\n⚠️ 事件密度偏低。", file=sys.stderr)
        print(f"建议：检查是否有窗口遗漏了事件", file=sys.stderr)
    else:
        print(f"\n✅ 事件密度正常。")


def main():
    parser = argparse.ArgumentParser(description="事件聚类工具")
    subparsers = parser.add_subparsers(dest="action", help="操作")

    # segment 子命令
    seg_parser = subparsers.add_parser("segment", help="将消息按时间分段")
    seg_parser.add_argument("--input", required=True, help="消息 JSON 文件路径")
    seg_parser.add_argument("--output", default=None, help="输出文件路径")
    seg_parser.add_argument("--gap-hours", type=float, default=2.0, help="分段间隔（小时，默认 2）")
    seg_parser.add_argument("--min-messages", type=int, default=5, help="最小窗口消息数，不足则合并到前一个窗口（默认 5）")

    # merge 子命令
    merge_parser = subparsers.add_parser("merge", help="将新事件合并到数据库")
    merge_parser.add_argument("--events", required=True, help="新事件 JSON 文件路径")
    merge_parser.add_argument("--base-dir", required=True, help="事件数据库目录")

    # list 子命令
    list_parser = subparsers.add_parser("list", help="列出已有事件")
    list_parser.add_argument("--base-dir", required=True, help="事件数据库目录")

    # summary 子命令
    summary_parser = subparsers.add_parser("summary", help="导出事件摘要")
    summary_parser.add_argument("--base-dir", required=True, help="事件数据库目录")
    summary_parser.add_argument("--output", default=None, help="输出文件路径")

    # density 子命令
    density_parser = subparsers.add_parser("density", help="检查事件密度")
    density_parser.add_argument("--windows", required=True, help="windows.json 文件路径")
    density_parser.add_argument("--base-dir", required=True, help="事件数据库目录")

    args = parser.parse_args()

    if args.action == "segment":
        do_segment(args)
    elif args.action == "merge":
        do_merge(args)
    elif args.action == "list":
        do_list(args)
    elif args.action == "summary":
        do_summary(args)
    elif args.action == "density":
        do_density(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
