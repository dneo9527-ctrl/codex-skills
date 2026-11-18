# 多 AI 协作开关与启动

仅在部署提供本聊天开关/启动设置时使用。面板维护策略，Skill/helper 只读；不另建一份可写偏好，不读账号或聊天存储。

## 策略来源

使用部署明确提供的安装根和策略文件路径。默认策略路径为 Mac `~/Library/Application Support/AgyConsole/coordination.json`、Windows `%LOCALAPPDATA%\AgyConsole\coordination.json`、Linux `${XDG_CONFIG_HOME:-~/.config}/agy-console/coordination.json`。自定义部署以服务报告的 `console_startup.policy_path` 为准；安装根来自已确认的部署，不从待验证快照自身接受一个任意根。

离线快照 schema=1、ready=true、installation_root 匹配，threads 中精确当前 ID 对应如下条目：

```json
{
  "multi_ai_collaboration": {
    "schema_version": 1,
    "codex_thread_id": "<exact-thread-uuid>",
    "enabled": true,
    "providers": {"agy":{"enabled":true},"muse":{"enabled":false},"claude":{"enabled":false}}
  },
  "auto_start_console": false
}
```

顶层 `launcher.path` 为本机共享的具体启动文件；自动启动按聊天隔离。所有开关须严格为 JSON bool。缺失/无效/ready=false 与“没有部署面板”不同，不允许将失败当作开启。写入中可短时重新读取一次，仍不可核实则本轮不派发。不从其他聊天复制设置；新聊天需在线正规 bind 建立默认条目，离线不能启动未配置的新聊天。

可运行（路径以实际 Skill 安装位置替换）：

```bash
python3 scripts/collaboration_policy.py --provider muse --installation-root /confirmed/console/root
```

helper 默认使用环境 `CODEX_THREAD_ID`，可用 `--policy-file` 指定已知部署路径。返回 `allowed`、`reason` 和当前聊天的规范策略。退出0为允许，3为已暂停，2为无法核实；不调用模型、不写策略。

选定 Ag 后的 `bridge --ensure` 返回可通过 stdin 交给 `collaboration_policy.py --provider agy --bridge-json`，不将原输出公开。新服务必须提供 `multi_ai_collaboration_supported:true` 与完整 canonical 对象。canonical.enabled 是总控；旧 `collaboration_enabled` 只是总控 && Agy，新状态存在时不能用旧 alias=false 压掉已允许的 Muse/Claude。旧服务只有 alias 时，只兼容 Agy；旧false继续总暂停，Muse/Claude不自动开启。

`GET /api/codex/<exact-thread-uuid>/collaboration` 可只读获取 canonical，无正文、不创建绑定。普通读取、bind、ensure不能恢复停用。改开关只能执行用户明确启停请求，通过面板设置或部署支持的局部写接口；开关开启仍需确认实际网页和材料范围。

## 启动入口

控制台设置保存绝对 `.command`（Mac）或 `.cmd`（Windows）文件。目录只能存在唯一受支持入口。helper 不安装程序、不编辑入口、不读取认证或自动登录。Mac 使用 Terminal 打开正规 launcher，Windows 使用可见新控制台；Windows 路径中 cmd 元字符会拒绝，需选择普通本地路径。Linux 尚无自动终端适配。

```bash
python3 scripts/console_start.py --installation-root /confirmed/console/root --ensure-running
```

省略 `--ensure-running` 只读检查。它先校验本聊天总控/Agy，再只对明确本机 loopback 地址 GET `/api/service`，核对安装身份和绑定功能；已有服务、暂停、auto_start=false均不打开终端。只有明确 connection refused 才可能启动；超时、非本安装、重定向等保持不确定，不另起服务。端口不同的部署用已配置 `--console-url`，不扫描端口。

启动前重新读取偏好。同安装跨聊天用短锁及 `console-start-attempts/` 元数据去重；pending/unknown不因时间流逝重开，健康检查证实ready后才解除不确定，并保留短冷却。超时不代表启动失败，更不代表模型任务失败。残留锁/收据需核对原终端与实际进程，不能自动删掉重试。

ready只证明本安装服务可用；随后重新读取在线策略、准确绑定和网页状态，才能派发。启动回执不证明浏览器已可见、登录有效或协作已经完成。启动helper不改变自动显示活动页偏好，也不控制其他提供方的客户端。
