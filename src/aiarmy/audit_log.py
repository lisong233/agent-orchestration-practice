"""
审计日志 — 部署后唯一的观测窗口。
每次判断的中间过程落盘为 jsonl，供事后复盘。
"""
import json
import time
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_PATH = LOG_DIR / "runs.jsonl"


def log_run(record: dict):
    """写入一行审计日志。写入失败静默（不影响主流程）。"""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        record["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 日志写入失败不影响主流程
