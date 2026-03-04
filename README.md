# panda-bot
panda bot 是一个通用智能体

## 1️⃣ 我们目标
* 不依赖复杂框架
* 只有 python3 + bash
* 可扩展工具,默认带有 playwright
* 有状态机
* 有验证层
* 有失败恢复
* 有最大步数防死循环

### 分层设计
```
┌─────────────────────┐
│        User         │
└─────────┬───────────┘
↓
┌─────────────────────┐
│   Control Layer     │   ← 你真正要设计的核心
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

---

## 2️⃣ 控制层必须具备的能力

### A. 状态机

每次循环必须有状态：

```
INIT → THINK → ACT → VALIDATE → DONE / ERROR
```

不能只有 message loop。

---

### B. 明确的 LLM 输出协议

LLM 只能输出三种类型：

```json
{
  "type": "final"
}
```
```json
{
  "type": "tool",
  "tool": "bash",
  "input": "ls -la"
}
```
```json
{
  "type": "think"
}
```

不允许自由文本污染控制层。

---

### C. 验证层（硬规则优先）

验证顺序：

1. exit code
2. JSON schema
3. 文件存在检查
4. 再让 LLM 判断语义

---

### D. 失败恢复

* 自动重试（最多 N 次）
* 超过阈值自动终止
* 防止无限循环

---

### E. 步数限制

```python
MAX_STEPS = 30
```

任何 Agent 没有这个都会炸。