"""
货币战争（三月七小助手）脚本。

通过 March7thAssistant CLI 调用货币战争功能。脚本只临时写入三月七
config.yaml 中货币战争相关配置，并在结束后恢复，避免影响三月七自身功能。
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from loguru import logger

from SRACore.task import BaseTask


EXE_CANDIDATES = (
    "March7th Assistant.exe",
    "March7th.exe",
    "March7thAssistant.exe",
)

M7_FIELD_MAP = {
    "currencywars_type": "currencywars_type",
    "currencywars_rank_difficulty": "currencywars_rank_difficulty",
    "currencywars_strategy": "currencywars_strategy",
    "currencywars_remembrance_trailblazer_name": "currencywars_remembrance_trailblazer_name",
    "currencywars_fast_mode": "currencywars_fast_mode",
    "currencywars_strategy_restart_on_special_tags": "currencywars_strategy_restart_on_special_tags",
    "currencywars_bonus_enable": "currencywars_bonus_enable",
}

M7_FIXED_FIELDS = {
    "currencywars_enable": True,
    "pause_after_success": False,
    "exit_after_failure": True,
    "auto_update": True,
    "after_finish": "None",
}

VALID_VALUES = {
    "currencywars_type": ("normal", "overclock"),
    "currencywars_rank_difficulty": ("current", "lowest", "highest"),
    "currencywars_strategy": ("default", "aglaea", "seele"),
}

RUN_MODE_TO_ACTION = {
    "normal": "currencywars",
    "temp": "currencywarstemp",
    "loop": "currencywarsloop",
}


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    image: str
    path: str


def _bool_param(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes", "y", "on")


def _int_param(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_config_value(raw: Any, current: Any) -> Any:
    if isinstance(current, bool):
        return _bool_param(raw, current)
    if isinstance(current, int):
        return _int_param(raw, current)
    return "" if raw is None else str(raw)


def _find_m7_exe(m7_path: str) -> Path:
    base = Path(m7_path).expanduser()
    if base.is_file():
        return base
    for name in EXE_CANDIDATES:
        candidate = base / name
        if candidate.exists():
            return candidate
    return base / EXE_CANDIDATES[0]


def _find_m7_config(m7_dir: Path) -> Path | None:
    for name in ("config/config.yaml", "config.yaml"):
        candidate = m7_dir / name
        if candidate.exists():
            return candidate
    return None


def _parse_scalar(value: str) -> Any:
    value = value.split("#", 1)[0].strip()
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    lower = value.lower()
    if lower in ("true", "false"):
        return lower == "true"
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if lower in ("none", "null"):
        return "None"
    return value


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) or isinstance(value, float):
        return str(value)
    text = "" if value is None else str(value)
    if text == "":
        return '""'
    if text in ("None", "none", "null"):
        return "None"
    if re.fullmatch(r"[A-Za-z0-9_.:/\\-]+", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _read_top_level_scalars(text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        if value.strip() == "":
            continue
        values[key] = _parse_scalar(value)
    return values


def _set_top_level_scalars(text: str, updates: dict[str, Any]) -> str:
    remaining = dict(updates)
    lines = text.splitlines()
    output: list[str] = []
    for line in lines:
        match = re.match(r"^([A-Za-z0-9_]+):(\s*)(.*)$", line)
        if match and not line.startswith((" ", "\t")):
            key = match.group(1)
            if key in remaining:
                comment = ""
                value_part = match.group(3)
                if "#" in value_part:
                    comment = " #" + value_part.split("#", 1)[1]
                output.append(f"{key}: {_format_scalar(remaining.pop(key))}{comment}")
                continue
        output.append(line)
    if remaining:
        if output and output[-1].strip():
            output.append("")
        output.append("# SRA 临时写入的三月七货币战争配置")
        for key, value in remaining.items():
            output.append(f"{key}: {_format_scalar(value)}")
    line_ending = "\r\n" if "\r\n" in text else "\n"
    return line_ending.join(output) + (line_ending if text.endswith(("\n", "\r\n")) else "")


def _remove_top_level_scalars(text: str, keys: set[str]) -> str:
    output: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_]+):", line)
        if match and match.group(1) in keys and not line.startswith((" ", "\t")):
            continue
        output.append(line)
    line_ending = "\r\n" if "\r\n" in text else "\n"
    return line_ending.join(output) + (line_ending if text.endswith(("\n", "\r\n")) else "")


def _read_processes() -> list[ProcessInfo]:
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'March7th*.exe' } | "
        "Select-Object ProcessId,Name,ExecutablePath | ConvertTo-Csv -NoTypeInformation"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    items: list[ProcessInfo] = []
    for row in csv.DictReader(StringIO(result.stdout)):
        try:
            items.append(ProcessInfo(
                pid=int(row.get("ProcessId") or 0),
                image=row.get("Name") or "",
                path=row.get("ExecutablePath") or "",
            ))
        except ValueError:
            continue
    return items


def _processes_for_exe(exe: Path) -> list[ProcessInfo]:
    target = os.path.normcase(os.path.abspath(str(exe)))
    return [
        p for p in _read_processes()
        if p.path and os.path.normcase(os.path.abspath(p.path)) == target
    ]


def _is_process_running(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _kill_process(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )
    except Exception:
        pass


def _quote_ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _start_m7(exe: Path, action: str, as_admin: bool) -> None:
    if as_admin:
        ps_cmd = (
            '$env:MARCH7TH_GUI_STARTED="true"; '
            f"Start-Process -FilePath {_quote_ps(str(exe))} "
            f"-ArgumentList {_quote_ps(action)} "
            f"-WorkingDirectory {_quote_ps(str(exe.parent))} "
            "-Verb RunAs"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return

    env = os.environ.copy()
    env["MARCH7TH_GUI_STARTED"] = "true"
    subprocess.Popen(
        [str(exe), action],
        cwd=str(exe.parent),
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


class _ConfigPatch:
    def __init__(self, path: Path, updates: dict[str, Any], restore: bool):
        self.path = path
        self.updates = updates
        self.restore = restore
        self.original_values: dict[str, Any] = {}
        self.missing_keys: set[str] = set()

    def apply(self) -> None:
        original_text = self.path.read_text(encoding="utf-8")
        current = _read_top_level_scalars(original_text)
        for key, value in self.updates.items():
            if key in current:
                self.original_values[key] = current[key]
            else:
                self.missing_keys.add(key)
            if current.get(key) != value:
                logger.info(f"  {key}: {current.get(key)!r} -> {value!r}")
        self.path.write_text(_set_top_level_scalars(original_text, self.updates), encoding="utf-8")

    def revert(self) -> None:
        if not self.restore:
            logger.info("已按配置保留三月七临时配置，不恢复 config.yaml")
            return
        current_text = self.path.read_text(encoding="utf-8")
        restored_text = _set_top_level_scalars(current_text, self.original_values)
        if self.missing_keys:
            restored_text = _remove_top_level_scalars(restored_text, self.missing_keys)
        self.path.write_text(restored_text, encoding="utf-8")
        logger.info("已恢复三月七原始配置")


class _CurrencyWarsM7Runner:
    def __init__(self, task: BaseTask, forced_mode: str | None = None):
        self.task = task
        self.forced_mode = forced_mode

    def run(self) -> bool:
        m7_path = self.task.get_param("m7_path", "D:\\March7thAssistant_full")
        m7_exe = _find_m7_exe(m7_path)
        if not m7_exe.exists():
            logger.error(f"未找到三月七可执行文件：{m7_exe}")
            return False

        m7_config = _find_m7_config(m7_exe.parent)
        if m7_config is None:
            logger.error(f"未找到三月七 config.yaml：{m7_exe.parent}")
            return False

        run_mode = self.forced_mode or str(self.task.get_param("run_mode", "normal")).strip().lower()
        action = RUN_MODE_TO_ACTION.get(run_mode)
        if action is None:
            logger.error(f"不支持的运行方式：{run_mode}")
            return False

        allow_existing = _bool_param(self.task.get_param("allow_existing_m7", False))
        existing = _processes_for_exe(m7_exe)
        if existing and not allow_existing:
            logger.error("检测到三月七已在运行，为避免影响其当前任务，本脚本已停止。")
            for p in existing:
                logger.error(f"  PID={p.pid} {p.path}")
            logger.error("确认没有其它三月七任务后，可开启“允许三月七已运行”。")
            return False

        logger.info("=== 货币战争（三月七）脚本启动 ===")
        logger.info(f"三月七路径：{m7_exe}")
        logger.info(f"配置文件：{m7_config}")
        logger.info(f"运行方式：{run_mode} ({action})")

        updates = self._build_config_updates(m7_config)
        restore = _bool_param(self.task.get_param("restore_config", True), True)
        patch = _ConfigPatch(m7_config, updates, restore)
        started_pids: set[int] = set()
        success = True

        try:
            patch.apply()
            run_times = _int_param(self.task.get_param("run_times", 1), 1)
            timeout = max(30, _int_param(self.task.get_param("wait_timeout", 7200), 7200))
            as_admin = _bool_param(self.task.get_param("start_as_admin", True), True)
            actual_times = 1 if run_mode == "loop" else max(1, run_times)

            for index in range(actual_times):
                if self._stopped():
                    success = False
                    break
                logger.info(f"--- 第 {index + 1} 次货币战争 ---")
                before = {p.pid for p in _processes_for_exe(m7_exe)}
                try:
                    _start_m7(m7_exe, action, as_admin)
                except Exception as e:
                    logger.error(f"启动三月七失败：{e}")
                    success = False
                    break

                pid = self._wait_new_pid(m7_exe, before)
                if pid is None:
                    logger.error("等待三月七启动超时（30s）")
                    success = False
                    break
                started_pids.add(pid)
                logger.info(f"三月七进程已启动 (PID={pid})，等待完成（超时 {timeout}s）...")

                if not self._wait_process_exit(pid, timeout):
                    success = False
                    break

        finally:
            for pid in list(started_pids):
                if _is_process_running(pid):
                    logger.info(f"终止仍在运行的三月七进程 (PID={pid})")
                    _kill_process(pid)
            try:
                patch.revert()
            except Exception as e:
                logger.warning(f"恢复三月七配置失败：{e}")

        logger.info(f"=== 货币战争（三月七）脚本{'完成' if success else '执行失败'} ===")
        return success

    def _build_config_updates(self, config_path: Path) -> dict[str, Any]:
        cfg = _read_top_level_scalars(config_path.read_text(encoding="utf-8"))
        updates: dict[str, Any] = dict(M7_FIXED_FIELDS)

        for sra_key, yaml_key in M7_FIELD_MAP.items():
            raw = self.task.get_param(sra_key, None)
            if raw is None:
                continue
            value = _coerce_config_value(raw, cfg.get(yaml_key, ""))
            allowed = VALID_VALUES.get(yaml_key)
            if allowed and value not in allowed:
                fallback = cfg.get(yaml_key)
                if fallback not in allowed:
                    fallback = allowed[0]
                logger.warning(f"{yaml_key}={value!r} 无效，使用 {fallback!r}")
                value = fallback
            updates[yaml_key] = value

        check_score = _bool_param(self.task.get_param("check_score", True), True)
        if not check_score:
            updates["currencywars_timestamp"] = time.time()
            logger.info("已关闭积分检查：本次临时设置 currencywars_timestamp，避免三月七运行后检查积分。")

        return updates

    def _wait_new_pid(self, exe: Path, before: set[int]) -> int | None:
        for _ in range(30):
            time.sleep(1)
            after = _processes_for_exe(exe)
            for proc in after:
                if proc.pid not in before:
                    return proc.pid
            if after and not before:
                return after[0].pid
        return None

    def _wait_process_exit(self, pid: int, timeout: int) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stopped():
                logger.info("收到停止信号，终止三月七进程")
                _kill_process(pid)
                return False
            if not _is_process_running(pid):
                logger.info("三月七进程已退出")
                return True
            time.sleep(3)
        logger.error(f"等待三月七超时（{timeout}s），强制终止")
        _kill_process(pid)
        return False

    def _stopped(self) -> bool:
        return bool(self.task.stop_event and self.task.stop_event.is_set())


class CurrencyWarsM7Task(BaseTask):
    """调用三月七执行货币战争。"""

    def run(self) -> bool:
        return _CurrencyWarsM7Runner(self).run()


class CurrencyWarsM7TempTask(BaseTask):
    """调用三月七接管当前货币战争。"""

    def run(self) -> bool:
        return _CurrencyWarsM7Runner(self, forced_mode="temp").run()
