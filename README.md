# SRA 脚本仓库

StarRailAssistant 自定义脚本仓库。

## 添加仓库

在 SRA 的「脚本仓库」页面添加以下地址：

```
https://github.com/Justice-ocr/sra-scripts
```

---

## 脚本开发指南

### 目录结构

```
repo/
  your_script/
    manifest.json     # 必须
    main.py           # 入口文件
    settings.json     # 可选，配置界面定义
    README.md         # 可选，在仓库页点击 README 按钮展示
    assets/           # 可选，图片等资源
```

### manifest.json

```json
{
  "id": "your_script",
  "name": "脚本显示名称",
  "version": "1.0.0",
  "description": "简短描述，显示在仓库脚本列表中",
  "author": "作者名",
  "settings": "settings.json",
  "tasks": [
    { "name": "任务名", "entry": "main.py", "class": "MyTaskClass" }
  ]
}
```

### settings.json

通过 `settings.json` 定义配置界面，SRA 会在任务页自动渲染「修改脚本配置」弹窗：

```json
[
  { "key": "group1", "type": "group", "label": "分组标题" },
  {
    "key": "MyParam",
    "label": "参数显示名",
    "type": "string",
    "default": "默认值",
    "description": "参数说明文字"
  },
  { "key": "Enable", "type": "bool",   "label": "开关参数", "default": "true" },
  {
    "key": "Mode",
    "type": "select",
    "label": "选择参数",
    "options": ["选项A", "选项B"],
    "default": "选项A"
  }
]
```

支持类型：`string` / `int` / `bool` / `select` / `group`（分组标题）

### Python 侧读取配置

```python
from SRACore.task import BaseTask

class MyTask(BaseTask):
    def _post_init(self):
        self.my_param = self.get_param("MyParam", "默认值")
        self.enable   = self.get_param("Enable", "true") == "true"

    def run(self) -> bool:
        ...
```

### repo.json 字段说明

`repo.json` 位于仓库根目录，SRA 通过它获取脚本列表：

```json
{
  "name": "仓库名称",
  "version": "1.0.0",
  "scripts": [
    {
      "id": "your_script",
      "name": "显示名称",
      "version": "1.0.0",
      "description": "简短描述",
      "author": "作者名",
      "download_url": "https://github.com/.../archive/refs/heads/main.zip",
      "repo_path": "repo/your_script",
      "last_updated": "2026-04-11",
      "settings": "settings.json",
      "tasks": [
        { "name": "任务名", "entry": "main.py", "class": "MyTaskClass" }
      ]
    }
  ]
}
```

`settings` 字段（可选）：指向配置定义文件名，前端自动读取并渲染配置弹窗。无此字段时弹窗显示「未找到 settings.json」提示。
