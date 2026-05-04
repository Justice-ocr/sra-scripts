"""
扫描 repo/ 目录下所有脚本文件夹，读取 manifest.json，
生成仓库根目录的 repo.json 索引。

每个脚本文件夹结构：
  repo/{script_id}/
    manifest.json   必需
    main.py         主任务（或 manifest.tasks 里指定的多个文件）
    README.md       可选

repo.json 格式：
{
  "name": "仓库名",
  "version": "生成时间戳",
  "scripts": [
    {
      "id": "script_id",
      "name": "...",
      "version": "1.0.0",
      "description": "...",
      "author": "...",
      "last_updated": "ISO时间",
      "download_url": "https://github.com/.../archive/main.zip 的 API URL",
      "tasks": [
        { "name": "任务名", "entry": "main.py", "class": "MainTask" }
      ]
    }
  ]
}
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent / "repo"
OUTPUT = Path(__file__).parent.parent / "repo.json"

# 从环境变量读取仓库信息（GitHub Actions 提供）
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "Justice-ocr/sra-scripts")
GITHUB_REF_NAME = os.getenv("GITHUB_REF_NAME", "main")

RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_REF_NAME}"
DOWNLOAD_BASE = f"https://github.com/{GITHUB_REPOSITORY}/releases/download"


def get_script_download_url(script_id: str, version: str) -> str:
    """
    返回脚本子目录的 raw base URL。
    应用端据此逐文件下载（manifest.json → 获取文件列表 → 逐文件下载）。
    格式：https://raw.githubusercontent.com/{user}/{repo}/{branch}/repo/{script_id}
    """
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_REF_NAME}/repo/{script_id}"


def build_index():
    scripts = []

    if not REPO_DIR.exists():
        print(f"repo/ 目录不存在: {REPO_DIR}")
        return

    for script_dir in sorted(REPO_DIR.iterdir()):
        if not script_dir.is_dir():
            continue

        manifest_path = script_dir / "manifest.json"
        if not manifest_path.exists():
            print(f"  跳过（无 manifest.json）: {script_dir.name}")
            continue

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"  解析失败: {script_dir.name}: {e}")
            continue

        script_id = manifest.get("id") or script_dir.name
        version = manifest.get("version", "0.0.0")

        entry = {
            "id": script_id,
            "name": manifest.get("name", script_id),
            "version": version,
            "description": manifest.get("description", ""),
            "author": manifest.get("author", ""),
            "last_updated": manifest.get("last_updated", ""),
            "download_url": get_script_download_url(script_id, version),
            "repo_path": f"repo/{script_dir.name}",  # 应用端从 zip 里定位用
            "tasks": manifest.get("tasks", [
                {"name": manifest.get("name", script_id),
                 "entry": "main.py",
                 "class": "".join(w.capitalize() for w in script_id.split("_"))}
            ]),
        }
        scripts.append(entry)
        print(f"  + {script_id} v{version}")

    repo_json = {
        "name": manifest.get("repo_name", "SRA Scripts") if scripts else "SRA Scripts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scripts": scripts,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(repo_json, f, ensure_ascii=False, indent=2)

    print(f"\n✅ repo.json 已生成，共 {len(scripts)} 个脚本")


if __name__ == "__main__":
    build_index()
