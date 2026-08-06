#!/usr/bin/env python3
"""prompt-mode-lint — 检出提示词里的 pipeline-only 条款。

配套《把 Agent 送上生产》第 4 章。

为什么存在：为「ASR→LLM→TTS」链路写的提示词，交给端到端语音模型时不会报错，
它会照做，然后以你想不到的方式崩坏——JSON 被念出来、身份声明被主动播报、
调用不存在的工具后卡死、没有数据源时直接沉默。

这个 linter 检的就是那五类条款。它不理解语义，只做模式匹配：
宁可多报，也不漏报——因为漏报的代价是一次线上通话。

用法：
    python3 prompt-mode-lint.py <file...>            # 检查文件
    python3 prompt-mode-lint.py --self-test          # 自测
    python3 prompt-mode-lint.py <file> --quiet       # 只输出判定标量

退出码：0=SAFE，1=UNSAFE_FOR_REALTIME，2=用法错误
"""
import re
import sys
from pathlib import Path

def ASCII_TOKEN(tok: str) -> str:
    r"""匹配一个 ASCII 词，但不依赖 \b。

    Python 的 \w 包含 CJK，所以 `\bJSON\b` 在「必须输出JSON对象」里**不会**匹配——
    而中文提示词恰恰不在 ASCII 词两侧加空格。独立评审实测：加空格能检出，
    不加空格永远漏。这里改用「两侧不是拉丁字母数字」作边界。
    """
    return r"(?<![A-Za-z0-9_])" + re.escape(tok) + r"(?![A-Za-z0-9_])"


# 五类规则，每类对应第 4 章的一个症状。
# 中英双语模式——真实项目里提示词常是混写的。
RULES = {
    "STRUCTURED_OUTPUT": {
        "desc": "结构化输出要求（会被 TTS 直接念出来）",
        "patterns": [
            ASCII_TOKEN("JSON"), r"json\s*schema", r"结构化输出", r"输出格式.{0,10}[:：].{0,20}\{",
            r"\{\s*[\"']?\w+[\"']?\s*:", r"markdown\s*格式", r"代码块",
            ASCII_TOKEN("tts_text"), ASCII_TOKEN("slot_updates"),
        ],
    },
    "TOOL_CALL": {
        "desc": "工具调用指令（端到端链路通常无工具，模型会卡死或空等）",
        "patterns": [
            ASCII_TOKEN("tool_call"), r"function[_ ]call", r"调用\s*工具", r"调用\s*\w+\(",
            r"(?<![A-Za-z0-9_])search_\w+", r"(?<![A-Za-z0-9_])book_\w+",
            r"(?<![A-Za-z0-9_])send_\w+", r"(?<![A-Za-z0-9_])handoff_\w+",
            r"使用.{0,6}工具", r"(?<![A-Za-z0-9_])tools?\s*[:：]",
        ],
    },
    "STATE_MACHINE": {
        "desc": "状态机推进（单会话链路里无意义，纯噪音）",
        "patterns": [
            ASCII_TOKEN("next_state"), r"(?<![A-Za-z0-9_])state\s*=", r"推进判定", r"进入\s*[SP]\d",
            r"(?<![A-Za-z0-9_])stage\s*\d", r"切换到.{0,8}状态", r"当前状态",
        ],
    },
    "IDENTITY_DECLARATION": {
        "desc": "身份声明条款（易被误读成开场主动播报）",
        "patterns": [
            r"我是\s*AI", r"不是真人", r"我是机器人", r"AI\s*助手", r"人工智能助手",
            r"表明身份", r"告知.{0,6}身份",
        ],
    },
    "DATA_DEPENDENCY": {
        "desc": "依赖外部数据的动作（无工具时会说完过渡语就沉默）",
        "patterns": [
            r"召回", r"查询.{0,8}(岗位|订单|记录|数据)", r"检索", r"查找.{0,8}(岗位|商品|信息)",
            r"从.{0,10}(数据库|系统|接口).{0,6}获取", r"帮您?查",
        ],
    },
}

# 只把**显式的反面案例标记**当作豁免。
#
# 首版把 "#" 和 "禁止/不要/忽略" 也算进来，后果是灾难性的：
#   1. 真实提示词都是 Markdown，`## 1. 输出格式：每轮必须是 JSON` 因行首 # 被整行跳过；
#      实测一份含全部五个症状的 Markdown 提示词得到 VERDICT=SAFE。
#   2. 「禁止空回复：必须调用 search_jobs」是一条**命令**，不是反面案例，却被豁免。
# 漏报比误报危险得多——漏报的代价是一次线上通话。所以这里只保留最窄的判据。
NEGATION_MARKERS = ("❌", "反面案例", "错误示范", "错误写法")


def is_negated(line: str) -> bool:
    stripped = line.strip()
    # 行首是 ❌ 之类的显式标记，或整行明确自称反面案例
    return stripped.startswith(NEGATION_MARKERS) or any(m in stripped for m in ("反面案例", "错误示范", "错误写法"))


def lint_text(text: str) -> dict:
    """返回 {类别: [(行号, 行内容, 命中的模式)]}"""
    hits: dict[str, list] = {k: [] for k in RULES}
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or is_negated(line):
            continue
        for cat, rule in RULES.items():
            for pat in rule["patterns"]:
                if re.search(pat, line, re.IGNORECASE):
                    hits[cat].append((lineno, line.strip()[:70], pat))
                    break
    return hits


def report(path: str, hits: dict, quiet: bool) -> int:
    total = sum(len(v) for v in hits.values())
    print(f"FILE={path}")
    for cat in RULES:
        print(f"HIT_{cat}={len(hits[cat])}")
    print(f"TOTAL_HITS={total}")
    verdict = "UNSAFE_FOR_REALTIME" if total else "SAFE"
    print(f"VERDICT={verdict}")
    if not quiet and total:
        print("--- 明细 ---")
        for cat, items in hits.items():
            if not items:
                continue
            print(f"[{cat}] {RULES[cat]['desc']}")
            for lineno, snippet, pat in items[:6]:
                print(f"  L{lineno}: {snippet}   ← /{pat}/")
            if len(items) > 6:
                print(f"  ... 另有 {len(items) - 6} 处")
    return 1 if total else 0


def run_self_test() -> int:
    passed = failed = 0

    def check(name, got, want):
        nonlocal passed, failed
        if got == want:
            print(f"  ok   {name}")
            passed += 1
        else:
            print(f"  FAIL {name} (got={got} want={want})")
            failed += 1

    # 五类各造一个正样本——对应第 4 章的五个症状
    cases = [
        ("症状1 结构化输出", "每轮回复必须是 JSON 对象", "STRUCTURED_OUTPUT"),
        ("症状2 身份声明", "你要说明我是 AI 顾问，不是真人", "IDENTITY_DECLARATION"),
        ("症状3 工具调用", "立刻 tool_call: handoff_to_human", "TOOL_CALL"),
        ("症状4 数据依赖", "召回 1-3 个岗位推荐给用户", "DATA_DEPENDENCY"),
        ("症状5 状态机", "推进判定：next_state = S7", "STATE_MACHINE"),
    ]
    for name, text, cat in cases:
        check(name, len(lint_text(text)[cat]) > 0, True)

    print("self-test: 干净样本")
    clean = "直接用口语回答候选人的问题，单句不超过 15 字。"
    check("无命中", sum(len(v) for v in lint_text(clean).values()), 0)

    print("self-test: 真实 Markdown 不再漏报（首版在此全线失守）")
    md = """# 招聘外呼 Agent 提示词 v3
## 1. 输出格式：每轮必须是 JSON
## 2. 工具：tool_call: search_jobs
## 3. 开场：必须表明身份，说明我是 AI 助手
## 4. 召回岗位：从数据库获取 1-3 个岗位后播报
## 5. 状态机：推进到 next_state"""
    h = lint_text(md)
    check("markdown 标题不再被跳过", sum(len(v) for v in h.values()) >= 5, True)
    check("  └ 结构化输出", len(h["STRUCTURED_OUTPUT"]) > 0, True)
    check("  └ 工具调用",   len(h["TOOL_CALL"]) > 0, True)
    check("  └ 身份声明",   len(h["IDENTITY_DECLARATION"]) > 0, True)
    check("  └ 数据依赖",   len(h["DATA_DEPENDENCY"]) > 0, True)
    check("  └ 状态机",     len(h["STATE_MACHINE"]) > 0, True)

    print("self-test: 中文紧贴 ASCII 词（\\b 失效那类）")
    check("必须输出JSON对象", len(lint_text("每轮回复必须输出JSON对象")["STRUCTURED_OUTPUT"]) > 0, True)
    check("立刻tool_call",   len(lint_text("立刻tool_call:handoff_to_human")["TOOL_CALL"]) > 0, True)
    check("JSONP 不误报",     len(lint_text("返回 JSONP 回调")["STRUCTURED_OUTPUT"]), 0)

    print("self-test: 命令句不再被误当反面案例")
    check("禁止X：必须调用工具", len(lint_text("禁止空回复：必须调用 search_jobs 工具后再答")["TOOL_CALL"]) > 0, True)

    print("self-test: 豁免范围（已收窄，见 NEGATION_MARKERS 注释）")
    # 只有显式反面案例标记才豁免
    check("❌ 前缀豁免", sum(len(v) for v in lint_text("❌ 不要输出 JSON 或 tool_call").values()), 0)
    check("反面案例豁免", sum(len(v) for v in lint_text("反面案例：输出 JSON 被念出来").values()), 0)
    # 下面两条在首版被豁免，现在**故意**计为命中：
    #   「忽略 §5 的 JSON schema 要求」——这句本身证明上游存在 JSON 要求，值得报出来
    #   「# ...」——真实提示词里 # 是 Markdown 标题，不是注释；首版据此豁免导致全线漏报
    check("豁免声明本身也报", len(lint_text("忽略 §5 的 JSON schema 要求")["STRUCTURED_OUTPUT"]) > 0, True)
    check("# 标题不再豁免",   len(lint_text("# JSON 输出、tool_call 已废弃")["STRUCTURED_OUTPUT"]) > 0, True)

    print()
    print(f"SELF_TEST_PASS={passed}")
    print(f"SELF_TEST_FAIL={failed}")
    print(f"VERDICT={'SELF_TEST_OK' if failed == 0 else 'SELF_TEST_FAILED'}")
    return 0 if failed == 0 else 1


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--self-test":
        return run_self_test()

    quiet = "--quiet" in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        print("未提供文件", file=sys.stderr)
        return 2

    worst = 0
    for f in files:
        p = Path(f)
        if not p.exists():
            print(f"FILE={f}")
            print("VERDICT=FILE_NOT_FOUND")
            worst = max(worst, 2)
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # 曾经直接抛栈退出 1，与 UNSAFE 同码，且后续文件全不检查
            print(f"FILE={f}"); print("VERDICT=UNREADABLE_NOT_UTF8")
            worst = max(worst, 2); continue
        except IsADirectoryError:
            print(f"FILE={f}"); print("VERDICT=IS_A_DIRECTORY")
            worst = max(worst, 2); continue
        except OSError as e:
            print(f"FILE={f}"); print(f"VERDICT=UNREADABLE ({type(e).__name__})")
            worst = max(worst, 2); continue
        worst = max(worst, report(f, lint_text(text), quiet))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
