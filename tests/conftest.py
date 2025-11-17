import sys
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Provide a fake biliup client so tests do not hit real network.
fake_bili_module = types.ModuleType("biliup.plugins.bili_webup")


class FakeData(list):
    def __init__(self):
        super().__init__()
        self.desc = ""
        self.title = ""
        self.tid = 0
        self.tags = []

    def set_tag(self, tags):
        self.tags = list(tags)


class FakeBiliBili:
    def __init__(self, _):
        self.video = None
        self.uploaded = []
        self.cover_path = None
        self.cookie_payload = None
        self.closed = False

    def login_by_cookies(self, payload):
        self.cookie_payload = payload

    def upload_file(self, path, lines="AUTO"):
        self.uploaded.append((path, lines))
        return {"path": path}

    def cover_up(self, cover_path):
        self.cover_path = cover_path
        return "COVER_ID"

    def submit(self):
        return {"code": 0, "data": {"aid": 42, "bvid": "BVfake"}}

    def close(self):
        self.closed = True


fake_bili_module.Data = FakeData
fake_bili_module.BiliBili = FakeBiliBili

fake_bili_root = sys.modules.setdefault("biliup", types.ModuleType("biliup"))
if not hasattr(fake_bili_root, "__path__"):
    fake_bili_root.__path__ = []
fake_plugins_pkg = sys.modules.setdefault("biliup.plugins", types.ModuleType("biliup.plugins"))
setattr(fake_bili_root, "plugins", fake_plugins_pkg)
sys.modules["biliup.plugins.bili_webup"] = fake_bili_module
class FakeWbi:
    UPDATE_INTERVAL = 3600

    def __init__(self):
        self.key = "fake"
        self.last_update = 0

    def update_key(self, *_args):
        self.key = "fake"
        self.last_update = 0


fake_plugins_pkg.wbi = FakeWbi()


class FakeDanmakuBilibili:
    heartbeat = b""
    heartbeatInterval = 30
    headers = {"User-Agent": "test"}

    @staticmethod
    async def get_ws_info(_url, _content):
        return "wss://example.com/sub", [b"AUTH"]

    @staticmethod
    def decode_msg(_payload):
        return []


fake_danmaku_pkg = sys.modules.setdefault("biliup.Danmaku", types.ModuleType("biliup.Danmaku"))
if not hasattr(fake_danmaku_pkg, "__path__"):
    fake_danmaku_pkg.__path__ = []
fake_danmaku_module = types.ModuleType("biliup.Danmaku.bilibili")
fake_danmaku_module.Bilibili = FakeDanmakuBilibili
setattr(fake_danmaku_pkg, "bilibili", fake_danmaku_module)
sys.modules["biliup.Danmaku.bilibili"] = fake_danmaku_module
