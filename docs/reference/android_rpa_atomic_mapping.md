# Android RPA Atomic Mapping

Source of truth:
- Official doc: `https://dev.moyunteng.com/docs/NewMYTOS/MYT_ANDROID_RPA`

Checked on:
- 2026-03-07

## Summary

- Official Android RPA doc methods reviewed: 49
- Exposed as engine atomic actions: 49
- Internal runtime-only methods intentionally not exposed as plugin actions: connection lifecycle and memory management helpers

## Atomic Coverage

| Official capability | Local wrapper | Atomic action |
|---|---|---|
| `getVersion` | `MytRpc.get_sdk_version()` | `device.get_sdk_version` |
| `checkLive` / connect state | `MytRpc.check_connect_state()` | `device.check_connect_state` |
| `execCmd` | `MytRpc.exec_cmd()` | `device.exec` |
| `dumpNodeXml` | `MytRpc.dump_node_xml()` | `ui.dump_node_xml` |
| `dumpNodeXmlEx` | `MytRpc.dump_node_xml_ex()` | `ui.dump_node_xml_ex` |
| `getDisplayRotate` | `MytRpc.get_display_rotate()` | `device.get_display_rotate` |
| `takeCaptrue` | `MytRpc.take_capture()` | `device.capture_raw` |
| `takeCaptrueEx` | `MytRpc.take_capture_ex()` | `device.capture_raw` |
| `takeCaptrueCompress` | `MytRpc.take_capture_compress()` | `device.capture_compressed` |
| `takeCaptrueCompressEx` | `MytRpc.take_capture_compress_ex()` | `device.capture_compressed` |
| `sendText` | `MytRpc.sendText()` | `ui.input_text` |
| `openApp` | `MytRpc.openApp()` | `app.open` |
| `stopApp` | `MytRpc.stopApp()` | `app.stop` |
| `touchDown` | `MytRpc.touchDown()` | `ui.touch_down` |
| `touchUp` | `MytRpc.touchUp()` | `ui.touch_up` |
| `touchMove` | `MytRpc.touchMove()` | `ui.touch_move` |
| `touchClick` | `MytRpc.touchClick()` | `ui.click` |
| `longClick` | `MytRpc.longClick()` | `ui.long_click` |
| `swipe` | `MytRpc.swipe()` | `ui.swipe` |
| `keyPress` | `MytRpc.keyPress()` | `ui.key_press` |
| `setRpaWorkMode` | `MytRpc.setRpaWorkMode()` | `device.set_work_mode` |
| `useNewNodeMode` | `MytRpc.use_new_node_mode()` | `device.use_new_node_mode` |
| `screentshot` | `MytRpc.screentshot()` | `device.screenshot` |
| `startVideoStream` | `MytRpc.start_video_stream()` | `device.video_stream_start` |
| `stopVideoStream` | `MytRpc.stop_video_stream()` | `device.video_stream_stop` |
| `createSelector` / `newSelector` | `MytRpc.create_selector()` | `ui.create_selector` |
| `clear_selector` | `MytRpc.clear_selector()` | `ui.selector_clear` |
| `free_selector` | `MytRpc.free_selector()` | `ui.selector_free` |
| selector query builders | `MytSelector.addQuery_*()` | `ui.selector_add_query` |
| `execQueryOne` | `MytSelector.execQueryOne()` | `ui.selector_exec_one` / `ui.selector_click_one` |
| `find_nodes` | `MytRpc.find_nodes()` | `ui.selector_find_nodes` |
| `free_nodes` | `MytRpc.free_nodes()` | `ui.selector_free_nodes` |
| `get_nodes_size` | `MytRpc.get_nodes_size()` | `ui.selector_get_nodes_size` |
| `get_node_by_index` | `MytRpc.get_node_by_index()` | `ui.selector_get_node_by_index` |
| `get_node_parent` | `MytRpc.get_node_parent()` | `ui.node_get_parent` |
| `get_node_child_count` | `MytRpc.get_node_child_count()` | `ui.node_get_child_count` |
| `get_node_child` | `MytRpc.get_node_child()` | `ui.node_get_child` |
| `get_node_json` | `MytRpc.get_node_json()` | `ui.node_get_json` |
| `get_node_text` | `MytRpc.get_node_text()` | `ui.node_get_text` |
| `get_node_desc` | `MytRpc.get_node_desc()` | `ui.node_get_desc` |
| `get_node_package` | `MytRpc.get_node_package()` | `ui.node_get_package` |
| `get_node_class` | `MytRpc.get_node_class()` | `ui.node_get_class` |
| `get_node_id` | `MytRpc.get_node_id()` | `ui.node_get_id` |
| `get_node_bound` | `MytRpc.get_node_bound()` | `ui.node_get_bound` |
| `get_node_bound_center` | `MytRpc.get_node_bound_center()` | `ui.node_get_bound_center` |
| `Click_events` | `MytRpc.click_node()` / `RpcNode.click_events()` | `ui.node_click` |
| `longClick_events` | `MytRpc.long_click_node()` / `RpcNode.long_click_events()` | `ui.node_long_click` |

## Runtime-only Methods

These exist in the local wrapper but are not exposed as plugin actions on purpose:

| Method | Reason |
|---|---|
| `openDevice` / `init` | connection lifecycle is centrally managed by action handlers |
| `closeDevice` / `close` | connection cleanup is automatic in action handlers |
| `release` / `freeRpcPtr` | memory management helper, not business-level automation |

## Notes

- Selector query methods are considered atomized through one generic action: `ui.selector_add_query`.
- Rectangular and full-screen capture are both covered through parameterized actions rather than duplicated action names.
- Connection establishment remains handler-managed so workflow authors do not need to manually open/close RPC sessions.
