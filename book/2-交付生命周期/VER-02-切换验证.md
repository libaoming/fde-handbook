# VER-02 · 切换验证：确认接活的是新版本

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
- 没有版本端点时，退而查进程或镜像：容器看镜像摘要（digest，不是 tag——tag 会被覆盖），
  进程看启动时间与命令行。

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
| 进程 | 列出同类进程，核对父进程与启动时间 | 无「父进程为 1（被 init 收养）且早于本次部署」的残留 |
| 容器/编排 | 列出全部副本 | 无旧版本副本处于 Running |
| 负载均衡 | **查运行时后端表**，见下表 | 后端列表中无旧实例地址 |

**负载均衡这一项必须单独给命令**，因为它是本节最容易出事、也最容易被「看配置文件」蒙混过去的一项：

| LB | 读运行时状态的命令 |
|---|---|
| HAProxy | `echo "show servers state" \| socat stdio /var/run/haproxy.sock` |
| Envoy | `curl -s localhost:15000/clusters` |
| Nginx Plus | `curl -s http://127.0.0.1/api/*/http/upstreams` |
| Kubernetes | `kubectl get endpointslices -l kubernetes.io/service-name=<svc>` |
| 开源 Nginx | ⚠️ 无运行时查询接口。`nginx -T` 读的是**配置**不是运行时状态——正是本项要防的东西。只能靠「重载后核对 worker 进程启动时间」间接判断 |

**你的 LB 不在此列时，只需问一句：这个接口读的是磁盘，还是内存？**
读磁盘的一律不算数。配置文件是「期望」，运行时表才是「事实」，
两者可以长期不一致而不报任何错——本节案例 PM-01 正是这个形态。

> **为什么旧进程会活下来**：杀掉父进程，子进程不会跟着死。POSIX 规定，进程退出后
> 它的子进程与僵尸进程的父进程 ID「shall be set to the process ID of an
> implementation-defined system process」——也就是被 init/systemd 收养后继续运行。
> （POSIX.1-2017 `_exit()`：https://pubs.opengroup.org/onlinepubs/9699919799/functions/_exit.html ）
>
> systemd 手册对只杀主进程（`KillMode=process`）的评语是一个带感叹号的「不推荐」：
> 这会让进程「escape the service manager's lifecycle and resource management, and to
> remain running **even while their service is considered stopped**」——
> **服务被认为已停止，不等于进程都死了。**
> （`systemd.kill(5)`，man7.org 官方手册镜像：
> https://man7.org/linux/man-pages/man5/systemd.kill.5.html
> ——freedesktop.org 原站拒绝抓取，内容同源）

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

**「探测了一次，通过了」**
配置与镜像的分发通常是渐进的，同一时刻不同节点可能跑着不同版本。
单点单次探测可能恰好命中已完成的那部分，给出「已恢复」的假信号（PM-02）。
**多节点、重复采样。**

**「在新环境验证过了」**
全新节点的启动顺序与存量节点不同，某些故障**只在存量节点重启时才显现**——
这意味着新环境的绿灯对存量环境没有证明力（PM-05）。**验证必须在存量运行节点上做。**

**「监控没报警，所以没问题」**
如果监控与被监控系统共享依赖，故障发生时验证手段会和故障一起消失——
此时的沉默不是绿灯（PM-04）。

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
用法与覆盖范围必须说清楚，否则它就成了本节自己批评的那种「给假绿灯的闸门」：

```
./verify-switch.sh <service> --pattern <进程匹配串> \
    --expect-version <本次版本标识> --version-cmd <取版本的命令> \
    --event <本次唯一标识>
```

| 检查项 | 脚本是否覆盖 |
|---|---|
| VER-02.1 服务活着 | ✅ |
| VER-02.2 版本对得上 | ✅ 需传 `--expect-version` 与 `--version-cmd`（缺一即用法错误） |
| VER-02.3 残留清零 | ⚠️ **仅覆盖进程残留**；**负载均衡器的运行时后端表脚本读不到**，必须按上面的命令表人工执行。脚本会输出 `NOTE=lb_backend_table_not_covered_check_manually` 提醒 |
| VER-02.4 它干过活 | ✅ 需传 `--event` |

退出码：`0`=SWITCHED，`1`=NOT_SWITCHED，`4`=测不出（`INDETERMINATE_*`），`2`=用法错误。

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
> 同类真实形态可参见 PM-03（配置服务返回合法空结果，进程健康、HTTP 200、内容是错的）。

---

## 相关小节

- **DEP-01 部署与切换**——本节的上游；切换动作本身怎么做
- **VER-03 可达性验证**——用户那条路通不通（本节只回答「谁在接活」，不回答「用户到得了吗」）
- **VER-05 验收与签收**——本节输出 `SWITCHED` 是进入验收的前置条件
- **DIS-01 证据分级**——「功能能用」为什么是信号而不是证据
- **DIS-02 三道焊缝**——为什么要让命令吐判定标量，而不是让人读输出
- **附录 A · FX-SVC-01**——症状「部署后改动似乎没生效」的速查入口
- **附录 B（未成稿）**——本节四项检查的可打印版本
