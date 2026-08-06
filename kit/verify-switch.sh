#!/usr/bin/env bash
# verify-switch.sh — 切换验真四项检查
#
# 配套《FDE 手册》VER-02 切换验证。
#
# 为什么存在：「功能能用」是间接信号，不是证据。它只能证明「有东西在工作」，
# 不能证明「在工作的是你刚部署的那个东西」。本脚本把 VER-02 的四项检查
# 做成一条命令，并输出人和模型都无法含糊其辞的判定标量。
#
# 用法：
#   ./verify-switch.sh <service> --pattern <进程匹配串> \
#       --expect-version <本次部署的版本标识> --version-cmd <取版本的命令> \
#       --event <业务事件grep串>
#   ./verify-switch.sh --self-test
#
# 输出（stdout，逐行 KEY=VALUE；字段名与 VER-02 正文一致）：
#   SERVICE_ACTIVE=yes|no                        VER-02.1
#   VERSION_MATCH=yes|no|unchecked               VER-02.2
#   STALE_INSTANCES=<n>|unknown                  VER-02.3
#   BUSINESS_EVENT_SINCE_DEPLOY=yes|no|unchecked VER-02.4
#   VERDICT=SWITCHED|NOT_SWITCHED|INDETERMINATE_*
#
# 退出码：0 = SWITCHED，1 = NOT_SWITCHED，2 = 用法错误，
#         4 = INDETERMINATE（有检查项没做成，按未通过处理）
#
# 保守缺省（fail-closed）：四项里任何一项**没做**或**测不出**，一律不判 SWITCHED。
# 「没测」与「测了是好的」必须区分开——这正是本节要防的那类错误。
# VER-02.3 覆盖不到负载均衡器的运行时后端表（脚本无法通用地访问它），
# 该项必须按 VER-02 正文的命令表人工执行。

set -uo pipefail

# ---------- 判定逻辑（纯函数，与数据采集分离，便于自测） ----------

# $1 = systemctl is-active 的原始输出
adjudicate_active() {
    [[ "${1:-}" == "active" ]] && echo "yes" || echo "no"
}

# $1 = ps 输出（格式：ppid cmd，每行一条），$2 = 进程匹配串
# 孤儿 = PPID 为 1 但不是 systemd 直管的残留进程。
# 注意：systemd 直管的主进程 PPID 也是 1，所以必须传入 $3 = 主进程 PID 来排除它。
count_orphans() {
    local ps_output="$1" pattern="$2" main_pid="${3:-}"
    # 采集失败必须与「数到 0 个」区分开。原实现在 ps 不可用时（distroless、
    # hidepid=2、无 procps）吞掉错误并输出 0，于是工具在根本没看到进程表的情况下
    # 判定「旧进程已经没了」——这正是本脚本存在的理由被反过来违反。
    if [[ -z "${ps_output// /}" ]]; then echo "unknown"; return; fi
    # awk -v 会解释 \t \n 等转义，模式里的反斜杠会被静默吞掉；改用环境变量传入
    PAT="$pattern" MAIN="$main_pid" awk '
        BEGIN { pat = ENVIRON["PAT"]; main = ENVIRON["MAIN"] }
        $1 == 1 && index($0, pat) > 0 {
            if (main == "" || $2 != main) n++
        }
        END { print n + 0 }
    ' <<< "$ps_output"
}

# $1 = journal 输出，$2 = 业务事件匹配串
# 未提供匹配串 = 这一项没做，不是这一项通过。
adjudicate_business_event() {
    local journal="$1" pattern="$2"
    [[ -z "$pattern" ]] && { echo "unchecked"; return; }
    grep -qF -- "$pattern" <<< "$journal" && echo "yes" || echo "no"
}

# $1 = 取版本命令的输出，$2 = 期望的版本标识
# 逐字符包含即通过。未提供任一方 = 这一项没做。
adjudicate_version() {
    local got="$1" want="$2"
    [[ -z "$want" ]] && { echo "unchecked"; return; }
    [[ -z "${got// /}" ]] && { echo "no"; return; }   # 取不到版本 ≠ 版本对
    [[ "$got" == *"$want"* ]] && echo "yes" || echo "no"
}

# $1=active $2=stale_instances $3=version_match $4=business_event
adjudicate_verdict() {
    local active="$1" stale="$2" version="$3" event="$4"
    # fail-closed。三类「测不出来」都必须与「测了是好的」区分开：
    #   1) stale="unknown" —— 没采到进程表
    #   2) stale=""        —— bash 里 [[ "" -eq 0 ]] 为真，空字符串会被当成 0
    #   3) version/event="unchecked" —— 这一项压根没做
    # 早期版本把第 3 类当成通过（自测里甚至有一条「业务事件跳过也算过」），
    # 于是不传参数的默认用法会在四项只做了两项的情况下吐 SWITCHED——
    # 一个在最关键的检查上给假绿灯的闸门，正是本手册反复批评的形态。
    if [[ -z "$stale" || ! "$stale" =~ ^[0-9]+$ ]]; then
        echo "INDETERMINATE_NO_PROCESS_DATA"; return
    fi
    if [[ "$version" == "unchecked" ]]; then
        echo "INDETERMINATE_NO_VERSION_CHECK"; return
    fi
    if [[ "$event" == "unchecked" ]]; then
        echo "INDETERMINATE_NO_BUSINESS_EVENT"; return
    fi
    if [[ "$active" == "yes" && "$stale" -eq 0 && "$version" == "yes" && "$event" == "yes" ]]; then
        echo "SWITCHED"
    else
        echo "NOT_SWITCHED"
    fi
}

# ---------- 自测 ----------

run_self_test() {
    local pass=0 fail=0
    check() {
        local name="$1" got="$2" want="$3"
        if [[ "$got" == "$want" ]]; then
            echo "  ok   $name"; ((pass++))
        else
            echo "  FAIL $name (got='$got' want='$want')"; ((fail++))
        fi
    }

    echo "self-test: adjudicate_active"
    check "active"        "$(adjudicate_active active)"     "yes"
    check "failed"        "$(adjudicate_active failed)"     "no"
    check "inactive"      "$(adjudicate_active inactive)"   "no"
    check "empty"         "$(adjudicate_active '')"         "no"

    echo "self-test: count_orphans"
    # fixture：还原第 1 章那晚的真实形态——主进程被 systemd 拉起(PPID=1,pid=178703)，
    # 同时残留 3 个被 init 收养的孤儿子进程。
    local ps_fixture="1 178703 /opt/agent/.venv/bin/python worker.py
1 45501 /opt/agent/.venv/bin/python worker.py
1 45502 /opt/agent/.venv/bin/python worker.py
1 45503 /opt/agent/.venv/bin/python worker.py
3312 9001 /usr/bin/unrelated-process"
    check "3 orphans + 排除主进程" "$(count_orphans "$ps_fixture" "/opt/agent" 178703)" "3"
    check "不传主进程则全计入"     "$(count_orphans "$ps_fixture" "/opt/agent")"        "4"
    check "干净状态"               "$(count_orphans "1 178703 /opt/agent/x.py" "/opt/agent" 178703)" "0"
    check "无匹配"                 "$(count_orphans "$ps_fixture" "/opt/nothing" 178703)" "0"

    echo "self-test: fail-closed（采集失败不得判 SWITCHED）"
    check "ps 输出为空→unknown"  "$(count_orphans "" "/opt/agent" 178703)" "unknown"
    check "unknown→测不出"       "$(adjudicate_verdict yes unknown yes yes)"   "INDETERMINATE_NO_PROCESS_DATA"
    check "空字符串→测不出"       "$(adjudicate_verdict yes "" yes yes)"        "INDETERMINATE_NO_PROCESS_DATA"
    check "非数字→测不出"         "$(adjudicate_verdict yes "abc" yes yes)"     "INDETERMINATE_NO_PROCESS_DATA"

    echo "self-test: 模式含反斜杠不被吞（awk -v 转义坑）"
    check "反斜杠字面匹配" "$(count_orphans "1 100 C:\\jobs\\run.py" "C:\\jobs\\run.py" "")" "1"

    echo "self-test: adjudicate_business_event"
    # 关键区分：只有启动日志 ≠ 干过活。这正是第 1 章那 35 分钟的形态。
    local journal_started_only="May 17 20:46:58 host svc[178703]: registered worker AW_xxx"
    local journal_with_work="May 17 20:46:58 host svc[178703]: registered worker AW_xxx
May 17 20:50:03 host svc[178703]: [ENTRYPOINT] room=call-0001"
    check "只有启动日志"   "$(adjudicate_business_event "$journal_started_only" '[ENTRYPOINT]')" "no"
    check "有业务事件"     "$(adjudicate_business_event "$journal_with_work" '[ENTRYPOINT]')"    "yes"
    check "未指定=没做"    "$(adjudicate_business_event "$journal_with_work" '')"                "unchecked"

    echo "self-test: adjudicate_version（VER-02.2）"
    check "逐字包含即通过"   "$(adjudicate_version 'build=7f3a91c' '7f3a91c')" "yes"
    check "版本对不上"       "$(adjudicate_version 'build=0000000' '7f3a91c')" "no"
    check "取不到版本≠通过"  "$(adjudicate_version '' '7f3a91c')"              "no"
    check "未提供期望=没做"  "$(adjudicate_version 'build=7f3a91c' '')"        "unchecked"

    echo "self-test: adjudicate_verdict（四项全对才通过）"
    check "四项全对"           "$(adjudicate_verdict yes 0 yes yes)"       "SWITCHED"
    check "有残留→不算"        "$(adjudicate_verdict yes 3 yes yes)"       "NOT_SWITCHED"
    check "服务没起→不算"      "$(adjudicate_verdict no 0 yes yes)"        "NOT_SWITCHED"
    check "版本对不上→不算"    "$(adjudicate_verdict yes 0 no yes)"        "NOT_SWITCHED"
    check "起了但没干活→不算"  "$(adjudicate_verdict yes 0 yes no)"        "NOT_SWITCHED"

    echo "self-test: fail-closed（没做的检查不得算通过）"
    check "没做版本核对→测不出"   "$(adjudicate_verdict yes 0 unchecked yes)"       "INDETERMINATE_NO_VERSION_CHECK"
    check "没做业务事件→测不出"   "$(adjudicate_verdict yes 0 yes unchecked)"       "INDETERMINATE_NO_BUSINESS_EVENT"
    check "两项都没做→测不出"     "$(adjudicate_verdict yes 0 unchecked unchecked)" "INDETERMINATE_NO_VERSION_CHECK"
    check "进程数据缺失优先报"    "$(adjudicate_verdict yes unknown unchecked yes)" "INDETERMINATE_NO_PROCESS_DATA"

    echo
    echo "SELF_TEST_PASS=$pass"
    echo "SELF_TEST_FAIL=$fail"
    [[ $fail -eq 0 ]] && { echo "VERDICT=SELF_TEST_OK"; return 0; }
    echo "VERDICT=SELF_TEST_FAILED"; return 1
}

# ---------- 真实采集 ----------

run_live() {
    local service="$1" pattern="$2" event="$3" expect_version="$4" version_cmd="$5"

    command -v systemctl >/dev/null 2>&1 || {
        # 曾经只写 stderr：管道里 grep VERDICT 会拿到空结果而非错误。
        echo "VERDICT=UNSUPPORTED_PLATFORM"
        echo "REASON=requires_systemd" 
        exit 3
    }

    local active_raw main_pid ps_out journal_out since
    active_raw="$(systemctl is-active "$service" 2>/dev/null || true)"
    main_pid="$(systemctl show -p MainPID --value "$service" 2>/dev/null || echo '')"
    [[ "$main_pid" == "0" ]] && main_pid=""
    since="$(systemctl show -p ActiveEnterTimestamp --value "$service" 2>/dev/null || echo '')"

    ps_out="$(ps -eo ppid,pid,cmd --no-headers 2>/dev/null || ps -eo ppid,pid,command 2>/dev/null)"
    if [[ -n "$since" ]]; then
        journal_out="$(journalctl -u "$service" --since "$since" --no-pager 2>/dev/null || true)"
    else
        journal_out="$(journalctl -u "$service" --no-pager -n 500 2>/dev/null || true)"
    fi

    local version_out=""
    if [[ -n "$version_cmd" ]]; then
        version_out="$(eval "$version_cmd" 2>/dev/null || true)"
    fi

    local a o m b v
    a="$(adjudicate_active "$active_raw")"
    o="$(count_orphans "$ps_out" "$pattern" "$main_pid")"
    m="$(adjudicate_version "$version_out" "$expect_version")"
    b="$(adjudicate_business_event "$journal_out" "$event")"
    v="$(adjudicate_verdict "$a" "$o" "$m" "$b")"

    echo "SERVICE_ACTIVE=$a"
    echo "VERSION_MATCH=$m"
    echo "STALE_INSTANCES=$o"
    echo "BUSINESS_EVENT_SINCE_DEPLOY=$b"
    echo "VERDICT=$v"
    # VER-02.3 的负载均衡器后端表本脚本覆盖不到，提醒必须人工执行
    echo "NOTE=lb_backend_table_not_covered_check_manually"
    case "$v" in
        SWITCHED)         return 0 ;;
        INDETERMINATE_*)  return 4 ;;
        *)                return 1 ;;
    esac
}

# ---------- 入口 ----------

main() {
    [[ $# -eq 0 ]] && { grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -20; exit 2; }
    [[ "$1" == "--self-test" ]] && { run_self_test; exit $?; }

    local service="$1" pattern="" event="" expect_version="" version_cmd=""
    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --pattern)
                [[ $# -lt 2 ]] && { echo "--pattern 缺少值" >&2; exit 2; }
                pattern="$2"; shift 2 ;;
            --event)
                [[ $# -lt 2 ]] && { echo "--event 缺少值" >&2; exit 2; }
                event="$2"; shift 2 ;;
            --expect-version)
                [[ $# -lt 2 ]] && { echo "--expect-version 缺少值" >&2; exit 2; }
                expect_version="$2"; shift 2 ;;
            --version-cmd)
                [[ $# -lt 2 ]] && { echo "--version-cmd 缺少值" >&2; exit 2; }
                version_cmd="$2"; shift 2 ;;
            *) echo "未知参数: $1" >&2; exit 2 ;;
        esac
    done
    [[ -z "$pattern" ]] && { echo "必须提供 --pattern（进程匹配串）" >&2; exit 2; }
    # --expect-version 与 --version-cmd 必须成对；只给一个是用法错误，
    # 不是「这项跳过」——否则又回到了「没测被当成测过」的老路。
    if [[ -n "$expect_version" && -z "$version_cmd" ]] || [[ -z "$expect_version" && -n "$version_cmd" ]]; then
        echo "--expect-version 与 --version-cmd 必须同时提供" >&2; exit 2
    fi

    run_live "$service" "$pattern" "$event" "$expect_version" "$version_cmd"
}

main "$@"
