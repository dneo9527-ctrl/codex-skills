# 活跃任务中的圆桌会议

保存的圆桌模式在本聊天下次活跃、适合协作的实质任务生效；不要求用户重复开启，也不唤醒闲置 Codex。日常 `assist` 仍只选择一个入口。本流程不修改提供方、模型、暂停或自动显示偏好。

## 准入与恢复优先

1. 依据[策略约定](collaboration-controls.md)读取精确 `CODEX_THREAD_ID` 的 canonical 总控与每个拟用提供方，在真正发送前再读。已知在线控制台使用正规 dispatcher 的 `--ensure` 读取绑定元数据：`codex_thread_id`、`console_conversation_id`、`roundtable`、`roundtable_plan`、`roundtable_meetings_supported`、`auto_open_activity` / `panel_action`。不把旧 `collaboration_enabled` 当新总控，也不在 `--ensure` 中传启停/主持/模型变更。元数据读取不选择 Ag；服务离线时不为读设置启动它。任务确需 Agy 且总控+Agy+自动启动均允许时，才按正规前台启动约定处理。
2. 核实当前任务检查点是否已有 `roundtable` 对象，字段见下文。已有 `meeting_id` 时先查该确切会议和已关联 turn，核对聊天、任务、分支；冻结主持和参与方以原会议为准，不以后来修改的下一场计划覆盖。未完成会议恢复缺失阶段；完成/部分完成的会议只复用结论，普通“继续”、刷新、换号或新恢复回合不自动再开一场。用户明确提出新议题或新评测，才建立新的任务身份。
3. 新会议要求在线元数据的 `roundtable` 和 `roundtable_plan` 彼此匹配：schema=1、精确聊天、mode=roundtable、rounds=2、有效host，participants按 `codex, agy, muse, claude` 顺序包含Codex及已启用提供方，ready=true、reason=ready、execution=active_codex_skill、steps为 `independent_proposals, peer_review, host_summary`。只有开关全开或一个网页可输入不能替代计划。用户当前限定提供方或暂停优先；不为凑全员修改配置。
4. 逐方核实当前聊天的项目会话。网页优先复用本聊天右侧已选且已确认的该项目会话，或准确保存的本项目URL；不能取系统浏览器最近页、清单第一项、其他聊天、标题或cwd。不改变草稿、账号、速度或模型。没有适合会话/工具、登录或额度受阻时如实记录不可用，不任意换网站。关闭提供方时不转投其他方绕过暂停。

当前服务不支持独立会议时，保留任务与证据并报告需要兼容后台；不退回伪造Agy锚点或每次新建独立CLI。计划/绑定不可核实继续本地可做部分。当前模式暂停/切回assist时不新派发，已发结果仍查询并保留；恢复旧会议不自动解除暂停。

## 当前用户任务的稳定身份

身份只存进已有 `codex-resume-work` 任务检查点，不创建第二份全局最近会话表。接受本次用户任务时保存：

```json
{
  "roundtable": {
    "task_id": "original-user-turn-id-or-persisted-task-uuid",
    "source_id": "rt-task-STABLE_HASH",
    "codex_thread_id": "exact-current-chat-uuid",
    "branch": "main",
    "console_conversation_id": "exact-bound-console-id",
    "meeting_id": null,
    "create_state": "prepared",
    "provider_sessions": {},
    "attempts": {},
    "artifacts": {}
  }
}
```

`task_id`优先取宿主实际提供的**最初发起该用户任务的回合ID**，恢复时沿用。不能把检查点后来更新的 `last_turn_id` 或当前“继续”的新回合当新任务。如果宿主没有可靠的发起回合ID，生成一次UUID并在首次外部操作前写进这个用户任务的检查点；该UUID只是本地任务ID，不冒充真实回合ID。没有保存成功就不调用外部方。

新会议 `source_id` 用确定性标识：`rt-task-` + SHA256(精确thread + 换行 + task_id + 换行 + branch)的前48位十六进制；保留原输入与创建JSON路径。不得以当前时间、进程ID、输出目录、全局最近记录或每次恢复重新生成UUID作为任务身份。会话与来源ID不构成发送授权。

创建请求仅 `{codex_thread_id, source_id, topic, branch?}`，主持/参与方由服务冻结；不能客户端自填。先保存prepared状态，再提交一次，立即保存返回的 `meeting_id` 与真实回执：

```bash
python3 /confirmed/console/bridge.py --meeting-create /absolute/create.json
python3 /confirmed/console/bridge.py --meeting-view MEETING_ID
```

示例路径须替换成已核实部署。dispatcher读取当前真实环境 `CODEX_THREAD_ID`，不能复制其他聊天ID。创建与查询本身不调用模型。创建返回不明时保持原source_id、任务和JSON；先按保存ID或分页查找该source_id。若无ID且创建结果确实未收到，可用**完全相同**创建JSON再次核对服务的幂等回执，不能换source_id、主题或分支另开一场；这只是元数据幂等核对，不是模型或网页重发。找到多个/不匹配记录即停止外发核对，不能挑最新一条。

## 两轮真实分工

首轮记录Codex实际提案，分别给已获准且会话已核实的参与方一个有界独立提案；Codex继续独立推进文件与测试。每位最多一次提案、一次互评，选定外部主持可额外一次最终总结。只发送必要议题、验收与真实材料，不复制整段聊天历史。第一轮所有参与方到真实终态才互评，第二轮针对真实提案的风险、分歧与代价；不得为缺失方补写同意或发言。

Agy先读取[适配说明](antigravity.md)及当前部署参考，使用已核实控制台的 `bridge.py`，沿用官方会话、窗口文字模型和分支。现有 `run_agy.py` 包装器没有会议参数时不要使用它，不退回standalone：

```bash
python3 /confirmed/console/bridge.py --meeting MEETING_ID --meeting-stage proposal \
  --task-file /absolute/agy-proposal.txt --out /absolute/new-run-directory --no-wait
```

互评改为 `review`；Agy确为冻结主持时才可用 `summary`。不传 `--model` 保留窗口选择与候补；不改账号或付费策略。派发前保存prompt与阶段意图，提交后立即保存真实turn_id和回执。返回不明先查询原会议的Agy槽位/任务：有turn_id即观察原任务，queued/running/cancelling不重发；completed核对非空正文、真实官方会话及无会话错配；failed/cancelled/interrupted如实保留，不另造新会议掩盖。请求未确认且原槽位仍pending时，先核对请求是否实际提交，不能把超时当失败。只有确认未提交且仍获准时才沿用同一prompt、模型覆盖和meeting/stage核对幂等；不得换prompt或任务身份绕过已有阶段。Agy状态与原文必须由真实CLI派生，不能用外部事件填成已完成。

网页方使用受支持UI。发送前再次核实总控/该方、具体项目URL、实时composer、草稿与已有生成。保留用户草稿；已有请求生成中时观察原结果。发送前登记 `sending` 并持久保存本次意图，单次发送确认进入原会话才记 `waiting`；点击/回执不明保持待核对，检查原会话，不换source_id或另开页补发。不能由文件或helper接管浏览器发送。

只有实际读到完整非空最终回复才登记 `completed`、原文和具体HTTPS会话URL。Muse形式为 `https://muse.ai/thread/<uuid>`，Claude为 `https://claude.ai/chat/<uuid>`，不带查询、片段或凭据；Codex本地发言的source_url为空。记录本次回复和必要代码块，不推断“已发送”就是成功，不把点击回执当最终结果。

```bash
python3 /confirmed/console/bridge.py --meeting-event /absolute/observed-event.json
```

事件字段：`{meeting_id, codex_thread_id, source_id, provider, stage, status, text?, source_url?, detail?}`。stage为proposal/review/summary；status为sending/waiting/completed/failed/unavailable/cancelled。建议event source_id沿用会议source_id加 `.provider.stage.status`，同一事件重新读取时复用原ID与完全相同内容；每次真实状态变化使用不同ID，不依靠新ID获得重发许可。completed要求真实非空text；failed/unavailable/cancelled写简短实际原因。待发且确定未发送的不可用方才可unavailable；sending/waiting不能退回未发送或凭超时称缺席，不能盲重试。终态不覆盖；实际结果已登记就复用，重新评估属于新授权任务。

## 按阶段获取本场材料

当 `--ensure` 返回 `roundtable_context_supported:true` 时，网页参与方或 Codex 在撰写本轮请求前，可按冻结会议与实际阶段读取一次：

```bash
python3 /confirmed/console/bridge.py --meeting-context MEETING_ID \
  --meeting-stage review --meeting-provider muse
```

这是只读材料，不发送消息、不打开标签、不解除暂停。核对返回的精确聊天、会议、分支、提供方和阶段后，取 `text` 作为本轮参考；发送前仍需重查策略与真实网页草稿。`proposal` 不附同轮发言；`review` 只含首轮；`summary` 只含前两轮并仅供冻结主持。前轮未结束会拒绝读取下一阶段。不要把其他场记录、同轮已到的意见或完整聊天历史混入首轮。

关联会议的 Agy 任务由服务在提交时冻结同一快照，候补沿用；不再用 `--context` 重复追加整份会议记录。快照包括真实状态，含转义的 JSON 总量上限 12,000 字符，长文公平保留头尾并标明省略，完整原文仍留在面板。`truncated` 是材料裁剪，不能称为模型记忆压缩或 token 节省；官方持久会话历史仍存在。

旧后台没有该能力时继续按既有流程手工整理准确的本场前阶段真实材料；不要擅自启动新服务、重建会议或虚构上下文。

## 主持总结、显示与完成

前两轮的所有槽位到终态后，由**冻结主持**依据实际发言归纳采用项、分歧、代价、未完成项及建议验证。Codex主持才记录自己的summary；外部主持必须取得其真实总结，不让Codex冒名。主持不可用时保留原主持，记录unavailable/真实失败；Codex只在本聊天明确说明状态，不静默换主持。暂停时不得启动新总结调用，已有尝试可按真实结果完成观察。

使用原会议查询返回的slots/speakers、status、phase、completed_count/total_count和revision核对。三方两轮加主持为7个槽位，只有全部真实完成才是completed；缺席/失败/取消等收尾为partial，不能称全员共识。面板显示记录与真实发送分开验收；使用部署支持的部分总结/核对操作时先读其实际契约，不以普通事件取消CLI进程。

Agy自动显示仍独立受 `auto_open_activity` 控制。允许时消费新会议创建返回的 `panel_action`，复用本聊天已有固定标签，在右侧显现并核实正确会议/活动；无标签时只创建返回的准确会议URL。支持版本会带 `meeting` 参数并在页内进入本场；已有页沿现有活动跟随更新，不因每条事件同步再次显示或新开标签。URL/句柄/排队打开不等于可见；工具指标与用户本次实际观察冲突时按[显现证据规则](antigravity.md)分别记录。关闭时不导航、不抢焦点；不以Agy panel_action覆盖已选Muse/Claude项目页，不反复开新标签。网页参与方沿用原会话，不通过刷新毁掉草稿或正在生成的结果。

有界等待前更新同一检查点：精确meeting/turn、provider_sessions、每槽位发送是否确认、正文/请求/回执路径、当前阶段和下一步；不要保存凭据。恢复先读取这些原记录，`sending`/`waiting`只允许核对原会话，idle模型不因Skill或页面自动醒来。结果整合后独立验证，并按已支持的 `--review-turn ACTUAL_ID --review-file FILE` 回填Agy采纳/拒绝/暂缓及实际检查；未支持写pending。最终汇报实际改动与边界，不能把设置开启、脚本可用或模型意见一致当作全自动运行验收。
