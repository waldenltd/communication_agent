"""
Agent Metrics

Observability metrics for the Level 2 Agent system.
Provides counters, gauges, and histograms for monitoring agent performance.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime
from collections import defaultdict


@dataclass
class MetricValue:
    """A single metric value with metadata."""
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: dict = field(default_factory=dict)


class Counter:
    """A monotonically increasing counter metric."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = threading.Lock()
        self._labels: dict[tuple, float] = defaultdict(float)

    def inc(self, value: float = 1.0, **labels) -> None:
        """Increment the counter."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                self._labels[key] += value
            else:
                self._value += value

    def get(self, **labels) -> float:
        """Get the current counter value."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                return self._labels.get(key, 0.0)
            return self._value

    def get_all(self) -> dict:
        """Get all label combinations and their values."""
        with self._lock:
            result = {"_total": self._value}
            for key, value in self._labels.items():
                label_str = ",".join(f"{k}={v}" for k, v in key)
                result[label_str] = value
            return result


class Gauge:
    """A metric that can increase or decrease."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = threading.Lock()
        self._labels: dict[tuple, float] = defaultdict(float)

    def set(self, value: float, **labels) -> None:
        """Set the gauge to a specific value."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                self._labels[key] = value
            else:
                self._value = value

    def inc(self, value: float = 1.0, **labels) -> None:
        """Increment the gauge."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                self._labels[key] += value
            else:
                self._value += value

    def dec(self, value: float = 1.0, **labels) -> None:
        """Decrement the gauge."""
        self.inc(-value, **labels)

    def get(self, **labels) -> float:
        """Get the current gauge value."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                return self._labels.get(key, 0.0)
            return self._value

    def get_all(self) -> dict:
        """Get all label combinations and their values."""
        with self._lock:
            result = {"_current": self._value}
            for key, value in self._labels.items():
                label_str = ",".join(f"{k}={v}" for k, v in key)
                result[label_str] = value
            return result


class Histogram:
    """A metric that tracks value distribution."""

    # Default bucket boundaries (in seconds for latency)
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self, name: str, description: str = "", buckets: tuple = None):
        self.name = name
        self.description = description
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._lock = threading.Lock()
        self._counts = {b: 0 for b in self.buckets}
        self._counts[float('inf')] = 0
        self._sum = 0.0
        self._count = 0

    def observe(self, value: float) -> None:
        """Record an observation."""
        with self._lock:
            self._sum += value
            self._count += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[bucket] += 1
            self._counts[float('inf')] += 1

    def get_stats(self) -> dict:
        """Get histogram statistics."""
        with self._lock:
            return {
                "count": self._count,
                "sum": self._sum,
                "avg": self._sum / self._count if self._count > 0 else 0,
                "buckets": {
                    f"le_{b}": c for b, c in self._counts.items()
                    if b != float('inf')
                },
                "le_inf": self._counts[float('inf')],
            }


class Timer:
    """Context manager for timing operations."""

    def __init__(self, histogram: Histogram):
        self.histogram = histogram
        self._start: Optional[float] = None

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._start:
            duration = time.time() - self._start
            self.histogram.observe(duration)
        return False


class AgentMetrics:
    """
    Central metrics registry for the Level 2 Agent.

    Tracks:
    - Orchestrator cycles and timing
    - Job processing counts and durations
    - Tool execution counts and errors
    - ReAct reasoning iterations
    - LLM API calls and latency
    """

    def __init__(self):
        # Orchestrator metrics
        self.cycles_total = Counter(
            "agent_cycles_total",
            "Total number of orchestrator cycles completed"
        )
        self.cycles_active = Gauge(
            "agent_cycles_active",
            "Number of currently active cycles"
        )
        self.cycle_duration = Histogram(
            "agent_cycle_duration_seconds",
            "Duration of orchestrator cycles",
            buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
        )

        # Job metrics
        self.jobs_total = Counter(
            "agent_jobs_total",
            "Total number of jobs processed"
        )
        self.jobs_active = Gauge(
            "agent_jobs_active",
            "Number of jobs currently being processed"
        )
        self.jobs_failed = Counter(
            "agent_jobs_failed_total",
            "Total number of failed jobs"
        )
        self.jobs_completed = Counter(
            "agent_jobs_completed_total",
            "Total number of successfully completed jobs"
        )
        self.job_duration = Histogram(
            "agent_job_duration_seconds",
            "Duration of job processing",
            buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
        )

        # Tool metrics
        self.tool_calls_total = Counter(
            "agent_tool_calls_total",
            "Total number of tool calls"
        )
        self.tool_errors_total = Counter(
            "agent_tool_errors_total",
            "Total number of tool call errors"
        )
        self.tool_duration = Histogram(
            "agent_tool_duration_seconds",
            "Duration of tool executions",
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
        )

        # ReAct metrics
        self.reasoning_iterations_total = Counter(
            "agent_reasoning_iterations_total",
            "Total number of ReAct reasoning iterations"
        )
        self.reasoning_iterations_per_job = Histogram(
            "agent_reasoning_iterations_per_job",
            "Number of reasoning iterations per job",
            buckets=(1, 2, 3, 5, 7, 10, 15, 20)
        )

        # LLM metrics
        self.llm_calls_total = Counter(
            "agent_llm_calls_total",
            "Total number of LLM API calls"
        )
        self.llm_errors_total = Counter(
            "agent_llm_errors_total",
            "Total number of LLM API errors"
        )
        self.llm_latency = Histogram(
            "agent_llm_latency_seconds",
            "LLM API call latency",
            buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0)
        )
        self.llm_tokens_total = Counter(
            "agent_llm_tokens_total",
            "Total tokens used in LLM calls"
        )

        # Scheduler metrics
        self.scheduler_sweeps_total = Counter(
            "agent_scheduler_sweeps_total",
            "Total number of scheduler sweeps"
        )
        self.scheduler_jobs_created = Counter(
            "agent_scheduler_jobs_created_total",
            "Total number of jobs created by scheduler"
        )

    def time_cycle(self) -> Timer:
        """Get a timer for measuring cycle duration."""
        return Timer(self.cycle_duration)

    def time_job(self) -> Timer:
        """Get a timer for measuring job duration."""
        return Timer(self.job_duration)

    def time_tool(self) -> Timer:
        """Get a timer for measuring tool duration."""
        return Timer(self.tool_duration)

    def time_llm(self) -> Timer:
        """Get a timer for measuring LLM latency."""
        return Timer(self.llm_latency)

    def record_tool_call(self, tool_name: str, success: bool, duration: float = 0) -> None:
        """Record a tool call with its outcome."""
        self.tool_calls_total.inc(tool=tool_name)
        if not success:
            self.tool_errors_total.inc(tool=tool_name)
        if duration > 0:
            self.tool_duration.observe(duration)

    def record_job_start(self, job_type: str) -> None:
        """Record the start of a job."""
        self.jobs_total.inc(job_type=job_type)
        self.jobs_active.inc(job_type=job_type)

    def record_job_complete(self, job_type: str, success: bool, iterations: int = 0) -> None:
        """Record the completion of a job."""
        self.jobs_active.dec(job_type=job_type)
        if success:
            self.jobs_completed.inc(job_type=job_type)
        else:
            self.jobs_failed.inc(job_type=job_type)
        if iterations > 0:
            self.reasoning_iterations_per_job.observe(iterations)

    def record_llm_call(self, success: bool, tokens: int = 0) -> None:
        """Record an LLM API call."""
        self.llm_calls_total.inc()
        if not success:
            self.llm_errors_total.inc()
        if tokens > 0:
            self.llm_tokens_total.inc(tokens)

    def record_scheduler_sweep(self, sweep_type: str, jobs_created: int) -> None:
        """Record a scheduler sweep."""
        self.scheduler_sweeps_total.inc(sweep_type=sweep_type)
        if jobs_created > 0:
            self.scheduler_jobs_created.inc(jobs_created, sweep_type=sweep_type)

    def get_summary(self) -> dict:
        """Get a summary of all metrics."""
        return {
            "orchestrator": {
                "cycles_total": self.cycles_total.get(),
                "cycles_active": self.cycles_active.get(),
                "cycle_duration": self.cycle_duration.get_stats(),
            },
            "jobs": {
                "total": self.jobs_total.get(),
                "active": self.jobs_active.get(),
                "completed": self.jobs_completed.get(),
                "failed": self.jobs_failed.get(),
                "duration": self.job_duration.get_stats(),
            },
            "tools": {
                "calls_total": self.tool_calls_total.get_all(),
                "errors_total": self.tool_errors_total.get_all(),
                "duration": self.tool_duration.get_stats(),
            },
            "reasoning": {
                "iterations_total": self.reasoning_iterations_total.get(),
                "iterations_per_job": self.reasoning_iterations_per_job.get_stats(),
            },
            "llm": {
                "calls_total": self.llm_calls_total.get(),
                "errors_total": self.llm_errors_total.get(),
                "tokens_total": self.llm_tokens_total.get(),
                "latency": self.llm_latency.get_stats(),
            },
            "scheduler": {
                "sweeps_total": self.scheduler_sweeps_total.get_all(),
                "jobs_created": self.scheduler_jobs_created.get_all(),
            },
        }

    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []

        def add_metric(name: str, value: float, labels: dict = None, help_text: str = ""):
            if help_text:
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} gauge")

            if labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"{name}{{{label_str}}} {value}")
            else:
                lines.append(f"{name} {value}")

        # Orchestrator metrics
        add_metric("agent_cycles_total", self.cycles_total.get(),
                   help_text="Total orchestrator cycles")
        add_metric("agent_cycles_active", self.cycles_active.get())

        # Job metrics
        add_metric("agent_jobs_total", self.jobs_total.get(),
                   help_text="Total jobs processed")
        add_metric("agent_jobs_active", self.jobs_active.get())
        add_metric("agent_jobs_completed_total", self.jobs_completed.get())
        add_metric("agent_jobs_failed_total", self.jobs_failed.get())

        # Tool metrics by name
        for key, value in self.tool_calls_total.get_all().items():
            if key == "_total":
                add_metric("agent_tool_calls_total", value,
                          help_text="Total tool calls")
            elif key:
                # Parse label from key
                parts = dict(item.split("=") for item in key.split(","))
                add_metric("agent_tool_calls_total", value, labels=parts)

        # LLM metrics
        add_metric("agent_llm_calls_total", self.llm_calls_total.get(),
                   help_text="Total LLM API calls")
        add_metric("agent_llm_errors_total", self.llm_errors_total.get())
        add_metric("agent_llm_tokens_total", self.llm_tokens_total.get())

        return "\n".join(lines)


# Global metrics instance
_metrics: Optional[AgentMetrics] = None


def get_metrics() -> AgentMetrics:
    """Get or create the global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = AgentMetrics()
    return _metrics


def reset_metrics() -> None:
    """Reset the global metrics instance (for testing)."""
    global _metrics
    _metrics = AgentMetrics()
