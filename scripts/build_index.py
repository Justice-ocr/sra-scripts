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
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "your-user/sra-scripts")
GITHUB_REF_NAME = os.getenv("GITHUB_REF_NAME", "main")

RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_REF_NAME}"
DOWNLOAD_BASE = f"https://github.com/{GITHUB_REPOSITORY}/releases/download"


def get_script_download_url(script_id: str, version: str) -> str:
    """
    下载 URL 策略：
    优先用 GitHub Releases（需要发 release），
    fallback 用 raw zip（直接从 git 打包）。
    这里统一用 raw zip 方式，简单可靠。
    格式：https://github.com/user/repo/raw/main/repo/{id}/
    实际下载整个文件夹用 ZIP API：
    https://github.com/user/repo/archive/refs/heads/main.zip 太大了，
    改用 GitHub Contents API 逐文件下载，或者
    推荐用 GitHub Releases 上传 zip。

    当前策略：用 GitHub API 下载文件夹 zip
    https://github.com/{repo}/archive/{ref}.zip 需要在应用端解压后找子目录
    更好的方式：用 degit 或者直接 GitHub API
    """
    # 使用 GitHub 的文件夹下载 API（通过 Code > Download ZIP 的方式）
    # 实际生效的 URL 格式（GitHub 支持）：
    # https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip
    # 应用端下载后从 zip 里找 repo/{script_id}/ 子目录
    # 这里记录 script_id 供应用端定位
    return f"https://github.com/{GITHUB_REPOSITORY}/archive/refs/heads/{GITHUB_REF_NAME}.zip"


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
