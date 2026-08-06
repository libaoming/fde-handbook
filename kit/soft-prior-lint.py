#!/usr/bin/env python3
"""soft-prior-lint — 检出「你以为是约束，模型当成建议」的三类风险。

配套《把 Agent 送上生产》第 5 章。

三类风险：
  1. CANDIDATE_LIST   给了候选词表/枚举清单 → 模型在信息不足时拿它当编造原料
  2. PUNCT_DIRECTIVE  要求用句号做节奏控制 → 迁到端到端链路后变成话轮结束信号
  3. TURN_END_RISK    多条目播报中夹句号 → 同上（⚠️ 噪声较高，多为说明性文字误报）
  4. NO_ESCAPE_HATCH  没写「不确定时怎么办」→ 模型没有承认无知的合法出路

第 2 类是首版遗漏的：真凶只含一个句号，逃过了第 3 类的多句号检测。
第 3 类保留但已知噪声高——它检「用了句号」，第 2 类才检「要求用句号」。

第 3 项是最容易被忽略的：前两项检的是「你给多了」，第 3 项检的是「你给少了」。
模型编造往往不是因为想骗你，而是因为「猜一个」的成本低于「承认不知道」。

用法：
    python3 soft-prior-lint.py <file...>
    python3 soft-prior-lint.py --self-test
    python3 soft-prior-lint.py <file> --quiet

退出码：0=OK，1=SOFT_PRIOR_RISK，2=用法错误
"""
import re
import sys
from pathlib import Path

# 顿号/逗号分隔的三项以上枚举——典型的「候选词表」形态
ENUM_PATTERN = re.compile(r"[一-龥A-Za-z]{2,8}([、,，][一-龥A-Za-z]{2,8}){2,}")

CANDIDATE_LIST_HINTS = [
    r"词表", r"候选(词|集|项|列表)", r"可能的?(词|说法|表述|岗位|类目)",
    r"(常见|典型)的?(词|说法|类型|岗位)", r"例如\s*[:：]", r"如\s*[:：]",
    r"包括(以下|如下)", r"参考(词|列表|清单)",
]

# 「连续播报多条」的意图信号——出现这类要求时，句号就成了风险
MULTI_ITEM_HINTS = [
    r"依次", r"连续(念|说|播报|输出)", r"逐(个|条|一)(念|说|介绍)",
    r"[一二三四五1-5]\s*个(岗位|选项|方案|条目)", r"分别介绍", r"全部(念|说)完",
    r"不要?停顿", r"一个\s*turn",
]

# 「要求用标点做控制」的元指令——pipeline 时代最典型的隐性约定。
# 首版遗漏了这一类：它只有一个句号，逃过了 TURN_END_RISK，而它恰恰是真凶。
PUNCT_DIRECTIVE_HINTS = [
    r"用句号", r"句号\s*/\s*换行", r"句号.{0,6}(体现|分隔|表示|停顿|间隔)",
    r"句间.{0,10}停顿", r"(逗号|句号|问号)\s*0?\.\d+\s*s?",
    r"以句号", r"加句号", r"打句号", r"换行体现",
]

# 明确**禁止**模型承认无知的指令。比「没写出路」更危险：它主动命令模型编造。
# 首版只做正向关键词存在性检查，于是「听不清也不要反问，猜一个最像的报出来」
# 这句话因为含「听不清」「反问」而被判定为「有出路」——检查被自己的否定满足了。
ANTI_ESCAPE_HINTS = [
    r"不要?(反问|追问|确认)", r"不(准|许|得)(反问|追问)", r"禁止(反问|追问)",
    r"不要说.{0,4}不知道", r"不(准|许|得)说.{0,4}不知道", r"禁止说.{0,4}不知道",
    r"必须给出.{0,6}(答案|结论)", r"不(准|许|得)拒答", r"禁止拒答",
    r"(猜|编)一个", r"猜测?最(接近|像)", r"也要给出", r"不能说不确定",
]

ESCAPE_HATCH_HINTS = [
    r"听不清", r"没听清", r"不确定", r"不知道", r"信息不足", r"无法确认",
    r"反问", r"追问", r"请用户重复", r"再问一遍", r"承认", r"不要(猜|编)",
    r"禁止(猜测|编造|臆测)", r"拿不准",
]

# 与 prompt-mode-lint 一致：只认显式反面案例标记。
# "#" 在真实提示词里是 Markdown 标题，据此豁免会导致整段漏报。
NEGATION_MARKERS = ("❌", "反面案例", "错误示范")


def _hit(patterns, text):
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


BULLET_RE = re.compile(r"^\s*[-*+•]\s*([一-龥A-Za-z][一-龥A-Za-z0-9]{0,10})\s*$")


def find_bullet_wordlist(lines):
    """连续 ≥3 行的短词条目 = 词表。

    首版的 ENUM_PATTERN 只匹配单行顿号/逗号分隔，而人们写词表最常用的形式是
    Markdown 列表。实测：一份 bullet 词表 + 「听不清就编一个」得到 VERDICT=OK。
    """
    hits, run_start, run = [], None, 0
    for i, line in enumerate(lines, 1):
        if BULLET_RE.match(line):
            if run == 0:
                run_start = i
            run += 1
        else:
            if run >= 3:
                hits.append((run_start, f"连续 {run} 条短词列表", "bullet 词表"))
            run, run_start = 0, None
    if run >= 3:
        hits.append((run_start, f"连续 {run} 条短词列表", "bullet 词表"))
    return hits


def lint_text(text: str) -> dict:
    lines = text.splitlines()
    hits = {"CANDIDATE_LIST": [], "PUNCT_DIRECTIVE": [], "TURN_END_RISK": [], "NO_ESCAPE_HATCH": []}

    wants_multi_item = _hit(MULTI_ITEM_HINTS, text)

    for lineno, line in enumerate(lines, 1):
        s = line.strip()
        if not s or any(s.startswith(m) for m in NEGATION_MARKERS):
            continue

        # 1) 候选词表：显式提示词 + 三项以上枚举，两者需同时出现才算
        #    首版还有一条「裸长枚举串」规则，实测对中文散文假阳性极高
        #    （「今天天气不错，我们先聊工作，然后聊薪资，最后聊时间」即命中），
        #    本书自己 7 个文件全部报警 → 判定标量失去信息量。已删除。
        if _hit(CANDIDATE_LIST_HINTS, s) and ENUM_PATTERN.search(s):
            hits["CANDIDATE_LIST"].append((lineno, s[:70], "词表提示 + 3项以上枚举"))

        # 2) 标点控制指令：要求用句号做节奏控制——迁到端到端链路时直接变成话轮结束信号
        if _hit(PUNCT_DIRECTIVE_HINTS, s):
            hits["PUNCT_DIRECTIVE"].append((lineno, s[:70], "要求用标点做控制（跨链路含义反转）"))

        # 3) turn-end 风险：仅在整份文档表达了「连续播报多条」意图时才检
        #    句号本身无罪，它只在这个场景下有害。⚠️ 本项噪声较高，见 README
        if wants_multi_item and "。" in s and s.count("。") >= 2:
            hits["TURN_END_RISK"].append((lineno, s[:70], "多条目语境中出现多个句号"))

    # bullet 形式的词表
    hits["CANDIDATE_LIST"].extend(find_bullet_wordlist(lines))

    # 出路：先看有没有**反向指令**（明令不许承认无知），那比缺出路更严重
    if _hit(ANTI_ESCAPE_HINTS, text):
        hits["NO_ESCAPE_HATCH"].append((0, "(全文)", "存在明令禁止承认无知/要求猜测的指令"))
    elif not _hit(ESCAPE_HATCH_HINTS, text):
        hits["NO_ESCAPE_HATCH"].append((0, "(全文)", "未发现「不确定时怎么办」的指引"))

    return hits


def report(path: str, hits: dict, quiet: bool) -> int:
    total = sum(len(v) for v in hits.values())
    print(f"FILE={path}")
    for k in ("CANDIDATE_LIST", "PUNCT_DIRECTIVE", "TURN_END_RISK", "NO_ESCAPE_HATCH"):
        print(f"HIT_{k}={len(hits[k])}")
    print(f"TOTAL_HITS={total}")
    print(f"VERDICT={'SOFT_PRIOR_RISK' if total else 'OK'}")
    if not quiet and total:
        print("--- 明细 ---")
        for k, items in hits.items():
            for lineno, snippet, why in items[:5]:
                loc = f"L{lineno}" if lineno else "全文"
                print(f"  [{k}] {loc}: {snippet}   ← {why}")
    return 1 if total else 0


def run_self_test() -> int:
    p = f = 0

    def check(name, got, want):
        nonlocal p, f
        if got == want:
            print(f"  ok   {name}"); p += 1
        else:
            print(f"  FAIL {name} (got={got} want={want})"); f += 1

    print("self-test: CANDIDATE_LIST")
    # 第 5 章那份词表的形态
    check("词表提示+枚举",
          len(lint_text("常见岗位词表如：服务员、保安、快递员、仓管、后厨")["CANDIDATE_LIST"]) > 0, True)
    check("正常句子不误报",
          len(lint_text("先问位置，再问通勤距离。听不清就反问。")["CANDIDATE_LIST"]), 0)

    print("self-test: TURN_END_RISK")
    multi = "连续念完三个岗位。一号服务员。二号前厅。三号面点。"
    check("多条目语境+多句号", len(lint_text(multi)["TURN_END_RISK"]) > 0, True)
    # 没有「连续播报」意图时，句号无罪
    check("单条目语境不误报",
          len(lint_text("你好。请问应聘什么岗位。听不清就反问。")["TURN_END_RISK"]), 0)

    print("self-test: PUNCT_DIRECTIVE（首版遗漏的真凶类型）")
    check("句间停顿用句号体现",
          len(lint_text("- **句间 0.6s 停顿**（用句号/换行体现）。")["PUNCT_DIRECTIVE"]) > 0, True)
    check("节奏对照表",
          len(lint_text("逗号 0.2s、句号 0.4s、问号 0.3s。")["PUNCT_DIRECTIVE"]) > 0, True)
    check("普通句子不误报",
          len(lint_text("先问位置，再问通勤距离。")["PUNCT_DIRECTIVE"]), 0)

    print("self-test: NO_ESCAPE_HATCH")
    check("缺出路→命中",
          len(lint_text("请回答用户的问题，保持简洁。")["NO_ESCAPE_HATCH"]) > 0, True)
    check("有出路→不命中",
          len(lint_text("请回答用户的问题。听不清就反问，不要猜测。")["NO_ESCAPE_HATCH"]), 0)

    print("self-test: bullet 词表（首版漏报）")
    bullet = """# 岗位候选词表
- 服务员
- 保安
- 快递员
听不清就直接编一个最接近的岗位报给用户，不要说你不知道。"""
    hb = lint_text(bullet)
    check("bullet 词表被检出", len(hb["CANDIDATE_LIST"]) > 0, True)
    check("反向指令→无出路",   len(hb["NO_ESCAPE_HATCH"]) > 0, True)

    print("self-test: 反向指令不再满足出路检查（首版被自己的否定满足）")
    check("听不清也不要反问", len(lint_text("听不清也不要反问，猜一个最像的报出来。")["NO_ESCAPE_HATCH"]) > 0, True)
    check("禁止说不知道",     len(lint_text("不确定时也必须给出一个确定答案，禁止说不知道。")["NO_ESCAPE_HATCH"]) > 0, True)

    print("self-test: 中文散文不再被当词表（首版假阳性来源）")
    prose = "今天天气不错，我们先聊工作，然后聊薪资，最后聊时间。听不清就反问，不要猜测。"
    check("散文不报词表", len(lint_text(prose)["CANDIDATE_LIST"]), 0)

    print("self-test: 反面案例行不误报")
    check("❌ 前缀", len(lint_text("❌ 例如：服务员、保安、快递员、仓管")["CANDIDATE_LIST"]), 0)

    print()
    print(f"SELF_TEST_PASS={p}")
    print(f"SELF_TEST_FAIL={f}")
    print(f"VERDICT={'SELF_TEST_OK' if f == 0 else 'SELF_TEST_FAILED'}")
    return 0 if f == 0 else 1


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__); return 2
    if args[0] == "--self-test":
        return run_self_test()
    quiet = "--quiet" in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        print("未提供文件", file=sys.stderr); return 2
    worst = 0
    for fp in files:
        path = Path(fp)
        if not path.exists():
            print(f"FILE={fp}"); print("VERDICT=FILE_NOT_FOUND"); worst = max(worst, 2); continue
        worst = max(worst, report(fp, lint_text(path.read_text(encoding="utf-8")), quiet))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
