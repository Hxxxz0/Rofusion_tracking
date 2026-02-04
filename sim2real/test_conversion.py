#!/usr/bin/env python3
"""
测试数据转换是否正确
验证Isaac顺序到MT顺序的映射
"""

import numpy as np

# Isaac关节顺序（左右交替）
ISAAC_JOINT_ORDER = [
    "left_hip_pitch_joint", "right_hip_pitch_joint", "waist_yaw_joint",
    "left_hip_roll_joint", "right_hip_roll_joint", "waist_roll_joint",
    "left_hip_yaw_joint", "right_hip_yaw_joint", "waist_pitch_joint",
    "left_knee_joint", "right_knee_joint",
    "left_shoulder_pitch_joint", "right_shoulder_pitch_joint",
    "left_ankle_pitch_joint", "right_ankle_pitch_joint",
    "left_shoulder_roll_joint", "right_shoulder_roll_joint",
    "left_ankle_roll_joint", "right_ankle_roll_joint",
    "left_shoulder_yaw_joint", "right_shoulder_yaw_joint",
    "left_elbow_joint", "right_elbow_joint",
    "left_wrist_roll_joint", "right_wrist_roll_joint",
    "left_wrist_pitch_joint", "right_wrist_pitch_joint",
    "left_wrist_yaw_joint", "right_wrist_yaw_joint",
]

# MT关节顺序（部署格式要求，按部位分组）
MT_JOINT_ORDER = [
    'left_hip_pitch_joint', 'left_hip_roll_joint', 'left_hip_yaw_joint', 
    'left_knee_joint', 'left_ankle_pitch_joint', 'left_ankle_roll_joint',
    'right_hip_pitch_joint', 'right_hip_roll_joint', 'right_hip_yaw_joint', 
    'right_knee_joint', 'right_ankle_pitch_joint', 'right_ankle_roll_joint',
    'waist_yaw_joint', 'waist_roll_joint', 'waist_pitch_joint',
    'left_shoulder_pitch_joint', 'left_shoulder_roll_joint', 'left_shoulder_yaw_joint', 
    'left_elbow_joint', 'left_wrist_roll_joint', 'left_wrist_pitch_joint', 'left_wrist_yaw_joint',
    'right_shoulder_pitch_joint', 'right_shoulder_roll_joint', 'right_shoulder_yaw_joint', 
    'right_elbow_joint', 'right_wrist_roll_joint', 'right_wrist_pitch_joint', 'right_wrist_yaw_joint'
]

def create_isaac_to_mt_mapping():
    """创建从Isaac顺序到MT顺序的索引映射"""
    mapping = []
    for mt_joint in MT_JOINT_ORDER:
        if mt_joint in ISAAC_JOINT_ORDER:
            mapping.append(ISAAC_JOINT_ORDER.index(mt_joint))
        else:
            raise ValueError(f"MT关节 '{mt_joint}' 在Isaac顺序中未找到!")
    return np.array(mapping)

def test_mapping():
    """测试映射是否正确"""
    print("=" * 60)
    print("测试Isaac到MT的关节顺序映射")
    print("=" * 60)
    
    # 创建映射
    mapping = create_isaac_to_mt_mapping()
    
    print(f"\n总关节数: {len(ISAAC_JOINT_ORDER)}")
    print(f"映射数组: {mapping}")
    
    # 验证映射
    print("\n映射验证:")
    all_correct = True
    for i, mt_joint in enumerate(MT_JOINT_ORDER):
        isaac_idx = mapping[i]
        isaac_joint = ISAAC_JOINT_ORDER[isaac_idx]
        if mt_joint == isaac_joint:
            status = "✓"
        else:
            status = "✗"
            all_correct = False
        print(f"  {i:2d}. MT[{i:2d}] {mt_joint:30s} ← Isaac[{isaac_idx:2d}] {isaac_joint:30s} {status}")
    
    print("\n" + "=" * 60)
    if all_correct:
        print("✓ 映射验证通过！")
    else:
        print("✗ 映射验证失败！")
    print("=" * 60)
    
    # 测试实际转换
    print("\n测试实际数据转换:")
    # 创建测试数据（每个关节用其索引值作为数据）
    isaac_data = np.arange(29, dtype=np.float32)
    print(f"Isaac顺序数据: {isaac_data}")
    
    # 转换为MT顺序
    mt_data = isaac_data[mapping]
    print(f"MT顺序数据:    {mt_data}")
    
    # 验证几个关键关节
    print("\n关键关节验证:")
    test_joints = [
        ("left_hip_pitch_joint", 0),
        ("right_hip_pitch_joint", 6),
        ("waist_yaw_joint", 12),
        ("left_ankle_pitch_joint", 4),
    ]
    
    for joint_name, expected_mt_idx in test_joints:
        isaac_idx = ISAAC_JOINT_ORDER.index(joint_name)
        actual_mt_idx = MT_JOINT_ORDER.index(joint_name)
        converted_value = mt_data[actual_mt_idx]
        
        print(f"  {joint_name}:")
        print(f"    Isaac索引: {isaac_idx}, MT索引: {actual_mt_idx}")
        print(f"    原始值: {isaac_data[isaac_idx]}, 转换后: {converted_value}")
        print(f"    {'✓ 正确' if isaac_data[isaac_idx] == converted_value else '✗ 错误'}")
    
    return all_correct

if __name__ == "__main__":
    success = test_mapping()
    exit(0 if success else 1)

