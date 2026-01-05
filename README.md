DDRecorderV2
============

轻量的 B 站直播录播守护：检测 ➜ 录制（含弹幕）➜ 合并/分段 ➜ 上传。即开即用、可观测、易运维。  
致谢 **AsaChiri**（DDRecorder）开源版本，本项目在其基础上精简重构并持续维护。

---

## 核心特性
- 多线程 Runner：房间独立调度，自动检测开播、录制、处理、切分、上传。
- 弹幕录制：可选同步采集弹幕并压制到合并文件。
- 自动重试：录制/上传内置重试与失败标记；失败不会删除已有文件。
- 清理守护：默认 24h 清理一次，保留 7 天，带失败标记的目录跳过。
- 观测友好：主日志 + detect/record/process/upload 分阶段日志，FFmpeg 独立日志。

## 快速开始
```bash
git clone https://github.com/yuki1sntSnow/DDRecorderV2.git
cd DDRecorderV2
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 守护运行（默认读取 config/config.json）
python -m ddrecorder run -c config/config.json
# 手动录制（可选时长，遵循配置的 enable_danmu）
python -m ddrecorder record -c config/config.json --room-id 1234 --duration 300
# 处理/合并 flv 目录或文件（可带字幕）
python -m ddrecorder process -c config/config.json --source path/to/flv_dir --room-id 1234 --subtitle-path path/to/danmu.jsonl
# 切分 / 上传 / 清理
python -m ddrecorder split  -c config/config.json --target path/to/*_merged.mp4 --split-interval 1800
python -m ddrecorder upload -c config/config.json --path path/to/splits_dir --room-id 1234
python -m ddrecorder clean  -c config/config.json --retention 7
```

### CLI 子命令
- `run`：自动流水线，可附带 `--cleanup-interval` / `--cleanup-retention`。
- `record`：手动录制指定房间，支持 `--duration`。
- `process`：转封装+合并 flv，支持字幕压制。
- `split`：按间隔切分 merged。
- `upload`：上传分段目录。
- `clean`：按天数清理录制数据与日志。
- `dump-creds`：导出账号 Token/Cookies；`test`：运行 pytest。

## 配置速览
`config/config.json` 示例：
```json
{
  "root": {
    "check_interval": 60,
    "print_interval": 60,
    "data_path": "./",
    "logger": { "log_path": "./log", "log_level": "INFO" },
    "uploader": { "lines": "AUTO" },
    "danmu_ass": { "font": "Noto Sans CJK SC", "font_size": 45 },
    "account": { "default": { "username": "", "password": "", "cookies": {} } }
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
字段说明要点：
- `root.check_interval` / `print_interval`：轮询与状态打印间隔（秒）。
- `root.data_path`：数据根目录，自动创建 `data/records|merged|splits|danmu|merge_confs`。
- `root.logger.log_path`：日志目录。
- `root.danmu_ass.*`：弹幕转 ASS 样式。
- `root.account.*`：账号列表（可引用 cookies.json）。
- `spec[].recorder.keep_raw_record` / `enable_danmu`：是否保留原始 flv、是否录制弹幕。
- `spec[].uploader.record.*`: 上传开关、切分间隔、稿件模板、上传后是否保留文件。

更多字段见 `config/config.example.json`。

## 日志与目录
- 主日志：`log/DDRecorder_*.log`
- 阶段日志：`log/detect/record/process/upload/*.log`
- FFmpeg：`log/ffmpeg/ffmpeg_<slug>_*.log`
- 数据：`data/records` (flv) / `data/merged` (合并 mp4) / `data/splits` (分段) / `data/danmu` (弹幕 jsonl/ass) / `data/merge_confs` (concat 列表)

## 常见说明
- 手动/自动流程遇错会保留已生成文件（除“完全无片段”的录制），便于排查。
- 默认转封装/合并启用 `aac_adtstoasc`、`faststart`；字幕压制强制 `yuv420p`，提高兼容性。
- 清理任务仅按天数删除旧文件，带上传失败标记的目录跳过。

## 贡献与 Roadmap
- 运行 `python -m ddrecorder test -c config/config.json` 可执行现有测试。
- Roadmap：
  - 规避版权方案：特定区域马赛克或动态切片
  - 弹幕 NLP / 过滤
  - 弹幕用户名去马赛克

欢迎反馈和 PR，提出希望支持的场景 🚀
