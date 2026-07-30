# Vyane Paw

Vyane Paw 是连接
[QwenPaw](https://github.com/agentscope-ai/QwenPaw) 与
[vyane-rs](https://github.com/zleo-ai/vyane-rs) 的私有集成与产品化仓。

它让 QwenPaw 继续负责用户交互、Agent 工作区、渠道、记忆和插件承载，让
Vyane 负责多模型路由、任务分发、广播评审、失败切换与工作流执行。本仓不是
QwenPaw fork，也不是另一套 Vyane 重构。

## 已定方案

- 产品名：**Vyane Paw**
- 仓库名：`vyane-paw`
- 可见性：private
- 首期接入：MCP 优先，先走本机 stdio 直连
- 常驻中间服务：暂不建设；只有出现远程、多租户、鉴权或协议转换需求时再立项
- 首个兼容基线：
  - QwenPaw `ebb5b24d0b2559af51d71a38547d88d384357a64`
  - `vyane-rs` 固定到 `4848ec4f9d0b740fd8dc5f5586bc30111dc3d373`
  - `rmcp` `3.0.0`

## 仓库职责

- QwenPaw 插件、安装描述和脱敏示例配置
- QwenPaw ↔ Vyane 跨语言 MCP 兼容测试
- 路由、分发、失败切换、广播评审与历史查询的产品化流程
- 策略与演示证据的可移植 schema
- 初赛、决赛材料所需的技术事实、指标和脱敏展示资产

当前工作包状态、暂缓范围和其他 Agent 的续接步骤，以
[docs/STATUS.md](docs/STATUS.md) 为准。

## 当前工程基线

VP-01 至 VP-03、VP-06 至 VP-08 均已完成并合入。当前已验证：

- 固定版本 QwenPaw 客户端与 `vyane-rs` 的 stdio MCP 兼容；
- 路由、失败切换、并行广播、超时和故障隔离；
- 受策略约束的 QwenPaw 插件与 launcher；
- 隔离执行的 `vyane-rs main` 候选兼容性 canary；
- 真实固定版本 QwenPaw 应用链路；
- 持久工作流提交、状态查询和显式取消。

## 产品入口

`qwenpaw-plugin/` 在不修改 QwenPaw 内核的前提下提供一个 `/vyane` 命令和七种
产品模式：

- `/vyane route <任务>`：确定性路由预览；
- `/vyane dispatch <任务>`：按安全默认值自动路由并执行；
- `/vyane failover <profile> -- <任务>`：使用已授权 profile 的失败切换链；
- `/vyane review <profile-a,profile-b> -- <任务>`：对二至四个目标并行评审；
- `/vyane workflow-submit <profile> -- <任务>`：提交固定单步只读工作流；
- `/vyane workflow-status <uuidv7>`：查询持久工作流状态；
- `/vyane workflow-cancel <uuidv7>`：显式请求取消持久工作流。

`scripts/run-vp03.sh` 复验插件与 launcher 合约，`scripts/run-vp07.sh` 复验真实
QwenPaw 应用链路，`scripts/run-vp08.sh` 复验持久工作流生命周期。

直接停止 QwenPaw 的请求协程仍不等于服务端请求已取消；请求型能力继续使用有限
超时。VP-08 的工作流取消是独立、显式的 Vyane 产品生命周期，不是 MCP 请求取消，
也不代表已经实现 MCP Tasks 扩展。

安装、录屏、比赛材料和线上文档发布当前均为暂缓项，功能推进优先。
