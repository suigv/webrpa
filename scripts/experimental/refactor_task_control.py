import re

with open("core/task_control.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the start of _work_loop
match = re.search(r'    def _work_loop\(self\) -> None:\n(.*?)(?=    def _resolve_target_runtime)', content, re.DOTALL)
if not match:
    print("Could not find _work_loop")
    exit(1)

work_loop_body = match.group(1)

# We want to keep the dequeue and mark_running in _work_loop, and submit the rest to executor
# The line to split at is: "            record = self._store.get_task(task_id)"

split_idx = work_loop_body.find('            record = self._store.get_task(task_id)')

loop_part1 = work_loop_body[:split_idx]
loop_part2 = work_loop_body[split_idx:]

# Part 1 stays in _work_loop, but we add executor submission
new_work_loop = f"""    def _work_loop(self) -> None:
{loop_part1}            if self._executor is not None:
                self._executor.submit(self._process_task, task_id)
            else:
                self._process_task(task_id)

    def _process_task(self, task_id: str) -> None:
"""

# Indent part2 correctly (it's currently indented 12 spaces, needs to be 8)
import textwrap
part2_unindented = textwrap.dedent(loop_part2)
part2_indented = textwrap.indent(part2_unindented, "        ")

new_work_loop += part2_indented

# Replace the old _work_loop with the new one
new_content = content[:match.start()] + new_work_loop + "\n" + content[match.end():]

with open("core/task_control.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("Refactored _work_loop successfully")
