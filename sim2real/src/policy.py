import json
import socket
import statistics
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import onnxruntime as ort
from scipy.spatial.transform import Rotation as R

from common.joint_mapper import create_isaac_to_real_mapper
from common.math_utils import (
    _linspace_rows,
    _remove_yaw_keep_rp_wxyz,
    _slerp,
    _yaw_component_wxyz,
    _zero_z,
)
from common.utils import DictToClass, MotionUDPServer, joint_names_23, joint_names_29
from paths import ASSETS_DIR, REAL_G1_ROOT

def benchmark_onnx(module, sample_input, runs=100, warmup=10, desc=""):
    for _ in range(warmup):
        _ = module(sample_input)

    ts = []
    for _ in range(runs):
        t0 = time.perf_counter()
        _ = module(sample_input)
        t1 = time.perf_counter()
        ts.append((t1 - t0) * 1000.0)

    mean = statistics.mean(ts)
    stdev = statistics.pstdev(ts)
    p50 = np.percentile(ts, 50)
    p90 = np.percentile(ts, 90)
    p95 = np.percentile(ts, 95)
    p99 = np.percentile(ts, 99)

    print(f"[{desc}] runs={runs}, warmup={warmup}")
    print(f"mean={mean:.3f} ms, stdev={stdev:.3f} ms")
    print(f"p50={p50:.3f} ms, p90={p90:.3f} ms, p95={p95:.3f} ms, p99={p99:.3f} ms")
    return {"mean": mean, "stdev": stdev, "p50": p50, "p90": p90, "p95": p95, "p99": p99}


class ONNXModule:
    def __init__(self, path: str):
        self.ort_session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        meta_path = path.replace(".onnx", ".json")
        with open(meta_path, "r") as f:
            self.meta = json.load(f)
        self.in_keys = [k if isinstance(k, str) else tuple(k) for k in self.meta["in_keys"]]
        self.out_keys = [k if isinstance(k, str) else tuple(k) for k in self.meta["out_keys"]]

    def __call__(self, input: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        args = {
            inp.name: input[key]
            for inp, key in zip(self.ort_session.get_inputs(), self.in_keys)
            if key in input
        }
        outputs = self.ort_session.run(None, args)
        outputs = {k: v for k, v in zip(self.out_keys, outputs)}
        return outputs

# =========================================
# Upright Detector
# =========================================
class UprightDetector:
    """
    Monitors robot IMU and joint angles to detect successful standing up.
    Uses roll/pitch angles AND knee joint angles to determine if robot is truly upright.
    """
    def __init__(self, controller, threshold_deg: float = 15.0, knee_threshold_rad: float = 0.3, consecutive_frames: int = 4):
        """
        Args:
            controller: Robot controller with .quat and .qj_isaac attributes
            threshold_deg: Maximum absolute roll/pitch angle (degrees) to consider upright
            knee_threshold_rad: Maximum absolute knee angle (radians) to consider legs straight (0.3 rad ≈ 17°)
            consecutive_frames: Number of consecutive frames that must satisfy condition
        """
        self.controller = controller
        self.threshold_rad = np.deg2rad(threshold_deg)
        self.knee_threshold_rad = knee_threshold_rad
        self.consecutive_frames = consecutive_frames
        self.upright_count = 0
        self.is_monitoring = False
        
        # Isaac joint order indices for knee joints
        self.left_knee_idx = 9   # "left_knee_joint" in ISAAC_JOINT_ORDER
        self.right_knee_idx = 10  # "right_knee_joint" in ISAAC_JOINT_ORDER
    
    def start_monitoring(self):
        """Start monitoring for upright condition"""
        self.is_monitoring = True
        self.upright_count = 0
        print(f"[UprightDetector] Started monitoring")
        print(f"  - IMU姿态: roll/pitch < ±{np.rad2deg(self.threshold_rad):.1f}°")
        print(f"  - 膝盖角度: < {np.rad2deg(self.knee_threshold_rad):.1f}° (伸直)")
        print(f"  - 连续帧数: {self.consecutive_frames}")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        self.upright_count = 0
        print(f"[UprightDetector] Stopped monitoring")
    
    def check(self) -> bool:
        """
        Check if robot is upright based on IMU quaternion AND knee angles.
        Returns True if upright condition satisfied for consecutive_frames.
        """
        if not self.is_monitoring:
            return False
        
        # 1. Check IMU orientation (roll and pitch)
        quat = self.controller.quat  # [w, x, y, z] - scalar first
        r = R.from_quat(quat, scalar_first=True)
        roll, pitch, yaw = r.as_euler('xyz')
        
        imu_ok = (abs(roll) < self.threshold_rad) and (abs(pitch) < self.threshold_rad)
        
        # 2. Check knee angles (legs should be straight)
        qj = self.controller.qj_isaac  # Joint positions in Isaac order
        left_knee = abs(qj[self.left_knee_idx])
        right_knee = abs(qj[self.right_knee_idx])
        
        knees_ok = (left_knee < self.knee_threshold_rad) and (right_knee < self.knee_threshold_rad)
        
        # Both conditions must be satisfied
        is_upright = imu_ok and knees_ok
        
        # 调试：每30帧打印一次当前状态
        if self.upright_count % 30 == 0:
            print(f"[UprightDetector] 检测中 [{self.upright_count}/{self.consecutive_frames}]:")
            print(f"  IMU: roll={np.rad2deg(roll):.1f}°, pitch={np.rad2deg(pitch):.1f}° {'✓' if imu_ok else '✗'}")
            print(f"  膝盖: 左={np.rad2deg(left_knee):.1f}°, 右={np.rad2deg(right_knee):.1f}° {'✓' if knees_ok else '✗'}")
        
        if is_upright:
            self.upright_count += 1
            if self.upright_count >= self.consecutive_frames:
                print(f"[UprightDetector] SUCCESS - Robot upright!")
                print(f"  - IMU: roll={np.rad2deg(roll):.1f}°, pitch={np.rad2deg(pitch):.1f}°")
                print(f"  - 膝盖: 左={np.rad2deg(left_knee):.1f}°, 右={np.rad2deg(right_knee):.1f}°")
                return True
        else:
            # Reset counter if condition not met
            if self.upright_count > 0:
                # Print debug info when losing upright condition
                reason = []
                if not imu_ok:
                    reason.append(f"IMU姿态(roll={np.rad2deg(roll):.1f}°, pitch={np.rad2deg(pitch):.1f}°)")
                if not knees_ok:
                    reason.append(f"膝盖弯曲(左={np.rad2deg(left_knee):.1f}°, 右={np.rad2deg(right_knee):.1f}°)")
                print(f"[UprightDetector] 检测中断: {', '.join(reason)}")
            self.upright_count = 0
        
        return False

# =========================================
# Policy Base
# =========================================
class Policy:
    FADE_OUT_DURATION = 2.0  # s

    def __init__(self, name: str, policy_cfg: DictToClass, controller):
        self.name = name
        self.controller = controller

        self.config = policy_cfg

        # Resolve policy path relative to repo root for robustness
        p = Path(policy_cfg.policy_path)
        self.policy_path = str(p if p.is_absolute() else (REAL_G1_ROOT / p))
        self.action_joint_names = list(policy_cfg.action_joint_names)
        self.action_scale_isaac = np.array(policy_cfg.action_scale, dtype=np.float32)
        self.alpha = float(policy_cfg.action_alpha)
        self.lowstate_alpha = float(policy_cfg.lowstate_alpha)
        self.action_clip = float(policy_cfg.action_clip)

        if hasattr(policy_cfg, "kps_real"):
            self.kps_real = np.array(policy_cfg.kps_real, dtype=np.float32)
        if hasattr(policy_cfg, "kds_real"):
            self.kds_real = np.array(policy_cfg.kds_real, dtype=np.float32)

        assert len(self.action_joint_names) == len(self.action_scale_isaac), (
            f"[{self.name}] action_joint_names ({len(self.action_joint_names)}) "
            f"!= action_scale ({len(self.action_scale_isaac)})"
        )

        self.module = ONNXModule(self.policy_path)

        self.mapper_action = create_isaac_to_real_mapper(
            self.action_joint_names,
            self.controller.config.real_joint_names
        )
        map_info = self.mapper_action.get_mapping_info()
        print(f"[Policy:{self.name}] Action mapping: {map_info['mapped_joints']}/{map_info['from_space_size']} mapped")
        if map_info['unmapped_from_joints']:
            print(f"[Policy:{self.name}] Unmapped policy action joints: {map_info['unmapped_from_joints']}")
        if map_info['unmapped_to_joints']:
            print(f"[Policy:{self.name}] Unmapped Real joints: {map_info['unmapped_to_joints']}")

        self.policy_input: Optional[Dict[str, np.ndarray]] = None
        self.applied_action_isaac = np.zeros(len(self.action_joint_names), dtype=np.float32)
        self.last_action = np.zeros(len(self.action_joint_names), dtype=np.float32)

        self._fading_deadline: Optional[float] = None
        self._active: bool = False

        self.obs_modules = []
        self.num_obs = 0
        self._build_obs_modules()

        self.policy_input = {
            "policy": np.zeros((1, self.num_obs), dtype=np.float32),
            "is_init": np.ones((1,), dtype=bool)
        }
        benchmark_onnx(self.module, self.policy_input, runs=100, warmup=200, desc="model@cuda")

    # -------- lifecycle ----------
    def fade_in(self):
        self.reset()
        self._active = True
        self._fading_deadline = None
        print(f"[Policy:{self.name}] fade_in()")

    def fade_out(self) -> float:
        self._fading_deadline = time.monotonic() + self.FADE_OUT_DURATION
        print(f"[Policy:{self.name}] fade_out() - continue until {self._fading_deadline:.3f}")
        return self._fading_deadline

    def is_fading(self) -> bool:
        return self._fading_deadline is not None

    def fading_done(self) -> bool:
        return self._fading_deadline is not None and time.monotonic() >= self._fading_deadline

    def deactivate(self):
        self._active = False
        self._fading_deadline = None
        print(f"[Policy:{self.name}] deactivated")

    # -------- abstract hooks ----------
    def _build_obs_modules(self):
        raise NotImplementedError

    def _reset_obs_modules(self):
        for m in self.obs_modules:
            if hasattr(m, "reset") and callable(m.reset):
                m.reset()

    def update_obs(self):
        obs_list = []
        for m in self.obs_modules:
            m.update()
            obs_list.append(m.compute())
        if self.policy_input is None:
            self.policy_input = {
                "policy": np.zeros((1, self.num_obs), dtype=np.float32),
                "is_init": np.ones((1,), dtype=bool),
            }
        else:
            self.policy_input["policy"][0, :] = np.concatenate(obs_list, axis=0)

    def compute_action(self) -> np.ndarray:
        try:
            out = self.module(self.policy_input)
        except Exception as e:
            print(f"[Policy:{self.name}] ONNX forward failed: {e}")
            return np.zeros(self.controller.dof_size_real, dtype=np.float32)

        if ("next", "adapt_hx") in out:
            self.policy_input["adapt_hx"][:] = out["next", "adapt_hx"]
        self.policy_input["is_init"][:] = False

        action_isaac = out["action"].copy()[0].astype(np.float32).clip( -self.action_clip, self.action_clip)
        self.last_action[:] = action_isaac
        self.applied_action_isaac[:] = action_isaac * self.action_scale_isaac

        action_real = self.mapper_action.map_action_from_to(self.applied_action_isaac)
        return action_real

    def reset(self):
        self.policy_input = None
        self.applied_action_isaac[:] = 0.0
        self.last_action[:] = 0.0
        self._reset_obs_modules()

# =========================================
# Policy Subclasses
# =========================================
def mapping_joints(data: np.ndarray, target: List[str]):
    nums = data.shape[-1]
    if nums == len(target):
        return data
    if nums == 29:
        current = joint_names_29
        print("[Mapping] from 29 to 23")
    elif nums == 23:
        current = joint_names_23
        print("[Mapping] from 23 to 29")
    else:
        raise ValueError(f"Unsupported number of joints: {nums}")

    new_data = np.zeros((data.shape[0], len(target)), dtype=np.float32)
    for i, name in enumerate(target):
        if name in current:
            new_data[:, i] = data[:, current.index(name)]
    return new_data.astype(np.float32)

class TrackingPolicyRaw(Policy):
    def __init__(self, name: str, policy_cfg: DictToClass, controller):
        # ---- Config ---------------------------------------------------------
        self.body_name = "torso_link"
        self.transition_steps = int(getattr(policy_cfg, "transition_steps", 100))
        self.udp_enable = bool(getattr(policy_cfg, "udp_enable", True))
        self.udp_host = str(getattr(policy_cfg, "udp_host", "127.0.0.1"))
        self.udp_port = int(getattr(policy_cfg, "udp_port", 28562))

        # ---- Load motions; keep all root data (no yaw split) ----------------
        self.motions: Dict[str, Dict[str, np.ndarray]] = {}
        for m in policy_cfg.motions:
            mc = DictToClass(m)
            motion_name = mc.name
            mp = Path(mc.path)
            path = str(mp if mp.is_absolute() else (REAL_G1_ROOT / mp))
            t0, t1 = int(mc.start), int(mc.end)

            data = np.load(path, allow_pickle=True)
            if not isinstance(data, np.lib.npyio.NpzFile):
                raise ValueError(f"[TrackingPolicyRaw] Only .npz is supported: {path}")

            # Support both 'dof_pos' (deployed format) and 'joint_pos' (simple format)
            if "dof_pos" in data:
                joint_pos = data["dof_pos"][t0:t1].astype(np.float32)
            elif "joint_pos" in data:
                joint_pos = data["joint_pos"][t0:t1].astype(np.float32)
            else:
                raise KeyError(f"[TrackingPolicyRaw] Motion file must contain either 'dof_pos' or 'joint_pos': {path}")
            root_pos = data["root_pos"][t0:t1].astype(np.float32)
            root_rot_xyzw = data["root_rot"][t0:t1].astype(np.float32)
            root_quat = np.concatenate([root_rot_xyzw[:, 3:4], root_rot_xyzw[:, :3]], axis=-1)

            joint_names = data.get("joint_names", None)
            if joint_names is not None:
                joint_names = joint_names.tolist()
                target_names = list(policy_cfg.dataset_joint_names)
                if joint_names != target_names:
                    name_to_idx = {n: i for i, n in enumerate(joint_names)}
                    remap = np.zeros((joint_pos.shape[0], len(target_names)), dtype=np.float32)
                    for i, n in enumerate(target_names):
                        j = name_to_idx.get(n, None)
                        if j is not None:
                            remap[:, i] = joint_pos[:, j]
                    joint_pos = remap

            self.motions[motion_name] = {
                "joint_pos": joint_pos,  # (T,J)
                "root_quat": root_quat,  # (T,4) wxyz
                "root_pos": root_pos,    # (T,3)
            }

        # ---- One-frame motion clips (config provided) ----------------------
        for m in policy_cfg.motion_clips:
            mc = DictToClass(m)
            motion_name = mc.name
            joint_pos_1 = mapping_joints(
                np.asarray(mc.joint_pos, dtype=np.float32).reshape(1, -1),
                policy_cfg.dataset_joint_names
            )
            root_quat_1 = np.asarray(mc.root_quat, dtype=np.float32).reshape(1, 4)
            root_pos_1 = np.asarray(mc.root_pos, dtype=np.float32).reshape(1, 3)

            self.motions[motion_name] = {
                "joint_pos": joint_pos_1,  # (1,J)
                "root_quat": root_quat_1,  # (1,4)
                "root_pos": root_pos_1,    # (1,3)
            }

        assert "default" in self.motions, "[TrackingPolicyRaw] motions must include a 'default' clip (length==1)."

        # ---- Reference stream ----------------------------------------------
        self.ref_joint_pos: Optional[np.ndarray] = None  # (T_ref, J)
        self.ref_root_quat: Optional[np.ndarray] = None  # (T_ref, 4)
        self.ref_root_pos: Optional[np.ndarray] = None   # (T_ref, 3)

        # ---- Playback state ------------------------------------------------
        self.ref_idx: int = 0
        self.ref_len: int = 0
        self.current_name: str = "default"
        self.current_done: bool = True  # boot: default done

        # ---- Misc ----------------------------------------------------------
        self.n_joints = len(policy_cfg.dataset_joint_names)

        # Optional UDP selector
        self._udp_server: Optional[MotionUDPServer] = None
        if self.udp_enable:
            try:
                self._udp_server = MotionUDPServer(self.udp_host, self.udp_port)
                self._udp_server.start()
            except Exception as e:
                print(f"[TrackingPolicyRaw] Failed to start UDP server: {e}")

        # Upright detector for "up" command (IMU姿态 + 膝盖角度)
        self._upright_detector = UprightDetector(
            controller, 
            threshold_deg=15.0,      # IMU roll/pitch threshold
            knee_threshold_rad=0.6,  # Knee angle threshold (≈34°) - 站立时膝盖可能稍微弯曲
            consecutive_frames=4
        )

        super().__init__(name, policy_cfg, controller)
        self.init_count = 0

    def fade_in(self):
        super().fade_in()
        self._start_motion_from_current("default")

    def fade_out(self) -> float:
        self._start_motion_from_current("default")
        return super().fade_out()

    def deactivate(self):
        if self._udp_server is not None:
            self._udp_server.stop()
        self.ref_root_pos = None
        self.ref_root_quat = None
        self.ref_joint_pos = None
        super().deactivate()

    def _build_obs_modules(self):
        from observation import (
            TrackingCommandObsRaw,
            TargetRootZObs,
            TargetJointPosObs,
            TargetProjectedGravityBObs,
            RootAngVelB,
            ProjectedGravityB,
            JointPos,
            PrevActions,
            BootIndicator,
        )
        self.obs_modules = [
            BootIndicator(),
            TrackingCommandObsRaw(self.controller, self),
            TargetRootZObs(self),
            TargetJointPosObs(self),
            TargetProjectedGravityBObs(self),
            RootAngVelB(self.controller),
            ProjectedGravityB(self.controller),
            JointPos(self.controller, pos_steps=[0, 1, 2, 3, 4, 8]),
            PrevActions(self, steps=3),
        ]
        self.num_obs = sum(m.size for m in self.obs_modules)

    def load_motion_from_file(self, name: str, filepath: str) -> bool:
        """
        动态加载新的运动文件到 self.motions 字典
        支持部署格式（dof_pos）和简单格式（joint_pos）
        """
        try:
            # 检查文件是否存在
            if not Path(filepath).exists():
                print(f"[TrackingPolicyRaw] 文件不存在: {filepath}")
                return False
            
            # 加载NPZ文件
            data = np.load(filepath, allow_pickle=True)
            if not isinstance(data, np.lib.npyio.NpzFile):
                print(f"[TrackingPolicyRaw] 不是有效的NPZ文件: {filepath}")
                return False
            
            # 支持两种格式
            if "dof_pos" in data:
                joint_pos = data["dof_pos"].astype(np.float32)
            elif "joint_pos" in data:
                joint_pos = data["joint_pos"].astype(np.float32)
            else:
                print(f"[TrackingPolicyRaw] NPZ文件必须包含 'dof_pos' 或 'joint_pos' 字段")
                return False
            
            root_pos = data["root_pos"].astype(np.float32)
            root_rot_xyzw = data["root_rot"].astype(np.float32)
            
            # 转换格式：root_rot xyzw → wxyz
            root_quat = np.concatenate([root_rot_xyzw[:, 3:4], root_rot_xyzw[:, :3]], axis=-1)
            
            # 处理joint_names映射（如果存在）
            joint_names = data.get("joint_names", None)
            if joint_names is not None:
                joint_names = joint_names.tolist()
                target_names = list(self.config.dataset_joint_names)
                if joint_names != target_names:
                    name_to_idx = {n: i for i, n in enumerate(joint_names)}
                    remap = np.zeros((joint_pos.shape[0], len(target_names)), dtype=np.float32)
                    for i, n in enumerate(target_names):
                        j = name_to_idx.get(n, None)
                        if j is not None:
                            remap[:, i] = joint_pos[:, j]
                    joint_pos = remap
            
            # 添加到motions字典
            self.motions[name] = {
                "joint_pos": joint_pos,   # (T,J)
                "root_quat": root_quat,   # (T,4) wxyz
                "root_pos": root_pos,     # (T,3)
            }
            
            print(f"[TrackingPolicyRaw] 成功加载动作 '{name}': {joint_pos.shape[0]} 帧")
            return True
            
        except Exception as e:
            print(f"[TrackingPolicyRaw] 加载动作失败 '{name}': {e}")
            import traceback
            traceback.print_exc()
            return False

    def request_motion(self, name: str) -> bool:
        """
        请求切换到新动作（允许中断当前动作）
        """
        if name not in self.motions:
            print(f"[TrackingPolicyRaw] Unknown motion '{name}'")
            return False
        
        # 修改逻辑：允许在任何时候切换到新动作或default
        if name == "default":
            # default可以随时切换
            self._start_motion_from_current(name)
            return True
        elif self.current_name == "default" and self.current_done:
            # 从default开始新动作
            self._start_motion_from_current(name)
            return True
        else:
            # 新增：动作执行中也允许切换（中断当前动作）
            print(f"[TrackingPolicyRaw] Interrupting '{self.current_name}' to start '{name}'")
            self._start_motion_from_current(name)
            return True

    def update_obs(self):
        if self._udp_server is not None:
            for cmd in self._udp_server.pop_all():
                # 新增：处理 LOAD: 命令
                if cmd.startswith("LOAD:"):
                    motion_name = cmd[5:].strip()
                    filepath = REAL_G1_ROOT / "assets/data/generated" / f"{motion_name}.npz"
                    if self.load_motion_from_file(motion_name, str(filepath)):
                        # 新动作到来时，允许中断当前动作
                        self.request_motion(motion_name)
                elif cmd == "START_UPRIGHT_MONITORING":
                    # 开始监测站起状态
                    self._upright_detector.start_monitoring()
                elif cmd == "default":
                    self.request_motion("default")
                else:
                    self.request_motion(cmd)
        
        # 检查站起状态（如果正在监测）
        if self._upright_detector.is_monitoring:
            if self._upright_detector.check():
                # 站起成功！发送通知并停止监测
                self._send_upright_success_notification()
                self._upright_detector.stop_monitoring()
        
        # 原有逻辑：更新ref_idx
        if self.ref_len > 0 and self.ref_idx < self.ref_len - 1:
            self.ref_idx += 1
            if self.ref_idx == self.ref_len - 1:
                self.current_done = True
                # 新增：发送动作完成通知（仅非default动作）
                if self.current_name != "default":
                    self._send_motion_complete_notification()
                    # 如果在监测站起但动作已完成仍未站起，停止监测
                    if self._upright_detector.is_monitoring:
                        print("[UprightDetector] Motion completed but robot not upright - stopping monitoring")
                        self._upright_detector.stop_monitoring()
        
        super().update_obs()

    def _send_motion_complete_notification(self):
        """
        通过UDP发送动作完成通知到text_to_motion.py
        注意：只在非default动作完成时调用，避免无限循环
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(b"MOTION_COMPLETE", ("127.0.0.1", 28563))
            sock.close()
        except Exception:
            pass  # 静默失败，不影响主流程
    
    def _send_upright_success_notification(self):
        """
        通过UDP发送站起成功通知到text_to_motion.py
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(b"UPRIGHT_SUCCESS", ("127.0.0.1", 28563))
            sock.close()
            print("[TrackingPolicyRaw] Sent UPRIGHT_SUCCESS notification")
        except Exception as e:
            print(f"[TrackingPolicyRaw] Failed to send UPRIGHT_SUCCESS: {e}")

    def _read_current_state(self) -> Dict[str, np.ndarray]:
        q_real = self.controller.qj_real.copy()
        real_names = list(self.controller.config.real_joint_names)
        target_names = list(self.config.dataset_joint_names)
        name_to_idx = {n: i for i, n in enumerate(real_names)}
        q_policy = np.zeros(len(target_names), dtype=np.float32)
        for i, n in enumerate(target_names):
            j = name_to_idx.get(n, None)
            if j is not None and j < q_real.shape[0]:
                q_policy[i] = q_real[j]

        if self.ref_root_pos is not None:
            root_pos = self.ref_root_pos[self.ref_idx]
            root_quat = self.ref_root_quat[self.ref_idx]
        else:
            root_pos = np.array([0.0, 0.0, 0.78], dtype=np.float32)
            root_quat = self.controller.quat.copy()
        return {
            "joint_pos": q_policy.astype(np.float32),
            "root_pos": root_pos,
            "root_quat": root_quat,
        }

    def _align_motion_to_current(
        self,
        motion: Dict[str, np.ndarray],
        curr: Dict[str, np.ndarray],
    ) -> Dict[str, np.ndarray]:
        p0 = motion["root_pos"][0]
        q0_yaw = _yaw_component_wxyz(motion["root_quat"][0])
        pc = curr["root_pos"]
        qc_yaw = _yaw_component_wxyz(curr["root_quat"])

        R0 = R.from_quat(q0_yaw, scalar_first=True)
        Rc = R.from_quat(qc_yaw, scalar_first=True)
        R_delta = Rc * R0.inv()

        root_pos_aligned = R_delta.apply(motion["root_pos"] - p0) + pc
        root_pos_aligned[:, 2] = motion["root_pos"][:, 2]  # keep original z

        root_quat_all = R.from_quat(motion["root_quat"], scalar_first=True)
        root_quat_aligned = (R_delta * root_quat_all).as_quat(scalar_first=True)

        return {
            "joint_pos": motion["joint_pos"].astype(np.float32).copy(),
            "root_quat": root_quat_aligned.astype(np.float32),
            "root_pos": root_pos_aligned.astype(np.float32),
        }

    def _build_transition_prefix(
        self,
        curr: Dict[str, np.ndarray],
        tgt_first: Dict[str, np.ndarray],
    ) -> Dict[str, np.ndarray]:
        T = int(self.transition_steps)
        if T <= 0:
            raise ValueError("[TrackingPolicyRaw] transition_steps must be > 0")

        joints_tr = _linspace_rows(curr["joint_pos"], tgt_first["joint_pos"], T)
        root_pos_tr = _linspace_rows(curr["root_pos"], tgt_first["root_pos"], T)
        root_quat_tr = _slerp(curr["root_quat"], tgt_first["root_quat"], T)

        return {
            "joint_pos": joints_tr,
            "root_quat": root_quat_tr,
            "root_pos": root_pos_tr,
        }

    def _start_motion_from_current(self, name: str):
        assert name in self.motions
        curr = self._read_current_state()

        m = self.motions[name]
        aligned_motion = self._align_motion_to_current(m, curr)

        tgt_first = {
            "joint_pos": aligned_motion["joint_pos"][0],
            "root_quat": aligned_motion["root_quat"][0],
            "root_pos": aligned_motion["root_pos"][0],
        }

        trans_motion = self._build_transition_prefix(curr, tgt_first)

        self.ref_joint_pos = np.concatenate([trans_motion["joint_pos"], aligned_motion["joint_pos"]], axis=0)
        self.ref_root_quat = np.concatenate([trans_motion["root_quat"], aligned_motion["root_quat"]], axis=0)
        self.ref_root_pos = np.concatenate([trans_motion["root_pos"], aligned_motion["root_pos"]], axis=0)

        self.ref_idx = 0
        self.ref_len = int(self.ref_joint_pos.shape[0])
        self.current_name = name
        self.current_done = (self.ref_len <= 1)

        print(f"[TrackingPolicyRaw] Start motion '{name}' | ref_len={self.ref_len}, transition={self.transition_steps}")
