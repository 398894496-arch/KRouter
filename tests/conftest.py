import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))
sys.path.insert(0, str(ROOT / "extras/host-daily-evolution"))

# 测试绝不能写宿主真实的查询日志 / 学习游标 / 召回缓存：查询日志是夜间学习的输入，
# 评测题漏进去会被学成触发词（留出集也就不再是留出集）。子进程继承这里的环境变量。
import os  # noqa: E402
import tempfile  # noqa: E402

_ISOLATED = Path(tempfile.mkdtemp(prefix="krouter-tests-"))
os.environ["KROUTER_STATE_DIR"] = str(_ISOLATED / "state")
os.environ.setdefault("KROUTER_CACHE_DIR", str(_ISOLATED / "cache"))
os.environ["KROUTER_NOTIFY"] = "0"  # 测试不弹桌面通知
os.environ["KROUTER_NO_PROMPT"] = "1"  # 测试里安装脚本不向终端提问
# 会话导入读的是宿主真实的 agent 会话记录；测试只读自己造的。一键安装也不许改宿主的 MCP 配置和库路径记录。
os.environ["KROUTER_CLAUDE_PROJECTS"] = str(_ISOLATED / "no-claude-projects")
os.environ["KROUTER_CODEX_SESSIONS"] = str(_ISOLATED / "no-codex-sessions")
os.environ["KROUTER_CURSOR_PROJECTS"] = str(_ISOLATED / "no-cursor-projects")
os.environ["KROUTER_VAULT_FILE"] = str(_ISOLATED / "config/vault")
os.environ["KROUTER_NO_MCP"] = "1"
os.environ["KROUTER_NO_HOOKS"] = "1"  # 也不许往宿主的 ~/.codex/hooks.json、~/.cursor/hooks.json 里加钩子
os.environ["KROUTER_CLAUDE_MEM_DB"] = str(_ISOLATED / "no-claude-mem.db")
os.environ["KROUTER_CLAUDE_DESKTOP_RUNNING"] = "0"  # 本机开着的 Claude Desktop 不影响测试；要测"开着"的测试自己设 1
# 冷热（hot.py）按"今天"算：测试固定今天，免得过两个月后固定的摘要、提示词因为卡变冷而换了顺序
os.environ.setdefault("KROUTER_TODAY", "2026-11-12")
