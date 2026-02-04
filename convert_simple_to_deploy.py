#!/usr/bin/env python3
"""
简单转换脚本：将包含joint_pos, root_pos, root_rot的NPZ转换为部署格式

使用方法:
    python convert_simple_to_deploy.py 000003.npz sim2real/assets/data/000003_deploy.npz --from-isaac
"""
import numpy as np
import argparse
from pathlib import Path
from scipy.spatial.transform import Rotation as R

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

# 创建Isaac到MT的映射
def create_isaac_to_mt_mapping():
    """创建从Isaac顺序到MT顺序的索引映射"""
    mapping = []
    for mt_joint in MT_JOINT_ORDER:
        if mt_joint in ISAAC_JOINT_ORDER:
            mapping.append(ISAAC_JOINT_ORDER.index(mt_joint))
        else:
            raise ValueError(f"MT关节 '{mt_joint}' 在Isaac顺序中未找到!")
    return np.array(mapping)

ISAAC_TO_MT_MAP = create_isaac_to_mt_mapping()

def convert_to_deploy_format(input_path, output_path, from_isaac=False, check_joint_order=True):
    """
    转换NPZ文件为部署格式
    
    Args:
        input_path: 输入NPZ文件路径
        output_path: 输出NPZ文件路径
        from_isaac: 是否从Isaac顺序转换（默认False，假设已是MT顺序）
        check_joint_order: 是否检查关节顺序
    """
    print(f"加载文件: {input_path}")
    data = np.load(input_path, allow_pickle=True)
    
    # 检查必需字段
    required_keys = ['joint_pos', 'root_pos', 'root_rot', 'fps']
    for key in required_keys:
        if key not in data:
            raise ValueError(f"缺少必需字段: {key}")
    
    # 提取数据
    joint_pos = data['joint_pos'].astype(np.float32)
    root_pos = data['root_pos'].astype(np.float32)
    root_rot = data['root_rot'].astype(np.float32)
    
    # 处理fps（可能是数组或标量）
    if isinstance(data['fps'], np.ndarray):
        fps = int(data['fps'][0])
    else:
        fps = int(data['fps'])
    
    print(f"  帧数: {joint_pos.shape[0]}")
    print(f"  帧率: {fps} fps")
    print(f"  关节数: {joint_pos.shape[1]}")
    
    # 检查并转换root_rot为xyzw格式
    try:
        R.from_quat(root_rot[0])
        root_rot_xyzw = root_rot
        print("✓ root_rot格式: xyzw")
    except:
        # 尝试wxyz格式
        root_rot_xyzw = np.concatenate([root_rot[:, 1:4], root_rot[:, 0:1]], axis=-1)
        try:
            R.from_quat(root_rot_xyzw[0])
            print("✓ root_rot格式: wxyz，已转换为xyzw")
        except:
            raise ValueError("无法识别root_rot格式，请检查数据")
    
    # 处理关节顺序
    if from_isaac:
        # 从Isaac顺序重排到MT顺序
        print("✓ 从Isaac顺序重排为MT顺序")
        dof_pos = joint_pos[:, ISAAC_TO_MT_MAP]
        print(f"  示例: Isaac索引 {ISAAC_TO_MT_MAP[:5]} → MT索引 [0, 1, 2, 3, 4]")
    else:
        # 假设已是MT顺序
        dof_pos = joint_pos.copy()
        
        # 检查关节顺序（如果有joint_names）
        if check_joint_order and 'joint_names' in data:
            joint_names_in = data['joint_names']
            if hasattr(joint_names_in, 'tolist'):
                joint_names_in = joint_names_in.tolist()
            else:
                joint_names_in = list(joint_names_in)
            
            if joint_names_in != MT_JOINT_ORDER:
                print(f"⚠ 警告: 关节顺序不匹配")
                print(f"   文件中的顺序: {joint_names_in[:5]}...")
                print(f"   MT标准顺序: {MT_JOINT_ORDER[:5]}...")
                print(f"   建议使用 --from-isaac 标志重新转换")
    
    # 保存为部署格式
    save_dict = {
        'fps': np.float32(fps),
        'root_pos': root_pos,
        'root_rot': root_rot_xyzw,
        'dof_pos': dof_pos,
        'joint_names': np.array(MT_JOINT_ORDER, dtype='<U26'),
    }
    
    # 创建输出目录
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    np.savez(output_path, **save_dict)
    
    print(f"\n✓ 转换完成!")
    print(f"  输出: {output_path}")
    print(f"  包含字段: {list(save_dict.keys())}")
    
    return save_dict

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="将NPZ文件转换为部署格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从Isaac顺序转换（推荐）
  python convert_simple_to_deploy.py 000003.npz sim2real/assets/data/000003_deploy.npz --from-isaac
  
  # 假设已是MT顺序
  python convert_simple_to_deploy.py 000003.npz sim2real/assets/data/000003_deploy.npz
        """
    )
    parser.add_argument("input", help="输入NPZ文件路径")
    parser.add_argument("output", help="输出NPZ文件路径")
    parser.add_argument("--from-isaac", action="store_true",
                       help="关节数据是Isaac顺序，需要重排为MT顺序")
    parser.add_argument("--no-check-order", action="store_true", 
                       help="不检查关节顺序（如果确定顺序正确）")
    
    args = parser.parse_args()
    
    convert_to_deploy_format(
        args.input, 
        args.output,
        from_isaac=args.from_isaac,
        check_joint_order=not args.no_check_order
    )
