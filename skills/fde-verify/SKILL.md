---
name: fde-verify
description: 部署后切换验真（fail-closed）。Use AFTER deploying, switching, restarting, or releasing a service; BEFORE claiming a deploy/rollout/上线/切换 succeeded; or when the user asks to 验证部署 / verify a deployment. Runs four checks and emits verdict scalars — any unchecked item yields INDETERMINATE, never SWITCHED.
---

# fde-verify · 切换验真

**功能能用只证明有东西在响应，不证明响应的是你刚部署的那个。**
服务显示 `active`、配置文件正确、页面能打开——都是**假绿灯**的常见形态：
接活的可能仍是上一版进程、旧副本或负载均衡器内存里的旧后端。
本 skill 在每次部署/切换后跑四项检查，输出机器可判的判定标量。

## 步骤

1. **集齐三样东西**（缺任何一样，走 fail-closed，不猜）：
   - 本次部署的**唯一版本标识**：构建号 / 镜像 digest / commit 短哈希。
     tag（`:latest`、`:prod`）不算——同一个 tag 可指向不同镜像；
   - 服务名与进程匹配串；
   - 服务日志的读取方式。

2. **发一笔带唯一标识的真实业务请求**（随机 request-id 或时间戳拼随机数），
   标识必须不可能来自上一次部署——它是第 4 项检查的锚。

3. **跑四项检查**：
   - systemd 环境，直接跑捆绑脚本：

     ```
     bash <本skill目录>/scripts/verify-switch.sh <service> --pattern <进程匹配串> \
         --expect-version <版本标识> --version-cmd <取版本的命令> \
         --event <第2步的唯一标识>
     ```

     退出码：`0`=SWITCHED，`1`=NOT_SWITCHED，`4`=INDETERMINATE，`2`=用法错误。
   - 其他环境（K8s / 容器 / PaaS）：按下方对照表逐项执行，
     自行产出同名判定标量，取值只许 `yes` / `no` / 数字 / `unknown`，不许留空。

4. **负载均衡器人工检查**（脚本覆盖不到）：链路上有 LB 时，
   按对照表查**运行时后端表**。判据只有一条：这个接口读的是磁盘还是内存？
   **读磁盘的（配置文件、渲染产物）一律不算数**——配置是「期望」，运行时表才是「事实」，
   两者可以长期不一致而不报错。查不了 → `STALE_INSTANCES=unknown`。

5. **输出判定标量并如实转述**：

   ```
   SERVICE_ACTIVE=yes|no
   VERSION_MATCH=yes|no|unchecked
   STALE_INSTANCES=<n>|unknown
   BUSINESS_EVENT_SINCE_DEPLOY=yes|no|unchecked
   VERDICT=SWITCHED|NOT_SWITCHED|INDETERMINATE_*
   ```

   只有 `VERDICT=SWITCHED` 才可以向用户报告「切换完成」。
   其他判定**原样上报**并指出挂在哪一项——修复后重跑**全部四项**，不是只补挂掉的那条。

完成判据：四个标量全部有值，VERDICT 与四项一致，且已如实转述给用户。

## fail-closed（铁律）

「没测」不是「测了是好的」。任何一项没做或测不出（权限不足、日志缺失、
没有版本端点、拿不到进程表）→ `VERDICT=INDETERMINATE_*`，按未通过处理，
并向用户列出缺了哪一项、需要什么才能测。用「看起来正常」补位 = 假绿灯本灯。

## 检查对照表（非 systemd 环境）

| 检查 | 命令 | 通过判据 |
|---|---|---|
| ① 服务在运行 | K8s: `kubectl get pods -l app=<svc>`；容器: `docker ps --filter name=<svc>` | Pod `Running` 且 READY 分子=分母；容器 `Up` |
| ② 版本对得上 | 查 `/version` 端点；无端点则容器查镜像 **digest**、进程查启动时间+命令行 | 与本次版本标识**逐字符**相等 |
| ③ 旧实例清干净 | 列全部副本/同类进程；LB 见下表 | 无旧版本副本 Running；无「父进程为 1 且早于本次部署」的残留 |
| ④ 真的干过活 | `grep <唯一标识>` 新实例日志 | 命中 |

LB 运行时后端表：

| LB | 命令 |
|---|---|
| HAProxy | `echo "show servers state" \| socat stdio /var/run/haproxy.sock` |
| Envoy | `curl -s localhost:15000/clusters` |
| Nginx Plus | `curl -s http://127.0.0.1/api/*/http/upstreams` |
| Kubernetes | `kubectl get endpointslices -l kubernetes.io/service-name=<svc>` |
| 开源 Nginx | 无运行时查询接口；`nginx -T` 读的是配置——只能核对 worker 进程启动时间间接判断 |

多节点渐进分发场景：单点单次采样会给假信号——采样须覆盖全部节点（或每分组有样本），
且横跨至少一个完整下发周期（周期多长，先问出来）。

## 出处

本 skill 是《FDE 手册》VER-02「切换验证」的可执行版：
https://github.com/libaoming/fde-handbook
手册含四项检查的完整判据、常见误判、与公开事故复盘证据
（Slack 2020 · Cloudflare 2025 · Datadog 2023 · GitLab 2017）。
速查入口：附录 A · FX-SVC-01「部署完了，但改动看起来没生效」。
