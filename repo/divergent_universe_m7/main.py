"""
差分宇宙（三月七小助手）脚本
调用 March7thAssistant 执行差分宇宙，支持通过 SRA 脚本配置页修改三月七的相关设置。

配置文件：{m7_path}/config/config.yaml
关键字段：
  - divergent_type: normal/cycle（演算模式，--task universe 时使用）
  - weekly_divergent_level: 1-6（难度等级）
  - divergent_team_type: 追击/dot/终结技/击破/盾反（队伍类型）
  - weekly_divergent_stable_mode: true/false（低性能兼容模式）
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

# SRA 配置项 -> 三月七 config.yaml 字段映射
M7_FIELD_MAP = {
    "divergent_type":              "divergent_type",
    "weekly_divergent_level":      "weekly_divergent_level",
    "weekly_divergent_stable_mode": "weekly_divergent_stable_mode",
}

# 固定写入（确保 --task universe 走差分宇宙分支）
M7_FIXED_FIELDS = {
    "universe_category": "divergent",
}


def _find_m7_exe(m7_path: str) -> Path:
    for name in ("March7th.exe", "March7thAssistant.exe", "March7thAssist.exe"):
        p = Path(m7_path) / name
        if p.exists():
            return p
    return Path(m7_path) / "March7th.exe"


def _find_m7_config(m7_path: str) -> Path | None:
    for name in ("config/config.yaml", "config.yaml"):
        p = Path(m7_path) / name
        if p.exists():
            return p
    return None


def _load_yaml(path: Path) -> dict:
    if not HAS_YAML:
        raise ImportError("缺少 PyYAML，请安装：pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict):
    if not HAS_YAML:
        raise ImportError("缺少 PyYAML，请安装：pip install pyyaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _coerce(value: str, current):
    """根据现有值的类型转换字符串"""
    if isinstance(current, bool):
        return str(value).lower() in ("true", "1", "yes")
    if isinstance(current, int):
        try:
            return int(value)
        except (ValueError, TypeError):
            return current
    return value


class DivergentUniverseM7Task(BaseTask):
    """差分宇宙（三月七小助手）任务"""

    def run(self) -> bool:
        logger.info("=== 差分宇宙（三月七）脚本启动 ===")

        m7_path   = self.get_param("m7_path", "D:\\March7thAssistant_full")
        run_times = int(self.get_param("run_times", 1))
        timeout   = int(self.get_param("wait_timeout", 7200))

        m7_exe = _find_m7_exe(m7_path)
        if not m7_exe.exists():
            logger.error(f"未找到三月七可执行文件：{m7_exe}")
            logger.error("请在脚本配置中确认「三月七安装目录」是否正确")
            return False

        m7_config = _find_m7_config(m7_path)
        logger.info(f"三月七路径：{m7_exe}")
        if m7_config:
            logger.info(f"配置文件：{m7_config}")
        else:
            logger.warning(f"未找到三月七配置文件，将使用原有配置运行")

        # 备份并修改配置
        backup = {}
        if m7_config:
            try:
                cfg = _load_yaml(m7_config)
                for yaml_key in list(M7_FIELD_MAP.values()) + list(M7_FIXED_FIELDS.keys()):
                    backup[yaml_key] = cfg.get(yaml_key)

                # 写入固定字段
                for yaml_key, val in M7_FIXED_FIELDS.items():
                    if cfg.get(yaml_key) != val:
                        logger.info(f"  {yaml_key}: {cfg.get(yaml_key)!r} → {val!r}")
                        cfg[yaml_key] = val

                # 写入用户配置
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
                logger.warning(f"修改三月七配置失败（将使用原有配置）：{e}")

        # 执行
        actual_times = run_times if run_times > 0 else 999999
        success = True

        for i in range(actual_times):
            if self.stop_event and self.stop_event.is_set():
                logger.info("收到停止信号，中断执行")
                success = False
                break

            logger.info(f"--- 第 {i + 1} 次差分宇宙 ---")
            ok = self._run_m7_once(m7_exe, timeout)
            if not ok:
                logger.error(f"第 {i + 1} 次执行失败")
                success = False
                break
            logger.info(f"第 {i + 1} 次完成")

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

    def _run_m7_once(self, m7_exe: Path, timeout: int) -> bool:
        cmd = [str(m7_exe), "divergent"]
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
                    try:
                        _, stderr = proc.communicate(timeout=2)
                        if stderr:
                            logger.error(f"错误输出：{stderr.decode('utf-8', errors='replace')}")
                    except Exception:
                        pass
                    return False
            time.sleep(2)

        logger.error(f"等待三月七超时（{timeout}s），强制终止")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return False
