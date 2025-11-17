DDRecorderV2
============

> 项目原始作者：**AsaChiri**（DDRecorder），感谢其开源的录播框架和思路；V2 在其基础上精简重构，继续服务 B 站直播录播用户。

> 面向 B 站直播的“检测 ➜ 录制 ➜ 合并 ➜ 分段 ➜ 上传”一体化守护程序，轻量且易运维。

---

## 为何做 V2？

- **专注主链路**：弱化 NLP、百度云等功能，核心只保留录制和投稿。
- **线程化调度**：每个直播间一个 `RoomRunner` 线程，结构直观，排障容易。
- **自动凭据更新**：配置缺少 token/cookies 时会调用旁边的 `BiliAuth.py` 自动登录并写回。
- **可观测性**：CLI 实时打印状态表，日志分级、轮询清理、失败目录打标等全部自带。
- **部署友好**：提供 `python -m ddrecorder` 单入口与 systemd 维护指南，内置定期清理。

---

## 功能总览

| 模块              | 功能要点                                                                 |
| ----------------- | ------------------------------------------------------------------------ |
| `ddrecorder.cli`  | 统一入口，支持守护、手动上传、一次性清理、pytest、自检                   |
| `RoomRunner`      | 检测开播、拉流、处理、上传、状态表输出，异常自动写日志                   |
| `RecordingProcessor` | 调用 FFmpeg 拼 TS、生成合并文件、自动转 ASS 并烧录字幕，按 `split_interval` 切分 |
| `BiliUploader`    | 调用 biliup 上传多 P，失败会在目录生成 `.upload_failed` 防止被清理        |
| `DanmuRecorder`   | 录制时并行拉取弹幕，仅保留用户弹幕，输出 jsonl 供 ASS/压制使用             |
| Cleanup Scheduler | 默认 24h 清理一次数据/日志，可通过 CLI 即时清理                         |
| Auto Refresh      | 调 BiliAuth 获取 access_token / cookies 并写回配置                       |

---

## 环境要求

- Python ≥ 3.10
- FFmpeg 命令可用
- Linux / macOS / Windows（部署示例以 Linux 为主）
- `pip install -r requirements.txt`（依赖 requests / ffmpeg-python / biliup 等）

---

## 安装步骤

```bash
cd /path/to
python -m venv DDRecorderV2/.venv
source DDRecorderV2/.venv/bin/activate      # Windows 使用 .venv\Scripts\activate
pip install -r DDRecorderV2/requirements.txt
```

> 若使用 systemd，请提前配置好虚拟环境路径。

---

## 配置说明

编辑 `config/config.json`（若放在 `config/` 目录，相对路径会自动提升到项目根 `DDRecorderV2/`）。示例：

```json
{
  "root": {
    "check_interval": 60,
    "print_interval": 60,
    "data_path": "./",
    "logger": { "log_path": "./log", "log_level": "INFO" },
    "uploader": { "lines": "AUTO" },
    "danmu_ass": {
      "font": "Microsoft YaHei",
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
        "cookies": {
          "SESSDATA": "",
          "bili_jct": "",
          "DedeUserID": "",
          "DedeUserID__ckMd5": "",
          "sid": ""
        }
      }
    }
  },
  "spec": [
    {
      "room_id": "12345",
      "recorder": { "keep_raw_record": false, "enable_danmu": false },
      "uploader": {
        "account": "default",
        "record": {
          "upload_record": true,
          "keep_record_after_upload": false,
          "split_interval": 3600,
          "title": "【{room_name}】{date}",
          "tid": 27,
          "tags": ["直播录播"],
          "desc": "",
          "cover": ""
        }
      }
    }
  ]
}
```

- `keep_raw_record`: 是否保留 flv 原片；`keep_record_after_upload`: 上传成功后是否保留 mp4；`enable_danmu`: 是否录制弹幕（需要登录信息，开启后会自动生成 ASS 并烧录到合并文件）。
- `danmu_ass`: 可选的弹幕样式配置（字体、字号、持续秒数、行数、纵向间距等），不设置时使用默认值。
- 账号字段：
  - `username` / `password` / `region`（可选）用于自动刷新 access_token / cookies；
  - `access_token` / `refresh_token` 可填已有凭据，也可留空等待运行时刷新；
  - `cookies` 必填，可通过 biliup-rs 或浏览器获取。
- 如需复用账号，可在 `root.account.<name>` 定义，再在 `spec[].uploader.account` 写名称。

---

## 常用命令

```bash
python -m ddrecorder                          # 常规守护（默认 config/config.json）
python -m ddrecorder --config other.json      # 指定配置
python -m ddrecorder --clean                  # 只执行一次清理
python -m ddrecorder --upload-path data/splits/123_2024-01-01_00-00-00 [--room-id 123]
python -m ddrecorder --run-tests              # 运行 pytest
```

参数速查：

```
--cleanup-interval HOURS   定期清理间隔（0 则关闭）
--cleanup-retention DAYS   清理保留天数
--upload-path DIR          手动上传目录（需包含 mp4 分段）
--room-id ROOM             与手动上传搭配指定房间号
```

> 运行时每 `print_interval` 秒在控制台输出状态表，展示房间 ID / 是否直播 / 当前阶段。

---

## 手动上传与清理策略

- `--upload-path`：复用配置里的账号，一次性上传目录内的分段；成功自动清除 `.upload_failed` 标记。
- 上传失败（包含异常）会在目录内生成 `.upload_failed`，清理器会跳过这些目录，避免误删。
- `--clean` 可用于 cron / systemd timer，例如：
  ```cron
  30 4 * * * /usr/bin/python /home/bot/DDRecorderV2 -m ddrecorder -c /home/bot/DDRecorderV2/config/config.json --clean >/dev/null 2>&1
  ```

### 手动集成测试

若想在本地验证“录制 + 弹幕”链路，可使用 `scripts/manual_flow.py`（默认读取 `config/test_config.json` 并强制开启弹幕），它会运行指定秒数然后停止 Runner：

```bash
source .venv/bin/activate
python -m scripts.manual_flow -c config/test_config.json -d 30
```

录制阶段结束后，再用 `scripts/process_session.py` 针对最新会话执行合并 + 弹幕压制 + 分段（不会走上传）：

```bash
python -m scripts.process_session --room 22508985 -c config/test_config.json
```

测试完成后可检查：

- `data/records/<房间_时间>/` 是否生成 flv 片段
- `data/danmu/<房间_时间>/danmu.jsonl` 是否记录弹幕
- `data/splits/`、`log/`、`log/ffmpeg/` 等目录内的输出与日志
- 如果开启自动上传，可在 `log/upload_*` 中查看投稿结果

弹幕 JSON 会写入 `data/danmu/<房间_时间>/danmu.jsonl`，只保留用户文字弹幕，便于后续转 ASS 或调试。

---

## 日志与观测

- 应用日志：`log/DDRecorder_*.log`；分阶段日志分为 detect / record / process / upload 四类，分别写入 `log/<stage>/info.log` 与 `log/<stage>/error.log`（带时间戳、线程、文件行号）。FFmpeg 日志位于 `log/ffmpeg/<room>_*.log`。
- 默认每 24 小时执行一次清理，删除 7 天前的日志/录制产物，可通过 `--cleanup-interval`/`--cleanup-retention` 调整，详见 [`MAINTENANCE.md`](./MAINTENANCE.md)。
- `journalctl -u ddrecorder -f` 可实时查看守护进程的输出；`tail -f log/DDRecorder_*.log` 看详细栈。

---

## 测试

```bash
cd DDRecorderV2
pytest   # 22 个用例覆盖配置、录制、处理、上传、清理、CLI 等
```

---

## 运维速查表

1. **systemd**：配置 unit 后 `sudo systemctl enable --now ddrecorder`、`systemctl status ddrecorder`。
2. **日志清理**：内置定时清理（默认 24h 一次，保留 7 天）；可在 CLI 中调整参数或手动运行 `python -m ddrecorder --clean --cleanup-retention <天数>`。
3. **配置变更**：修改 `config/config.json` 后 `sudo systemctl restart ddrecorder`。
4. **磁盘巡检**：`du -sh data/*`, `du -sh log`。
5. **手动上传/清理**：见上一节 CLI 命令。

---

## 更新日志

### 2025-11-13

- 新增 `DanmuRecorder`：录制过程中并行拉取弹幕，过滤非用户内容，只保留 `uid/uname/text` 并写入 `data/danmu/<slug>/danmu.jsonl`。
- 合并阶段引入 `jsonl_to_ass`，自动把弹幕转换为 ASS 并通过 FFmpeg 烧录到最终 MP4；新增 `root.danmu_ass` 配置允许覆盖分辨率、字体（默认加大到 45px）、行数、飘屏距离等。
- 提供 `scripts/manual_flow`（限定运行秒数的 Runner）与 `scripts/process_session`（针对单个会话执行合并/切分）方便阶段性验证和补录。
- 日志体系改进：阶段日志 handler `delay=True`，FFmpeg 日志初始化受保护，`scripts.process_session` 会主动配置 logging，避免空日志文件。
- pytest 覆盖新增弹幕/ASS/处理链路，所有用例默认传入 `DanmuAssConfig`，确保配置缺省也能安全运行。

---

## Roadmap

- [ ] 多平台直播源（Douyu / Twitch / YouTube）
- [ ] Runner 状态导出 Prometheus 指标
- [ ] Webhook / PushPlus 等通知
- [x] **弹幕采集 + 压制**：录制阶段并行拉取弹幕，生成与时间轴对齐的 ASS，合并阶段直接用 FFmpeg 烧录（已上线，可通过 `root.danmu_ass` 自定义样式）
- [ ] **规避版权方案**：马赛克特定区域，或非固定数值切片分割

如有建议或想法，欢迎 Issue / PR！

> 本文档由 AI 辅助生成并通过人工审阅。
