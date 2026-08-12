#!/usr/bin/env python3
"""技术保真检查：确认语体改写没有顺手改掉技术内容。

语体改写最大的风险不是改不动，是**改的时候顺手改掉事实**。一个被「改得更通顺」
的命令行参数，读者照着敲会失败，而这个错误由作者署名承担。这类错误肉眼极难发现，
所以每次改完都跑一遍——不是不信任你，是这种错误的代价不对称。

用法：
    python3 fidelity.py 改前.md 改后.md
    python3 fidelity.py 改前.md 改后.md --json

退出码：全 PASS 返回 0，有 FAIL 返回 1（可以挂进 CI 或 pre-commit）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
URL_RE = re.compile(r"https?://[^\s)\]<>，。；]+")
# 版本号、端口、日期、纯数字量：语体改写不该动到任何一个
NUM_RE = re.compile(r"\bv?\d+(?:\.\d+)+(?:-[a-z0-9.]+)?\b|\b\d{4}-\d{2}-\d{2}\b")


def code_blocks(text: str) -> list:
    """按出现顺序返回围栏代码块内容（不含围栏行本身）。"""
    out, cur, in_fence, marker = [], [], False, ""
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence, marker, cur = True, m.group(2), []
                continue
            if m.group(2) == marker:
                in_fence = False
                out.append("\n".join(cur))
                continue
        if in_fence:
            cur.append(line)
    return out


def strip_code(text: str) -> str:
    """去掉围栏代码块，留下散文（用来采集散文里的行内 code）。"""
    out, in_fence, marker = [], False, ""
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence, marker = True, m.group(2)
            elif m.group(2) == marker:
                in_fence = False
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def check(old_path: str, new_path: str) -> tuple:
    old = Path(old_path).read_text(encoding="utf-8")
    new = Path(new_path).read_text(encoding="utf-8")
    results = []

    def add(name, ok, detail=""):
        results.append({"check": name, "passed": ok, "detail": detail})

    # 1. 代码块逐字节
    bo, bn = code_blocks(old), code_blocks(new)
    if len(bo) != len(bn):
        add("代码块数量", False, f"{len(bo)} → {len(bn)}，块被增删了")
    else:
        bad = [i for i, (a, b) in enumerate(zip(bo, bn)) if a != b]
        add("代码块逐字节保真",
            not bad,
            f"{len(bn)} 块全部一致" if not bad else f"第 {bad} 块被改动")

    # 2. 散文里的行内 code：改后不该出现改前没有的标识符
    #    （反过来允许——语体改写可以删掉一句带 code 的话）
    io = set(INLINE_CODE_RE.findall(strip_code(old)))
    inn = set(INLINE_CODE_RE.findall(strip_code(new)))
    # 只在代码块里出现过的标识符，第一次写进散文是正常的，不算新增
    in_blocks = "\n".join(bn)
    novel = sorted(c for c in (inn - io) if c not in in_blocks)
    add("散文行内 code 无凭空新增", not novel,
        "无" if not novel else f"改后多出：{novel}")

    # 3. URL
    uo, un = set(URL_RE.findall(old)), set(URL_RE.findall(new))
    lost, gained = sorted(uo - un), sorted(un - uo)
    add("URL 未被改写", not gained,
        "无新增" if not gained else f"改后出现未见过的 URL：{gained}")
    if lost:
        add("URL 有减少（删段落时正常，确认一下）", True, f"改后不再出现：{lost}")

    # 4. 版本号 / 日期
    no, nn = set(NUM_RE.findall(old)), set(NUM_RE.findall(new))
    changed = sorted(nn - no)
    add("版本号/日期无凭空新增", not changed,
        "无" if not changed else f"改后出现未见过的：{changed}")

    ok = all(r["passed"] for r in results)
    return ok, results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="语体改写的技术保真检查")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        ok, results = check(a.old, a.new)
    except OSError as e:
        print(f"读不了文件：{e}", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps({"passed": ok, "checks": results},
                         ensure_ascii=False, indent=2))
    else:
        print(f"技术保真：{a.old}  →  {a.new}")
        for r in results:
            print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['check']}"
                  f"{'：' + r['detail'] if r['detail'] else ''}")
        print(f"\n结果：{'PASS' if ok else 'FAIL —— 改坏了技术内容，修完重跑'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
