"""
差分宇宙（三月七小助手）脚本
调用 March7thAssistant 执行差分宇宙，支持通过 SRA 脚本配置页修改三月七的相关设置。

三月七小助手配置文件路径：{m7_path}\\config\\config.json
三月七可执行文件路径：{m7_path}\\March7th.exe
"""

import json
import os
import subprocess
import time
from pathlib import Path

from loguru import logger

from SRACore.task import BaseTask

# 三月七 config.json 中差分宇宙相关字段
# 参考 March7thAssistant 源码 module/config/config.py
M7_DU_CONFIG_KEYS = {
    "universe_level":     ("Universe", "level"),
    "run_times":          ("Universe", "run_times"),
    "team_number":        ("Universe", "team_number"),
    "use_support":        ("Universe", "enable_support"),
    "support_character":  ("Universe", "support_character"),
    "use_technique":      ("Universe", "use_technique"),
    "technique_fight":    ("Universe", "technique_fight"),
    "buff_index":         ("Universe", "buff_index"),
    "max_lost_buffs":     ("Universe", "max_lost_buffs"),
}


def _get_m7_config_path(m7_path: str) -> Path:
    """获取三月七 config.json 路径"""
    return Path(m7_path) / "config" / "config.json"


def _get_m7_exe_path(m7_path: str) -> Path:
    """获取三月七可执行文件路径"""
    # 支持两种常见的可执行文件名
    for exe_name in ("March7th.exe", "March7thAssistant.exe", "March7thAssist.exe"):
        p = Path(m7_path) / exe_name
        if p.exists():
            return p
    return Path(m7_path) / "March7th.exe"


def _load_m7_config(config_path: Path) -> dict:
    """读取三月七配置文件"""
    if not config_path.exists():
        raise FileNotFoundError(f"未找到三月七配置文件：{config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_m7_config(config_path: Path, config: dict):
    """保存三月七配置文件"""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _set_nested(d: dict, keys: tuple, value):
    """设置嵌套字典的值，key 可以是 (section, field) 形式"""
    section, field = keys
    if section not in d:
        d[section] = {}
    d[section][field] = value


def _get_nested(d: dict, keys: tuple, default=None):
    """获取嵌套字典的值"""
    section, field = keys
    return d.get(section, {}).get(field, default)


def _coerce(value: str, target):
    """按目标值类型转换字符串"""
    if isinstance(target, bool):
        return str(value).lower() in ("true", "1", "yes")
    if isinstance(target, int):
        try:
            return int(value)
        except (ValueError, TypeError):
            return target
    return value


class DivergentUniverseM7Task(BaseTask):
    """
    差分宇宙（三月七小助手）任务
    
    运行流程：
    1. 读取 SRA 脚本配置
    2. 读取三月七的 config.json，备份差分宇宙相关字段
    3. 将 SRA 配置写入三月七 config.json
    4. 以命令行参数启动三月七执行差分宇宙
    5. 等待三月七完成
    6. 恢复三月七原始配置
    """

    def run(self) -> bool:
        logger.info("=== 差分宇宙（三月七）脚本启动 ===")

        # 读取配置
        m7_path   = self.get_param("m7_path", "C:\\Program Files\\March7thAssistant")
        run_times = int(self.get_param("run_times", 1))
        timeout   = int(self.get_param("wait_timeout", 600))

        m7_exe        = _get_m7_exe_path(m7_path)
        m7_config_path = _get_m7_config_path(m7_path)

        # 验证三月七路径
        if not m7_exe.exists():
            logger.error(f"未找到三月七可执行文件：{m7_exe}")
            logger.error("请在脚本配置中确认「三月七安装目录」是否正确")
            return False

        if not m7_config_path.exists():
            logger.error(f"未找到三月七配置文件：{m7_config_path}")
            return False

        logger.info(f"三月七路径：{m7_exe}")
        logger.info(f"配置文件：{m7_config_path}")

        # 读取并备份三月七配置
        try:
            m7_config = _load_m7_config(m7_config_path)
        except Exception as e:
            logger.error(f"读取三月七配置失败：{e}")
            return False

        backup = {}
        for param_key, config_keys in M7_DU_CONFIG_KEYS.items():
            backup[param_key] = _get_nested(m7_config, config_keys)

        logger.info(f"已备份三月七差分宇宙配置：{backup}")

        # 将 SRA 脚本配置写入三月七 config.json
        try:
            modified = self._apply_config_to_m7(m7_config)
            if modified:
                _save_m7_config(m7_config_path, m7_config)
                logger.info("已将 SRA 配置写入三月七 config.json")
        except Exception as e:
            logger.error(f"写入三月七配置失败：{e}")
            return False

        # 执行（支持多次运行）
        success = True
        actual_times = run_times if run_times > 0 else 999999  # -1 = 无限循环

        for i in range(actual_times):
            if self.stop_event and self.stop_event.is_set():
                logger.info("收到停止信号，中断执行")
                success = False
                break

            run_no = i + 1
            logger.info(f"--- 第 {run_no} 次差分宇宙 ---")

            ok = self._run_m7_once(m7_exe, m7_config_path, timeout)
            if not ok:
                logger.error(f"第 {run_no} 次执行失败")
                success = False
                break

            logger.info(f"第 {run_no} 次完成")

            # 无限循环时每次重新检查停止信号
            if run_times == -1 and self.stop_event and self.stop_event.is_set():
                break

        # 恢复三月七原始配置
        try:
            m7_config_restore = _load_m7_config(m7_config_path)
            for param_key, config_keys in M7_DU_CONFIG_KEYS.items():
                if backup[param_key] is not None:
                    _set_nested(m7_config_restore, config_keys, backup[param_key])
            _save_m7_config(m7_config_path, m7_config_restore)
            logger.info("已恢复三月七原始配置")
        except Exception as e:
            logger.warning(f"恢复三月七配置失败（不影响结果）：{e}")

        if success:
            logger.info("=== 差分宇宙（三月七）脚本完成 ===")
        else:
            logger.error("=== 差分宇宙（三月七）脚本执行失败 ===")
        return success

    def _apply_config_to_m7(self, m7_config: dict) -> bool:
        """将 SRA 脚本参数写入三月七配置，返回是否有修改"""
        modified = False
        type_hints = {
            "universe_level":    1,
            "run_times":         1,
            "team_number":       1,
            "use_support":       False,
            "support_character": "",
            "use_technique":     False,
            "technique_fight":   False,
            "buff_index":        1,
            "max_lost_buffs":    0,
        }
        # 单次运行时写 run_times=1（由 SRA 脚本控制循环，三月七每次只跑一轮）
        single_run_keys = {"run_times"}

        for param_key, config_keys in M7_DU_CONFIG_KEYS.items():
            raw_val = self.get_param(param_key, None)
            if raw_val is None:
                continue
            hint = type_hints.get(param_key)
            if hint is not None:
                val = _coerce(raw_val, hint)
            else:
                val = raw_val

            # run_times 由 SRA 控制，三月七每次只跑1轮
            if param_key in single_run_keys:
                val = 1

            current = _get_nested(m7_config, config_keys)
            if current != val:
                _set_nested(m7_config, config_keys, val)
                logger.info(f"  {config_keys[0]}.{config_keys[1]}: {current!r} → {val!r}")
                modified = True

        # 固定设置：任务类型设为差分宇宙（Universe mode = divergent_universe）
        # 三月七的任务模式字段（具体字段名根据版本可能不同）
        for mode_key in (("Scheduler", "universe_task"), ("Universe", "universe_type")):
            current_mode = _get_nested(m7_config, mode_key)
            if current_mode is not None and current_mode != "divergent_universe":
                _set_nested(m7_config, mode_key, "divergent_universe")
                logger.info(f"  {mode_key[0]}.{mode_key[1]}: {current_mode!r} → 'divergent_universe'")
                modified = True

        return modified

    def _run_m7_once(self, m7_exe: Path, m7_config_path: Path, timeout: int) -> bool:
        """
        启动三月七执行一次差分宇宙，等待完成。

        三月七支持以下命令行参数（参考官方文档）：
          --auto-run          自动开始运行
          --task universe     指定执行差分宇宙任务
          --exit-after-done   完成后自动退出
        """
        cmd = [
            str(m7_exe),
            "--auto-run",
            "--task", "universe",
            "--exit-after-done",
        ]

        logger.info(f"启动三月七：{' '.join(cmd)}")

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(m7_exe.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            logger.error(f"启动三月七失败：{e}")
            return False

        logger.info(f"三月七进程已启动 (PID={proc.pid})，等待完成（超时 {timeout}s）...")

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.stop_event and self.stop_event.is_set():
                logger.info("收到停止信号，终止三月七进程")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False

            ret = proc.poll()
            if ret is not None:
                if ret == 0:
                    logger.info(f"三月七正常退出（返回码 {ret}）")
                    return True
                else:
                    logger.error(f"三月七异常退出（返回码 {ret}）")
                    # 读取错误输出
                    try:
                        _, stderr = proc.communicate(timeout=2)
                        if stderr:
                            logger.error(f"三月七错误输出：{stderr.decode('utf-8', errors='replace')}")
                    except Exception:
                        pass
                    return False
            time.sleep(2)

        # 超时
        logger.error(f"等待三月七超时（{timeout}s），强制终止进程")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return False
