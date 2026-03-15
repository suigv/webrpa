from __future__ import annotations

import json
import anyio
from collections.abc import AsyncIterator

from core.task_control import get_task_controller
from models.task import TaskStatus

TERMINAL_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}


async def get_task(task_id: str):
    controller = get_task_controller()
    return await anyio.to_thread.run_sync(controller.get, task_id)


async def stop_device_tasks(device_id: int) -> tuple[int, list[str]]:
    controller = get_task_controller()
    
    def _do_stop():
        task_ids = controller.list_running_task_ids_by_device(device_id)
        cancelled_count = 0
        for tid in task_ids:
            state = controller.cancel_state(tid)
            if state in {"cancelled", "cancelling"}:
                cancelled_count += 1
        return cancelled_count, task_ids

    return await anyio.to_thread.run_sync(_do_stop)


async def stream_task_events(task_id: str, after_event_id: int = 0) -> AsyncIterator[str]:
    """异步生成器：从数据库流式读取任务事件并转化为 SSE 格式。"""
    controller = get_task_controller()
    cursor = after_event_id
    
    while True:
        # 在线程池中执行同步的数据库查询
        events = await anyio.to_thread.run_sync(
            lambda: controller.list_events(task_id=task_id, after_event_id=cursor)
        )
        
        for event in events:
            yield (
                f"id: {event.event_id}\n"
                f"event: {event.event_type}\n"
                f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
            )
            cursor = event.event_id

        # 检查任务是否已结束
        latest = await anyio.to_thread.run_sync(lambda: controller.get(task_id))
        if latest and latest.status in TERMINAL_STATUSES:
            # 抓取最后残留的事件
            final_events = await anyio.to_thread.run_sync(
                lambda: controller.list_events(task_id=task_id, after_event_id=cursor)
            )
            for event in final_events:
                yield (
                    f"id: {event.event_id}\n"
                    f"event: {event.event_type}\n"
                    f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
                )
            yield ": close\n\n"
            break
            
        # 非阻塞等待
        await anyio.sleep(0.5)
