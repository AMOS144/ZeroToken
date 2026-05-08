# ZeroToken

<!-- mcp-name: io.github.AMOS144/zerotoken -->

[![CI](https://github.com/AMOS144/zerotoken/actions/workflows/ci.yml/badge.svg)](https://github.com/AMOS144/zerotoken/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/zerotoken.svg)](https://pypi.org/project/zerotoken/)
[![Python versions](https://img.shields.io/pypi/pyversions/zerotoken.svg)](https://pypi.org/project/zerotoken/)
[![Downloads](https://static.pepy.tech/badge/zerotoken/month)](https://pepy.tech/project/zerotoken)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ZeroToken - Record once, automate forever.**

> Lightweight MCP for AI agent browser automation. Record once, replay forever — cut token cost and speed up repetitive tasks.

一个面向 AI Agent 的轻量化浏览器自动化 MCP 引擎，支持操作记录与详细执行上下文导出。

## 在 OpenClaw 中使用 ZeroToken

ZeroToken 是 OpenClaw 的浏览器执行层，适合**录制一次、重复执行**的自动化任务（如每日登录、定时抓取）。下面说明完整接入流程。

### 为什么需要 HTTP 模式？

OpenClaw 通过 MCPorter 调用 MCP 时，若使用 stdio（command 模式），**每次工具调用都会新建进程**，导致 browser 实例被销毁、状态丢失。因此必须改用 **Streamable HTTP 模式**：ZeroToken 以 HTTP 服务常驻，OpenClaw 通过 URL 连接，同一会话内 browser 状态得以保持。

### 接入步骤（完整流程）

#### 1. 安装 ZeroToken

```bash
# 通过 pip 或 uv
pip install zerotoken
# 或
uv add zerotoken

# 安装 Playwright 浏览器（必须）
playwright install chromium
```

若通过 MCPorter 安装到 OpenClaw：

```bash
npm install -g mcporter
mcporter install zerotoken --target openclaw --configure
```

安装后同样需执行 `playwright install chromium`。

#### 2. 在后台启动 HTTP 服务，并保持常驻

在终端中运行（**不要关闭**）：

```bash
zerotoken-mcp-http
```

默认监听 `http://0.0.0.0:8000/mcp`。可指定端口：

```bash
zerotoken-mcp-http --port 8001
# 或
ZEROTOKEN_HTTP_PORT=8001 zerotoken-mcp-http
```

#### 3. 配置 openclaw.json

在 `~/.openclaw/openclaw.json`（或项目内 `openclaw.json`）的 `mcpServers` 中，将 ZeroToken 配置为 **URL**，不要用 command：

```json
{
  "mcpServers": {
    "zerotoken": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

若使用非默认端口，修改 URL 中的端口号即可。

#### 4. 安装 zerotoken-openclaw Skill

将 Skill 放入 OpenClaw 的 skills 目录之一：

或通过 ClawHub：`clawhub install zerotoken-openclaw`

或从本仓库复制：

```bash
cp -r skills/zerotoken-openclaw ~/.openclaw/skills/
```

#### 5. 在 OpenClaw 中启用

在 OpenClaw 中启用名为 `zerotoken` 的 MCP server，并确保 `zerotoken-openclaw` Skill 已加载。Agent 即可通过 MCP 调用浏览器工具。

### 典型工作流

1. **录制轨迹**：用户描述任务（如「每日登录某站并拉取报表」），Agent 调用 `browser_init` → `browser_open` / `browser_click` / `browser_input` 等 → `trajectory_complete`，完成一次录制。
2. **生成脚本**：对重复/定时任务，Agent 调用 `trajectory_to_script(task_id)` 将轨迹转为可回放脚本。
3. **绑定定时任务**：Agent 调用 `script_binding_set(binding_key=job_id, script_task_id=task_id)` 将 OpenClaw 的 job_id 与脚本绑定。
4. **定时执行**：OpenClaw 触发定时任务时，Agent 调用 `run_script_by_job_id(binding_key=job_id)` 一步执行，无需 LLM 逐步推理，Token 消耗低。

更多详情见：`skills/zerotoken-openclaw/SKILL.md`、`docs/skills.md`。

### 常见问题

- **browser 状态丢失、每次操作都像第一次**：说明仍在使用 command 模式。请确保 (1) 在后台运行 `zerotoken-mcp-http`；(2) `openclaw.json` 中 `zerotoken` 配置为 `url` 而非 `command`。
- **连接失败 / MCP 不可用**：确认 `zerotoken-mcp-http` 已启动且端口正确（默认 8000），URL 与配置一致。

## 核心理念

### 问题
AI Agent 直接控制浏览器执行重复任务时，每次都需要消耗大量 Token 进行推理，成本高且执行速度慢。

### ZeroToken 解决方案

1. **操作执行**: AI 通过 ReAct 模式分步推理，调用 MCP 原子能力完成浏览器操作
2. **轨迹记录**: 系统记录完整的操作轨迹（包括页面状态、截图、执行结果、模糊点标记）
3. **AI 提示导出**: 轨迹可导出为 AI 友好格式，含需判断的模糊点说明，供 Skills 或其他模块进一步分析

## 核心特性

- **完整轨迹记录** - 每次操作记录步骤、页面状态、截图
- **结构化操作记录** - OperationRecord 包含完整的执行上下文
- **模糊点/DFU 标记** - 显式标记需 AI/人判断或需要上层决策/产出 vars 的步骤（如验证码、多选链接、评论文案），含 reason 与 hint
- **Script Engine** - 从 SQLite 数据库中的脚本表读取脚本，提供无 LLM 的确定性回放（`run_script`），支持暂停（dfu_pause/step_failed）与恢复（resolution）
- **SQLite 存储** - **scripts / trajectories / sessions 三类数据全部入库**，便于查询、复盘与定时任务调度
- **MCP 协议** - 标准化接口，易于集成到各种 AI Agent
- **稳定性增强** - 智能选择器、等待策略、错误恢复三大模块
- **自适应元素定位** - 首次命中时保存元素指纹（auto_save），改版后选择器失效时按相似度重定位（adaptive），无需改代码
- **反爬/云盾应对** - `browser_init(stealth=true)` 启用隐蔽启动与指纹伪装，降低被识别为自动化浏览器的概率（先能抓得到，Cloudflare 过验证后续可选）

## 稳定性增强

### 不稳定因素分析

```
选择器失效 (60%)     动态 ID、类名变化、DOM 结构改变
时序问题 (25%)       元素未加载、网络请求、动画未执行
环境变化 (10%)       视口变化、用户状态、Cookie 影响
其他因素 (5%)        弹窗干扰、资源加载失败
```

### 解决方案

**1. SmartSelector - 智能选择器生成**
- 自动生成多个备选选择器
- 优先级：data-testid > id > aria > CSS > XPath
- 检测并过滤不稳定类名（如 `el-*`, `ant-*`, `Mui-*`）

**2. SmartWait - 智能等待策略**
- 多种等待条件：selector, visible, networkidle, text, function
- 级联等待支持
- 页面稳定性检测

**3. ErrorRecovery - 错误恢复机制**
- 自动检测错误类型
- 选择器变体尝试
- 指数退避重试
- iframe 内元素查找

## 系统架构（含 ScriptEngine 与 DB 存储）

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Agent (ReAct 模式)                    │
│  系统提示词：分步推理 → 调用 MCP → 分析结果 → 下一步          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ MCP 工具调用
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  ZeroToken MCP Server                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Browser Tools (原子能力层)                            │   │
│  │  - browser_open(url) → OperationRecord               │   │
│  │  - browser_click(selector) → OperationRecord         │   │
│  │  - browser_input(selector, text) → OperationRecord   │   │
│  │  - browser_get_text(selector) → OperationRecord      │   │
│  │  - browser_extract_data(schema) → OperationRecord    │   │
│  │  ...                                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Trajectory Tools (轨迹管理)                           │   │
│  │  - trajectory_start(task_id, goal)                   │   │
│  │  - trajectory_complete() → AI Prompt (含模糊点)       │   │
│  │  - trajectory_get(format=json|ai_prompt) 当前轨迹      │   │
│  │  - trajectory_list(limit?, since?) 已保存列表         │   │
│  │  - trajectory_load(task_id, format?) 按 task_id 加载  │   │
│  │  - trajectory_delete(task_id) 删除已保存轨迹          │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Script / Session Tools                              │   │
│  │  - script_save / script_load / script_list          │   │
│  │  - run_script(task_id, vars?) → 确定性回放           │   │
│  │  - session_list / session_get(session_id)           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 OperationRecord (结构化记录)                  │
│  {                                                            │
│    "step": 1,                                                │
│    "action": "click",                                        │
│    "params": {"selector": "#login-btn"},                     │
│    "result": {"success": true, "navigated": true},           │
│    "page_state": {"url": "...", "title": "..."},             │
│    "screenshot": "base64...",  ← 视觉快照                     │
│    "fuzzy_point": {         ← 可选，需判断时存在               │
│      "requires_judgment": true,                              │
│      "reason": "验证码需识别", "hint": "AI 视觉"               │
│    },                                                         │
│    "timestamp": "2024-01-01T12:00:00"                        │
│  }                                                            │
└─────────────────────────────────────────────────────────────┘
```

### Mermaid 架构图

```mermaid
graph TB
    subgraph "AI Agent Layer"
        A[AI Agent - ReAct Mode]
    end

    subgraph "MCP Server"
        B1[Browser Tools]
        B2[Trajectory Tools]
    end

    subgraph "Core Modules"
        C1[BrowserController]
        C2[TrajectoryRecorder]
        C3[ScriptEngine]
    end

    subgraph "Storage"
        D1["SQLite: scripts/trajectories/sessions"]
    end

    subgraph "Browser"
        E[Playwright/Chromium]
    end

    A -->|MCP Calls| B1
    A -->|MCP Calls| B2

    B1 --> C1
    B2 --> C2

    C1 --> E
    C1 --> C2
    C2 --> D1
    C3 --> D1
```

## 安装

**OpenClaw 用户**：完整步骤见上文「[在 OpenClaw 中使用 ZeroToken](#在-openclaw-中使用-zerotoken)」。

**Cursor 等 IDE**：安装后使用 stdio 模式，在客户端配置 `command: "zerotoken-mcp"` 或 `command: "uv", args: ["run", "zerotoken-mcp"]` 即可。

### 本地开发 / pip 安装

```bash
# 克隆项目
git clone https://github.com/AMOS144/zerotoken.git
cd zerotoken

# 安装依赖
uv sync

# 或 pip 安装
pip install zerotoken

# 安装 Playwright 浏览器
playwright install chromium
```

## 快速开始

### 1. 启动 MCP Server

| 场景 | 命令 | 说明 |
|------|------|------|
| **OpenClaw** | `zerotoken-mcp-http` | 在后台常驻，`openclaw.json` 配置 `url: "http://localhost:8000/mcp"`。详见「[在 OpenClaw 中使用 ZeroToken](#在-openclaw-中使用-zerotoken)」。 |
| **Cursor 等 IDE** | `zerotoken-mcp` 或由客户端拉起 | stdio 模式，配置 `command: "zerotoken-mcp"`。 |

```bash
# OpenClaw：HTTP 模式（后台常驻）
zerotoken-mcp-http

# Cursor：stdio 模式
zerotoken-mcp
```

### 2. AI Agent 通过 MCP 调用浏览器工具

示例流程：

```
# 初始化浏览器（遇反爬/云盾可传 stealth=true）
→ browser_init(headless=true)
← {"success": true, "config": {...}}

# 开始轨迹记录
→ trajectory_start(task_id="login_task", goal="登录系统")
← {"success": true, "task_id": "login_task"}

# 执行浏览器操作（自动记录到轨迹）
→ browser_open(url="https://example.com/login")
← {
     "step": 1,
     "action": "open",
     "params": {"url": "https://example.com/login"},
     "result": {"success": true, "title": "Login"},
     "page_state": {"url": "...", "title": "..."},
     "screenshot": "base64..."
   }

→ browser_input(selector="#username", text="testuser")
→ browser_input(selector="#password", text="secret123")
→ browser_click(selector="#submit-btn")

# 完成轨迹并获取 AI 提示（含模糊点标记）
→ trajectory_complete(export_for_ai=true)
← {
     "success": true,
     "ai_prompt": "Task Goal: 登录系统\n\nOperation History:\n[Step 1] open(...)\n[Step 2] click(...) [需判断: 验证码需识别]"
   }
```

AI 收到 `ai_prompt` 后，可结合 Skills 或自定义逻辑，对标记为「需判断」的步骤进行处理。建议通过 `trajectory_list` 查看已保存轨迹，对不需要的调用 `trajectory_delete(task_id)` 避免记录过多；browser 类工具可传 `include_screenshot: false` 减少响应体积；失败时返回结构化错误（含 `code`、`retryable`）便于模型重试。对关键元素可传 `auto_save: true` 保存指纹，改版后传 `adaptive: true` 自动重定位。

## 核心模块 API

### BrowserController

```python
from zerotoken import BrowserController

controller = BrowserController()
await controller.start(headless=True)

# 每个操作都返回 OperationRecord
record = await controller.open("https://example.com")
print(record.to_dict())
# {
#   "step": 1,
#   "action": "open",
#   "params": {...},
#   "result": {...},
#   "page_state": {...},
#   "screenshot": "base64..."
# }

await controller.stop()
```

### TrajectoryRecorder

```python
from zerotoken import TrajectoryRecorder, BrowserController

controller = BrowserController()
recorder = TrajectoryRecorder()
recorder.bind_controller(controller)

# 开始记录
recorder.start_trajectory("task_001", "完成用户登录")

# 执行操作（自动记录）
await controller.open("https://example.com")
await controller.click("#login-btn")

# 完成记录
trajectory = recorder.complete_trajectory()
recorder.save_trajectory()

# 导出给 AI 分析（含模糊点标记）
ai_prompt = trajectory.to_ai_prompt_format()
```

### 模糊点标记 (fuzzy_point)

需要 AI 或人工判断的步骤可标记为模糊点：

```python
# extract_data 默认自动标记 fuzzy_point
record = await controller.extract_data(schema)

# 其他操作可手动传入 fuzzy_reason、fuzzy_hint
record = await controller.click("#link", fuzzy_reason="页面有多个链接", fuzzy_hint="需选择目标链接")
```

## OperationRecord 结构

每个浏览器操作都返回详细的 OperationRecord：

```json
{
  "step": 1,
  "action": "click",
  "params": {
    "selector": "#submit-btn",
    "timeout": 30000
  },
  "result": {
    "success": true,
    "navigated": true,
    "new_url": "https://example.com/dashboard"
  },
  "page_state": {
    "url": "https://example.com/dashboard",
    "title": "Dashboard",
    "timestamp": "2024-01-01T12:00:00"
  },
  "screenshot": "base64_encoded_image_data",
  "fuzzy_point": {
    "requires_judgment": true,
    "reason": "验证码需识别",
    "hint": "AI 视觉"
  },
  "timestamp": "2024-01-01T12:00:00"
}
```

`fuzzy_point` 为可选字段，仅在需要 AI/人判断的步骤存在。导出 AI 提示时，会追加 `[需判断: {reason}]` 等标记。

## 项目结构

```
zerotoken/
├── zerotoken/
│   ├── __init__.py
│   ├── controller.py         # BrowserController - 浏览器控制
│   ├── trajectory.py         # TrajectoryRecorder - 轨迹记录
│   ├── selector.py           # SmartSelector - 智能选择器
│   ├── wait_strategy.py      # SmartWait - 等待策略
│   └── recovery.py           # ErrorRecovery - 错误恢复
├── zerotoken.db              # SQLite 数据库（脚本/轨迹/会话，运行时生成）
├── mcp_server.py             # MCP Server 入口（stdio）
├── mcp_server_http.py        # MCP Server HTTP 入口（Streamable HTTP）
└── README.md
```

## 使用场景

1. **AI Agent 浏览器自动化** - OpenClaw、LLM Agent 等
2. **RPA 流程自动化** - 重复性网页操作录制回放
3. **数据采集** - 定时抓取网页数据
4. **自动化测试** - 记录测试步骤并回放

**OpenClaw 配套 Skill**：见 [docs/skills.md](docs/skills.md)，用于定时/重复任务时按轨迹重放、降低 Token 消耗。

## 社区

加入 **ZT Agent Club** QQ 群，一起交流 ZeroToken 与 AI Agent 自动化：

![ZT Agent Club QQ 群二维码](assets/qq-group-qr.png)

- 群号：942359087
- 扫一扫二维码，加入群聊

## 参与贡献

欢迎提 Issue 和 PR，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

MIT License，见 [LICENSE](LICENSE)。

---

**ZeroToken** - Record once, automate forever.
