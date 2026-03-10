import os
import sys
from pathlib import Path

# 将项目根目录加入路径
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from hardware_adapters.mytRpc import MytRpc

def dump_ui():
    device_ip = "192.168.1.214"
    rpa_port = 30002
    output_file = "device_6_1_dump.xml"

    print(f"正在建立 RPC 实例...")
    rpc = MytRpc()
    
    print(f"正在连接云机 {device_ip}:{rpa_port}...")
    # 根据 _rpc_bootstrap.py，连接方法是 init(ip, port, timeout)
    connected = rpc.init(device_ip, rpa_port, 10)
    
    if not connected:
        print("错误：无法建立连接，请检查云机状态或网络。")
        return

    try:
        print("连接成功，正在抓取 UI 布局...")
        # 根据 mytRpc.py，获取 XML 的方法是 dump_node_xml(dump_all)
        xml_data = rpc.dump_node_xml(True)
        
        if xml_data:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(xml_data)
            print(f"成功！UI 数据已保存至: {os.path.abspath(output_file)}")
            print(f"文件大小: {len(xml_data)} 字节")
        else:
            print("错误：获取到的 XML 数据为空。")
            
    except Exception as e:
        print(f"抓取过程中出现异常: {e}")
    finally:
        rpc.close()

if __name__ == "__main__":
    dump_ui()
