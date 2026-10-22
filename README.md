# 外设电量 · 贱驴 RSR5S + PMO P75

> **只适配这两台设备，别的设备不会自己认出来。**
>
> | 设备 | 走哪个接收器 |
> |---|---|
> | 贱驴 James Donkey **RSR5S**（2.4G） | Ultra-Link 8K 接收器 `362D:D028` |
> | PMO **P75**（2.4G / 有线） | RDR 2.4G 接收器 `36B0:3002`（有线时是 `36B0:302B`） |
>
> 换设备需要照 `protocols.py` 里的结构自己加一条（接口 usage page + 请求帧 + 回复里电量的下标）。

一个常驻托盘的小工具：直读 2.4G 接收器拿电量，不经过官方驱动。
界面是 WebView2 渲染的 HTML/CSS（暖纸色、衬线大标题、细线刻度），
托盘图标是“小卡片 + 数字 + 电量条”，跟随任务栏明暗。

**灵感与起点**：[yszyszysz233/2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer)
里那份可复用 Prompt（枚举 HID → 抓包 → 逆协议 → 做托盘/面板 → 避开那些坑）。
方法论几乎照搬，只把设备换成桌上这两台，界面从 tkinter 换成了 WebView2 + HTML/CSS。

## 直接双击用

```
dist\外设电量\外设电量.exe
```

桌面已有快捷方式「外设电量」。首次启动约 2 秒（要起 WebView2）。

- **点窗口右上角的 X**：收进托盘，不退出（后台继续刷新）
- **左键点托盘图标**：把窗口调回来
- **右键点托盘图标**：菜单 —— 打开面板 / 立即刷新 / 开机自启（勾选）/ 退出
- **开机自启**：已默认开启（启动文件夹里的 `外设电量.lnk` → exe），
  在托盘菜单或界面里都能随时开关
- 托盘图标本体就是电量：小卡片 + 数字 + 底部电量条（充电时条变橙）
- 鼠标悬停托盘图标：`余量 · 贱驴 RSR5S · 90%`
- 彻底退出：右键托盘 → 退出，或界面右下角「退出」

## 从源码跑

```bash
pip install pywebview pythonnet        # 只有界面需要，读电量只用标准库
python periph_battery.py               # 常驻（托盘 + 窗口）
python periph_battery.py --once        # 命令行读一次
python periph_battery.py --panel       # 只要窗口，不要托盘
python periph_battery.py --install     # 建桌面快捷方式
python periph_battery.py --autostart on|off
```

重新打包：

```powershell
powershell -File build.ps1
```

## 协议（都是实测出来的）

只给这两台写死了协议，不认识的设备直接跳过（不会乱猜、不会去碰鼠标键盘的顶层集合）。

### 贱驴 RSR5S（Ultra-Link 8K 接收器 `362D:D028`）

- 接口 usage page **0xFFC1**，64 字节报文
- 请求 `B3 06 00 …`（载荷首字节 `0x06`）
- 回复 report id `B4`、载荷 `[0]==0x06`，**载荷[19]** 低 7 位 = 电量%，最高位 = 充电
- 顺带：载荷[18] 休眠分钟、载荷[2..4] DPI 档位
- 实测连续三读稳定（91%，未充电）

### PMO P75（RDR 2.4G 接收器 `36B0:3002`）

- RDR 帧：`[rid, 0xAA, cmd, offLo, offHi, len, …]`
- `0x10` 开始通讯 / `0x12` 设备信息 / `0x30` 电池 / `0x11` 结束通讯
- 回复 `0x55` = 成功，数据从第 8 字节起：`data[8]` 电量、`data[9]` 充电
- 实现照抄 PMOHub 的 `RDRComm`（`CMD_GET_BATTERY_STATUS = 48`）

**现状（实测，别被驱动截图骗了）**：

- 驱动里显示 `93%` 是真的——但那是**键盘醒着那一刻**读到的。
- 键盘一旦休眠（它默认就 10 分钟级别），接收器对 `0x10/0x12/0x30` 就**完全不回**，
  只留一个状态广播：
  ```
  0xFF60: AA D0 00 00 18 00 00 00 | 01 B0 36 2B 30 02   ← 最后一个字节随状态变（02/05）
  0xFF00: AA C0 00 80 01 00 06 47 | B0 36 2B 30 02      ← 固定应答，不带电量
  ```
- PMOHub 自己也会卡在首页报「无法识别蓝牙模式」——说明它也是同样在等键盘醒。
- 所以本工具的做法：键盘读不到就 **每 15 秒重试一次**（每次把电池指令重发 3 遍 +
  一次完整握手），键盘一醒、或者你按一下键，下一次轮询就能抓到。

还读不到就手动抓一次：

```bash
python tools\watch_pmo.py        # 挂上 PMOHub 的钩子开始记录
```

然后用键盘正常打字 1~2 分钟，日志会落在 `download\pmo_watch.log`，
里面会包含官方驱动真正发的帧（现在拿到的是空的，因为键盘在睡）。

其他排查顺序：确认在 2.4G 模式（不是蓝牙/关机）；或插 USB 线
（有线模式 pid `302B`，代码里 `alt` 列表已包含 P75/PMO80/Aurora80/WAVE75）。

## 结构

| 文件 | 作用 |
|---|---|
| `periph_battery.py` | 入口：托盘线程、配置、开机自启、快捷方式、`--once` |
| `webapp.py` | WebView2 窗口 + JS↔Python 桥 |
| `ui/index.html` | 界面（HTML+CSS+JS，动效都在这里） |
| `hidlib.py` | ctypes HID 层（枚举 / 重叠 I/O） |
| `protocols.py` | 两台设备的电量协议 |
| `icons.py` | 托盘图标（GDI 双通道：蒙版 + 彩色 → 降采样，圆角透明） |
| `build.ps1` | 打包脚本 |
| `tools/` | 逆向与验证用的小脚本 |

## 几个坑（写下来免得重踩）

- HID 读写全部走 `FILE_FLAG_OVERLAPPED` + 事件超时 + `CancelIoEx`，
  绝不在同一句柄上「阻塞读 + 并发写」。
- 托盘图标只能 `NIM_MODIFY` 更新；`NIM_DELETE` 之后必须 `NIM_ADD` 才能回来。
- 销毁托盘窗口要 `PostQuitMessage(0)`，否则窗口没了图标也没了、进程还活着。
- pywebview 会把 js_api 对象上的**公开属性**也当桥暴露出去，
  内部状态必须全加下划线，否则它会去递归 introspection 一个 Window 对象，
  触发 COM 递归爆栈（`window.native.AccessibilityObject.Bounds.Empty.Empty…`）。
- WebView2 有 UI 线程限制：后台线程不要调 `window.evaluate_js`，
  改成前端 600ms 轮询 `api.state()`。
- PyInstaller 的 `--onefile` 会让 pywebview 起不来（窗口 0×0），
  所以用 `--onedir`，并把 `webview/lib` 显式 `--add-data` 进去。
- 两个进程抢同一个 pywebview 窗口时，量到的窗口尺寸会互相干扰（排查时先
  `Get-Process python | Stop-Process` 清干净，否则会以为窗口只有 158×26）。
