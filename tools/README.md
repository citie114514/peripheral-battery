# tools —— 逆向 / 验证用的小脚本

不是运行时依赖，留着方便以后加设备时复用同一套流程。

## 枚举与嗅探
| 脚本 | 作用 |
|---|---|
| `hid_probe.py` | 列出所有 HID 接口：VID/PID、usage page、报文长度、产品名 |
| `desc.py` | 打印某个设备的 report descriptor 与 report id 布局（`python desc.py 362d:d028`） |
| `sniff.py` | 被动监听厂商接口的输入报文（不写任何东西），确认设备会不会自己广播 |
| `win_list.py` | 列出某个进程的窗口（类名/标题/尺寸/是否可见），排查 pywebview 窗口问题 |

## 协议探针
| 脚本 | 作用 |
|---|---|
| `probe1k.py` | 通用重叠 I/O 句柄封装（`Chan`），其它探针都 import 它 |
| `mouse_battery.py` | 贱驴 RSR5S 的最小可运行示例：`B3 06` → 载荷[19] = 电量 |
| `probe_rdr.py` | PMO P75 的 RDR 帧试发（`AA cmd off len`），看哪个通道有回应 |
| `probe_rdr11.py` | 耐心版：两个接口 × 6 次重试，专门用来抓「键盘醒着」那一刻 |

## 抓官方驱动的报文（PMOHub = Electron + WebHID）
| 脚本 | 作用 |
|---|---|
| `cdp_client.py` | 极简 CDP-over-WebSocket 客户端（纯标准库） |
| `hook_pmo.py` | 带 `--remote-debugging-port` 启动 PMOHub，注入 `HIDDevice.prototype` 钩子，把收发帧打出来 |
| `watch_pmo.py` | 同上但常驻写文件：`python tools\watch_pmo.py`，然后正常用键盘打字，日志落 `download\pmo_watch.log` |

## 拆 Electron 的 app.asar
| 脚本 | 作用 |
|---|---|
| `asar_extract.py` | 解包 asar（`python asar_extract.py app.asar outdir`，加第三个参数只列文件） |
| `asar_scan.py` | 直接在二进制里找 VID/PID/产品名字符串 |
| `grep_js.py` / `js_window.py` | 在压缩过的 JS 里按关键词定位，并把窗口附近的代码粗略美化 |
| `tree_grep.py` / `file_window.py` | 整目录搜索 / 单文件取上下文（都写 utf-8 文件，避开控制台编码问题） |
| `db_peek.py` | 看 PMOHub 的 sqlite 配置库 |

## 界面 / 图标验证
| 脚本 | 作用 |
|---|---|
| `make_ico.py` | 用图标绘制代码导出多尺寸 `app.ico` |
| `tray_zoom.py` | 把任务栏托盘区截下来放大 4 倍，肉眼看图标 |
| `grab_now.py` | 按标题抓当前窗口（DPI 感知，先抢前台再 BitBlt） |
| `capture_web.py` | 启动应用 + 截屏一条龙 |
| `ui_verify.py` | 不开屏幕也能验证界面：注入一份假状态，读回 DOM 文本断言 |
