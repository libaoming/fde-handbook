#!/usr/bin/env bash
# check-book-samples.sh — 正文里印的每一个判定标量，必须真的由 kit 产生。
#
# 存在的理由（真事）：第 3 章初稿印过一段这样的输出——
#     LOCAL_HAIRPIN=ok
#     EXTERNAL=fail
#     PATH_COVERAGE=hairpin_only
# 而这三个字段名在 kit/ 里一次都没出现过。我先写了正文的示意输出、
# 后写的脚本，脚本换了字段名，正文没同步。它不是伪造实验数据，
# 但它是一段没有任何命令产生过、却以命令输出形式印在正文里的文本。
#
# 一本讲「完成声明前先回读」的书出这种错，等于宣布护城河是虚的。
# 所以把它变成一道机械闸门：正文中所有 UPPER_SNAKE=... 形式的字段名，
# 必须能在 kit/ 的某个脚本里找到定义。
#
# 规则：
#   - 只检大写下划线形式（VERDICT / HIT_XXX / ALL_PASS）——那是 kit 判定标量的约定
#   - 小写字段（i16_max_abs / event / head8）跳过：那些是外部日志引用，不是 kit 产物
#   - 白名单见下，用于第三方工具输出与通用常量
#
# 用法：bash kit/check-book-samples.sh [--verbose]
# 退出码：0=全部有据，1=发现无出处的字段

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

VERBOSE=0
[[ "${1:-}" == "--verbose" ]] && VERBOSE=1

# 非 kit 产出但合法出现在正文里的标量：第三方工具输出、通用常量、正文自造的示意变量
WHITELIST=(
    # 第三方 / 系统输出
    "EXIT" "SSH_OK" "SSH_EXIT" "REAL_SSH_EXIT" "FILE_EXISTS" "LINES"
    "PKG_PATH" "VERSION" "PATH" "REPO" "TIMEOUT"
    # 数值常量（在 kit 源码里是 Python 变量而非输出字段）
    "INT16_MAX" "SAMPLE_RATE" "DURATION_S" "AMPLITUDE" "NEAR" "RAIL"
)

is_whitelisted() {
    local k="$1"
    for w in "${WHITELIST[@]}"; do [[ "$k" == "$w" ]] && return 0; done
    return 1
}

# 一个字段是否真的由 kit 产生。
# 两种形态都算数：
#   1. 字面量  —— 脚本里直接写着 VERDICT=、ALL_PASS= 等
#   2. 动态拼接 —— 脚本里是 print(f"HIT_{cat}=...")，字面量 HIT_TOOL_CALL 并不存在，
#      但前缀 HIT_{ 与键名 "TOOL_CALL" 都在源码里。
#      首版只查了字面量，于是把 7 个真实字段误报成孤儿——修法是让它理解拼接，
#      而不是把它们塞进白名单（那等于把闸门拆了）。
field_is_produced() {
    local f="$1"
    grep -rq -- "$f" kit/ --include='*.sh' --include='*.py' 2>/dev/null && return 0

    # 动态拼接：拆成 前缀_ + 余下
    if [[ "$f" == *_* ]]; then
        local prefix="${f%%_*}_"
        local rest="${f#*_}"
        if grep -rq -- "${prefix}{" kit/ --include='*.py' 2>/dev/null \
           && grep -rq -- "\"$rest\"" kit/ --include='*.py' 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# 1) 从正文代码块里抽出所有 UPPER_SNAKE= 的字段名
#
# 递归扫描 book/ 全部子目录（正文已按「部」分目录存放；早期只扫 book/*.md 顶层，
# 结果是新写的规程节根本没被这道闸门覆盖——一道漏掉了大半正文的闸门，
# 比没有闸门更危险，因为它会给你安全感）。
# 排除 _旧稿-回忆录版/：那里是已被取代的素材，其样例过时是已知且已标注的。
FIELDS=()
while IFS= read -r line; do
    [[ -n "$line" ]] && FIELDS+=("$line")
done < <(
    find book -name '*.md' -not -path 'book/_旧稿-回忆录版/*' -print0 2>/dev/null \
    | xargs -0 awk '
        # 只校验「声称是工具输出」的代码块。
        # ```checklist 标记的是人工填写的自检表——它按设计就不由任何脚本产生，
        # 拿它当孤儿字段报警是判据错了，不是正文错了。
        # 这个区分本身就是 DIS-01 的规矩：命令产生的（可溯源）与人写的（转述）不是一回事。
        /^```checklist/ { skip = 1; next }
        /^```/          { if (skip) { skip = 0; next } ; infence = !infence; next }
        skip            { next }
        /^[A-Z][A-Z0-9_]{2,}=/ { print }
      ' 2>/dev/null \
    | grep -oE '^[A-Z][A-Z0-9_]{2,}=' | sed 's/=$//' | sort -u
)

# 空数组在 set -u 下展开会报 unbound variable（bash 3.2）。
# 这里必须与「扫到了但都合规」区分开——扫不到任何字段本身就是可疑信号。
if [[ ${#FIELDS[@]} -eq 0 ]]; then
    echo "FIELDS_CHECKED=0"
    echo "FIELDS_ORPHAN=0"
    echo "VERDICT=NO_SAMPLES_FOUND"
    echo "REASON=正文中未扫到任何 KEY=VALUE 样例，请确认扫描路径是否正确" >&2
    exit 1
fi

missing=0
checked=0
declare -a MISSING_LIST=()

for field in "${FIELDS[@]}"; do
    [[ -z "$field" ]] && continue
    is_whitelisted "$field" && continue
    ((checked++))
    if field_is_produced "$field"; then
        [[ $VERBOSE -eq 1 ]] && echo "  ok      $field"
    else
        echo "  ORPHAN  $field   ← 正文印了它，但 kit/ 里没有任何脚本产生这个字段"
        MISSING_LIST+=("$field")
        ((missing++))
    fi
done

echo "---"
echo "FIELDS_CHECKED=$checked"
echo "FIELDS_ORPHAN=$missing"
if [[ $missing -eq 0 ]]; then
    echo "VERDICT=ALL_SAMPLES_TRACEABLE"
    exit 0
fi
echo "ORPHAN_FIELDS=${MISSING_LIST[*]}"
echo "VERDICT=UNTRACEABLE_SAMPLES_FOUND"
exit 1
