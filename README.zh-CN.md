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

## 今天就能启动

[VP-01](work-packages/VP-01.md) 已完成并合入：未修改的 QwenPaw MCP 客户端
能够连接固定版本的 `vyane-rs` stdio MCP server，完成初始化、精确 9 工具发现、
安全调用、非法参数拒绝和干净退出。

[VP-02](work-packages/VP-02.md) 的首个 hermetic 增量已在本地跑通：无需真实密钥
或付费模型，即可复验确定性路由、失败切换、并行广播、单目标故障隔离与超时。
测试也确认了一个边界：直接取消 QwenPaw 的本地 `call_tool` 协程目前不会传播
MCP cancellation notification，因此不能宣称服务端 run 已取消。

## 产品入口（开发中）

`qwenpaw-plugin/` 已提供不修改 QwenPaw 内核的 bundle 插件：

- `/vyane route <任务>`：只做确定性路由预览；
- `/vyane dispatch <任务>`：使用安全默认值自动路由并执行；
- `/vyane failover <profile> -- <任务>`：使用该 profile 已声明的失败切换链；
- `/vyane review <profile-a,profile-b> -- <任务>`：对二至四个目标做一次并行评审。

安装时保持 QwenPaw 离线：

```bash
install -m 0755 bin/vyane-paw-mcp "$HOME/.local/bin/vyane-paw-mcp"
qwenpaw plugin install /path/to/vyane-paw/qwenpaw-plugin
```

随后将 `config/examples/qwenpaw-mcp.example.json` 中的示例配置路径替换为
部署环境里的 Vyane 配置文件，并在 QwenPaw Console 的“智能体 → MCP”页面导入。
配置只允许产品所需工具，不包含模型凭据；Vyane provider 凭据继续由部署环境提供。
