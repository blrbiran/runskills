#!/usr/bin/env python3
"""deslop 扫描器：给 Markdown 文稿找 AI 味的嫌疑处，并统计排版密度。

只找嫌疑，不定罪——正则区分不了「作者在划类比边界」和「假反转」，
所以输出永远是候选清单，判断交给读清单的人或模型。
因此退出码恒为 0：它是诊断工具，不是 CI gate。

用法：
    python3 scan.py FILE [FILE ...]        人读的文本报告
    python3 scan.py FILE --json            机器读的 JSON
    python3 scan.py FILE --only red        只看红线级
    python3 scan.py FILE --max-per-rule 5  每条规则最多列几处（默认 8）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------

@dataclass
class Rule:
    id: str          # 稳定标识，JSON 里用它，如 "zh-opener"
    name: str        # 报告里的显示名
    lang: str        # "zh" / "en" / "any"
    severity: str    # "red" / "amber"
    pattern: str     # 正则源串
    why: str         # 为什么这是问题——直接印进报告
    fix: str         # 该往哪个方向改——直接印进报告
    flags: int = re.IGNORECASE


@dataclass
class Hit:
    rule: Rule
    line: int        # 1-based
    snippet: str     # 带 ±12 字符上下文的片段


@dataclass
class Report:
    path: str
    cjk_ratio: float
    body_units: int  # 中文算字，英文算词
    lang: str        # "zh" / "en"
    hits: list = field(default_factory=list)
    density: dict = field(default_factory=dict)


SEV_ORDER = {"red": 0, "amber": 1}
SEV_NAME = {"red": "红线", "amber": "酌情"}


# --------------------------------------------------------------------------
# 规则表：中文 13 条
# --------------------------------------------------------------------------

ZH_RULES = [
    Rule(
        id="zh-opener",
        name="清嗓子开场",
        lang="zh",
        severity="red",
        pattern=(
            r"在当今[^，。]{0,12}[，的]"
            r"|随着[^，。]{2,18}的(不断|快速|迅猛)?发展"
            r"|众所周知|不得不说"
            r"|说到[^，。]{2,12}就?不得不提"
            r"|让我们(一起)?(来)?(看看?|走进|探讨|聊聊)"
            r"|首先要明确的是|在正式开始之前|话不多说"
        ),
        why="这些话在正文开始前先宣布一遍「我要开始讲了」，不携带任何信息。人类作者动笔就直接进入内容。",
        fix="删掉整句，从下一句真正有内容的地方开始。",
    ),
    Rule(
        id="zh-emphasis",
        name="强调废话",
        lang="zh",
        severity="red",
        # 两个逆序否定断言是刻意的：「最/尤其/更值得注意的是」在做排序，有实义。
        pattern=(
            r"(?<![最尤更])值得注意的是"
            r"|(?<!尤其)需要注意的是"
            r"|需要指出的是|值得一提的是|划重点|敲黑板|重要的事情说三遍|请记住这一点"
            r"|这一点(非常|十分)?(重要|关键)"
            r"|不难看出|显而易见的是|毋庸置疑"
        ),
        why="宣布某件事重要，代替不了把它讲清楚。真正重要的内容靠位置和论证获得重量，不靠贴标签。",
        fix="删掉标签，直接说那件事。如果删掉后读者感觉不到它重要，说明缺的是论证。",
    ),
    Rule(
        id="zh-wrapup",
        name="万能收尾与拔高",
        lang="zh",
        severity="red",
        pattern=(
            r"总而言之|综上所述|总的来说|概括来说|由此可见|不难发现"
            r"|希望(本文|这篇|以上)[^。]{0,20}(帮助|参考)"
            r"|希望对你有(所)?帮助|未来可期"
            r"|让我们(共同)?(期待|拭目以待)|任重道远"
            r"|值得(我们)?(深思|思考|玩味)"
            r"|这或许(就)?是[^。]{0,15}的(魅力|意义|智慧|哲学)"
        ),
        why="AI 收尾的固定动作：先复述一遍，再往上拔一层。读者刚读完，不需要复述；拔高那一层通常是空的。",
        fix="删掉。文章可以在最后一个实质结论处直接停住。",
    ),
    Rule(
        id="zh-contrast",
        name="二元对比套路",
        lang="zh",
        severity="amber",
        pattern=(
            r"不是[^。；！？]{1,24}(，|,)?\s*而是"
            r"|并非[^。；！？]{1,24}(，|,)?\s*而是"
            r"|与其说[^。]{1,24}不如说"
            r"|不仅仅?是[^。；！？]{1,24}(，|,)?\s*(更|而)是"
            r"|表面上[^。]{1,24}(实际上|其实)"
            r"|[^，。]{1,12}的本质(并)?不是"
        ),
        why=(
            "这条的假阳性率在技术文档里特别高，别按命中就改。判据只有一个：X 是不是读者真的可能相信的东西。"
            "「模型不是按字数算长度，而是切成 token」——读者真会那么以为，这是在纠正误解，该留。"
            "「这不是技术问题，而是管理问题」——没人主张它纯是技术问题，X 是临时立的靶子，"
            "这才是 AI 味：用一个假反转把平淡的 Y 包装成洞见。"
        ),
        fix="X 是真误解 → 保留。X 是自己立的靶子 → 删掉前半句，直接说 Y。",
    ),
    Rule(
        id="zh-vague",
        name="空泛判断",
        lang="zh",
        severity="red",
        pattern=(
            r"具有(重要|重大)(意义|作用|价值)"
            r"|起到了?(重要|关键)(的)?作用"
            r"|意义(重大|深远)|影响(是)?深远"
            r"|背后(其实)?(有其)?(深层的?)?(原因|逻辑)"
            r"|本质上是一(种|场)"
            r"|存在(着)?一定的?(问题|差异|局限)"
        ),
        why="说某件事「重要」「有深层原因」而不说是什么，等于什么都没说。这类句子最容易蒙混过关，因为它语法完整、看起来像结论。",
        fix="把那个具体的东西写出来：具体什么意义、具体什么原因。写不出来就删掉整句。",
    ),
    Rule(
        id="zh-jargon",
        name="互联网黑话",
        lang="zh",
        severity="amber",
        # 刻意不收「心智模型」「反馈闭环」「控制闭环」——技术语境里它们是正当译法，
        # 所以「心智」「闭环」都加了前缀限定。
        pattern=(
            r"赋能|抓手|拉通|对齐颗粒度|颗粒度"
            r"|(用户|抢占|占领)心智"
            r"|(业务|生态|增长|商业)闭环"
            r"|护城河|组合拳|打法|生态位|降维打击|底层逻辑|价值主张|全链路|数字化转型"
            r"|提升[^，。]{0,6}(体感|水位)"
            r"|(做|打)厚|长期主义"
        ),
        why="黑话把一个具体动作换成一个抽象名词，读者要在脑子里再翻译一遍。而且它经常掩盖「我还没想清楚具体要做什么」。",
        fix="换成那个具体动作。「赋能业务」→「让业务方自己能改配置」。",
    ),
    Rule(
        id="zh-europeanized",
        name="翻译腔与过度名词化",
        lang="zh",
        severity="amber",
        pattern=(
            r"进行(了)?[一二三]?(个|次|下)?[^，。]{1,8}(处理|操作|优化|分析|改造|讨论)"
            r"|做出[^，。]{1,10}的(决定|判断|选择)"
            r"|对[^，。]{1,12}(进行|加以)[^，。]{1,8}"
            r"|实现[^，。]{1,10}的(提升|下降|优化|转变)"
            r"|当涉及到|在某种程度上|从某种意义上(说|讲)?"
            r"|基于[^，。]{1,10}的考虑|你可能会问|有(以下)?几个原因"
        ),
        why="「对 X 进行优化」比「优化 X」多三个字、少一分力气。中文的动词天生能直接带宾语，套上「进行/实现/加以」是从英文语法搬来的空壳。",
        fix="把名词还原成动词：「进行了优化」→「优化了」；「对配置进行调整」→「改配置」。",
    ),
    Rule(
        id="zh-passive",
        name="被动滥用",
        lang="zh",
        severity="amber",
        pattern=(
            r"被[^，。]{1,10}(所)?(实现|完成|执行|处理|考虑|设计|采用|使用)"
            r"|受到[^，。]{1,12}的(影响|限制|制约)"
            r"|由[^，。]{1,12}所(决定|驱动|完成)"
        ),
        why="被动句把动作的执行者藏起来。读者要问「谁干的」，而藏起执行者往往正是因为作者自己也没想清楚是谁。",
        fix="找出执行者，把它放到句首。豁免：执行者确实不重要或不存在时，被动是对的——「这个字段已经被废弃」，谁废弃的无关紧要。",
    ),
    Rule(
        id="zh-intensifier",
        name="纯程度副词",
        lang="zh",
        severity="red",
        pattern=r"非常|十分|极其|极为|尤为|相当地",
        why="「非常重要」不比「重要」更重要，只是更长。这一类只加长度不加力量，删掉之后断言强度不变。",
        fix="直接删掉。真需要强调，换一个更准确的名词或动词。",
    ),
    Rule(
        id="zh-hedge",
        name="软化词与限定词",
        lang="zh",
        severity="amber",
        pattern=r"真正的?|确实|其实|基本上|某种程度上|一定程度上|可以说|应该说|或许可以说|不失为",
        why="软化词是在给自己留退路，读者感觉得到那份不自信。但这一条假阳性高：同样的词也可能在诚实地限定断言范围。",
        fix=(
            "先过豁免，别默认删。判据：删掉之后这句话变强了吗？变强了而事实不支持那么强，就留着——"
            "「基本上都能跑」在承认例外，「理论上支持」在提示没实测，删掉就是把断言偷偷加强。"
            "纯粹当口头禅的（其实、可以说）删。"
        ),
    ),
    Rule(
        id="zh-agency",
        name="虚假主体",
        lang="zh",
        severity="amber",
        pattern=(
            r"数据(告诉|表明|显示)(我们)?"
            r"|技术(的发展)?(推动|驱动|催生)"
            r"|时代(呼唤|要求)|市场(选择|奖励|惩罚)了?"
            r"|历史(证明|告诉)|需求驱动了?"
            r"|架构(决定|要求)了?[^，。]{1,10}必须"
        ),
        why="数据不会说话，市场不会奖励谁。这类句子把人从句子里删掉了，而读者真正想知道的恰好是「谁做的决定」。",
        fix="点出人：「数据告诉我们要拆服务」→「我们看完这组数据决定拆服务」。",
    ),
    Rule(
        id="zh-template",
        name="三段式模板",
        lang="zh",
        severity="amber",
        # 唯一的跨行规则：在整个 body 上匹配。
        # [^#] 让匹配不跨越 Markdown 标题，避免把两个小节的「首先」「其次」拼成一处命中。
        pattern=r"首先[^。]{0,40}。[^#]{0,600}?其次[^。]{0,40}。[^#]{0,600}?(最后|再次|第三)",
        why="「首先/其次/最后」是把提纲直接当成文章交付。它让每一段的地位变得一样，读者读不出哪个更重要，也看不到段与段之间真正的逻辑关系。",
        fix="改成能承载逻辑的连接：因果、递进、转折、让步。或者干脆用小标题。",
    ),
    Rule(
        id="zh-disclaimer",
        name="AI 式免责",
        lang="zh",
        severity="red",
        pattern=(
            r"以上(内容)?仅供参考"
            r"|具体情况(可能)?(会)?(有所)?不同"
            r"|请根据(自身|实际)情况"
            r"|如有(错误|不足)(请|欢迎)"
            r"|本文不构成任何建议"
        ),
        why="这是模型在给自己买保险，不是在为读者服务。真正的不确定性应该写在它出现的那个具体断言旁边，说清楚哪一条不确定、为什么。",
        fix="删掉套话。如果确有不确定的断言，就在那一条旁边写明：哪里没核实过、该怎么自己验证。",
    ),
]


# --------------------------------------------------------------------------
# 规则表：英文 10 条
# --------------------------------------------------------------------------

EN_RULES = [
    Rule(
        id="en-opener",
        name="Throat-clearing opener",
        lang="en",
        severity="red",
        pattern=(
            r"\bhere'?s (the thing|what|why|how|where)\b"
            r"|\bthe (uncomfortable )?truth is\b"
            r"|\bit turns out\b|\blet me be clear\b|\bcan we talk about\b"
            r"|\bin today'?s\b|\bin a world where\b|\bat its core\b"
            r"|\bat the end of the day\b|\bwhen it comes to\b"
        ),
        why="Announcing that a point is coming, instead of making it.",
        fix="Delete the opener. Start with the content.",
    ),
    Rule(
        id="en-emphasis",
        name="Emphasis crutch",
        lang="en",
        severity="red",
        pattern=(
            r"\bfull stop\b|\blet that sink in\b|\bmake no mistake\b"
            r"|\bthis matters because\b|\bhere'?s why (that|this) matters\b"
            r"|\bit'?s worth noting\b"
        ),
        why="Declaring importance is not the same as demonstrating it.",
        fix="Cut it and state the fact.",
    ),
    Rule(
        id="en-contrast",
        name="Binary contrast",
        lang="en",
        severity="amber",
        pattern=(
            r"\b(is|isn'?t|was|wasn'?t|not) [^.;!?]{1,40}?\bit'?s (actually |really )?\b"
            r"|\bnot because [^.;!?]{1,40}?\bbut because\b"
            r"|\bthe question isn'?t\b|\bthe answer isn'?t\b"
            r"|\bnot just [^.;!?]{1,30}?\bbut\b"
            r"|\bstops being [^.;!?]{1,20}?\bstarts being\b"
        ),
        why="A telegraphed reversal: negate a claim nobody made, then present Y as insight.",
        fix="State Y directly. Keep the negation only if readers genuinely hold belief X.",
    ),
    Rule(
        id="en-vague",
        name="Vague declarative",
        lang="en",
        severity="red",
        pattern=(
            r"\bthe (reasons|implications|consequences|stakes) are\b"
            r"|\bthis is the deepest\b|\bactually matters\b"
            r"|\bthis is what [a-z ]{3,20} looks like\b"
        ),
        why="Claims significance without naming the specific thing.",
        fix="Name the specific implication, or cut the sentence.",
    ),
    Rule(
        id="en-adverb",
        name="Adverb / hedge",
        lang="en",
        severity="amber",
        pattern=(
            r"\b(really|just|literally|genuinely|honestly|simply|actually|deeply|truly"
            r"|fundamentally|inherently|inevitably|interestingly|importantly|crucially)\b"
        ),
        why="Empty emphasis. The adverb adds length, not force.",
        fix="Delete it. If the sentence weakens, the verb or noun was the problem.",
    ),
    Rule(
        id="en-jargon",
        name="Business jargon",
        lang="en",
        severity="red",
        pattern=(
            r"\bnavigate (the |these |those )?(challenges|complexit)"
            r"|\bunpack\b|\blean into\b|\bgame-?changer\b|\bdouble down\b"
            r"|\bdeep dive\b|\bcircle back\b|\bmoving forward\b"
            r"|\bon the same page\b|\btake a step back\b"
        ),
        why="Replaces a concrete action with a stock phrase.",
        fix="Use the plain verb: handle, explain, commit, revisit.",
    ),
    Rule(
        id="en-passive",
        name="Passive voice",
        lang="en",
        severity="amber",
        pattern=(
            r"\b(was|were|is|are|been|being) (created|made|reached|decided|believed"
            r"|considered|implemented|designed|performed|conducted|utilized)\b"
            r"|\bit is believed that\b|\bmistakes were made\b"
        ),
        why="Hides the actor. Readers want to know who did it.",
        fix="Name the actor and put them first.",
    ),
    Rule(
        id="en-agency",
        name="False agency",
        lang="en",
        severity="amber",
        pattern=(
            r"\bthe (data|market|culture|conversation|decision|complaint) "
            r"(tells|rewards|shifts|moves|emerges|becomes)\b"
            r"|\b(lives or dies|gives rise to)\b"
        ),
        why="Inanimate things given human verbs. Data sits there; a person reads it.",
        fix="Name the human, or use 'you' to put the reader in the seat.",
    ),
    Rule(
        id="en-meta",
        name="Meta-commentary",
        lang="en",
        severity="red",
        pattern=(
            r"\bthe rest of this (essay|article|post)\b"
            r"|\blet me walk you through\b|\bin this section,? we'?ll\b"
            r"|\bas we'?ll see\b|\bi want to explore\b|\bplot twist\b|\bspoiler\b"
        ),
        why="The piece announces its own structure instead of moving.",
        fix="Delete. Let the next paragraph do the work.",
    ),
    Rule(
        id="en-wh-start",
        name="Wh- sentence opener",
        lang="en",
        severity="amber",
        # 必须区分大小写才能定位句首，所以关掉 IGNORECASE。
        pattern=r"(?:^|(?<=[.!?]\s))(What|When|Where|Which|Who|Why|How) [a-z]",
        why="'What makes this hard is...' buries the subject. It becomes a crutch fast.",
        fix="Lead with the subject: 'The constraint is...' — better, name the constraint.",
        flags=0,
    ),
]

ALL_RULES = ZH_RULES + EN_RULES


# --------------------------------------------------------------------------
# 密度指标
# --------------------------------------------------------------------------

# (limit, label, unit, why)。阈值是拿一批中文技术文档实测出来的经验带，不是标准。
# 超标不等于错，等于「这一项该看一眼」。
DENSITY_LIMITS = {
    "bold_char_ratio": (
        10.0, "加粗字占比", "%",
        "加粗超过一成，读者的眼睛就没有落点了。加粗该留给跳读时必须看到的那几处。",
    ),
    "bold_para_ratio": (
        85.0, "含加粗段落", "%",
        "段段都加粗，等于没有加粗——它不再标记重点，只是一种排版习惯。让至少三成段落保持素面，剩下的加粗才有对比度。",
    ),
    "em_dash": (
        2.5, "破折号 ——", "",
        "破折号最容易滥用。多数场合逗号或句号更清楚，破折号只该用在真正的插入或转折。",
    ),
    "exclaim": (
        0.5, "感叹号", "",
        "技术文档里的感叹号几乎总是虚假热情。",
    ),
    "connective": (
        8.0, "连接词", "",
        "因此/然而/此外 密集出现，说明段落之间的逻辑是硬贴上去的，不是长出来的。",
    ),
    "emoji": (
        0.3, "emoji", "",
        "emoji 小标题是 AI 排版最明显的指纹。全文统一的约定符号（比如固定用 📌 标旁注）不算。",
    ),
    "rule_of_three": (
        2.0, "三项排比", "",
        "三项并列朗朗上口，所以 AI 特别爱用。两项通常更诚实。",
    ),
}

CONNECTIVES = r"因此|然而|此外|与此同时|另一方面|同时|不过|但是|并且|从而|进而"

EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f0ff⬀-⯿]"
)

RULE_OF_THREE_RE = re.compile(
    r"[^，。；：、\s]{2,8}、[^，。；：、\s]{2,8}、[^，。；：、\s]{2,8}(?=[，。；：！？])"
)

CJK_RE = r"[一-鿿]"
WORD_RE = r"[A-Za-z][A-Za-z'-]*"


# --------------------------------------------------------------------------
# 掩码：代码块 / 行内代码 / URL / 链接目标 / frontmatter
# --------------------------------------------------------------------------

FENCE_RE = re.compile(r"^(\s*)(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
URL_RE = re.compile(r"https?://\S+")
LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")


def _blank(m: re.Match) -> str:
    """替换成等长空格——行号列号必须保持可跳转。"""
    return " " * (m.end() - m.start())


def mask_noncontent(text: str) -> str:
    """把非正文内容换成等长空格。

    核心不变式：输出与输入的行数、每行长度完全相同。
    绝不删除任何字符，否则报告里的 L46 就跳不回原文了。
    """
    lines = text.split("\n")
    out = []
    in_frontmatter = False
    in_fence = False
    fence_marker = ""

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # frontmatter：仅当第 0 行是 --- 才进入
        if idx == 0 and stripped == "---":
            in_frontmatter = True
            out.append(" " * len(line))
            continue
        if in_frontmatter:
            if stripped in ("---", "..."):
                in_frontmatter = False
            out.append(" " * len(line))  # 结束行本身也掩码
            continue

        # 围栏代码块：marker 必须与开启时相同才关闭（``` 块里的 ~~~ 不误关）
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(2)
            if not in_fence:
                in_fence = True
                fence_marker = marker
                out.append(" " * len(line))
                continue
            if marker == fence_marker:
                in_fence = False
                out.append(" " * len(line))
                continue
        if in_fence:
            out.append(" " * len(line))
            continue

        # 普通行：行内代码 → URL → 链接目标（链接文字保留在正文里参与扫描）
        masked = INLINE_CODE_RE.sub(_blank, line)
        masked = URL_RE.sub(_blank, masked)
        masked = LINK_TARGET_RE.sub(_blank, masked)
        out.append(masked)

    return "\n".join(out)


def is_indented_code(line: str) -> bool:
    """四空格缩进代码块。放过缩进的列表项、引用、表格行。

    注意：必须拿**原始行**判断。掩码后的行开头全是空格，判断会失真。
    """
    if not line.startswith("    "):
        return False
    return not line.lstrip().startswith(("-", "*", "+", ">", "|"))


# --------------------------------------------------------------------------
# 语言判定与计数
# --------------------------------------------------------------------------

def detect_lang(body: str) -> tuple:
    """返回 (lang, cjk_ratio)。

    分母先去掉所有空白：掩码把代码块换成了大量空格，不去掉会把 CJK 占比冲到接近 0，
    让中文文档跑英文规则。
    """
    stripped = re.sub(r"\s", "", body)
    cjk = len(re.findall(CJK_RE, body))
    ratio = cjk / max(len(stripped), 1)
    return ("zh" if ratio >= 0.20 else "en"), ratio


def count_units(body: str, lang: str) -> int:
    if lang == "zh":
        return len(re.findall(CJK_RE, body))
    return len(re.findall(WORD_RE, body))


# --------------------------------------------------------------------------
# 加粗统计
# --------------------------------------------------------------------------

def bold_stats(body: str, lang: str) -> tuple:
    """返回 (加粗字占比%, 含加粗段落占比%, 参与统计的段落数)。

    只统计 ≥30 个计数单位的正文段落，跳过 # 开头和 | 开头的块：
    标题、表格、短列表项本来就常带加粗，算进去会把比例冲淡，
    看不出正文段落是不是段段都加粗。
    """
    unit_re = CJK_RE if lang == "zh" else WORD_RE
    paras = []
    for block in re.split(r"\n\s*\n", body):
        s = block.strip()
        if not s or s.startswith("#") or s.startswith("|"):
            continue
        if len(re.findall(unit_re, s)) < 30:
            continue
        paras.append(s)

    if not paras:
        return 0.0, 0.0, 0

    total = sum(len(re.findall(unit_re, p)) for p in paras)
    bold = sum(
        len(re.findall(unit_re, m))
        for p in paras
        for m in re.findall(r"\*\*([^*\n]+)\*\*", p)
    )
    with_bold = sum(1 for p in paras if "**" in p)  # 朴素判断，不要求配对
    return 100.0 * bold / max(total, 1), 100.0 * with_bold / len(paras), len(paras)


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------

def scan_text(text: str, path: str) -> Report:
    body = mask_noncontent(text)
    lang, ratio = detect_lang(body)
    units = count_units(body, lang)
    per_k = max(units, 1) / 1000.0

    active = [r for r in ALL_RULES if r.lang in (lang, "any")]
    lines = body.split("\n")          # 掩码后
    raw_lines = text.split("\n")      # 原始
    hits = []

    for rule in active:
        rx = re.compile(rule.pattern, rule.flags)

        if rule.id == "zh-template":  # 唯一的跨行分支
            for m in rx.finditer(body):
                ln = body[: m.start()].count("\n") + 1
                hits.append(Hit(rule, ln, "首先…其次…最后（跨段）"))
            continue

        for idx, line in enumerate(lines, 1):
            if not line.strip() or is_indented_code(raw_lines[idx - 1]):
                continue
            for m in rx.finditer(line):
                s, e = m.start(), m.end()
                left = max(0, s - 12)
                right = min(len(line), e + 12)
                snip = line[left:right].strip()
                if left > 0:
                    snip = "…" + snip
                if right < len(line):
                    snip = snip + "…"
                hits.append(Hit(rule, idx, snip))

    # 密度
    bold_pct, bold_para_pct, n_paras = bold_stats(body, lang)
    counts = {
        "em_dash": len(re.findall(r"——|(?<= )—(?= )", body)),
        "exclaim": len(re.findall(r"[!！]", body)),
        "connective": len(re.findall(CONNECTIVES, body)),
        "emoji": len(EMOJI_RE.findall(body)),
        "rule_of_three": len(RULE_OF_THREE_RE.findall(body)),
    }
    ratios = {"bold_char_ratio": bold_pct, "bold_para_ratio": bold_para_pct}

    density = {}
    for key, (limit, label, unit, why) in DENSITY_LIMITS.items():
        if key in ratios:
            value, count = ratios[key], None
        else:
            count = counts[key]
            value = count / per_k
        density[key] = {
            "label": label,
            "count": count,
            "value": round(value, 1),
            "unit": unit or ("/千字" if lang == "zh" else "/千词"),
            "limit": limit,
            "over": value > limit,  # 严格大于：恰好等于阈值不算超标
            "why": why,
        }
    # 段落数对读者有意义（知道样本量），加粗字数没有 → bold_char_ratio.count 保持 None
    density["bold_para_ratio"]["count"] = n_paras

    return Report(
        path=path,
        cjk_ratio=ratio,
        body_units=units,
        lang=lang,
        hits=hits,
        density=density,
    )


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def render(report: Report, only: str | None = None, max_per_rule: int = 8) -> str:
    bar = "=" * 72
    lang_name = "中文为主" if report.lang == "zh" else "英文为主"
    unit_name = "字" if report.lang == "zh" else "词"

    out = [bar]
    out.append(f"文件  {report.path}")
    out.append(
        f"语言  {lang_name}（CJK {report.cjk_ratio:.0%}）   "
        f"正文 {report.body_units:,} {unit_name}（已排除代码块）"
    )
    out.append(bar)
    out.append("")

    # 密度指标：--only 不影响这一节，密度永远全量输出
    out.append("【密度指标】")
    for key in DENSITY_LIMITS:
        d = report.density[key]
        count = d["count"]
        count_cell = f"{count:>5} 处" if count is not None else " " * 7
        value_cell = f"{d['value']:>6}{d['unit']}"
        flag = "⚠ 偏高" if d["over"] else "ok"
        out.append(f"  {d['label']:<12}{count_cell}   {value_cell:<12} 上限 {d['limit']}   {flag}")

    overs = [report.density[k] for k in DENSITY_LIMITS if report.density[k]["over"]]
    if overs:
        out.append("")
        for d in overs:
            out.append(f"  ⚠ {d['label']}：{d['why']}")

    # 逐条命中：--only 在分组之前过滤，所以「共 N 处」是过滤后的数量
    shown = [h for h in report.hits if only is None or h.rule.severity == only]
    out.append("")
    out.append(f"【逐条命中】共 {len(shown)} 处，按严重度排序")

    if not shown:
        out.append("  没有命中。")
        return "\n".join(out)

    groups = {}
    for h in shown:
        groups.setdefault(h.rule.id, []).append(h)

    ordered = sorted(
        groups.values(),
        key=lambda g: (SEV_ORDER[g[0].rule.severity], -len(g)),
    )

    for group in ordered:
        rule = group[0].rule
        out.append("")
        out.append(f"■ {rule.name}（{SEV_NAME[rule.severity]}） — {len(group)} 处")
        out.append(f"  为什么：{rule.why}")
        out.append(f"  怎么改：{rule.fix}")
        for h in group[:max_per_rule]:
            out.append(f"    L{h.line:<5} {h.snippet}")
        rest = len(group) - max_per_rule
        if rest > 0:
            out.append(f"    …另有 {rest} 处（--max-per-rule 调整）")

    return "\n".join(out)


def to_dict(report: Report) -> dict:
    """JSON 输出：hits 永远全量，summary 计数不受 --only / --max-per-rule 影响。"""
    return {
        "path": report.path,
        "lang": report.lang,
        "cjk_ratio": round(report.cjk_ratio, 3),
        "body_units": report.body_units,
        "density": report.density,
        "hits": [
            {
                "rule": h.rule.id,
                "name": h.rule.name,
                "severity": h.rule.severity,
                "line": h.line,
                "snippet": h.snippet,
            }
            for h in report.hits
        ],
        "summary": {
            "red": sum(1 for h in report.hits if h.rule.severity == "red"),
            "amber": sum(1 for h in report.hits if h.rule.severity == "amber"),
            "density_over": [
                report.density[k]["label"] for k in DENSITY_LIMITS if report.density[k]["over"]
            ],
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="给 Markdown 文稿找 AI 味的嫌疑处，并统计排版密度。"
    )
    ap.add_argument("files", nargs="+", help="一个或多个文件路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON 数组而非文本报告")
    ap.add_argument("--only", choices=["red", "amber"], help="只列该严重度的命中")
    ap.add_argument("--max-per-rule", type=int, default=8, help="每条规则在文本报告里最多列几处")
    args = ap.parse_args(argv)

    reports = []
    for raw in args.files:
        p = Path(raw)
        if not p.is_file():
            print(f"跳过（不是文件）：{raw}", file=sys.stderr)
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        reports.append(scan_text(text, str(p)))

    if args.json:
        print(json.dumps([to_dict(r) for r in reports], ensure_ascii=False, indent=2))
    else:
        for r in reports:
            print(render(r, only=args.only, max_per_rule=args.max_per_rule))
            print()

    return 0  # 恒为 0：诊断工具，不是 CI gate


if __name__ == "__main__":
    sys.exit(main())
