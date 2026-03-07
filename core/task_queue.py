from __future__ import annotations

import heapq
import importlib
import os
import queue
import threading
import time
from typing import Protocol


class QueueBackend(Protocol):
    def enqueue(
        self,
        task_id: str,
        delay_seconds: int = 0,
        priority: int = 50,
        run_at_epoch: float | None = None,
    ) -> None: ...

    def dequeue(self, timeout_seconds: int = 1) -> str | None: ...


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._q: queue.PriorityQueue[tuple[int, int, str]] = queue.PriorityQueue()
        self._delayed: list[tuple[float, int, int, str]] = []
        self._lock = threading.Lock()
        self._counter = 0

    def enqueue(
        self,
        task_id: str,
        delay_seconds: int = 0,
        priority: int = 50,
        run_at_epoch: float | None = None,
    ) -> None:
        prio = max(0, min(100, int(priority)))
        has_delay = run_at_epoch is not None or delay_seconds > 0
        if not has_delay:
            with self._lock:
                self._counter += 1
                self._q.put((-prio, self._counter, task_id))
            return
        if run_at_epoch is not None:
            due = float(run_at_epoch)
        else:
            due = time.time() + float(delay_seconds)
        with self._lock:
            self._counter += 1
            heapq.heappush(self._delayed, (due, -prio, self._counter, task_id))

    def _promote_due(self) -> None:
        now = time.time()
        with self._lock:
            while self._delayed and self._delayed[0][0] <= now:
                _due, prio, order, task_id = heapq.heappop(self._delayed)
                self._q.put((prio, order, task_id))

    def dequeue(self, timeout_seconds: int = 1) -> str | None:
        deadline = time.time() + max(0, int(timeout_seconds))
        while True:
            self._promote_due()
            try:
                _prio, _order, task_id = self._q.get(timeout=0.1)
                return task_id
            except queue.Empty:
                if time.time() >= deadline:
                    return None


class RedisTaskQueue:
    def __init__(self, redis_url: str, queue_key: str = "myt:new:tasks:queue") -> None:
        try:
            redis = importlib.import_module("redis")
        except Exception as exc:
            raise RuntimeError("redis package is required for RedisTaskQueue") from exc

        self._client = redis.from_url(redis_url, decode_responses=True)
        self._queue_key = queue_key
        self._delayed_key = f"{queue_key}:delayed"
        self._seq_key = f"{queue_key}:seq"

    def enqueue(
        self,
        task_id: str,
        delay_seconds: int = 0,
        priority: int = 50,
        run_at_epoch: float | None = None,
    ) -> None:
        prio = max(0, min(100, int(priority)))
        has_delay = run_at_epoch is not None or delay_seconds > 0
        if not has_delay:
            seq = int(self._client.incr(self._seq_key))
            score = (100 - prio) * 1_000_000_000 + seq
            self._client.zadd(self._queue_key, {task_id: float(score)})
            return
        if run_at_epoch is not None:
            score = float(run_at_epoch)
        else:
            score = time.time() + float(delay_seconds)
        payload = f"{prio}:{task_id}"
        self._client.zadd(self._delayed_key, {payload: score})

    def _promote_due(self) -> None:
        now = time.time()
        due_items = self._client.zrangebyscore(self._delayed_key, min="-inf", max=now, start=0, num=100)
        if not due_items:
            return
        pipe = self._client.pipeline()
        for item in due_items:
            try:
                prio_str, task_id = str(item).split(":", 1)
                prio = max(0, min(100, int(prio_str)))
            except Exception:
                prio = 50
                task_id = str(item)
            seq = int(self._client.incr(self._seq_key))
            score = (100 - prio) * 1_000_000_000 + seq
            pipe.zrem(self._delayed_key, item)
            pipe.zadd(self._queue_key, {task_id: float(score)})
        pipe.execute()

    def dequeue(self, timeout_seconds: int = 1) -> str | None:
        deadline = time.time() + max(0, int(timeout_seconds))
        while True:
            self._promote_due()
            remaining = max(0.1, deadline - time.time())
            block_seconds = int(min(1.0, remaining))
            if block_seconds < 1:
                block_seconds = 1
            item = self._client.zpopmin(self._queue_key, 1)
            if item:
                value = item[0][0]
                return str(value)
            time.sleep(0.05)
            if time.time() >= deadline:
                return None


def create_task_queue() -> QueueBackend:
    backend = os.environ.get("MYT_TASK_QUEUE_BACKEND", "redis").strip().lower()
    redis_url = os.environ.get("MYT_REDIS_URL", "redis://127.0.0.1:6379/0")
    if backend == "memory":
        return InMemoryTaskQueue()

    try:
        return RedisTaskQueue(redis_url=redis_url)
    except Exception:
        return InMemoryTaskQueue()
