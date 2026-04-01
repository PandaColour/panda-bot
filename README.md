# panda-bot
Panda Bot 是一个通用智能体

## 快速开始

### 环境要求
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 初始化

```bash
# 克隆项目
git clone https://github.com/your-repo/panda-bot.git
cd panda-bot

# 创建虚拟环境并安装依赖
uv .venv
uv pip install -r requirements.txt

# 运行
uv run python src/main.py
```

### 配置

编辑 `config.json` 配置 LLM 和 MCP 服务器。

---

## 架构设计

### 分层设计
```
┌─────────────────────┐
│        User         │
└─────────┬───────────┘
↓
┌─────────────────────┐
│   Control Layer     │   ← 核心控制层
│---------------------│
│ State Machine       │
│ Tool Router         │
│ Validation Engine   │
│ Retry Manager       │
│ Memory Manager      │
│ Safety Guard        │
└─────────┬───────────┘
↓
┌─────────────────────┐
│   LLM Decision      │
└─────────┬───────────┘
↓
┌─────────────────────┐
│ Tools (bash/python) │
└─────────────────────┘
```

### 目录结构
```
src/
├── main.py              # 入口
├── agent/               # Agent 核心
│   ├── agent.py         # AgentLoop 状态机
│   ├── session.py       # 会话管理
│   ├── planner.py       # 任务规划
│   ├── task.py          # 任务管理
│   └── tools/           # 工具集
├── channel/             # 交互渠道
│   └── chat_window.py   # PySide6 GUI
├── config/              # 配置管理
└── utils/               # 工具函数
```

---

## 控制层能力

### A. 状态机

```
INIT → THINK → ACT → VALIDATE → DONE / ERROR
```

### B. 失败恢复
- 自动重试（最多 N 次）
- 超过阈值自动终止
- 防止无限循环

### C. 步数限制

```python
MAX_STEPS = 30
```

---

## 技术栈
- **GUI**: PySide6 + qasync (Qt + asyncio 共享事件循环)
- **MCP**: 支持 Stdio 和 HTTP 两种连接方式
- **异步**: asyncio
