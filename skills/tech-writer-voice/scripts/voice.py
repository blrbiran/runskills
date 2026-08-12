#!/usr/bin/env python3
"""语体扫描器：给中文技术文稿找「生硬、不像人说话」的嫌疑处。

和 tech-writer-deslop 的 scan.py 是两把不同的尺子，别混：
  scan.py  问「这句话有没有携带只有作者知道的信息」——抓空转。
  voice.py 问「这句话你会这么跟同事说吗」——抓语体。
实测过：一篇被作者判定「看不下去、太生硬」的稿子，scan.py 全绿。
两把尺子正交，所以要各扫各的。

只找嫌疑，不定罪——正则分不清「取决于」是在做严谨限定还是在端着。
退出码恒为 0：诊断工具，不是 CI gate。

用法：
    python3 voice.py FILE [FILE ...]         人读的文本报告
    python3 voice.py FILE --json             机器读的 JSON
    python3 voice.py FILE --max-per-rule 5   每条规则最多列几处（默认 8）
    python3 voice.py OLD NEW --diff          改前改后对账，看指标降了没有
    python3 voice.py FILE --deslop           顺带跑一次 deslop 的密度回归

掩码逻辑（代码块 / 行内代码 / URL / frontmatter 一律不扫）沿用
tech-writer-deslop/scripts/scan.py 的实现，保持行号可跳转。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------

@dataclass
class Rule:
    id: str
    name: str
    pattern: str
    why: str
    fix: str


@dataclass
class Hit:
    rule: Rule
    line: int
    snippet: str


@dataclass
class Report:
    path: str
    body_units: int
    hits: list = field(default_factory=list)
    density: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# 规则表
#
# 每条只收 deslop 抓不到的东西。deslop 已经管了「进行/加以」这类欧化名词化
# （zh-europeanized）和被动滥用（zh-passive），这里不重复收录——同一处被两把
# 尺子各报一次，读报告的人会以为有两个问题。
# --------------------------------------------------------------------------

RULES = [
    Rule(
        id="reg-topicless",
        name="段落没有起点",
        pattern=(
            r"(?m)^(?:\*\*)?(由于|基于|通过|对于|关于|随着|作为|鉴于|"
            r"为了|值得|需要注意|要注意|注意，)"
        ),
        why=(
            "中文口语的句子要先落地再展开。用书面连接词起头，读者找不到"
            "「谁在说、在说什么」，整段悬在空中。\n"
            "  （注意这里只收书面连接词。裸存在句「有两个坑容易踩」在口语里"
            "完全成立，正则分不出它和「有两个维度容易被混为一谈」的差别——"
            "后者难受在成语和被动，不在「有」。存在句该由「无人称段落」那项指标兜。）"
        ),
        fix=(
            "给它一个起点：主语（我/你/我们）、话题词（这里/这套/这一节）"
            "或指示代词。「有两个维度容易被混为一谈」→「这里有两个维度，特别容易混在一起」。"
        ),
    ),
    Rule(
        id="reg-metaphrase",
        name="讲义腔的提示语",
        pattern=(
            r"关键(点)?在于|重点在于|值得(解释|注意|一提|说明|强调)|"
            r"需要(说明|指出|注意|强调)的是|这里(要|需要)(说明|注意|强调)|"
            r"这带来一个|由此带来|不难(看出|发现)|由此可见|综上|众所周知|"
            r"首先要明确|我们不妨|接下来我们(将|来)"
        ),
        why=(
            "这类句子在宣布自己要说话，而不是在说话。它是讲义和论文的过渡装置，"
            "口语里没人这么开口——你不会跟同事说「关键点在于」，你会直接讲那个关键点。"
        ),
        fix="删掉提示语，把后面那句话顶上来。「关键点在于：X 把 A 和 B 拆开了」→「X 干的事就是把 A 和 B 拆开」。",
    ),
    Rule(
        id="reg-doc-voice",
        name="文档自称与指代",
        # 「下文」要挡住「上下文」——技术文里「上下文窗口」出现得比「下文」多得多，
        # 不挡的话每篇稿子都会白报好几处。
        pattern=(r"本文|本节|本篇|本小节|上文|(?<!上)下文|上述|如下所示|下表所示|"
                 r"笔者|业界|该字段|该文件|该参数|该方法"),
        why=(
            "「本文」「上述」「笔者」是写给评审看的措辞，暴露的是"
            "「我在交一份文档」而不是「我在跟你讲一件事」。「业界」尤其空——"
            "它通常可以直接删掉而不损失任何信息。"
        ),
        fix="「本文」→「这篇」或直接删；「上述」→「上面那个」；「笔者」→「我」；「业界目前有三种」→「眼下主流的就三种」。",
    ),
    Rule(
        id="reg-formal-word",
        name="书面动词与虚词",
        pattern=(
            r"在于|取决于|旨在|以[^，。]{1,12}为准|即可(?![能])|无需|"
            r"(?<![必务])须(?!臾)|应予|较为|颇为|尚未|亦|"
            r"之(?=[一二三四五六七八九十])|予以|得以|从而使|使之"
        ),
        # 「必须」「其中」是正常口语，早期版本用 `须` 和 `其(?=中)` 扫出一片假阳性，
        # 一篇稿子里 11 处 reg-formal-word 有 5 处是「必须」。定语要留住。
        why=(
            "这些词单看都没错，但它们成批出现的时候，文章的口型就变了——"
            "从「跟你说」变成「兹通知」。技术文尤其容易染上，因为文档模板都长这样。"
        ),
        fix="「取决于 X」→「看 X」「要看 X」；「即可」→「就行」；「无需」→「不用」；「较为」→「比较」；「以 X 为准」→「你看 X」。",
    ),
    Rule(
        id="reg-nominal-side",
        name="把「侧/方面/层面」当名词用",
        pattern=r"[一-龥A-Za-z]{1,8}侧(?![面重])|[^，。]{2,10}方面(?![军])|[^，。]{2,10}层面",
        why=(
            "「网关侧」「客户端侧」是画架构图时的切分词，不是开口说话的词。"
            "作者点名说过这类词读着别扭。"
        ),
        fix="「网关侧是我自己在用的」→「网关这部分我自己一直在用」；「在性能方面」→「说性能的话」或直接删。",
    ),
    Rule(
        id="reg-idiom",
        name="四字成语",
        pattern=(
            r"混为一谈|一目了然|不言而喻|显而易见|大同小异|无独有偶|"
            r"行之有效|至关重要|不失为|应运而生|层出不穷|屡见不鲜|"
            r"一劳永逸|事半功倍|水到渠成|一蹴而就"
        ),
        why=(
            "成语是压缩过的书面表达，念出来有背诵感。口语里同样的意思会说得散一点、"
            "也更准一点——「混为一谈」和「混在一起」的区别就是背课文和说话的区别。"
        ),
        fix="拆成大白话：「混为一谈」→「混在一起」；「至关重要」→「特别要紧」或说清到底怎么要紧。",
    ),
]


# --------------------------------------------------------------------------
# 掩码（沿用 deslop scan.py 的实现，保证行号可跳转）
# --------------------------------------------------------------------------

FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
URL_RE = re.compile(r"https?://\S+")
LINK_TARGET_RE = re.compile(r"\]\([^)\s]+\)")
CJK_RE = re.compile(r"[一-鿿]")


def _blank(m: re.Match) -> str:
    return " " * (m.end() - m.start())


def mask_noncontent(text: str) -> str:
    """把非正文内容换成等长空格。行数和每行长度必须与输入完全相同。"""
    lines = text.split("\n")
    out = []
    in_frontmatter = False
    in_fence = False
    fence_marker = ""

    for idx, line in enumerate(lines):
        stripped = line.strip()

        if idx == 0 and stripped == "---":
            in_frontmatter = True
            out.append(" " * len(line))
            continue
        if in_frontmatter:
            if stripped in ("---", "..."):
                in_frontmatter = False
            out.append(" " * len(line))
            continue

        m = FENCE_RE.match(line)
        if m:
            marker = m.group(2)
            if not in_fence:
                in_fence, fence_marker = True, marker
                out.append(" " * len(line))
                continue
            if marker == fence_marker:
                in_fence = False
                out.append(" " * len(line))
                continue
        if in_fence:
            out.append(" " * len(line))
            continue

        masked = INLINE_CODE_RE.sub(_blank, line)
        masked = URL_RE.sub(_blank, masked)
        masked = LINK_TARGET_RE.sub(_blank, masked)
        out.append(masked)

    return "\n".join(out)


def is_structural(line: str) -> bool:
    """标题、表格、四空格代码块——不参与段落级统计。"""
    s = line.strip()
    if not s:
        return True
    if s.startswith("#") or s.startswith("|") or s.startswith("---"):
        return True
    if line.startswith("    ") and not s.startswith(("-", "*", "+", ">", "|")):
        return True
    return False


# --------------------------------------------------------------------------
# 语体指标
#
# 阈值来自实测：拿同一篇技术文的「作者判定生硬」版和「作者认可」版对照标定，
# 取两版之间、偏向认可版的一侧。它们是提示线不是及格线，见 SKILL.md「过线即停」。
# --------------------------------------------------------------------------

DENSITY_LIMITS = {
    "impersonal_para_ratio": (
        55.0, "无人称段落", "%",
        "整段不出现「你/我/我们」，读起来就是说明书。技术文不可能段段有人称，"
        "但过半没有，全文的口型就固定成了「兹说明」。\n"
        "     这是四项里最灵的一项：同一篇稿子，作者判定「看不下去」的版本是 76.5% 和 59.5%，"
        "改到作者认可是 48.6% 和 40.0%。别的指标都没这么大动静。",
    ),
    "long_sentence_ratio": (
        32.0, "长句（>30 字）", "%",
        "长句本身不是错，成堆才是。口语的节奏是长短交替；长句连着长句，"
        "读者得在心里断句，那份费力就是「生硬」的实感来源。\n"
        "     这项是弱信号（实测改前改后只差 4 个百分点），别指望它报警，"
        "它超标的时候通常问题已经很明显了。",
    ),
    "formal_hits": (
        3.5, "书面腔命中合计", "/千字",
        "逐条看每个词都站得住，成批出现才暴露口型。这一项超标时先看命中最多的那条规则。",
    ),
}


SENT_SPLIT_RE = re.compile(r"[。！？；\n]")
PERSON_RE = re.compile(r"[你我]|咱们|我们|你们")


def paragraphs(masked: str) -> list:
    """按空行切段，丢掉标题/表格/代码行。返回 [(起始行号, 文本)]。"""
    out, cur, start = [], [], 0
    for i, line in enumerate(masked.split("\n"), 1):
        if is_structural(line):
            if cur:
                out.append((start, " ".join(cur)))
                cur = []
            continue
        if not cur:
            start = i
        cur.append(line.strip())
    if cur:
        out.append((start, " ".join(cur)))
    return [(s, t) for s, t in out if len(CJK_RE.findall(t)) >= 10]


def compute_density(masked: str, units: int) -> dict:
    paras = paragraphs(masked)
    per_k = lambda n: (n / units * 1000) if units else 0.0

    impersonal = sum(1 for _, t in paras if not PERSON_RE.search(t))
    para_ratio = (impersonal / len(paras) * 100) if paras else 0.0

    sents = [s for s in SENT_SPLIT_RE.split(" ".join(t for _, t in paras))
             if len(CJK_RE.findall(s)) >= 4]
    longs = sum(1 for s in sents if len(CJK_RE.findall(s)) > 30)
    long_ratio = (longs / len(sents) * 100) if sents else 0.0

    # 早期版本还统计过「的」字密度，实测改前改后是 29.1→28.6 和 34.2→33.7，
    # 基本不动——它量的是题材不是语体，留着只会让报告变长，已经删掉。

    return {
        "impersonal_para_ratio": (para_ratio, impersonal, len(paras)),
        "long_sentence_ratio": (long_ratio, longs, len(sents)),
        "formal_hits": (0.0, 0, units),  # 扫完规则后回填
    }


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------

def scan_text(text: str, path: str) -> Report:
    masked = mask_noncontent(text)
    units = len(CJK_RE.findall(masked))
    rep = Report(path=path, body_units=units)

    lines = masked.split("\n")
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    def line_of(idx: int) -> int:
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if offsets[mid] <= idx:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for rule in RULES:
        for m in re.finditer(rule.pattern, masked):
            ln = line_of(m.start())
            raw = lines[ln - 1]
            col = m.start() - offsets[ln - 1]
            snip = raw[max(0, col - 12): col + len(m.group(0)) + 20].strip()
            rep.hits.append(Hit(rule=rule, line=ln, snippet=snip))

    rep.density = compute_density(masked, units)
    total = len(rep.hits)
    rep.density["formal_hits"] = (
        (total / units * 1000) if units else 0.0, total, units)
    return rep


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def render(rep: Report, max_per_rule: int = 8) -> str:
    L = []
    L.append("=" * 72)
    L.append(f"文件  {rep.path}")
    L.append(f"正文  {rep.body_units:,} 字（已排除代码块 / 行内代码 / URL / frontmatter）")
    L.append("=" * 72)

    L.append("\n【语体指标】")
    for key, (limit, name, unit, why) in DENSITY_LIMITS.items():
        val, n, tot = rep.density[key]
        flag = "⚠ 偏高" if val > limit else "ok"
        detail = f"{n}/{tot}" if unit == "%" else f"{n} 处"
        L.append(f"  {name:<16}{detail:>12}{val:>8.1f}{unit:<6}上限 {limit:<6}{flag}")
    over = [k for k in DENSITY_LIMITS if rep.density[k][0] > DENSITY_LIMITS[k][0]]
    for key in over:
        L.append(f"\n  ⚠ {DENSITY_LIMITS[key][1]}：{DENSITY_LIMITS[key][3]}")

    by_rule = {}
    for h in rep.hits:
        by_rule.setdefault(h.rule.id, []).append(h)

    L.append(f"\n【逐条命中】共 {len(rep.hits)} 处")
    if not rep.hits:
        L.append("  无")
    for rid, hits in sorted(by_rule.items(), key=lambda kv: -len(kv[1])):
        r = hits[0].rule
        L.append(f"\n■ {r.name} — {len(hits)} 处")
        L.append(f"  为什么：{r.why}")
        L.append(f"  怎么改：{r.fix}")
        for h in hits[:max_per_rule]:
            L.append(f"    L{h.line:<5}  {h.snippet}")
        if len(hits) > max_per_rule:
            L.append(f"    …还有 {len(hits) - max_per_rule} 处")

    L.append("\n提示：命中不等于该改。技术术语、严谨限定、全文统一的约定说法都可能"
             "合法地命中——定罪是你的活，不是正则的。")
    return "\n".join(L)


def to_dict(rep: Report) -> dict:
    return {
        "path": rep.path,
        "body_units": rep.body_units,
        "density": {k: {"value": round(v[0], 2), "count": v[1], "total": v[2],
                        "limit": DENSITY_LIMITS[k][0],
                        "over": v[0] > DENSITY_LIMITS[k][0]}
                    for k, v in rep.density.items()},
        "summary": {"total_hits": len(rep.hits),
                    "by_rule": {rid: sum(1 for h in rep.hits if h.rule.id == rid)
                                for rid in {h.rule.id for h in rep.hits}}},
        "hits": [{"rule": h.rule.id, "line": h.line, "snippet": h.snippet}
                 for h in rep.hits],
    }


def render_diff(old: Report, new: Report) -> str:
    """改前改后对账。「我改过了」和「指标真的降下来了」是两回事。"""
    L = ["=" * 72, f"对账  {old.path}  →  {new.path}", "=" * 72, ""]
    L.append(f"  {'指标':<18}{'改前':>10}{'改后':>10}{'变化':>10}   上限")
    for key, (limit, name, unit, _) in DENSITY_LIMITS.items():
        o, n = old.density[key][0], new.density[key][0]
        arrow = "↓" if n < o else ("↑" if n > o else "=")
        warn = "  ⚠ 仍超标" if n > limit else ("  ⚠ 改后才超标" if o <= limit < n else "")
        L.append(f"  {name:<18}{o:>10.1f}{n:>10.1f}{arrow + f'{n - o:+.1f}':>10}   {limit}{warn}")
    L.append(f"\n  {'命中总数':<18}{len(old.hits):>10}{len(new.hits):>10}"
             f"{len(new.hits) - len(old.hits):>+10}")
    rules_o = {r.id: sum(1 for h in old.hits if h.rule.id == r.id) for r in RULES}
    rules_n = {r.id: sum(1 for h in new.hits if h.rule.id == r.id) for r in RULES}
    L.append("")
    for r in RULES:
        if rules_o[r.id] or rules_n[r.id]:
            L.append(f"    {r.name:<20}{rules_o[r.id]:>6}{rules_n[r.id]:>8}"
                     f"{rules_n[r.id] - rules_o[r.id]:>+8}")
    return "\n".join(L)


# --------------------------------------------------------------------------
# deslop 密度回归
#
# 为什么要串这一步：口语化会系统性地制造 deslop 要抓的排版病。实测过一次——
# 把长句改写成「主句——补充」之后读着确实像说话了，但破折号从 1.1/千字
# 冲到 3.3，越过 deslop 的 2.5 线。一个 skill 检查不了自己刚制造的问题。
# --------------------------------------------------------------------------

DESLOP_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "tech-writer-deslop" / "scripts" / "scan.py",
    Path.home() / ".claude" / "skills" / "tech-writer-deslop" / "scripts" / "scan.py",
]


def find_deslop(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None
    for c in DESLOP_CANDIDATES:
        if c.exists():
            return c
    return None


def run_deslop(scan_py: Path, files: list) -> str:
    L = ["", "=" * 72, "【deslop 密度回归】口语化最容易顶上去的是破折号和加粗", "=" * 72]
    for f in files:
        try:
            out = subprocess.run(
                [sys.executable, str(scan_py), f, "--json"],
                capture_output=True, text=True, timeout=60)
            d = json.loads(out.stdout)
            # scan.py --json 顶层是列表（一个文件一项），这里一次只喂一个文件
            entry = d[0] if isinstance(d, list) else d
        except Exception as e:                                  # noqa: BLE001
            L.append(f"  {f}: 跑不起来（{e}）")
            continue
        dens = entry.get("density", {})
        over = [(k, v) for k, v in dens.items()
                if isinstance(v, dict) and v.get("over")]
        L.append(f"\n  {f}")
        if not over:
            L.append("    密度项全部在线内")
        for k, v in over:
            L.append(f"    ⚠ {v.get('label', k)}：{v.get('value')}{v.get('unit', '')}"
                     f" > 上限 {v.get('limit')}")
            L.append(f"       {v.get('why', '')}")
    return "\n".join(L)


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="语体扫描：找中文技术文稿里「不像人说话」的地方")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--max-per-rule", type=int, default=8)
    ap.add_argument("--diff", action="store_true",
                    help="两个文件对账：voice.py OLD NEW --diff")
    ap.add_argument("--deslop", nargs="?", const="", default=None,
                    help="顺带跑 deslop 密度回归；可跟 scan.py 路径")
    args = ap.parse_args(argv)

    reports = []
    for f in args.files:
        try:
            text = Path(f).read_text(encoding="utf-8")
        except OSError as e:
            print(f"读不了 {f}: {e}", file=sys.stderr)
            return 0
        reports.append(scan_text(text, f))

    if args.diff:
        if len(reports) != 2:
            print("--diff 需要正好两个文件：OLD NEW", file=sys.stderr)
            return 0
        print(render_diff(reports[0], reports[1]))
    elif args.json:
        print(json.dumps([to_dict(r) for r in reports],
                         ensure_ascii=False, indent=2))
    else:
        for r in reports:
            print(render(r, args.max_per_rule))
            print()

    if args.deslop is not None:
        scan_py = find_deslop(args.deslop or None)
        if scan_py:
            print(run_deslop(scan_py, args.files))
        else:
            print("\n找不到 deslop 的 scan.py，跳过密度回归。"
                  "用 --deslop /path/to/scan.py 显式指定。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
