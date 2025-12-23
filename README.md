DDRecorderV2
============

轻量的 B 站直播录播守护：检测 ➜ 录制（含弹幕）➜ 合并/分段 ➜ 上传。即开即用、可观测、易运维。

> 致谢 **AsaChiri**（DDRecorder） 的原始开源版本；V2 在其基础上精简重构并持续维护。

---

## 特性

- 多线程 Runner：房间独立调度，自动检测开播、录制、处理、上传。
- 弹幕支持：实时采集、生成 ASS，合并时可直接压制到 MP4。
- 内置清理：默认 24h 清理，保留 7 天，失败目录自动打标跳过。
- 观测友好：主日志 + detect/record/process/upload 阶段日志；FFmpeg 日志默认精简。
- 运维友好：单入口 `python -m ddrecorder`，支持手动上传、自检、一次性清理。

---

## 快速开始

```bash
git clone https://github.com/yuki1sntSnow/DDRecorderV2.git
cd DDRecorderV2
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ddrecorder                      # 使用 config/config.json 守护运行
python -m ddrecorder --clean              # 只执行一次清理
python -m ddrecorder --split-path data/merged/<room>_<time>_merged.mp4 [--split-interval 3600] [--room-id <room>]
python -m ddrecorder --upload-path data/splits/<room>_<time> [--room-id <room>]
```

常用参数：`--config` 指定配置；`--cleanup-interval/--cleanup-retention` 调整清理；`--run-tests` 运行 pytest。

---

## 配置示例

编辑 `config/config.json`（可放项目根或 `config/` 下）：

```json
{
  "root": {
    "check_interval": 60,
    "print_interval": 60,
    "data_path": "./",
    "logger": { "log_path": "./log", "log_level": "INFO" },
    "uploader": { "lines": "AUTO" },
    "danmu_ass": {
      "font": "Noto Sans CJK SC",
      "font_size": 45,
      "duration": 6,
      "row_count": 12,
      "line_height": 40,
      "margin_top": 60,
      "scroll_end": -200
    },
    "account": {
      "default": {
        "username": "YOUR_USERNAME",
        "password": "YOUR_PASSWORD",
        "region": "86",
        "access_token": "",
        "refresh_token": "",
        "cookies": {}
      }
    }
  },
  "spec": [
    {
      "room_id": "12345",
      "recorder": { "keep_raw_record": false, "enable_danmu": true },
      "uploader": {
        "account": "default",
        "record": {
          "upload_record": true,
          "keep_record_after_upload": false,
          "split_interval": 3600,
          "title": "【直播录播】{date}",
          "tid": 27,
          "tags": ["直播录播"]
        }
      }
    }
  ]
}
```

- `enable_danmu`: 采集弹幕并生成 ASS，合并时自动压制到视频。
- `keep_raw_record` / `keep_record_after_upload`: 控制是否保留 flv/mp4。
- 账号可配置多份：在 `root.account.<name>` 定义，在 `spec[].uploader.account` 填名称复用。
- 字体：Linux 默认使用 `Noto Sans CJK SC`，如需 Emoji 建议安装 `fonts-noto-cjk`、`fonts-noto-color-emoji` 并按需修改 `danmu_ass.font`。

更详细字段说明见 `config/config.example.json`。

---

## 日志与观测

- 主日志：`log/DDRecorder_*.log`
- 阶段：`log/detect/detect.log`, `log/record/record.log`, `log/process/process.log`, `log/upload/upload.log`（时间戳+线程+文件行号）
- FFmpeg：默认仅错误/警告，文件在 `log/ffmpeg/<room>_*.log`；需要详细进度设 `DDRECORDER_FFMPEG_VERBOSE=1`
- 清理：内置定时清理（默认 24h/保留 7 天），可用 `--clean` 手动触发
- 凭据导出：`python -m ddrecorder --dump-credentials [--config <path>] [--account <name>]` 将 Token/Cookies 保存到配置目录的 `cookies.json`（请确保 root.account 中已填写用户名/密码或可用的登录方式）

运维：推荐配合 systemd；`journalctl -u ddrecorder -f` 实时查看。

---

## 贡献与反馈

- 运行 `pytest` 查看现有用例覆盖配置、录制、处理、上传、清理等。
- 遇到问题或有需求，欢迎提交 Issue / PR。

Roadmap:
- [ ] **规避版权方案**：马赛克特定区域，或非固定数值切片分割
- [ ] **弹幕 NLP / 过滤**：基于结构化弹幕做语义分析/屏蔽
- [ ] **弹幕用户名去马赛克**：提升弹幕用户名还原能力（对接更完整字段或请求）

欢迎提出希望支持的场景 🚀

> 本文档由 AI 辅助生成。
