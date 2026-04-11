# SRA 脚本仓库

StarRailAssistant 自定义脚本仓库。

## 使用方法

在 SRA 的「脚本仓库」页面添加以下地址：

```
https://github.com/Justice-ocr/sra-scripts
```

## 脚本列表

### 背包资源查询 `bag_check`

查询崩铁背包中的星琼、专票、通票、信用点数量，通过通知渠道发送结果。

**无需配置**，直接使用。

---

### 差分宇宙 `divergent_universe`

原生复刻三月七小助手的差分宇宙逻辑，**无需安装三月七**。

**支持功能：**
- 常规演算 / 周期演算
- 自动处理随意门（HSV 颜色检测）
- 自动选择祝福 / 方程 / 奇物 / 奇迹 / 面具
- 自动处理事件、站点卡、混沌药箱
- 自动开启战斗、进出关卡

**通过 `settings.json` 提供配置界面，在任务页点击「修改脚本配置」进行配置：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `Mode` | select | `normal` | `normal`=常规演算，`cycle`=周期演算 |
| `Level` | select | `4` | 关卡难度 1-5 |
| `StableMode` | bool | `false` | 云游戏/低配开启 |
| `CheckScore` | bool | `false` | 完成后检查积分 |

---

## 脚本开发指南

### 目录结构

```
repo/
  your_script/
    manifest.json     # 必须
    main.py           # 入口文件
    settings.json     # 可选，配置界面定义
    README.md         # 可选，在仓库页展示
    assets/           # 可选，图片等资源
```

### settings.json 格式

脚本可以通过 `settings.json` 定义配置界面，SRA 会在任务页自动渲染弹窗：

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
  { "key": "Enable", "type": "bool", "label": "开关参数", "default": "true" },
  {
    "key": "Mode",
    "type": "select",
    "label": "选择参数",
    "options": ["选项A", "选项B"],
    "default": "选项A"
  }
]
```

支持类型：`string`、`int`、`bool`、`select`、`group`（分组标题）

### Python 侧读取配置

```python
from SRACore.task import BaseTask

class MyTask(BaseTask):
    def _post_init(self):
        # 优先读 config.json，其次读 settings.json 保存的值
        self.my_param = self.get_param("MyParam", "默认值")
        self.enable   = self.get_param("Enable", "true") == "true"

    def run(self) -> bool:
        ...
```

### repo.json 字段说明

```json
{
  "id": "script_id",
  "name": "显示名称",
  "version": "1.0.0",
  "description": "简短描述",
  "author": "作者名",
  "download_url": "https://github.com/.../archive/refs/heads/main.zip",
  "repo_path": "repo/script_id",
  "last_updated": "2026-04-11",
  "settings": "settings.json",
  "tasks": [
    { "name": "任务名", "entry": "main.py", "class": "MyTaskClass" }
  ]
}
```

`settings` 字段（可选）：指向配置定义文件名，前端会在脚本列表和任务页自动读取并渲染配置弹窗。
