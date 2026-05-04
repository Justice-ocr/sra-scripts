"""
差分宇宙（三月七小助手）脚本
通过 PowerShell Start-Process -Verb RunAs 以管理员身份启动三月七。
"""

import subprocess
import time
from pathlib import Path

from loguru import logger

from SRACore.task import BaseTask

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

M7_FIELD_MAP = {
    "divergent_type":               "divergent_type",
    "weekly_divergent_level":       "weekly_divergent_level",
    "weekly_divergent_stable_mode": "weekly_divergent_stable_mode",
}

M7_FIXED_FIELDS = {
    "universe_category":   "divergent",
    "pause_after_success": False,   # 完成后自动退出，不等待用户按回车
    "exit_after_failure":  True,    # 失败后也自动退出
}


def _find_m7_exe(m7_path: str) -> Path:
    for name in ("March7th Assistant.exe", "March7th.exe", "March7thAssistant.exe"):
        p = Path(m7_path) / name
        if p.exists():
            return p
    return Path(m7_path) / "March7th Assistant.exe"


def _find_m7_config(m7_path: str):
    for name in ("config/config.yaml", "config.yaml"):
        p = Path(m7_path) / name
        if p.exists():
            return p
    return None


def _load_yaml(path):
    if not HAS_YAML:
        raise ImportError("缺少 PyYAML")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path, data):
    if not HAS_YAML:
        raise ImportError("缺少 PyYAML")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _coerce(value, current):
    if isinstance(current, bool):
        return str(value).lower() in ("true", "1", "yes")
    if isinstance(current, int):
        try:
            return int(value)
        except (ValueError, TypeError):
            return current
    return value


def _get_m7_pid(exe_name: str) -> int | None:
    """通过进程名找到三月七的 PID"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True
        )
        for line in result.stdout.strip().splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2 and parts[0].lower() == exe_name.lower():
                return int(parts[1])
    except Exception:
        pass
    return None


def _is_process_running(pid: int) -> bool:
    """检查进程是否还在运行"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _kill_process(pid: int):
    """强制终止进程"""
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                      capture_output=True)
    except Exception:
        pass


class DivergentUniverseM7Task(BaseTask):
    """差分宇宙（三月七小助手）任务"""

    def run(self) -> bool:
        logger.info("=== 差分宇宙（三月七）脚本启动 ===")

        m7_path   = self.get_param("m7_path",      "D:\\March7thAssistant_full")
        run_times = int(self.get_param("run_times", 1))
        timeout   = int(self.get_param("wait_timeout", 7200))

        m7_exe = _find_m7_exe(m7_path)
        if not m7_exe.exists():
            logger.error(f"未找到三月七可执行文件：{m7_exe}")
            return False

        m7_config = _find_m7_config(m7_path)
        logger.info(f"三月七路径：{m7_exe}")

        # 备份并修改配置
        backup = {}
        if m7_config:
            logger.info(f"配置文件：{m7_config}")
            try:
                cfg = _load_yaml(m7_config)
                for yaml_key in list(M7_FIELD_MAP.values()) + list(M7_FIXED_FIELDS.keys()):
                    backup[yaml_key] = cfg.get(yaml_key)
                for yaml_key, val in M7_FIXED_FIELDS.items():
                    if cfg.get(yaml_key) != val:
                        cfg[yaml_key] = val
                for sra_key, yaml_key in M7_FIELD_MAP.items():
                    raw = self.get_param(sra_key, None)
                    if raw is None:
                        continue
                    val = _coerce(raw, cfg.get(yaml_key, ""))
                    if cfg.get(yaml_key) != val:
                        logger.info(f"  {yaml_key}: {cfg.get(yaml_key)!r} → {val!r}")
                        cfg[yaml_key] = val
                _save_yaml(m7_config, cfg)
                logger.info("已将配置写入三月七 config.yaml")
            except Exception as e:
                logger.warning(f"修改三月七配置失败：{e}")

        # 执行
        actual_times = run_times if run_times > 0 else 999999
        success = True
        exe_name = m7_exe.name

        for i in range(actual_times):
            if self.stop_event and self.stop_event.is_set():
                success = False
                break

            logger.info(f"--- 第 {i + 1} 次差分宇宙 ---")

            # 用 PowerShell Start-Process -Verb RunAs 以管理员身份启动
            # 设置环境变量 MARCH7TH_GUI_STARTED=true，让三月七跳过暂停直接退出
            ps_cmd = (
                f'$env:MARCH7TH_GUI_STARTED="true"; '
                f'Start-Process -FilePath "{m7_exe}" '
                f'-ArgumentList "divergent" '
                f'-WorkingDirectory "{m7_exe.parent}" '
                f'-Verb RunAs'
            )
            logger.info(f"启动三月七（管理员）...")
            try:
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception as e:
                logger.error(f"启动三月七失败：{e}")
                success = False
                break

            # 等待进程出现
            pid = None
            for _ in range(30):
                time.sleep(1)
                pid = _get_m7_pid(exe_name)
                if pid:
                    logger.info(f"三月七进程已启动 (PID={pid})，等待完成（超时 {timeout}s）...")
                    break

            if not pid:
                logger.error("等待三月七启动超时（30s）")
                success = False
                break

            # 等待进程结束
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self.stop_event and self.stop_event.is_set():
                    logger.info("收到停止信号，终止三月七进程")
                    _kill_process(pid)
                    success = False
                    break
                if not _is_process_running(pid):
                    logger.info(f"第 {i + 1} 次完成")
                    break
                time.sleep(3)
            else:
                logger.error(f"等待三月七超时（{timeout}s），强制终止")
                _kill_process(pid)
                success = False
                break

            if not success:
                break

        # 恢复配置
        if m7_config and backup:
            try:
                cfg = _load_yaml(m7_config)
                for yaml_key, orig_val in backup.items():
                    if orig_val is not None:
                        cfg[yaml_key] = orig_val
                    elif yaml_key in cfg:
                        del cfg[yaml_key]
                _save_yaml(m7_config, cfg)
                logger.info("已恢复三月七原始配置")
            except Exception as e:
                logger.warning(f"恢复三月七配置失败：{e}")

        logger.info(f"=== 差分宇宙（三月七）脚本{'完成' if success else '执行失败'} ===")
        return success
