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
- **部署友好**：提供 `python -m ddrecorder` 单入口、systemd + logrotate 维护文档。

---

## 功能总览

| 模块              | 功能要点                                                                 |
| ----------------- | ------------------------------------------------------------------------ |
| `ddrecorder.cli`  | 统一入口，支持守护、手动上传、一次性清理、pytest、自检                   |
| `RoomRunner`      | 检测开播、拉流、处理、上传、状态表输出，异常自动写日志                   |
| `RecordingProcessor` | 调用 FFmpeg 拼 TS、生成合并文件、按 `split_interval` 切分               |
| `BiliUploader`    | 调用 biliup 上传多 P，失败会在目录生成 `.upload_failed` 防止被清理        |
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
    "uploader": { "lines": "AUTO" }
  },
  "spec": [
    {
      "room_id": "12345",
      "recorder": { "keep_raw_record": false },
      "uploader": {
        "account": {
          "username": "YOUR_USERNAME",
          "password": "YOUR_PASSWORD",
          "region": "86",
          "cookies": {
            "SESSDATA": "",
            "bili_jct": "",
            "DedeUserID": "",
            "DedeUserID__ckMd5": "",
            "sid": ""
          }
        },
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

- `keep_raw_record: false`：TS 合并后删除原始 flv
- `keep_record_after_upload: false`：上传成功即删除 mp4 分段
- 自动凭据：缺少 token/cookies 会调用 `BiliAuth.py` 模拟登录

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

---

## 日志与观测

- 应用日志：`log/DDRecorder_*.log`（同时输出到 stdout）。
- 建议结合 systemd + logrotate，详见 [`MAINTENANCE.md`](./MAINTENANCE.md)。
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
2. **logrotate**：`/etc/logrotate.d/ddrecorder` 轮换 `log/*.log`。
3. **配置变更**：修改 `config/config.json` 后 `sudo systemctl restart ddrecorder`。
4. **磁盘巡检**：`du -sh data/*`, `du -sh log`。
5. **手动上传/清理**：见上一节 CLI 命令。

---

## Roadmap

- [ ] 多平台直播源（Douyu / Twitch / YouTube）
- [ ] Runner 状态导出 Prometheus 指标
- [ ] Webhook / PushPlus 等通知
- [ ] **弹幕采集 + 压制**：录制阶段并行拉取弹幕，生成与时间轴对齐的 ASS，合并阶段直接用 FFmpeg 烧录（无需复杂特效/限流，可全屏飘过，保持与 V1 `ts→mp4` 处理一致）
- [ ] **规避版权方案**：马赛克特定区域，或非固定数值切片分割

如有建议或想法，欢迎 Issue / PR！

> 本文档由 AI 辅助生成并通过人工审阅。
