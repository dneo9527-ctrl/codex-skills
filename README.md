# Codex Skills

**v0.1.0-preview.5 · MIT · Python 3.9+ · macOS / Linux**

本库提供两个可独立安装的通用 Skill：

- `codex-project-memory`：为每个 Codex 聊天保留精简项目档案、长期约束和已验证经验，交接保留可选检查点中的授权、等待状态及操作收据。
- `external-ai-team`：优先复用当前聊天右侧项目 AI 会话，按聊天核对总控与 Agy/Muse/Claude 独立开关；保留草稿、暂停、绑定与模型设置，读取实际结果后由 Codex 验证整合。

| 下载 | 完整包 |
| --- | --- |
| 多 AI 协作 Skill | [external-ai-team-0.1.0-preview.5.zip](https://github.com/dneo9527-ctrl/codex-skills/releases/download/v0.1.0-preview.5/external-ai-team-0.1.0-preview.5.zip) |
| 项目记忆 Skill（内容沿用 preview.1） | [codex-project-memory-0.1.0-preview.1.zip](https://github.com/dneo9527-ctrl/codex-skills/releases/download/v0.1.0-preview.5/codex-project-memory-0.1.0-preview.1.zip) |
| 本版完整源码与测试 | [codex-skills-0.1.0-preview.5-source.zip](https://github.com/dneo9527-ctrl/codex-skills/releases/download/v0.1.0-preview.5/codex-skills-0.1.0-preview.5-source.zip) |

[发行记录及 SHA256SUMS](https://github.com/dneo9527-ctrl/codex-skills/releases/tag/v0.1.0-preview.5) · [CI](https://github.com/dneo9527-ctrl/codex-skills/actions/workflows/checks.yml)

## 多 AI 协作：external-ai-team

默认复用当前 Codex 聊天右侧已打开的 AI 网页，按项目保留专用会话；可选适配已安装的 Antigravity 控制台。Codex 负责分工、读取实际结果、独立核对与整合。明确提供方、仅 Codex 指令和已有暂停优先；当前选中且确认属于本项目的会话优于历史绑定，不凭标签清单顺序或系统浏览器的最新网页猜目标。

解压完整 Skill 包后运行：

```sh
python3 external-ai-team/install.py
# 或指定 Codex home：
python3 external-ai-team/install.py --codex-home /path/to/codex-home
```

源码安装使用 `python3 skills/external-ai-team/install.py`。安装器已有目标时拒绝覆盖，不修改其他 Skill、AGENTS、权限、账号或模型。升级已有同名 Skill 时，先备份到 `skills` 目录外并核对自定义适配，再自行替换；安装器不自动迁移本机部署。重新加载后使用 `$external-ai-team`；默认参与还需使用者的项目指令与有效授权。宿主需提供能操作当前聊天浏览器的工具，目标 AI 服务需由使用者就绪。

完整包包含九个文件：Skill、安装器、界面元数据、通用 Ag 参考、提供方与启动约定、圆桌会议参考、策略读取与可见控制台启动 helper，以及 MIT 许可。它不随包提供外部账号、Ag 服务、后台唤醒或网页登录；不自动上传私人文件、联系其他聊天或购买额度。已输入的草稿和生成中的任务会被保留，真正发送前重新核实页面与会话。全部网站、原生 Windows 及所有旧聊天自动发现均未验收；工具不可用时记录实际未完成状态。详见 [Skill 指引](skills/external-ai-team/SKILL.md)。

## 提供方开关与控制台启动

配套面板保存当前聊天的「多 AI 协作」总控及 Agy、Muse、Claude 独立开关；总控和选中提供方均允许才可派发。多个开启表示可选范围，不群发。关闭的提供方不会被自动替换，旧暂停不会因升级恢复。每次发送前重新读取当前聊天策略，不能用其他聊天的开关或全机最近会话推断。

这些面板开关和离线策略需要支持对应接口的 Agy Console；仅安装 Skill 不会安装控制台或创建三个网站客户端。通用浏览器协作仍需宿主提供受支持的浏览器工具，目标站点和本项目会话由使用者准备。新版与相关面板完整包成套发布；具体配套版本与下载以本版 Release 为准。

控制台自动启动与自动展示、协作许可分别保存，自动启动默认关闭。仅在当前活跃任务确需 Agy、当前聊天允许自动启动、用户配置了有效 `.command`／`.cmd` 正规入口，且服务明确未运行时，helper 打开一次可见终端并有界等待；已有服务直接复用。启动结果不明时保留待核实记录，避免重复开启。不新增后台常驻服务，也不唤醒空闲 Codex。Linux 当前只做状态检查，未支持自动打开终端。

策略缺失、损坏、身份不匹配、总控暂停或提供方关闭时停止新派发，继续 Codex 可独立完成的工作。服务就绪与获得发送权限分别核对；官方登录、文件外发及付费仍遵守使用者授权。真实冷启动、Windows 原生终端和 Muse/Claude 实际网页投递尚未验收，不能将隔离测试视为跨站端到端通过。见 [开关与启动约定](skills/external-ai-team/references/collaboration-controls.md)。

## 独立圆桌会议（配套 Agy Console preview.16）

完整九文件 Skill 与 [Agy Console preview.16](https://github.com/dneo9527-ctrl/agy-console/releases/tag/v0.1.0-preview.16) 成套发行，完整面板包也含完全相同的 Skill。默认 `assist` 继续单提供方协作；明确设置为 `roundtable` 时，活跃 Codex 依据准确聊天的计划创建独立会议，组织提案、互评与选定主持总结。每次新外发仍重新检查总控与对应提供方许可，保留项目会话、模型、草稿和暂停。

会议使用稳定 ID 和来源标识，冻结主持、参与方与工作会话。Muse/Claude 的真实网页贡献可以独立入会，无需等待 Agy 成功；Agy 阶段关联真实官方 CLI 任务。未知发送结果先核对原会话，不盲目补发；缺席、失败和部分完成分别记录。见 [圆桌流程与恢复](skills/external-ai-team/references/roundtable.md)。

需使用者准备可用的项目网页和受支持浏览器工具；Skill 不替人登录，不创建后台采集器，不唤醒闲置 Codex，也不保证所有旧聊天自动加载。开发者 Mac 的现场记录与发行端隔离测试、各平台 CI 分别列示，不能推断 Windows/Linux 真实模型或跨窗口自动运行已经验收。由 preview.8 升级面板必须使用完整安装包；程序更新不会自动安装 Skill。

本版补充会议恢复与结果核对规则：先恢复准确会议、已有来源标识与已发结果；“继续”不是重建会议的指令。只读核对不派发模型，缺席仅用于待发且没有关联原生任务的步骤，需要理由与确认；未知发送结果先核对原会话。主持结论优先，墙钟与模型执行时间、Agy 已知用量与网页未知用量分别表述。

## 项目记忆：codex-project-memory 安装

原生 Windows 暂不支持，helper 使用 POSIX 文件锁。下载 Skill ZIP 并完整解压，在解压目录运行：

```sh
python3 codex-project-memory/install.py
```

安装器复制完整 Skill、helper、引用和 MIT 许可到 `${CODEX_HOME:-~/.codex}/skills/codex-project-memory`。已有同名目录、文件或符号链接时停止，不覆盖；多个 Codex home 可显式指定：

```sh
python3 codex-project-memory/install.py --codex-home /path/to/codex-home
```

从源码仓库安装则运行 `python3 skills/codex-project-memory/install.py`。安装不调用模型或网络，不改已有 `AGENTS.md`、权限、Hook 或其他 Skill。重新打开或新建 Codex 聊天后，使用 `$codex-project-memory`。如需默认参与项目工作，可自行在项目指令中引用该 Skill。

## 项目记忆的使用与数据

让 Codex 使用当前环境的 `CODEX_THREAD_ID` 读取本聊天档案，依据实际项目保存指导；不要借用其他聊天身份。常用动作是 `show`、`save`、`enable`、`disable`、`handoff` 和 `report`。格式及命令见 [使用说明](skills/codex-project-memory/references/profile-format.md)。

档案保存在 Codex home 的 `project-memory`，目录/文件分别使用 `0700`/`0600`。报告默认仅当前聊天；用户明确要求本机跨聊天汇总时才使用 `--all-chats`。档案、学习事件与交接可能包含私人项目信息，应保留在本机项目数据区，不上传到仓库或 Issue。

可选检查点位于 `task-checkpoints/<CODEX_THREAD_ID>.json`，必须有匹配的顶层 `thread_id`。helper 只读取并保留其状态，不调度或恢复任务。停用保留数据；卸载时只移除安装器创建的 Skill 目录，档案与证据另行保管。

这是结构化的本地工作指导，不训练模型、不自动压缩或唤醒聊天，也不承诺量化的 token 节省。重新加载 Skill 是否自动发生取决于宿主版本。全量验证见 [发行记录](https://github.com/dneo9527-ctrl/codex-skills/releases/tag/v0.1.0-preview.1)。

## 其他相关能力

| 能力 | 分发位置 |
| --- | --- |
| Agy 面板的 Codex 接入 | [Agy Console](https://github.com/dneo9527-ctrl/agy-console)，绑定 `agy-console` Skill 随项目完整包发布；本库通用协作指引可选适配现有控制台 |
| 等待回答时 Bark 提醒 | [Bark Bridge](https://github.com/dneo9527-ctrl/bark-bridge-macos)，模板和接入工具随 App 发布 |
| 图片型 PPT | 第三方 [ningzimu/codex-ppt-skill](https://github.com/ningzimu/codex-ppt-skill)，由上游独立维护与许可 |

本库只分发列出的自有通用 Skill，不包含系统/官方插件技能或私有桌面恢复协议。

## 开发与许可

```sh
python3 -B -m unittest discover -s tests -v
```

测试仅使用临时数据。84 项隔离行为检查包含项目记忆 26 项及协作策略、启动、真实解析器集成与安装 58 项；测试只使用合成聊天身份和临时目录，不启动真实终端或模型。CI 对 macOS/Linux 的 Python 3.9 与 3.13 执行行为检查；结果须以相应提交的 Actions 为准。项目源码采用 [MIT](LICENSE)，独立 Skill 包内也带同一许可证。
