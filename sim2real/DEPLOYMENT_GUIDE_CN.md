# G1 运动追踪部署完整指南

从 Sim2Sim 仿真测试到真机部署的完整流程。

---

## 📋 目录

1. [环境准备](#环境准备)
2. [Sim2Sim 仿真测试](#sim2sim-仿真测试)
3. [真机部署](#真机部署)
4. [运动切换](#运动切换)
5. [故障排除](#故障排除)

---

## 环境准备

### 1. 创建 Conda 环境
```bash
conda create -n gentle python=3.10
conda activate gentle
```

### 2. 安装 Unitree SDK2 Python
```bash
cd /home/limx/project/motion_tracking/sim2real/unitree_sdk2_python
pip3 install -e .
```

如果遇到 cyclonedds 错误：
```bash
cd ~
git clone https://github.com/eclipse-cyclonedds/cyclonedds -b releases/0.10.x 
cd cyclonedds && mkdir build install && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=../install
cmake --build . --target install

cd /home/limx/project/motion_tracking/sim2real/unitree_sdk2_python
export CYCLONEDDS_HOME="~/cyclonedds/install"
pip3 install -e .
```

### 3. 安装其他依赖
```bash
cd /home/limx/project/motion_tracking/sim2real
pip install -r requirements.txt
```

---

## Sim2Sim 仿真测试

**⚠️ 强烈建议先在仿真中测试所有动作！**

### 启动流程

#### 终端 1：启动仿真器
```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/sim2sim.py --xml_path assets/g1/g1.xml
```

**会打开 3D 可视化窗口**，保持此终端焦点以接收键盘输入。

#### 终端 2：启动控制器
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

#### 终端 1：按键操作

在**仿真器终端**（运行 sim2sim.py 的终端）按键：

1. **按 `s`** → 机器人移动到默认姿态
   - 仿真器输出：`Moving to default pose...`
   - 控制器输出：`Moving to init pos....`

2. **按 `a`** → 开始运动追踪
   - 仿真器输出：`Running control loop...`
   - 控制器输出：`Running high level...`

3. **按 `x`** → 退出

#### 终端 3：运动选择器（可选）

```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/motion_select.py
```

可用命令：
- `list` - 显示所有可用运动
- `1` 或 `default` - 回到默认姿态
- `12` 或 `walk1_subject1` - 选择运动
- 空行回车 - 重复上次选择
- `r` - 重新加载配置
- `q` - 退出

---

## 真机部署

### 前置准备

#### 1. 硬件连接
- G1 机器人开机
- 用网线连接 G1 和 PC
- 遥控器开机并配对

#### 2. 网络配置
```bash
# 确保网卡启动
sudo ip link set enp4s0 up

# 配置静态 IP（与 G1 在同一网段）
sudo ip addr add 192.168.123.100/24 dev enp4s0

# 验证配置
ip addr show enp4s0

# 测试连通性
ping -c 3 192.168.123.161
```

#### 3. 测试连接（可选）
```bash
cd /home/limx/project/motion_tracking/sim2real
python3 test_connection.py enp4s0
```

看到 IMU 数据和关节状态说明连接正常。

#### 4. 关闭冲突服务（如果需要）
```bash
# 关闭测试服务（如果在运行）
python3 disable_test_services.py enp4s0

# 检查服务状态
python3 disable_sport_mode.py enp4s0
```

---

### 🔴 关键步骤：进入调试模式

**⚠️ 这是最重要的步骤！**

#### G1 默认状态
- **紫灯常亮** - 零力矩模式（默认）
- 在此模式下**无法运行底层控制**

#### 进入调试模式（阻尼模式）
使用遥控器：
1. **同时按住 `L2` + `R2`**
2. G1 灯光变为 **橙灯常亮**
3. 此时进入调试模式（阻尼模式）

**只有在橙灯常亮（调试模式）下才能运行底层控制！**

---

### 启动控制器

#### 终端 1：启动控制器
```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/deploy.py --net enp4s0 --real
```

等待看到：
```
[Controller] State mapping: 29/29 mapped
Successfully connected to the robot.
Enter zero torque state.
Waiting for the start signal...
```

#### 遥控器操作流程

**阶段 1：零力矩模式**
```
状态：紫灯常亮
操作：同时按 L2 + R2 进入调试模式
结果：橙灯常亮
```

**阶段 2：启动控制**
```
终端显示：Waiting for the start signal...
操作：按遥控器 start 键
结果：机器人移动到默认姿态（约 2 秒）
终端显示：Moving to init pos....
```

**阶段 3：等待激活**
```
终端显示：Press A to tracking policy...
操作：确保机器人站稳（如果在地面）
操作：按遥控器 A 键
结果：开始运动追踪
终端显示：Running high level...
             Time: 0.00, Time real: 0.01, Height: 0.78
```

**阶段 4：正常运行**
- 机器人执行默认运动
- 终端每秒显示状态
- 可以使用运动选择器切换动作

**阶段 5：停止**
```
操作：按遥控器 select 键
结果：安全退出
终端显示：Closing...
```

---

### 运动切换

在控制器运行时，打开新终端：

```bash
cd /home/limx/project/motion_tracking/sim2real
conda activate gentle
python3 src/motion_select.py
```

#### 可用运动列表

| 编号 | 名称 | 描述 |
|-----|------|------|
| 1 | default | 默认站立姿态 |
| 2 | dance1_subject1 | 跳舞 1 |
| 3 | dance2_subject1 | 跳舞 2 |
| 4 | fallAndGetUp1_subject1 | 摔倒与起身 1 |
| 5 | fallAndGetUp2_subject2 | 摔倒与起身 2 |
| 6 | fight1_subject2 | 格斗动作 1 |
| 7 | fightAndSports1_subject1 | 格斗与运动 |
| 8 | jumps1_subject1 | 跳跃 |
| 9 | run1_subject2 | 跑步 1 |
| 10 | run2_subject1 | 跑步 2 |
| 11 | sprint1_subject2 | 冲刺 |
| 12 | walk1_subject1 | 行走 1 |
| 13 | walk2_subject1 | 行走 2 |
| 14 | walk3_subject1 | 行走 3 |

#### 运动切换规则
- 策略只在当前动作完成并回到 `default` 时才开始新运动
- 发送 `default` 会立即让机器人淡出回到空闲姿态
- 建议先发送 `default`，等待几秒，再选择新运动

#### 推荐测试顺序
```bash
# 1. 从简单到复杂
1       # default - 站立
12      # walk1_subject1 - 行走
1       # default

# 2. 动态动作
9       # run1_subject2 - 跑步
1       # default

# 3. 复杂动作
2       # dance1_subject1 - 跳舞
8       # jumps1_subject1 - 跳跃
```

---

## 遥控器按键说明

### 关键按键

| 按键 | 功能 | 说明 |
|------|------|------|
| **L2 + R2** | **进入调试模式** | **橙灯常亮，必须先执行此步骤** |
| `start` | 移动到默认姿态 | 从零力矩 → 初始姿态 |
| `A` | 启动运动追踪策略 | 开始执行运动 |
| `select` | 紧急停止并退出 | 安全退出程序 |

### 按键映射（完整）

| 索引 | 按键名 | 功能 |
|-----|--------|------|
| 0 | R1 | 右上肩键 |
| 1 | L1 | 左上肩键 |
| 2 | start | 启动键 |
| 3 | select | 选择/退出键 |
| 4 | R2 | 右下肩键 |
| 5 | L2 | 左下肩键 |
| 6 | F1 | 功能键 1 |
| 7 | F2 | 功能键 2 |
| 8 | A | A 键 |
| 9 | B | B 键 |
| 10 | X | X 键 |
| 11 | Y | Y 键 |
| 12-15 | 方向键 | 上/右/下/左 |

---

## 故障排除

### 问题 1：Loop rate: 0 Hz

**症状：**
```
Running high level...
[Warning] Loop rate: 0 Hz
Closing...
```

**原因：** 未进入调试模式（阻尼模式）

**解决：**
1. 确认 G1 灯光为 **橙灯常亮**
2. 如果是紫灯，按遥控器 **L2 + R2** 进入调试模式
3. 重新启动控制器

---

### 问题 2：关节抽搐或无力

**可能原因：**
1. 未关闭冲突服务
2. 增益参数不合适
3. 电池电量不足

**解决：**
```bash
# 关闭测试服务
python3 disable_test_services.py enp4s0

# 检查电池电压（应 > 45V）
python3 debug_robot_state.py enp4s0
```

---

### 问题 3：网络连接失败

**症状：**
```
ping: Destination Host Unreachable
```

**解决：**
```bash
# 检查网线连接
# 确认 IP 配置
ip addr show enp4s0

# 重新配置
sudo ip link set enp4s0 up
sudo ip addr add 192.168.123.100/24 dev enp4s0
```

---

### 问题 4：遥控器无响应

**可能原因：**
1. 遥控器未开机或电量不足
2. 遥控器未配对
3. 信号干扰

**解决：**
1. 检查遥控器电量
2. 重新配对遥控器
3. 运行调试脚本查看遥控器状态：
```bash
python3 debug_robot_state.py enp4s0
```

---

## 安全注意事项

### ⚠️ 部署前检查清单

- [ ] 已在 Sim2Sim 中测试过要运行的动作
- [ ] G1 电池充满（电压 > 45V）
- [ ] 周围有足够空间（至少 3×3 米）
- [ ] 地面平整、无障碍物
- [ ] 有人在旁监控
- [ ] 熟悉紧急停止方法（按 select 键）
- [ ] 准备好物理紧急停止按钮

### 🔴 紧急停止方法

1. **按遥控器 `select` 键** - 软件停止
2. **物理紧急停止按钮** - 硬件断电
3. **拔掉电池** - 最后手段

### 📹 建议

- 第一次运行建议录像记录
- 从简单动作（walk）开始测试
- 逐步尝试更复杂的动作
- 任何异常立即停止

---

## 配置文件说明

### 主要配置文件

| 文件 | 说明 |
|------|------|
| `config/controller.yaml` | 控制器配置（PID 增益、关节限位等） |
| `config/tracking.yaml` | 追踪策略配置（模型路径、运动数据等） |
| `assets/ckpts/G1TRACKING-AMASS/policy.onnx` | AMASS 数据集训练的策略模型 |
| `assets/ckpts/G1TRACKING-LAFAN/policy.onnx` | LAFAN 数据集训练的策略模型 |
| `assets/data/*.npz` | 运动参考数据 |

### 切换模型

编辑 `config/tracking.yaml`：

```yaml
# 使用 AMASS 模型（默认）
policy_path: "assets/ckpts/G1TRACKING-AMASS/policy.onnx"
action_scale: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, ...]  # AMASS 动作缩放

# 或使用 LAFAN 模型
# policy_path: "assets/ckpts/G1TRACKING-LAFAN/policy.onnx"
# action_scale: [0.5, 0.5, 0.25, 0.25, 0.25, 0.25, ...]  # LAFAN 动作缩放
```

---

## 快速参考

### Sim2Sim 快速启动
```bash
# 终端 1
python3 src/sim2sim.py --xml_path assets/g1/g1.xml

# 终端 2  
python3 src/deploy.py --net lo --sim2sim

# 终端 1: 按 s → 按 a

# 终端 3（可选）
python3 src/motion_select.py
```

### 真机快速启动
```bash
# 网络配置
sudo ip link set enp4s0 up
sudo ip addr add 192.168.123.100/24 dev enp4s0

# 启动控制器
python3 src/deploy.py --net enp4s0 --real

# 遥控器操作
# 1. 按 L2 + R2（橙灯）
# 2. 按 start
# 3. 按 A

# 运动切换（可选）
python3 src/motion_select.py
```

---

## 常用工具脚本

| 脚本 | 功能 |
|------|------|
| `test_connection.py` | 测试机器人连接和状态 |
| `debug_robot_state.py` | 实时显示遥控器和机器人状态 |
| `disable_sport_mode.py` | 检查并关闭 sport_mode 服务 |
| `disable_test_services.py` | 关闭测试服务 |

---

## 技术支持

遇到问题？
1. 先查看 [故障排除](#故障排除) 部分
2. 运行 `debug_robot_state.py` 检查状态
3. 查看项目主 README 和官方文档
4. 提交 Issue 到 GitHub

---

## 版本信息

- 测试环境：Ubuntu 22.04 + Python 3.10
- G1 固件：需要支持底层控制的版本
- SDK 版本：unitree_sdk2_python

---

**祝部署成功！🎉**

