#!/usr/bin/env bash
# reach-probe.sh — 多位置可达性探测：把「哪一段路通」变成判定标量
#
# 配套《把 Agent 送上生产》第 3 章。
#
# 为什么存在：「在服务器上测通了」这句话的信息量，取决于服务器到用户之间
# 还剩多少段路没被覆盖。本机 hairpin 自测能绕过中间链路上的一切问题
# （运营商拦截、CDN、企业代理、DNS 劫持），却给你一个「全绿」的反馈。
#
# 本脚本强制你在拿到 ok 的同时，看到这个 ok 覆盖了多大范围。
#
# 用法：
#   ./reach-probe.sh <host> [port]            # 探测
#   ./reach-probe.sh <host> --via <ssh-alias> # 额外从远端机器探一次
#   ./reach-probe.sh --self-test
#
# 输出：
#   LOCAL_DNS=<ip|fail>
#   LOCAL_TCP=<ok|fail>
#   LOCAL_TLS=<ok|fail|skipped>
#   REMOTE_TCP=<ok|fail|skipped>
#   PATH_COVERAGE=<描述本次实际覆盖了哪几段>
#   VERDICT=<REACHABLE|MIDDLEBOX_SUSPECTED|DNS_PROBLEM|UNREACHABLE|PARTIAL>
#
# 退出码：0=REACHABLE，1=其他判定，2=用法错误

set -uo pipefail

TIMEOUT=8

# ---------- 输入校验（安全边界） ----------

# 主机名白名单：字母数字、点、连字符、冒号(IPv6)。任何引号/分号/空格/反引号一律拒绝。
is_safe_hostname() {
    [[ "$1" =~ ^[A-Za-z0-9._:-]+$ ]]
}
# ssh 目标：额外禁止以 - 开头（会被 ssh 当选项吃掉）
is_safe_via() {
    [[ "$1" =~ ^[A-Za-z0-9._@:-]+$ ]] && [[ "$1" != -* ]]
}
is_safe_port() {
    [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 1 && $1 <= 65535 ))
}

# ---------- 判定逻辑（纯函数，可自测） ----------

# 中间链路可疑的特征：某些位置通、某些位置不通。
# 全通=正常；全不通=服务端或 DNS 问题；不一致=中间有东西在挑人。
adjudicate() {
    local dns="$1" local_tcp="$2" local_tls="$3" remote_tcp="$4"

    # fail-closed：任何一项是「没测到」而非「测到了」，都不许得出乐观结论。
    # 独立评审指出：采集层失败时本工具会把「我没有数据」当成「数据说没问题」——
    # 这正是本书第 1、3 章批评的错误，出现在配套工具里。
    if [[ -z "$dns" || -z "$local_tcp" || -z "$local_tls" ]]; then
        echo "INDETERMINATE_NO_DATA"; return
    fi
    [[ "$local_tcp" == "unknown" || "$local_tls" == "unknown" ]] && { echo "INDETERMINATE_NO_DATA"; return; }
    [[ "$remote_tcp" == "unreachable_vantage" ]] && { echo "INDETERMINATE_VANTAGE_UNREACHABLE"; return; }

    [[ "$dns" == "fail" ]] && { echo "DNS_PROBLEM"; return; }

    # 有远端对照时，位置间不一致是中间设备的典型指纹
    if [[ "$remote_tcp" != "skipped" ]]; then
        if [[ "$local_tcp" != "$remote_tcp" ]]; then
            echo "MIDDLEBOX_SUSPECTED"; return
        fi
    fi

    # TCP 通但 TLS 挂：握手被中途打断，也是中间设备的典型形态
    # （第 3 章那次就是：ClientHello 之后被 RST）
    if [[ "$local_tcp" == "ok" && "$local_tls" == "fail" ]]; then
        echo "MIDDLEBOX_SUSPECTED"; return
    fi

    [[ "$local_tcp" == "fail" ]] && { echo "UNREACHABLE"; return; }
    [[ "$local_tls" == "skipped" ]] && { echo "PARTIAL"; return; }

    # 单观测点不得判 REACHABLE。
    # 独立评审指出：不传 --via（默认用法）时只做了本机 hairpin 探测，
    # 而本工具存在的全部理由就是「本机通不代表用户那条路通」——
    # 从一个位置得出的乐观结论，恰恰是 VER-03 要防的那个错误。
    # 「我只站在一个位置看过」必须与「多个位置都通」区分开。
    [[ "$remote_tcp" == "skipped" ]] && { echo "INDETERMINATE_SINGLE_VANTAGE"; return; }

    echo "REACHABLE"
}

# 覆盖范围描述——本脚本存在的全部意义在这一行
describe_coverage() {
    local remote="$1" segs="local_client→network→target"
    # 只有远端探测真的产出了结论才算覆盖。ssh 连不上时曾被算作「已覆盖」，
    # 于是工具宣称了一段它从未测量过的路径。
    if [[ "$remote" == "ok" || "$remote" == "fail" ]]; then
        segs="$segs + remote_vantage→target"
    elif [[ "$remote" == "unreachable_vantage" ]]; then
        segs="$segs (remote vantage UNREACHABLE — 未覆盖)"
    fi
    echo "$segs"
}

# ---------- 自测 ----------

run_self_test() {
    local pass=0 fail=0
    check() {
        if [[ "$2" == "$3" ]]; then echo "  ok   $1"; ((pass++))
        else echo "  FAIL $1 (got='$2' want='$3')"; ((fail++)); fi
    }

    echo "self-test: adjudicate"
    check "DNS 挂"                "$(adjudicate fail   fail ok      skipped)" "DNS_PROBLEM"
    # 本机全通但只有一个观测点：不许判 REACHABLE（这条曾经断言 REACHABLE，是 fail-open）
    check "单点全通→不定"          "$(adjudicate 1.2.3.4 ok  ok      skipped)" "INDETERMINATE_SINGLE_VANTAGE"
    check "双点一致才算通"          "$(adjudicate 1.2.3.4 ok  ok      ok)"      "REACHABLE"
    # 第 3 章的形态：TCP 能连上，TLS 握手被中途打断
    check "TCP通/TLS挂→中间设备"  "$(adjudicate 1.2.3.4 ok  fail    skipped)" "MIDDLEBOX_SUSPECTED"
    # 本机通、外部不通 —— 正是 hairpin 自测骗人的那次
    check "位置不一致→中间设备"   "$(adjudicate 1.2.3.4 fail ok     ok)"      "MIDDLEBOX_SUSPECTED"
    check "两处都不通→不可达"     "$(adjudicate 1.2.3.4 fail fail   fail)"    "UNREACHABLE"
    check "未测TLS→部分"          "$(adjudicate 1.2.3.4 ok  skipped skipped)" "PARTIAL"

    echo "self-test: 输入校验（安全边界）"
    check "拒绝注入分号" "$(is_safe_hostname "a.com'; id; echo '" && echo yes || echo no)" "no"
    check "拒绝反引号"   "$(is_safe_hostname 'a.com`id`' && echo yes || echo no)" "no"
    check "拒绝空格"     "$(is_safe_hostname 'a.com b' && echo yes || echo no)" "no"
    check "接受正常域名" "$(is_safe_hostname 'docs.example.com' && echo yes || echo no)" "yes"
    check "拒绝 -开头via" "$(is_safe_via '-Efile' && echo yes || echo no)" "no"
    check "接受 user@host" "$(is_safe_via 'root@10.0.0.1' && echo yes || echo no)" "yes"
    check "拒绝非数字端口" "$(is_safe_port '443x' && echo yes || echo no)" "no"
    check "拒绝越界端口"   "$(is_safe_port '70000' && echo yes || echo no)" "no"

    echo "self-test: fail-closed（缺数据不得判乐观）"
    check "空值→不定"      "$(adjudicate '' ok ok skipped)"        "INDETERMINATE_NO_DATA"
    check "unknown→不定"   "$(adjudicate 1.2.3.4 unknown ok skipped)" "INDETERMINATE_NO_DATA"
    check "跳板不可达→不定" "$(adjudicate 1.2.3.4 ok ok unreachable_vantage)" "INDETERMINATE_VANTAGE_UNREACHABLE"

    echo "self-test: describe_coverage"
    check "仅本地" "$(describe_coverage skipped)" "local_client→network→target"
    check "含远端" "$(describe_coverage ok)"      "local_client→network→target + remote_vantage→target"
    check "跳板不可达不算覆盖" "$(describe_coverage unreachable_vantage)" "local_client→network→target (remote vantage UNREACHABLE — 未覆盖)"

    echo
    echo "SELF_TEST_PASS=$pass"
    echo "SELF_TEST_FAIL=$fail"
    [[ $fail -eq 0 ]] && { echo "VERDICT=SELF_TEST_OK"; return 0; }
    echo "VERDICT=SELF_TEST_FAILED"; return 1
}

# ---------- 真实探测 ----------

probe_dns() {
    local host="$1" ip
    ip="$(dscacheutil -q host -a name "$host" 2>/dev/null | awk '/^ip_address/{print $2; exit}')"
    [[ -z "$ip" ]] && ip="$(getent hosts "$host" 2>/dev/null | awk '{print $1; exit}')"
    [[ -z "$ip" ]] && ip="$(python3 -c "import socket,sys;print(socket.gethostbyname(sys.argv[1]))" "$host" 2>/dev/null)"
    echo "${ip:-fail}"
}

probe_tcp() {
    local host="$1" port="$2" out
    # `nc -G` 是 BSD/macOS 专有；Linux 的 netcat-openbsd / nmap-ncat 都不认它，
    # 而 `command -v nc` 又挡住了兜底分支 —— 结果每个 Linux 读者对每个主机
    # 都得到 LOCAL_TCP=fail。自测发现不了，因为自测不碰采集层。
    # 现在优先用 python3（跨平台行为确定）。
    if command -v python3 >/dev/null 2>&1; then
        out="$(python3 -c 'import socket,sys
try:
    socket.create_connection((sys.argv[1], int(sys.argv[2])), float(sys.argv[3])).close()
    print("ok")
except Exception:
    print("fail")' "$host" "$port" "$TIMEOUT" 2>/dev/null)"
        [[ "$out" == "ok" || "$out" == "fail" ]] && { echo "$out"; return; }
    fi
    if command -v nc >/dev/null 2>&1; then
        nc -z -w "$TIMEOUT" "$host" "$port" >/dev/null 2>&1 && echo ok || echo fail
        return
    fi
    echo unknown          # 没有任何可用探测手段 —— 不许伪装成 fail
}

probe_tls() {
    local host="$1" port="$2"
    [[ "$port" != "443" ]] && { echo skipped; return; }
    command -v openssl >/dev/null 2>&1 || { echo skipped; return; }
    local out rc
    # 不用 -brief：macOS 自带的是 LibreSSL，不认这个选项、直接退出 1 →
    # 每个健康 HTTPS 站点都会被判成 MIDDLEBOX_SUSPECTED。
    # 也不再 grep 通用词（LibreSSL 的 usage 文本里恰好含 "cipher"，
    # 原实现只是靠 pipefail 侥幸没误报）。改为看握手是否真的建立。
    out="$(echo | openssl s_client -connect "$host:$port" -servername "$host" 2>&1)"; rc=$?
    if grep -qiE 'unknown option|usage:' <<< "$out"; then echo unknown; return; fi
    if [[ $rc -eq 0 ]] && grep -qiE 'SSL-Session|Cipher *:|Protocol *:' <<< "$out"; then
        echo ok
    else
        echo fail
    fi
}

main() {
    [[ $# -eq 0 ]] && { grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -22; exit 2; }
    [[ "$1" == "--self-test" ]] && { run_self_test; exit $?; }

    local host="$1" port="443" via=""
    shift
    [[ $# -gt 0 && "$1" =~ ^[0-9]+$ ]] && { port="$1"; shift; }
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --via)
                # shift 2 在只剩一个参数时不 shift 任何东西 → while 永不终止，
                # 实测 100% CPU 挂死。改为先检查再消费。
                [[ $# -lt 2 ]] && { echo "--via 缺少值" >&2; exit 2; }
                via="$2"; shift 2 ;;
            *) echo "未知参数: $1" >&2; exit 2 ;;
        esac
    done

    is_safe_hostname "$host" || { echo "非法主机名（仅允许字母数字 . - : _）" >&2; exit 2; }
    is_safe_port "$port"     || { echo "非法端口" >&2; exit 2; }
    if [[ -n "$via" ]]; then
        is_safe_via "$via" || { echo "非法 --via 目标" >&2; exit 2; }
    fi

    local dns tcp tls remote="skipped"
    dns="$(probe_dns "$host")"
    if [[ "$dns" == "fail" ]]; then
        tcp="fail"; tls="skipped"
    else
        tcp="$(probe_tcp "$host" "$port")"
        tls="$(probe_tls "$host" "$port")"
    fi

    if [[ -n "$via" ]]; then
        # 安全说明：$host 曾被直接拼进远端 shell 命令，单引号可闭合 →
        # 远程命令执行。独立评审实测拿到 uid 并在远端落了文件，而本工具仍打印
        # REMOTE_TCP=ok，注入不留痕。--via 按设计指向生产跳板机，故这是高危缺陷。
        # 现在：入口白名单校验（见 main），此处再做一次防御性校验，双保险。
        if ! is_safe_hostname "$host" || ! is_safe_via "$via"; then
            echo "REMOTE_TCP=refused_unsafe_argument" >&2
            remote="skipped"
        else
            local rout
            rout="$(ssh -o ConnectTimeout=10 -o BatchMode=yes \
                    -o StrictHostKeyChecking=accept-new -- "$via" \
                    "bash -c 'exec 3<>/dev/tcp/${host}/${port}' >/dev/null 2>&1 && echo ok || echo fail" \
                    2>/dev/null)"
            # ssh 自身失败（别名错、密钥缺、拒绝 BatchMode）与「远端探测到不通」
            # 必须区分开——前者是我们没测到，后者才是测到了。
            if [[ "$rout" == "ok" ]]; then remote="ok"
            elif [[ "$rout" == "fail" ]]; then remote="fail"
            else remote="unreachable_vantage"; fi
        fi
    fi

    echo "LOCAL_DNS=$dns"
    echo "LOCAL_TCP=$tcp"
    echo "LOCAL_TLS=$tls"
    echo "REMOTE_TCP=$remote"
    echo "PATH_COVERAGE=$(describe_coverage "$remote")"
    local v; v="$(adjudicate "$dns" "$tcp" "$tls" "$remote")"
    echo "VERDICT=$v"
    # 退出码语义与 verify-switch.sh 保持一致：
    # 0 = 通过，1 = 判定为不通过，4 = 测不出（缺数据/缺观测点，按未通过处理）
    case "$v" in
        REACHABLE)       return 0 ;;
        INDETERMINATE_*) return 4 ;;
        *)               return 1 ;;
    esac
}

main "$@"
