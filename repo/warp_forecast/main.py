from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger

from SRACore.notification import try_send_notification
from SRACore.task import BaseTask


PULL_COST = 160

GRID_FIRST_X, GRID_FIRST_Y = 188, 191
GRID_STEP_X, GRID_STEP_Y = 125, 149
GRID_COLS, GRID_ROWS = 9, 5
GRID_CELLS = [
    (
        round((GRID_FIRST_X + col * GRID_STEP_X) / 1920, 4),
        round((GRID_FIRST_Y + row * GRID_STEP_Y) / 1080, 4),
    )
    for row in range(GRID_ROWS)
    for col in range(GRID_COLS)
]

DETAIL_TITLE = dict(from_x=0.55, from_y=0.08, to_x=0.98, to_y=0.18)
DETAIL_COUNT = dict(from_x=0.70, from_y=0.24, to_x=0.85, to_y=0.36)
TOP_BAR = dict(from_x=0.55, from_y=0.0, to_x=1.0, to_y=0.08)


@dataclass
class Resources:
    jade: int = 0
    special_pass: int = 0
    normal_pass: int = 0

    def add(self, other: "Resources") -> "Resources":
        return Resources(
            jade=self.jade + other.jade,
            special_pass=self.special_pass + other.special_pass,
            normal_pass=self.normal_pass + other.normal_pass,
        )

    @property
    def limited_pulls(self) -> float:
        return self.special_pass + self.jade / PULL_COST

    @property
    def standard_pulls(self) -> int:
        return self.normal_pass


@dataclass
class Schedule:
    start_date: date | None
    end_date: date | None
    preview_date: date | None
    remaining_days: int
    endgame_refresh_count: int
    weekly_count: int
    preview_pending: bool


def _int_param(task: BaseTask, key: str, default: int) -> int:
    try:
        return int(task.get_param(key, default))
    except (TypeError, ValueError):
        return default


def _bool_param(task: BaseTask, key: str, default: bool = False) -> bool:
    raw = task.get_param(key, default)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("true", "1", "yes", "y", "on")


def _text_param(task: BaseTask, key: str, default: str = "") -> str:
    raw = task.get_param(key, default)
    return default if raw is None else str(raw).strip()


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        logger.warning(f"日期格式无效：{value!r}，需要 YYYY-MM-DD")
        return None


def _clean_number(text: str) -> int | None:
    nums = re.findall(r"\d[\d,]*", text.replace("，", ","))
    if not nums:
        return None
    try:
        return int(nums[-1].replace(",", ""))
    except ValueError:
        return None


def _ocr_text(results: list[Any] | None, min_confidence: float = 0.55) -> str:
    return " ".join(str(item[1]) for item in (results or []) if len(item) >= 3 and item[2] >= min_confidence)


def _ocr_items(results: list[Any] | None, min_confidence: float = 0.55) -> list[Any]:
    return [item for item in (results or []) if len(item) >= 3 and item[2] >= min_confidence]


def _box_center(item: Any) -> tuple[float, float]:
    box = item[0]
    return (
        (box[0][0] + box[2][0]) / 2,
        (box[0][1] + box[2][1]) / 2,
    )


def _find_num_near_keyword(results: list[Any] | None, keywords: tuple[str, ...]) -> int | None:
    items = _ocr_items(results)
    for index, item in enumerate(items):
        text = str(item[1])
        if not any(keyword in text for keyword in keywords):
            continue
        direct = _clean_number(text)
        if direct is not None:
            return direct

        box = item[0]
        keyword_y = (box[0][1] + box[2][1]) / 2
        keyword_right = max(point[0] for point in box)
        candidates: list[tuple[float, int]] = []
        for other in items:
            if other is item:
                continue
            number = _clean_number(str(other[1]))
            if number is None:
                continue
            ox, oy = _box_center(other)
            if abs(oy - keyword_y) <= 35 and ox >= keyword_right - 10:
                candidates.append((ox, number))
        if candidates:
            return min(candidates, key=lambda pair: pair[0])[1]

        if index + 1 < len(items):
            return _clean_number(str(items[index + 1][1]))
    return None


class WarpForecastTask(BaseTask):
    """预测当前版本结束前的抽卡资源。"""

    def run(self) -> bool:
        logger.info("抽卡资源预测开始")

        current = self._manual_current_resources()
        if _bool_param(self, "scan_bag", True):
            scanned = self._read_bag_resources()
            current = Resources(
                jade=scanned.jade if scanned.jade > 0 else current.jade,
                special_pass=scanned.special_pass if scanned.special_pass > 0 else current.special_pass,
                normal_pass=scanned.normal_pass if scanned.normal_pass > 0 else current.normal_pass,
            )

        event = self._manual_event_resources()
        if _bool_param(self, "scan_event_guide", True):
            scanned_event = self._read_event_guide_rewards()
            event = event.add(scanned_event)

        schedule = self._build_schedule()
        future = self._future_resources(schedule)
        total = current.add(event).add(future)

        message = self._format_report(current, event, future, total, schedule)
        logger.info("\n" + message)
        try_send_notification("抽卡资源预测", message, result="success", operator=self.operator)
        logger.info("抽卡资源预测完成")
        return True

    def _manual_current_resources(self) -> Resources:
        return Resources(
            jade=max(0, _int_param(self, "manual_current_jade", 0)),
            special_pass=max(0, _int_param(self, "manual_special_pass", 0)),
            normal_pass=max(0, _int_param(self, "manual_normal_pass", 0)),
        )

    def _manual_event_resources(self) -> Resources:
        return Resources(
            jade=max(0, _int_param(self, "manual_event_jade", 0)),
            special_pass=max(0, _int_param(self, "manual_event_special_pass", 0)),
            normal_pass=max(0, _int_param(self, "manual_event_normal_pass", 0)),
        )

    def _build_schedule(self) -> Schedule:
        today = date.today()
        start = _parse_date(_text_param(self, "version_start_date", ""))
        version_days = max(1, _int_param(self, "version_days", 42))
        preview_before_end = max(0, _int_param(self, "preview_before_end_days", 12))

        end = start + timedelta(days=version_days) if start else None
        preview_date = end - timedelta(days=preview_before_end) if end else None
        remaining_days = max(0, (end - today).days) if end else 0

        endgame_count = self._remaining_endgame_count(start, end, today)
        weekly_count = self._remaining_weekly_count(end, today)

        preview_status = _text_param(self, "preview_status", "auto").lower()
        if preview_status == "done":
            preview_pending = False
        elif preview_status == "not_done":
            preview_pending = True
        else:
            preview_pending = bool(preview_date and today < preview_date)

        return Schedule(
            start_date=start,
            end_date=end,
            preview_date=preview_date,
            remaining_days=remaining_days,
            endgame_refresh_count=endgame_count,
            weekly_count=weekly_count,
            preview_pending=preview_pending,
        )

    def _remaining_endgame_count(self, start: date | None, end: date | None, today: date) -> int:
        override = _int_param(self, "endgame_refresh_count_override", -1)
        if override >= 0:
            return override
        if start is None or end is None:
            return 0

        interval = max(1, _int_param(self, "endgame_refresh_interval_days", 14))
        offset = _int_param(self, "endgame_first_refresh_offset_days", 0)
        include_today = _bool_param(self, "include_today_endgame", True)
        lower_bound = today if include_today else today + timedelta(days=1)

        count = 0
        refresh = start + timedelta(days=offset)
        while refresh < lower_bound:
            refresh += timedelta(days=interval)
        while refresh < end:
            count += 1
            refresh += timedelta(days=interval)
        return count

    def _remaining_weekly_count(self, end: date | None, today: date) -> int:
        override = _int_param(self, "weekly_count_override", -1)
        if override >= 0:
            return override
        if end is None:
            return 0

        weekday = min(6, max(0, _int_param(self, "weekly_reset_weekday", 0)))
        include_today = _bool_param(self, "include_today_weekly", True)
        lower_bound = today if include_today else today + timedelta(days=1)

        days_until_reset = (weekday - lower_bound.weekday()) % 7
        reset = lower_bound + timedelta(days=days_until_reset)
        count = 0
        while reset < end:
            count += 1
            reset += timedelta(days=7)
        return count

    def _future_resources(self, schedule: Schedule) -> Resources:
        daily = _int_param(
            self,
            "daily_jade_with_card" if _bool_param(self, "has_monthly_card", False) else "daily_jade_without_card",
            150 if _bool_param(self, "has_monthly_card", False) else 90,
        )
        endgame_jade = max(0, _int_param(self, "endgame_jade_per_refresh", 800))
        weekly_jade = max(0, _int_param(self, "weekly_universe_jade", 225))
        preview_jade = max(0, _int_param(self, "preview_jade", 300)) if schedule.preview_pending else 0

        return Resources(
            jade=(
                max(0, schedule.remaining_days) * max(0, daily)
                + max(0, schedule.endgame_refresh_count) * endgame_jade
                + max(0, schedule.weekly_count) * weekly_jade
                + preview_jade
            )
        )

    def _read_bag_resources(self) -> Resources:
        op = self.operator
        resources = Resources()
        try:
            self._activate_window()
            op.click_point(0.5, 0.5, after_sleep=0.5)
            op.press_key("b")
            op.sleep(2.5)

            if op.wait_ocr("背包", timeout=8, confidence=0.75, from_x=0.0, from_y=0.0, to_x=0.18, to_y=0.12) is None:
                logger.warning("背包未打开，跳过背包自动识别")
                return resources

            top_bar = op.ocr(**TOP_BAR, trace=False)
            resources.jade = _find_num_near_keyword(top_bar, ("星琼", "琼")) or 0

            self._click_precious_tab()
            special, normal = self._scan_passes()
            resources.special_pass = special or 0
            resources.normal_pass = normal or 0
            op.press_key("escape")
            op.sleep(0.5)
        except Exception as exc:
            logger.warning(f"背包资源自动识别失败：{exc}")
        logger.info(f"背包识别结果：星琼={resources.jade}, 专票={resources.special_pass}, 通票={resources.normal_pass}")
        return resources

    def _activate_window(self) -> None:
        op = self.operator
        for attempt in range(2):
            try:
                op.get_win_region(active_window=(attempt == 0))
                return
            except Exception as exc:
                logger.warning(f"激活窗口失败 attempt={attempt}: {exc}")
                op.sleep(0.5)

    def _click_precious_tab(self) -> None:
        op = self.operator
        tab_y = int(op.height * 0.044)
        step = max(1, int(op.width * 0.01))
        for px in range(int(op.width * 0.75), int(op.width * 0.20), -step):
            op.click_point(px, tab_y, after_sleep=0.25)
            label = _ocr_text(op.ocr(from_x=0.0, from_y=0.03, to_x=0.22, to_y=0.11, trace=False), 0.7)
            if "贵重" in label:
                logger.info(f"已切换到贵重物品页签 px={px}")
                return
        logger.warning("未确认贵重物品页签，继续尝试扫描当前页")

    def _scan_passes(self) -> tuple[int | None, int | None]:
        op = self.operator
        special_pass = None
        normal_pass = None
        for index, (gx, gy) in enumerate(GRID_CELLS):
            if self.stop_event and self.stop_event.is_set():
                break
            if special_pass is not None and normal_pass is not None:
                break

            op.click_point(int(op.width * gx), int(op.height * gy), after_sleep=0.25)
            title = self._read_detail_title()
            if not title:
                continue
            logger.debug(f"背包格子 {index + 1}: {title}")
            if "星轨专票" in title and special_pass is None:
                special_pass = self._read_detail_count()
            elif "星轨通票" in title and normal_pass is None:
                normal_pass = self._read_detail_count()
        return special_pass, normal_pass

    def _read_detail_title(self) -> str:
        results = self.operator.ocr(**DETAIL_TITLE, trace=False)
        candidates = [
            str(item[1])
            for item in _ocr_items(results, 0.7)
            if re.search(r"[\u4e00-\u9fff]", str(item[1]))
        ]
        return max(candidates, key=len) if candidates else ""

    def _read_detail_count(self) -> int | None:
        results = self.operator.ocr(**DETAIL_COUNT, trace=False)
        full_text = _ocr_text(results, 0.5)
        match = re.search(r"[xX×]\s*(\d+)", full_text)
        if match:
            return int(match.group(1))
        return _clean_number(full_text)

    def _read_event_guide_rewards(self) -> Resources:
        resources = Resources()
        try:
            if not self._open_reward_guide():
                logger.warning("未能打开奖励指南，跳过奖励指南识别")
                return resources
            results = self.operator.ocr(from_x=0.0, from_y=0.0, to_x=1.0, to_y=1.0, trace=False)
            resources = self._parse_event_rewards(results)
            self.operator.press_key("escape")
            self.operator.sleep(0.4)
        except Exception as exc:
            logger.warning(f"奖励指南自动识别失败：{exc}")
        logger.info(f"奖励指南识别结果：星琼={resources.jade}, 专票={resources.special_pass}, 通票={resources.normal_pass}")
        return resources

    def _open_reward_guide(self) -> bool:
        op = self.operator
        self._activate_window()
        op.click_point(0.5, 0.5, after_sleep=0.3)

        world_text = _ocr_text(op.ocr(from_x=0.0, from_y=0.86, to_x=0.14, to_y=1.0, trace=False), 0.55)
        if "Enter" in world_text or "回车" in world_text:
            op.press_key("escape")
            op.sleep(1.0)

        if op.wait_ocr("旅情事记", timeout=3, confidence=0.65, from_x=0.55, from_y=0.20, to_x=0.95, to_y=0.78) is None:
            op.press_key("escape")
            op.sleep(1.0)

        menu = op.ocr(from_x=0.50, from_y=0.18, to_x=0.98, to_y=0.82, trace=False)
        if not self._click_text(menu, "旅情事记", fallback=(0.73, 0.52)):
            return False
        op.sleep(1.2)

        guide = op.ocr(from_x=0.10, from_y=0.02, to_x=0.45, to_y=0.20, trace=False)
        if not self._click_text(guide, "奖励指南", fallback=(0.24, 0.08)):
            return False
        op.sleep(1.0)
        return True

    def _click_text(self, results: list[Any] | None, text: str, fallback: tuple[float, float]) -> bool:
        for item in _ocr_items(results, 0.55):
            if text in str(item[1]):
                x, y = _box_center(item)
                if self.operator.width and self.operator.height:
                    self.operator.click_point(int(x), int(y), after_sleep=0.5)
                else:
                    self.operator.click_point(fallback[0], fallback[1], after_sleep=0.5)
                return True
        self.operator.click_point(fallback[0], fallback[1], after_sleep=0.5)
        return True

    def _parse_event_rewards(self, results: list[Any] | None) -> Resources:
        reward_type = _text_param(self, "event_reward_type", "auto").lower()
        items = _ocr_items(results, 0.5)
        resources = Resources()

        for item in items:
            text = str(item[1])
            if "剩余" not in text:
                continue

            number = _clean_number(text) or self._number_right_of(item, items)
            if number is None:
                continue

            actual_type = reward_type
            if actual_type == "auto":
                actual_type = self._guess_event_reward_type(item, items)

            if actual_type == "normal_pass":
                resources.normal_pass += number
            elif actual_type == "special_pass":
                resources.special_pass += number
            else:
                resources.jade += number

        return resources

    def _number_right_of(self, item: Any, items: list[Any]) -> int | None:
        box = item[0]
        y = (box[0][1] + box[2][1]) / 2
        right = max(point[0] for point in box)
        candidates: list[tuple[float, int]] = []
        for other in items:
            if other is item:
                continue
            number = _clean_number(str(other[1]))
            if number is None:
                continue
            ox, oy = _box_center(other)
            if ox >= right - 10 and abs(oy - y) <= 45:
                candidates.append((ox, number))
        if not candidates:
            return None
        return min(candidates, key=lambda pair: pair[0])[1]

    def _guess_event_reward_type(self, item: Any, items: list[Any]) -> str:
        box = item[0]
        y = (box[0][1] + box[2][1]) / 2
        nearby = []
        for other in items:
            _, oy = _box_center(other)
            if abs(oy - y) <= 60:
                nearby.append(str(other[1]))
        text = " ".join(nearby)
        if "星轨通票" in text or "通票" in text:
            return "normal_pass"
        if "星轨专票" in text or "专票" in text:
            return "special_pass"
        return "jade"

    def _format_report(
        self,
        current: Resources,
        event: Resources,
        future: Resources,
        total: Resources,
        schedule: Schedule,
    ) -> str:
        lines = [
            "抽卡资源预测结果",
            "",
            "当前资源",
            f"- 星琼：{current.jade}",
            f"- 星轨专票：{current.special_pass}",
            f"- 星轨通票：{current.normal_pass}",
            f"- 当前限定池可用：{current.limited_pulls:.2f} 抽",
            f"- 当前常驻池可用：{current.standard_pulls} 抽",
            "",
            "奖励指南剩余",
            f"- 星琼：{event.jade}",
            f"- 星轨专票：{event.special_pass}",
            f"- 星轨通票：{event.normal_pass}",
            "",
            "版本剩余估算",
            f"- 版本起始：{schedule.start_date or '未设置'}",
            f"- 版本结束：{schedule.end_date or '未设置'}",
            f"- 前瞻日期：{schedule.preview_date or '未设置'}",
            f"- 剩余日常天数：{schedule.remaining_days}",
            f"- 剩余深渊刷新：{schedule.endgame_refresh_count}",
            f"- 剩余周常奖励：{schedule.weekly_count}",
            f"- 前瞻兑换码：{'计入' if schedule.preview_pending else '不计入'}",
            f"- 预计未来星琼：{future.jade}",
            "",
            "版本结束预计",
            f"- 总星琼：{total.jade}",
            f"- 总星轨专票：{total.special_pass}",
            f"- 总星轨通票：{total.normal_pass}",
            f"- 限定池预计：{total.limited_pulls:.2f} 抽",
            f"- 常驻池预计：{total.standard_pulls} 抽",
        ]
        return "\n".join(lines)
