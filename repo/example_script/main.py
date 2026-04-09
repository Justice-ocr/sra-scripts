from SRACore.task import BaseTask


class ExampleTask(BaseTask):
    """示例任务：演示如何编写 SRA 自定义任务"""

    def run(self) -> bool:
        # self.config 包含当前配置
        # self.operator 包含截图、点击等操作接口
        # self.stop_event 用于检查是否被用户停止
        print("示例任务开始运行")

        if self.stop_event.is_set():
            return False

        # 你的任务逻辑写在这里
        print("示例任务完成")
        return True
