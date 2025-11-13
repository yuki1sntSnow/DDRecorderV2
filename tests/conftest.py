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
sys.modules.setdefault("biliup", types.ModuleType("biliup"))
sys.modules.setdefault("biliup.plugins", types.ModuleType("biliup.plugins"))
sys.modules["biliup.plugins.bili_webup"] = fake_bili_module
