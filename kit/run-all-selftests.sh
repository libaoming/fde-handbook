#!/usr/bin/env bash
# run-all-selftests.sh — 跑遍 kit/ 下所有自测，输出单一判定标量。
#
# 为什么存在：本书写作过程中，我曾把「命令+参数」塞进一个变量再执行，
# shell 把整串当成文件名，五条自测全部 no such file or directory——
# 而我当时没看退出码就继续往下走了。结果碰巧是对的，过程是空转的。
#
# 所以这个 runner 有两条硬要求：
#   1. 任何一条自测未能真正执行（而非执行后失败），必须报错而不是静默跳过
#   2. 最终只输出一个 ALL_PASS=yes|no，不让人去读五段输出自己判断
#
# 用法：bash kit/run-all-selftests.sh [--verbose]
# 退出码：0=全通过，1=有失败

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

VERBOSE=0
[[ "${1:-}" == "--verbose" ]] && VERBOSE=1

# 名称::命令 —— 用数组而不是字符串拼接，避免开头说的那个坑
TESTS=(
    "verify-switch::bash kit/verify-switch.sh --self-test"
    "float32-misread::python3 kit/float32-int16-misread.py --assert"
    "reach-probe::bash kit/reach-probe.sh --self-test"
    "prompt-mode-lint::python3 kit/prompt-mode-lint.py --self-test"
    "soft-prior-lint::python3 kit/soft-prior-lint.py --self-test"
    "book-samples::bash kit/check-book-samples.sh"
)

pass=0; fail=0; missing=0

for entry in "${TESTS[@]}"; do
    name="${entry%%::*}"
    cmd="${entry#*::}"
    # 取出脚本路径，先确认文件真的存在——防止「没跑成」被当成「跑过了」
    script="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^kit\//) {print $i; exit}}' <<< "$cmd")"
    if [[ ! -f "$script" ]]; then
        echo "MISSING  $name  ($script 不存在)"
        ((missing++)); continue
    fi

    if [[ $VERBOSE -eq 1 ]]; then
        eval "$cmd"; rc=$?
    else
        eval "$cmd" >/dev/null 2>&1; rc=$?
    fi

    if [[ $rc -eq 0 ]]; then
        echo "PASS     $name"
        ((pass++))
    else
        echo "FAIL     $name  (exit=$rc)"
        ((fail++))
    fi
done

echo "---"
echo "KIT_TOTAL=${#TESTS[@]}"
echo "KIT_PASS=$pass"
echo "KIT_FAIL=$fail"
echo "KIT_MISSING=$missing"

if [[ $fail -eq 0 && $missing -eq 0 && $pass -eq ${#TESTS[@]} ]]; then
    echo "ALL_PASS=yes"
    exit 0
fi
echo "ALL_PASS=no"
exit 1
