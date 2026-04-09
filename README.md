# SRA Scripts

StarRailAssistant 脚本仓库。

## 如何添加此仓库到 SRA

在 SRA 拓展页 → 脚本仓库 → 添加仓库，填入：

```
https://github.com/Your name/sra-scripts
```

## 如何提交脚本

1. Fork 此仓库
2. 在 `repo/` 目录下新建文件夹（以脚本 ID 命名）
3. 创建 `manifest.json` 和脚本文件
4. 提交 Pull Request

## 脚本结构

```
repo/{script_id}/
├── manifest.json   # 脚本元信息（必需）
├── main.py         # 主任务文件
└── README.md       # 说明文档（可选）
```

## manifest.json 格式

```json
{
  "id": "my_script",
  "name": "我的脚本",
  "version": "1.0.0",
  "description": "脚本描述",
  "author": "作者名",
  "last_updated": "2026-01-01",
  "tasks": [
    {
      "name": "任务名称",
      "entry": "main.py",
      "class": "MyTask"
    }
  ]
}
```

## 开发脚本

```python
from SRACore.task import BaseTask

class MyTask(BaseTask):
    def run(self) -> bool:
        # 你的逻辑
        return True
```
