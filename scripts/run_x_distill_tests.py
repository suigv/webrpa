#!/usr/bin/env python3
import time
import requests
import json
import sys

API_BASE = "http://127.0.0.1:8001"

def main():
    # 1. Check health
    try:
        health = requests.get(f"{API_BASE}/health").json()
        print("✅ Server is reachable.")
    except Exception as e:
        print(f"❌ Cannot connect to server at {API_BASE}: {e}")
        sys.exit(1)

    # 2. Get online devices
    try:
        resp = requests.get(f"{API_BASE}/api/devices/")
        resp.raise_for_status()
        devices = resp.json()
    except Exception as e:
        print(f"❌ Failed to fetch devices: {e}")
        sys.exit(1)
        
    online_clouds = []
    for d in devices:
        device_id = d.get("device_id") or d.get("id")
        for c in d.get("cloud_machines", []):
            if c.get("status") == "running" and c.get("availability_state") == "available":
                online_clouds.append({"device_id": device_id, "cloud_id": c["cloud_id"]})
            
    print(f"Found {len(online_clouds)} cloud instances.")
    if len(online_clouds) < 3:
        print("⚠️ Warning: Less than 3 cloud instances found, will reuse them or only run partial tests.")
        if not online_clouds:
            print("❌ No cloud instances found. Exiting.")
            sys.exit(1)

    # 3. Define the flows for 'x' app
    flows = [
        "点击左上角的个人头像，打开左侧边栏菜单",
        "在底部导航栏中找到并点击'通知'或'Notifications'图标",
        "点击底部的'搜索'图标，准备进行搜索"
    ]
    
    submitted_tasks = []
    
    # 4. Submit tasks
    for i, prompt in enumerate(flows):
        target = online_clouds[i % len(online_clouds)]
        payload = {
            "task": "gpt_executor",
            "payload": {
                "app": "x",
                "goal": prompt,
                "expected_state_ids": ["success", "target_reached"],
                "allowed_actions": [
                    "ui.click",
                    "ui.input_text",
                    "ui.swipe",
                    "ui.key_press"
                ]
            },
            "targets": [target],
            "priority": 50
        }
        
        try:
            print(f"Submitting flow {i+1}: {prompt} to Cloud {target['cloud_id']} on Device {target['device_id']}")
            res = requests.post(f"{API_BASE}/api/tasks/", json=payload)
            res.raise_for_status()
            task_id = res.json().get("task_id")
            print(f"  -> Task created: {task_id}")
            submitted_tasks.append(task_id)
        except Exception as e:
            print(f"❌ Failed to submit task: {e}")
            if hasattr(e, 'response') and e.response:
                print(e.response.text)
                
    print("\n--- Summary ---")
    print("All tasks submitted. You can monitor the progress on the web console (http://127.0.0.1:8001/web)")
    print("Or you can check the trace files later at: config/data/traces/<task_id>")
    for t in submitted_tasks:
        print(f"Task ID: {t}")

if __name__ == "__main__":
    main()
