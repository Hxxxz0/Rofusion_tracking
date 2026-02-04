# 文本生成动作部署指南

## 概述

`text_to_motion.py` 是一个交互式工具，通过文本描述实时生成机器人动作，支持sim2sim仿真和真机部署。

## 系统架构

```
用户输入文本 → text_to_motion.py ←→ StableMoFusion服务器(SSH隧道)
                   ↓                         
              格式转换+保存NPZ
                   ↓
          UDP(28562): LOAD命令 → policy.py
          UDP(28563): 状态反馈 ← policy.py
                   ↓
         动作完成 → 自动发送default
```

## 快速开始

### 1. 准备工作

#### 安装依赖

```bash
cd /home/limx/project/motion_tracking/sim2real
pip install -r requirements.txt
```

#### 建立SSH隧道（连接远程服务器）

```bash
# 方式1：使用SSH config别名
ssh -L 8000:127.0.0.1:8000 4090-2

# 方式2：使用完整参数
ssh -L 8000:127.0.0.1:8000 root@14.103.233.39 -p 29020

# 方式3：后台运行（推荐）
ssh -L 8000:127.0.0.1:8000 -N -f 4090-2
```

**验证隧道：**
```bash
curl http://127.0.0.1:8000/
# 应该返回服务器状态JSON
```

### 2. Sim2Sim测试流程

#### 终端1：启动仿真器
```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/sim2sim.py --xml_path assets/g1/g1.xml
```

保持此终端窗口焦点，准备接收键盘输入：
- 按 `s` → 机器人移动到默认姿态
- 按 `a` → 开始运动追踪

#### 终端2：启动控制器
```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/deploy.py --net lo --sim2sim
```

等待看到：
```
Successfully connected to the robot.
Enter zero torque state.
Waiting for the start signal...
```

然后切换到终端1按 `s` 和 `a`。

#### 终端3：启动文本生成工具
```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/text_to_motion.py
```

### 3. 交互使用

启动后显示：
```
=== 文本生成动作工具 ===
  输入文本描述 → 生成并加载动作
  - 动作执行中可随时输入新文本切换动作
  - 动作完成后自动切换到default姿态

命令:
  <文本描述>  - 生成新动作
  default     - 手动回到默认姿态
  last        - 重新加载上一个生成的动作
  list        - 显示所有已生成的动作
  clear       - 清理旧的生成文件
  status      - 显示当前动作状态
  tunnel      - 显示SSH隧道配置帮助
  q/quit      - 退出
========================
```

#### 示例会话

```bash
[空闲] > a person walks forward
[生成中] 文本: 'a person walks forward'
          长度: 4.0s, 推理步数: 10
[转换中] 解析动作数据...
[保存] /home/limx/project/motion_tracking/sim2real/assets/data/generated/gen_20260204_153045.npz
[加载中] gen_20260204_153045
[15:30:45] 发送命令 'LOAD:gen_20260204_153045' 到 udp://127.0.0.1:28562

[完成] 动作执行完毕
[自动切换] 发送default命令...

[空闲] > a person jumps
[生成中] 文本: 'a person jumps'
...
```

## 使用场景

### 场景1：正常生成并执行动作

1. 输入文本描述（如 "a person walks forward"）
2. 系统生成动作并自动加载
3. 机器人执行动作
4. 动作完成后自动切换到default姿态

### 场景2：动作执行中切换新动作

1. 当前动作正在执行（如walk）
2. 输入新文本描述（如 "a person runs"）
3. 系统立即中断当前动作
4. 从当前状态平滑过渡到新动作
5. 新动作完成后自动切换到default

### 场景3：手动切换default

随时输入 `default` 命令，立即回到默认姿态。

## 真机部署

### 前置准备

1. **硬件连接**
   - G1机器人开机
   - 网线连接G1和PC
   - 遥控器开机并配对

2. **网络配置**
```bash
sudo ip link set enp4s0 up
sudo ip addr add 192.168.123.100/24 dev enp4s0
ping -c 3 192.168.123.161
```

3. **进入调试模式**
   - 遥控器同时按 `L2 + R2`
   - G1灯光变为**橙灯常亮**

### 启动流程

#### 终端1：启动控制器
```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/deploy.py --net enp4s0 --real
```

遥控器操作：
1. 按 `start` → 移动到默认姿态
2. 按 `A` → 启动运动追踪

#### 终端2：启动文本生成工具
```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/text_to_motion.py
```

然后输入文本描述生成动作。

## 配置说明

配置文件：`sim2real/config/tracking.yaml`

```yaml
text_to_motion:
  enable: true
  ws_host: "127.0.0.1"  # WebSocket地址
  ws_port: 8000
  remote_server:
    host: "14.103.233.39"  # 远程服务器
    port: 29020
    user: "root"
    ssh_alias: "4090-2"
  default_motion_length: 4.0  # 默认动作长度（秒）
  default_inference_steps: 10  # 推理步数（10=快速，50=高质量）
  adaptive_smooth: true  # 自适应平滑
  static_start: true  # 强制静态起始
  static_frames: 2  # 静态帧数
  blend_frames: 8  # 混合帧数
  auto_default_on_complete: true  # 动作完成后自动切换default
```

## 生成文件管理

### 文件位置
所有生成的动作保存在：
```
sim2real/assets/data/generated/gen_YYYYMMDD_HHMMSS.npz
```

### 查看已生成的动作
```bash
[空闲] > list

=== 已生成的动作 (3个) ===
  1. gen_20260204_153045 (2026-02-04 15:30:45)
  2. gen_20260204_153120 (2026-02-04 15:31:20)
  3. gen_20260204_153300 (2026-02-04 15:33:00)
========================================
```

### 清理旧文件
```bash
[空闲] > clear
[清理] 删除 0 个旧文件...
保留最近 10 个文件
```

## 故障排除

### 问题1：WebSocket连接失败

**症状：**
```
[错误] WebSocket连接失败: [Errno 111] Connection refused
```

**解决：**
1. 检查SSH隧道是否建立
2. 验证隧道：`curl http://127.0.0.1:8000/`
3. 检查远程服务器是否运行

### 问题2：缺少websockets库

**症状：**
```
[错误] 缺少 websockets 库
```

**解决：**
```bash
pip install websockets
```

### 问题3：动作不执行

**症状：**
生成成功但机器人不动作

**解决：**
1. 确认deploy.py正在运行
2. 检查UDP端口28562是否被占用
3. 查看deploy.py终端的日志输出

### 问题4：动作完成后不自动切换default

**症状：**
动作播放完毕但没有自动切换到default

**解决：**
1. 检查配置文件中 `auto_default_on_complete: true`
2. 确认UDP端口28563没有被占用
3. 重启text_to_motion.py

## 高级用法

### 自定义生成参数

在交互模式中，可以修改配置文件后无需重启：

```yaml
# 高质量生成
default_inference_steps: 50

# 更长的动作
default_motion_length: 8.0
```

### 命令行参数

```bash
python3 src/text_to_motion.py --config custom_config.yaml
```

## 技术细节

### 数据格式转换

服务器返回38D格式：
- `joint_pos`: (T, 29) [w,x,y,z] quaternion
- `root_rot`: (T, 4) wxyz

自动转换为部署格式：
- `dof_pos`: (T, 29) 按MT_JOINT_ORDER排列
- `root_rot`: (T, 4) xyzw

### UDP通信

- **端口28562**：发送命令到policy.py
  - `LOAD:gen_20260204_153045` - 加载生成的动作
  - `default` - 切换到默认姿态
  
- **端口28563**：接收状态反馈
  - `MOTION_COMPLETE` - 动作执行完毕

## 安全提示

1. **Sim2Sim测试优先**：所有新动作先在仿真中测试
2. **真机测试准备**：
   - 周围至少3×3米空间
   - 地面平整无障碍
   - 有人监控
   - 熟悉紧急停止方法（遥控器select键）
3. **渐进式测试**：从简单动作（walk）开始，逐步尝试复杂动作

## 参考资料

- [CLIENT_API.md](CLIENT_API.md) - WebSocket API详细文档
- [DEPLOYMENT_GUIDE_CN.md](DEPLOYMENT_GUIDE_CN.md) - 完整部署指南
- [convert_simple_to_deploy.py](../convert_simple_to_deploy.py) - 格式转换参考

## 支持

遇到问题？
1. 查看本文档的故障排除部分
2. 检查终端日志输出
3. 验证SSH隧道和网络连接
4. 提交Issue到GitHub

---

**版本**: 1.0  
**最后更新**: 2026-02-04

