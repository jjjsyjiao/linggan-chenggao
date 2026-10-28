"""Prometheus 指标：HTTP 通用 + AI 专用（token、任务队列、执行耗时等）。"""

from prometheus_client import Counter, Gauge, Histogram

# HTTP 通用由 prometheus-fastapi-instrumentator 自动暴露

# AI 专用指标
ai_token_usage_total = Counter(
    "ai_token_usage_total",
    "各模型/Agent 的 Token 消耗",
    ["model", "agent_role"],
)
ai_task_queue_depth = Gauge(
    "ai_task_queue_depth",
    "当前等待处理的 AI 任务队列深度",
)
crew_execution_seconds = Histogram(
    "crew_execution_seconds",
    "编排流程耗时分布（秒）",
    ["flow_name"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)
ai_agent_error_total = Counter(
    "ai_agent_error_total",
    "智能体失败/重试次数",
    ["agent_role", "error_type"],
)
