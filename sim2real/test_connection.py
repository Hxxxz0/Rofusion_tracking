#!/usr/bin/env python3
"""
简单的 G1 连接测试脚本
只读取状态，不发送控制指令
"""
import sys
import time
from unitree_sdk2py.core.channel import ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowState_

class G1StateReader:
    def __init__(self):
        self.low_state = unitree_hg_msg_dds__LowState_()
        self.received_count = 0
        
        # 订阅底层状态
        self.lowstate_subscriber = ChannelSubscriber("rt/lowstate", LowState_)
        self.lowstate_subscriber.Init(self.state_handler, 0)
        
    def state_handler(self, msg):
        """状态回调函数"""
        self.low_state = msg
        self.received_count += 1
        
    def print_status(self):
        """打印机器人状态"""
        if self.received_count == 0:
            print("⏳ 等待接收机器人数据...")
            return
            
        print(f"\n{'='*60}")
        print(f"✅ 已接收 {self.received_count} 条消息")
        print(f"{'='*60}")
        
        # IMU 数据
        print("\n📐 IMU 状态:")
        quat = self.low_state.imu_state.quaternion
        gyro = self.low_state.imu_state.gyroscope
        print(f"  四元数: [{quat[0]:.3f}, {quat[1]:.3f}, {quat[2]:.3f}, {quat[3]:.3f}]")
        print(f"  角速度: [{gyro[0]:.3f}, {gyro[1]:.3f}, {gyro[2]:.3f}] rad/s")
        
        # 电池（G1 可能没有直接的电池字段，跳过）
        # print(f"\n🔋 电池状态:")
        # print(f"  电压: {self.low_state.power_v:.2f} V")
        # print(f"  电流: {self.low_state.power_a:.2f} A")
        
        # 前几个关节状态（示例）
        print(f"\n🦿 关节状态 (前6个):")
        for i in range(min(6, len(self.low_state.motor_state))):
            motor = self.low_state.motor_state[i]
            print(f"  关节{i}: 位置={motor.q:6.3f} rad, 速度={motor.dq:6.3f} rad/s, 力矩={motor.tau_est:6.3f} Nm")
        
        # 无线遥控器
        print(f"\n🎮 遥控器状态:")
        print(f"  按键: {list(self.low_state.wireless_remote[:8])}")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 test_connection.py <网卡名称>")
        print("示例: python3 test_connection.py enp4s0")
        sys.exit(1)
    
    network_interface = sys.argv[1]
    
    print(f"🤖 G1 机器人连接测试")
    print(f"📡 网络接口: {network_interface}")
    print(f"{'='*60}\n")
    
    # 初始化 DDS 通信
    ChannelFactoryInitialize(0, network_interface)
    
    # 创建状态读取器
    reader = G1StateReader()
    
    print("⏳ 连接中...")
    print("   (如果长时间无响应，请检查:")
    print("   1. 机器人是否开机")
    print("   2. 网线是否连接")
    print("   3. IP 地址是否配置正确)")
    print("\n按 Ctrl+C 退出\n")
    
    try:
        # 每秒打印一次状态
        while True:
            reader.print_status()
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\n\n👋 测试结束")
        if reader.received_count > 0:
            print(f"✅ 连接成功！共接收 {reader.received_count} 条消息")
        else:
            print("❌ 未接收到数据，请检查连接")

if __name__ == "__main__":
    main()

