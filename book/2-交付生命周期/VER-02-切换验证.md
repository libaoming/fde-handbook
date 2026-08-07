# VER-02 · 切换验证：确认接活的是新版本

2020 年 Slack 的一次事故里，磁盘配置正确、进程健康、流量正常，三件事同时成立——
而新部署的实例一个请求都没接到（案例 PM-01）。「部署完成」和「切换完成」是两回事，
中间隔着本节的四项检查。

**目的**　部署动作执行完之后，判断这次切换是否真的完成——即确认**正在处理真实流量的，
就是你刚部署的那个版本**。本节给出四项检查与一个可粘贴的判定输出。

**前置条件**

- 部署或切换动作已执行（本节不负责部署本身，见 DEP-01）
- 你能访问服务管理器或编排器（systemd / Kubernetes / 进程管理器 / 负载均衡器管理接口）
- 目标服务的日志可读，且日志里能区分「启动事件」与「业务事件」
- 已知本次部署的版本标识（构建号、镜像摘要、commit 短哈希，任选其一但必须唯一）

---

## 规程

四项检查全部通过才算切换完成。**任何一项不通过，本次切换按未完成处理。**

![四项检查的判定流：四项全是才输出 SWITCHED；任一项为否输出 NOT_SWITCHED；任一项没做或测不出输出 INDETERMINATE，按未通过处理](../figures/ver02-four-checks.svg)

### VER-02.1　服务管理器认为它在运行

| 环境 | 命令 | 通过判据 |
|---|---|---|
| systemd | `systemctl is-active <svc>` | 输出 `active`，退出码 0 |
| Kubernetes | `kubectl get pods -l app=<svc>` | 目标 Pod `Running` 且 `READY` 分子=分母 |
| 容器 | `docker ps --filter name=<svc>` | 容器在列且状态为 `Up` |

> `systemctl is-active` 在至少一个单元处于活动状态时返回退出码 0，否则返回非零
> （`systemctl(1)`，man7.org 官方手册镜像：
> https://man7.org/linux/man-pages/man1/systemctl.1.html ）。

**这一项排除的是**：以为启动了、其实启动失败。**它不能证明任何别的事。**

### VER-02.2　正在响应的实例，版本对得上

不要问「服务活着吗」，要问「**回答我的这个东西，是哪个版本**」。

- 让服务暴露一个版本端点（`/version` 返回构建号或 commit 哈希），部署后直接查；
- 没有版本端点时，退路的锚点必须仍是**不可变标识**：
  - 容器：查镜像摘要（digest，不是 tag——tag 会被覆盖），与本次部署的 digest 逐字符比对；
  - 裸进程（Linux）：对**运行中进程的可执行文件真身**做校验和——`sha256sum /proc/<PID>/exe`，
    与本次部署产物的 sha256 逐字符比对。顺手 `ls -l /proc/<PID>/exe`：显示 `(deleted)`
    即磁盘文件已被替换而进程还跑着旧二进制——这本身就是「未切换」的直接证据；
  - 解释型服务（可执行文件是解释器，代码在脚本里）：从命令行定位实际加载的入口文件，
    对它做同样的校验和比对。

  启动时间与命令行只是辅助信号：启动时间新只证明「重启过」，不证明「跑的是新版」
  ——重启一个旧二进制，启动时间同样是新的。

**通过判据**：查到的版本标识 == 本次部署的版本标识，**逐字符相等**。

> ⚠️ 用镜像 tag（如 `:latest`、`:prod`）核对**不成立**——同一个 tag 可以指向不同镜像。
> 必须用不可变标识（digest / 构建号 / commit 哈希）。
>
> ⚠️ **Web 交付另有一层**：你查到的版本来自源站还是边缘节点？
> CDN 与浏览器缓存持有旧资源，是「部署完了改动没生效」在 Web 场景的头号原因。
> 带 cache-busting 参数查一次、直连源站再查一次，两次都要对上。

### VER-02.3　旧实例已经清干净

**这是最常被跳过、也最常出事的一项。** 「新的起来了」和「旧的死透了」是两件独立的事，
两者都为真才叫切换。

| 环境 | 检查 | 通过判据 |
|---|---|---|
| 进程 | `systemctl show -p MainPID <svc>` 取当前主进程，再列同名进程 | 排除当前主进程后，无 PPID=1 的同名残留（启动时间早于本次部署＝实锤） |
| 容器/编排 | 列出全部副本 | 无旧版本副本处于 Running |
| 负载均衡 | **查运行时后端表**，见下表 | 后端列表中无旧实例地址 |

⚠️ 进程残留**不能单看「PPID=1」**——systemd 直管服务的正常主进程 PPID 也是 1，
单看这一条会把刚起的新实例误判成残留。先取当前登记的主进程把它排除
（`systemctl show -p MainPID <svc>`），剩下的同名 PPID=1 进程才是被收养的孤儿；
再用启动时间复核：`ps -eo pid,ppid,lstart,cmd` 里启动早于本次部署时刻
（`systemctl show -p ActiveEnterTimestamp <svc>` 可取）的即残留。
`kit/verify-switch.sh` 用的就是这条逻辑（PPID=1 且 PID≠MainPID 计为孤儿）。

**负载均衡这一项必须单独给命令**，因为它是本节最容易出事、也最容易被「看配置文件」蒙混过去的一项：

| LB | 读运行时状态的命令 |
|---|---|
| HAProxy | `echo "show servers state" \| socat stdio /var/run/haproxy.sock` |
| Envoy | `curl -s localhost:15000/clusters` |
| Nginx Plus | `curl -s http://127.0.0.1/api/*/http/upstreams` |
| Kubernetes | `kubectl get endpointslices -l kubernetes.io/service-name=<svc>` |
| 开源 Nginx | ⚠️ 无运行时查询接口——走下方「开源 Nginx 三步替代」 |

**你的 LB 不在此列时，只需问一句：这个接口读的是磁盘，还是内存？**
读磁盘的一律不算数。配置文件是「期望」，运行时表才是「事实」，
两者可以长期不一致而不报任何错——本节案例 PM-01 正是这个形态：

![磁盘上的配置正确，但进程内存里的后端表停在旧值：流量仍流向旧实例，新实例从未接到流量。读磁盘的检查给假绿灯，只有查运行时表能看见](../figures/ver02-disk-vs-runtime.svg)

**开源 Nginx 三步替代**（无运行时接口时的组合判据，三步全过才算本项通过）：

| 步 | 命令 | 通过判据 | 它证明什么 |
|---|---|---|---|
| 1 | `nginx -T \| grep <旧实例地址>` | 零命中 | 磁盘配置已无旧地址——只证**意图**（`nginx -T` 读的是配置文件，不是运行时状态） |
| 2 | `ps -o pid,etime,cmd -C nginx` | 全部 worker 的运行时长（`etime`）短于「距 reload 已过的时间」 | reload 确已发生——worker 是 reload 时新起的；旧 worker 在优雅退出期内暂存属正常，等它处理完存量连接 |
| 3 | 部署后 `tail` 旧实例的 access log | 零新增条目（同时 VER-02.4 的唯一标识命中新实例日志） | 流量真的不再走旧后端——三步里唯一的**直接证据** |

第 1 步证意图、第 2 步证动作、第 3 步证结果；缺第 3 步，前两步只是「应该切了」。

旧进程为什么会活下来、为什么「服务已停止」不等于进程都死了——
机理与出处见常见误判「停止了服务，所以旧进程都死了」。

### VER-02.4　它真的干过活

前三项只证明「它站起来了」，这一项证明「**活落在了它头上**」。

**通过判据**：主动打一次带**唯一标识**的真实业务请求，然后在服务日志中 grep 该标识，
命中即通过。标识可以是随机 request-id、订单号，或本次部署的短哈希——
关键是它**不可能来自上一次**。

不要用「日志里有业务事件」这种判据：在一套你不熟的服务日志里，
你分不清哪一行是业务事件、哪一行是健康检查。**用一个只属于这一次的标识把它钉死**，
判断就从「主观识别」变成了「grep 命中与否」。（同一手法在 DIS-03.2 有更一般的表述。）

---

## 常见误判

**「功能能用，所以切换成功了」**
功能能用只证明有某个东西在响应，不证明响应的是你刚部署的那个。
用户视角的黑盒验证与「哪个版本在服务」的白盒问题，是两类不同的证据
——Google SRE 把这两类监控明确分开：黑盒是「以用户所见的方式测试外部可见行为」，
白盒是「基于系统内部暴露的指标」
（*Site Reliability Engineering*, Ch.6：https://sre.google/sre-book/monitoring-distributed-systems/ ）。
**拿黑盒的答案回答白盒的问题，是这类事故的标准起点。**

> 边界：SRE 书主张两类监控**互补**，不是黑盒无用。本节只借它区分证据类型，
> 不构成「黑盒验证可以省略」的主张。

**「配置文件是对的，所以生效的配置是对的」**
磁盘上的内容是期望值，运行时加载的才是事实。两者可以静默地长期不一致（PM-01）。

**「停止了服务，所以旧进程都死了」**
杀掉父进程，子进程不会跟着死。POSIX 规定，进程退出后它的子进程与僵尸进程的父进程 ID
「shall be set to the process ID of an implementation-defined system process」——
也就是被 init/systemd 收养后继续运行
（POSIX.1-2017 `_exit()`：https://pubs.opengroup.org/onlinepubs/9699919799/functions/_exit.html ）。
systemd 手册对只杀主进程（`KillMode=process`）的评语是一个带感叹号的「不推荐」：
这会让进程「escape the service manager's lifecycle and resource management, and to
remain running **even while their service is considered stopped**」——
**服务被认为已停止，不等于进程都死了**
（`systemd.kill(5)`，man7.org 官方手册镜像：
https://man7.org/linux/man-pages/man5/systemd.kill.5.html ）。
所以 VER-02.3 数的是残留进程本身，不是服务状态。

**「探测了一次，通过了」**
配置与镜像的分发通常是渐进的，同一时刻不同节点可能跑着不同版本。
单点单次探测可能恰好命中已完成的那部分，给出「已恢复」的假信号（PM-02）。
**多节点、重复采样**——覆盖判据是两个问题：横向，采样是否覆盖了全部节点
（或至少每个分组各有样本）；纵向，采样是否横跨了**至少一个完整的下发周期**。
PM-02 里那个周期是 5 分钟，你的系统的周期是多少，要先问出来——
在下发周期内做的任何次数的采样，都只是同一时刻的重复。

**「在新环境验证过了」**
全新节点的启动顺序与存量节点不同，某些故障**只在存量节点重启时才显现**——
这意味着新环境的绿灯对存量环境没有证明力（PM-05）。**验证必须在存量运行节点上做。**

**「监控没报警，所以没问题」**
如果监控与被监控系统共享依赖，故障发生时验证手段会和故障一起消失——
此时的沉默不是绿灯（PM-04，案例全文见 VER-01）。

---

## 判定标准

四项全部通过才输出 `SWITCHED`。建议让脚本直接吐出判定标量，而不是让人读三段输出自己下结论
（理由见 DIS-02）：

```
SERVICE_ACTIVE=yes                # VER-02.1
VERSION_MATCH=yes                 # VER-02.2  部署版本 == 响应版本
STALE_INSTANCES=0                 # VER-02.3  进程/副本残留数
BUSINESS_EVENT_SINCE_DEPLOY=yes   # VER-02.4  唯一标识已在日志中命中
VERDICT=SWITCHED
```

任一项为否 → `VERDICT=NOT_SWITCHED`，**不得进入 VER-05 验收**。

**参考实现**：`kit/verify-switch.sh`（systemd 场景，含 29 条自测用例）。
它不覆盖全部四项——一个覆盖范围不明的验证脚本，本身就是另一盏假绿灯，
所以用法与覆盖范围如下，逐项说清：

```
./kit/verify-switch.sh <service> --pattern <进程匹配串> \
    --expect-version <本次版本标识> --version-cmd <取版本的命令> \
    --event <本次唯一标识>
```

| 检查项 | 脚本是否覆盖 |
|---|---|
| VER-02.1 服务活着 | ✅ |
| VER-02.2 版本对得上 | ✅ 需传 `--expect-version` 与 `--version-cmd`（缺一即用法错误） |
| VER-02.3 残留清零 | ⚠️ **仅覆盖进程残留**；**负载均衡器的运行时后端表脚本读不到**，必须按上面的命令表人工执行。脚本会输出 `NOTE=lb_backend_table_not_covered_check_manually` 提醒 |
| VER-02.4 它干过活 | ✅ 需传 `--event` |

退出码：`0`=SWITCHED，`1`=NOT_SWITCHED，`4`=测不出（`INDETERMINATE_*`），
`3`=非 systemd 环境（脚本只支持 systemd，其他环境按上文命令表人工执行四项），`2`=用法错误。
版本参数的两种漏传是两种码：**只传一个**（`--expect-version` 与 `--version-cmd` 缺一）
是用法错误，退出码 2；**两个都不传**是「没做版本核对」，按测不出处理，退出码 4。

> **保守缺省**：四项中任何一项**没做**或**测不出**（工具不可用、权限不足、日志缺失、
> 未传对应参数），一律按**未通过**处理。脚本对此是 fail-closed 的——
> 没传版本参数会得到 `VERDICT=INDETERMINATE_NO_VERSION_CHECK` 并以退出码 4 结束，
> **不会**因为「没检查」而输出 `SWITCHED`。
>
> 这条缺省与一条业界通行的分级原则同构：拿不准时按更坏的情况走，事后复盘再降级
> ——PagerDuty 事故响应手册把它写作 **"Always Assume The Worst"**
> （https://response.pagerduty.com/before/severity_levels/ ）。
> 该原则原本用于事故严重度分级，这里是**类比借用**，不是它的原始适用范围。

---

## 示例走查：一次完整执行

> 本节是**操作走查**，不是事故记录：按顺序列出你在一次真实切换后要跑的命令、
> 每条命令回答哪一问、以及判定输出的三种形态。命令是可直接抄的；
> 判定输出的字段与取值由 `kit/verify-switch.sh` 定义（见文末真实自测输出）。

设定：你刚在一台 systemd 机器上部署了 `orders-api` 服务，本次构建号 `build-4187`，
服务暴露 `/version` 端点。逐项走查：

| 步骤 | 命令 | 它回答哪一问 |
|---|---|---|
| 1 | `systemctl is-active orders-api` | VER-02.1：服务管理器认为它在运行吗 |
| 2 | `curl -s localhost:8080/version` | VER-02.2：**回答我的这个东西**是 `build-4187` 吗（逐字符比对） |
| 3 | `systemctl show -p MainPID orders-api`，再 `ps -eo pid,ppid,lstart,cmd \| grep orders-api` | VER-02.3a：排除当前主进程后，有没有 PPID=1 且启动早于本次部署的残留 |
| 4 | 按 VER-02.3 命令表查 LB 运行时后端表 | VER-02.3b：后端表里还有没有旧实例地址（**脚本覆盖不到，必须人工**） |
| 5 | 发一笔带唯一标识的真实请求，再 `grep <标识> 日志` | VER-02.4：活真的落在了它头上吗 |

五步合成一条命令（第 4 步除外）：

```
./kit/verify-switch.sh orders-api --pattern orders-api \
    --expect-version build-4187 \
    --version-cmd "curl -s localhost:8080/version" \
    --event "req-$(date +%s)-$RANDOM"
```

**判定输出的三种形态**（字段名与本节检查项一一对应）：

- 四项全过——退出码 0，可进入 VER-05：

  ```
  SERVICE_ACTIVE=yes
  VERSION_MATCH=yes
  STALE_INSTANCES=0
  BUSINESS_EVENT_SINCE_DEPLOY=yes
  VERDICT=SWITCHED
  NOTE=lb_backend_table_not_covered_check_manually
  ```

  注意最后一行：即使 `SWITCHED`，脚本也会提醒 LB 后端表未覆盖——
  第 4 步没做完，这个 `SWITCHED` 就还不完整。

- 旧实例有残留——退出码 1，回去清理后**重跑全部四项**：

  ```
  STALE_INSTANCES=2
  VERDICT=NOT_SWITCHED
  ```

- 忘了传版本参数——退出码 4，**不会**因为「没检查」而放行：

  ```
  VERSION_MATCH=unchecked
  VERDICT=INDETERMINATE_NO_VERSION_CHECK
  ```

  这是 fail-closed 的含义：「没测」与「测了是好的」在输出上必须可区分。

**脚本自身的可信度**：它带 29 条自测用例，覆盖判定逻辑与 fail-closed 缺省。
以下为 2026-08-07 在本手册仓库实跑 `bash kit/verify-switch.sh --self-test` 的输出摘录
（`reproducible` 档：读者可自行复跑）：

```
self-test: adjudicate_verdict（四项全对才通过）
  ok   四项全对
  ok   有残留→不算
  ok   服务没起→不算
  ok   版本对不上→不算
  ok   起了但没干活→不算
self-test: fail-closed（没做的检查不得算通过）
  ok   没做版本核对→测不出
  ok   没做业务事件→测不出
  ok   两项都没做→测不出
  ok   进程数据缺失优先报

SELF_TEST_PASS=29
SELF_TEST_FAIL=0
VERDICT=SELF_TEST_OK
```

---

## 案例证据

> ### 案例 PM-01 · 公开事故复盘｜Slack，2020
>
> 一次容量伸缩后，负载均衡器上的**新实例始终没有接到流量**。
>
> 官方复盘原文：同步程序「always attempted to find a slot for new webapp instances
> before it freed slots taken up by old webapp instances that were no longer running.
> This program began to fail and exit early because it was unable to find any empty slots,
> meaning that the running HAProxy instances weren't getting their state updated.」
>
> **它验证了 VER-02.3 为什么必须查运行时后端表**：consul-template 渲染出的主机列表
> 完全正确，任何「看配置文件」的检查都会通过；而 HAProxy 进程内存里的后端表停在旧状态。
> 磁盘正确 + 进程健康 + 流量正常，三者同时成立，新实例却一个请求都没接到。
>
> 出处：https://slack.engineering/a-terrible-horrible-no-good-very-bad-day-at-slack/
> ｜不可外推：这是 HAProxy Runtime API 特定的槽位复用逻辑，不能据此论断所有 LB 都会静默保留旧后端。

> ### 案例 PM-05 · 公开事故复盘｜Datadog，2023
>
> 一次多区域网络故障，根因是一个**装上之后没有立刻生效**的更新：
> "a security update to systemd was automatically applied to a number of VMs, which caused
> a latent adverse interaction in the network stack (on Ubuntu 22.04 via systemd v249)
> to manifest upon systemd-networkd restarting."——磁盘上的包版本与运行中进程的版本
> 长期不一致，故障要等进程重启那一刻才显现。
>
> 更关键的是官方复盘对「为什么测试没拦住」的解释：
> "neither a fresh node nor a rebooted node exhibit this behavior because during a normal
> boot sequence systemd-networkd always starts before routing rules are installed by the
> CNI plugin."——**全新节点与重启节点的启动顺序不同，故障只在存量运行节点上显现**。
> 任何在新环境做的验证都必然通过，且这份「通过」对存量环境毫无证明力。
>
> **它验证了本节两条规矩**：VER-02.2 的「安装 ≠ 生效」（版本核对必须问运行中的进程，
> 不是磁盘上的包），以及常见误判里的「验证必须在存量运行节点上做」。
>
> 出处：https://www.datadoghq.com/blog/2023-03-08-multiregion-infrastructure-connectivity-issue/
> ｜不可外推：绑定 Ubuntu 22.04 + systemd v249 + CNI 的具体组合，不能写成「自动安全更新普遍危险」。

> ### 案例 PM-02 · 公开事故复盘｜Cloudflare，2025
>
> 一次全网故障中，一个特征文件由数据库集群每 5 分钟生成一次，而集群正在灰度升级：
> "every five minutes there was a chance of either a good or a bad set of configuration
> files being generated and rapidly propagated across the network. This fluctuation made
> it unclear what was happening as the entire system would recover and then fail again"——
> 系统在恢复与崩溃之间横跳，且 "Initially, this led us to believe this might be caused
> by an attack."
>
> **它验证了「探测了一次，通过了」为什么是误判**：分发是渐进的，单点单次采样有相当
> 概率恰好命中好的那一批，给出「已恢复」的假信号——并把排查引向完全错误的方向
> （误判为攻击）。采样必须覆盖多节点、横跨至少一个完整下发周期。
>
> 出处：https://blog.cloudflare.com/18-november-2025-outage/
> ｜不可外推：波动源于上游权限变更的特定 bug，不能用来论证「配置灰度本身有害」。

> ### 案例 PM-09 · 公开事故复盘｜GitLab，2017
>
> 数据库事故后需要恢复备份时才发现：
> "The standard backup procedure uses pg_dump to perform a logical backup of the database.
> This procedure failed silently."——备份任务天天在跑，产物一直是空的。
> 失败通知也没送到："Unfortunately DMARC was not enabled for the cronjob emails,
> resulting in them being rejected by the receiver. This means we were never aware of
> the backups failing, until it was too late."
>
> **它验证了 VER-02.4 的锚点选择**：「任务在跑」「没收到告警」都是间接信号；
> 自动化动作的验收锚点是**产物本身**（对备份：产物存在、非空、且能恢复出来）。
> 把这条平移到切换验证：进程在跑不算数，**带唯一标识的业务事件落进了新实例的日志**才算数。
>
> 出处：https://about.gitlab.com/blog/2017/02/10/postmortem-of-database-outage-of-january-31/
> ｜不可外推：pg_dump 版本不匹配的具体故障，不可推广为「逻辑备份不可靠」。

> ### 案例 · 合成示例（教学场景，非真实事故）
>
> 一次滚动更新中，编排器报告新副本 `Running` 且就绪探针通过，服务对外正常。
> 但就绪探针只检查了进程端口是否监听，而新副本所需的配置项拉取失败，
> 代码走了兜底分支返回缓存结果——**请求全部成功，返回的却全是旧数据**。
>
> 本例说明 VER-02.4 为什么要断言**业务事件**而不是心跳：
> 探针测的是「进程在不在」，业务事件测的是「活干得对不对」。
>
> ⚠️ **本例为本手册构造的教学场景，不是真实事故记录**，不含任何真实读数。
> 同类真实形态可参见 PM-03（配置服务返回合法空结果，进程健康、HTTP 200、内容是错的；案例全文见 VER-04）。

---

## 相关小节

- **DEP-01 部署与切换**——本节的上游；切换动作本身怎么做
- **VER-03 可达性验证**——用户那条路通不通（本节只回答「谁在接活」，不回答「用户到得了吗」）
- **VER-05 验收与签收**——本节输出 `SWITCHED` 是进入验收的前置条件
- **DIS-01 证据分级**——「功能能用」为什么是信号而不是证据
- **DIS-02 三道焊缝**——为什么要让命令吐判定标量，而不是让人读输出
- **DIS-03 助手产出验证**——VER-02.4「唯一标识钉死」手法的一般形式（DIS-03.2）
- **附录 A · FX-SVC-01**——症状「部署后改动似乎没生效」的速查入口
- **附录 B · B-VER-02**——本节四项检查的可打印版本
