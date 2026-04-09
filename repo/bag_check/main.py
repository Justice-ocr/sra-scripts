"""
背包资源查询脚本 - 贵重物品页读取专票/通票
"""
import re

from loguru import logger

from SRACore.task import BaseTask
from SRACore.util.notify import try_send_notification

# 格子坐标（比例，相对于游戏窗口，从截图重新标定）
_G1X, _G1Y = 188, 191   # 第1格中心像素（1920x1080窗口内）
_DW,  _DH  = 125, 149   # 格子间距
_COLS, _ROWS = 9, 5

GRID_CELLS = [
    (round((_G1X + c * _DW) / 1920, 4),
     round((_G1Y + r * _DH) / 1080, 4))
    for r in range(_ROWS)
    for c in range(_COLS)
]

# 右侧详情区
DETAIL_TITLE = dict(from_x=0.55, from_y=0.08, to_x=0.98, to_y=0.18)
DETAIL_COUNT = dict(from_x=0.70, from_y=0.24, to_x=0.85, to_y=0.36)
TOP_BAR      = dict(from_x=0.55, from_y=0.0,  to_x=1.0,  to_y=0.08)


class BagCheckTask(BaseTask):

    def run(self) -> bool:
        op = self.operator
        logger.info("背包资源查询开始")

        # 1. 激活窗口，失败则重试一次（不激活也要获取窗口尺寸）
        for attempt in range(2):
            try:
                op.get_win_region(active_window=(attempt == 0))
                break
            except Exception as e:
                logger.warning(f"激活窗口失败(attempt={attempt}): {e}")
                op.sleep(0.5)

        # 确认窗口尺寸有效
        if op.width == 0 or op.height == 0:
            logger.error("无法获取游戏窗口，请确认游戏正在运行")
            try_send_notification("背包资源查询", "无法获取游戏窗口，请确认游戏正在运行。",
                                  result="fail", operator=op)
            return False

        logger.info(f"窗口: left={op.left}, top={op.top}, {op.width}x{op.height}")
        op.sleep(0.5)

        # 2. 点击中央获取焦点
        op.click_point(0.5, 0.5, after_sleep=0.5)

        # 3. 检测ESC菜单
        esc = op.ocr(from_x=0.6, from_y=0.2, to_x=1.0, to_y=0.5, trace=False)
        if any('开拓等级' in item[1] for item in (esc or []) if item[2] > 0.7):
            logger.info("关闭ESC菜单...")
            op.press_key('escape')
            op.sleep(0.8)
            op.click_point(0.5, 0.5, after_sleep=0.3)

        # 4. 打开背包
        logger.info("打开背包...")
        op.press_key('b')
        op.sleep(2.5)

        # 5. 确认背包打开
        if op.wait_ocr('背包', timeout=8, confidence=0.8,
                       from_x=0.0, from_y=0.0, to_x=0.15, to_y=0.1) is None:
            logger.error("背包未打开")
            try_send_notification("背包资源查询", "背包未成功打开。",
                                  result="fail", operator=op)
            return False

        logger.info(f"背包已打开，窗口: {op.width}x{op.height}")

        # 6. 读取顶栏
        jade, credits = self._read_top_bar(op)

        # 7. 切换到贵重物品页签
        logger.info("切换到贵重物品页签...")
        tab_y = int(op.height * 0.044)
        step  = max(1, int(op.width * 0.01))
        found_precious = False
        for px in range(int(op.width * 0.75), int(op.width * 0.20), -step):
            op.click_point(px, tab_y, after_sleep=0.35)
            lbl = op.ocr(from_x=0.0, from_y=0.03, to_x=0.2, to_y=0.11, trace=False)
            lbl_text = ' '.join(i[1] for i in (lbl or []) if i[2] > 0.7)
            logger.debug(f"页签扫描 px={px} -> {lbl_text}")
            if '贵重物' in lbl_text:
                logger.info(f"贵重物品页签 px={px}")
                found_precious = True
                break
        if not found_precious:
            logger.warning("未找到贵重物品页签")

        op.sleep(0.5)

        # 8. 逐格扫描，找专票和通票
        logger.info("逐格扫描贵重物品页...")
        special_pass = None
        standard_pass = None

        for i, (gx, gy) in enumerate(GRID_CELLS):
            if self.stop_event and self.stop_event.is_set():
                break
            if special_pass is not None and standard_pass is not None:
                break

            px = int(op.width * gx)
            py = int(op.height * gy)
            op.click_point(px, py, after_sleep=0.25)

            # 读详情标题
            t_res = op.ocr(**DETAIL_TITLE, trace=False)
            title = self._get_title(t_res)
            if not title:
                continue
            logger.debug(f"格子{i+1} ({gx:.3f},{gy:.3f}) px=({px},{py}) -> {title}")

            if '星轨专票' in title and special_pass is None:
                count = self._read_count(op)
                special_pass = count
                logger.info(f"找到星轨专票: {count}")
            elif '星轨通票' in title and standard_pass is None:
                count = self._read_count(op)
                standard_pass = count
                logger.info(f"找到星轨通票: {count}")

        logger.info(f"扫描结果: 专票={special_pass}, 通票={standard_pass}")

        # 9. 发送通知
        lines = [
            "背包资源查询结果", "",
            f"星琼：{jade or '未识别'}",
            f"星轨专票：{special_pass or '未识别'}",
            f"星轨通票：{standard_pass or '未识别'}",
            f"信用点：{credits or '未识别'}",
        ]
        message = "\n".join(lines)
        logger.info(message)
        try_send_notification("背包资源查询", message, result="success", operator=op)

        op.sleep(0.3)
        op.press_key('escape')
        op.sleep(0.5)
        logger.info("背包资源查询完成")
        return True

    def _read_top_bar(self, op):
        results = op.ocr(**TOP_BAR, trace=False)
        jade    = self._find_num(results, ['星琼', '琼'])
        credits = self._find_num(results, ['信用点'])
        if jade is None or credits is None:
            nums_x = sorted(
                [((item[0][0][0] + item[0][2][0]) / 2, item[1].replace(',', ''))
                 for item in (results or [])
                 if item[2] > 0.85 and re.match(r'^\d{4,}$', item[1].replace(',', ''))],
                key=lambda t: t[0]
            )
            logger.debug(f"顶栏数字(左→右): {nums_x}")
            if len(nums_x) >= 1 and credits is None:
                credits = nums_x[0][1]   # 左=信用点
            if len(nums_x) >= 2 and jade is None:
                jade = nums_x[1][1]      # 右=星琼
        logger.info(f"信用点={credits}, 星琼={jade}")
        return jade, credits

    def _get_title(self, results) -> str:
        if not results:
            return ''
        cands = [item[1] for item in results if item[2] > 0.7
                 and re.search(r'[\u4e00-\u9fff]', item[1])]
        return max(cands, key=len) if cands else ''

    def _read_count(self, op) -> str | None:
        """识别详情区的 × N 数量"""
        results = op.ocr(**DETAIL_COUNT, trace=False)
        logger.debug(f"数量区OCR: {[(i[1], round(i[2],2)) for i in (results or [])]}")
        if not results:
            return None
        # 把所有识别文本拼在一起，从中找 × 后面的数字
        full_text = ' '.join(item[1] for item in results if item[2] > 0.5)
        logger.debug(f"数量区全文: {full_text}")
        # 匹配 × 3 / x 3 / X3 格式
        m = re.search(r'[×xX×]\s*(\d+)', full_text)
        if m:
            return m.group(1)
        # fallback：找独立数字
        for item in results:
            if item[2] < 0.6:
                continue
            nums = re.findall(r'\d+', item[1])
            if nums:
                return nums[0]
        return None

    def _find_num(self, results, keywords) -> str | None:
        if not results:
            return None
        for i, item in enumerate(results):
            if item[2] < 0.6 or not any(kw in item[1] for kw in keywords):
                continue
            nums = re.findall(r'[\d,]+', item[1])
            if nums:
                return nums[-1].replace(',', '')
            kb = item[0]
            ky = (kb[0][1] + kb[2][1]) / 2
            kx = kb[1][0]
            kh = abs(kb[2][1] - kb[0][1]) or 20
            cands = [(ob[0][0], ns[-1].replace(',', ''))
                     for other in results
                     if other is not item and other[2] > 0.5
                     for ns in [re.findall(r'[\d,]+', other[1])] if ns
                     for ob in [other[0]]
                     if abs((ob[0][1]+ob[2][1])/2 - ky) < kh*1.5
                     and ob[0][0] >= kx - 10]
            if cands:
                return min(cands, key=lambda c: c[0])[1]
            if i + 1 < len(results):
                ns2 = re.findall(r'[\d,]+', results[i+1][1])
                if ns2:
                    return ns2[0].replace(',', '')
        return None
