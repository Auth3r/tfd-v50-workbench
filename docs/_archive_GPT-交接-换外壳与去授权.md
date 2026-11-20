# 交接 · 换外壳 + 去授权（不碰内核）

读者：`F:\Codex\TFD\rewrite` / `F:\Codex\tfd-offline-2` 的作者
目标：**只换外壳（UI / 授权提示 / 广告），保留现已跑通的启动链与注入桥（`client.dll` 继续用）。**

**阅读顺序**（两份文档各管一半，别混着看）：
1. 先读 `docs/GPT-交接-SYNC.md` → 搞清“客户端为什么必须被启动器驱动、为什么裸启 15 秒自退、最早兼容边界 `procedure 1 → 2010 → 30004`”。**这是能不能连上的前提。**
2. 再读本文件 → 搞清“外壳换成我们自己的、授权和广告怎么不出现”。

**分工一句话**：SYNC 管**连接**，本文件管**界面**。先连接，再界面。

---

## 0. 一句话

外壳可以完全自己做，**授权和广告都是外壳层的**；内核（`unpacked/client.dll`）暂时留着，因为启动链必须靠它。
我们已验证的 7 个旁路点，照抄即可，不需要重新逆向授权。

---

## 1. 授权链由哪些东西组成（实测）

| 组件 | 位置 | 作用 | 能否绕 |
|---|---|---|---|
`license_core` / `license_format` / `license_public` | 编译在 `client.dll` | Ed25519 验签 + 机器绑定 | 绕，见 §2 |
`device.dpapi`（262 B，三份副本） | `data/launcher/licensing/`、`data/licensing/`、`licensing/` | DPAPI 机器信封 | 删（换机解不开） |
`keygen.key`（64 B） | `%LOCALAPPDATA%\TFD-Offline\` | 本机生成的密钥 | 保留 |
`branding.json`（314 B，带签名） | `data/launcher/licensing/` | 广告来源（`group:"1131987001"` 是 QQ 群号） | **不要改数字**，签名会失效；改行为即可 |
`guard_ui.json` | `%LOCALAPPDATA%\TFD-Offline\` | 授权/守卫界面状态 | 随外壳一起消失 |

**结论**：所谓“每次要授权”，本质是 `LicenseClient.validate_local / connection_check / renew / request` 这条链在每次启动时跑一遍。它在外壳里，不在游戏里。

---

## 2. 我们已验证的 7 个旁路点（`patch_v50.py`，直接对照行号）

| # | 行号 | 做了什么 |
|---|---|---|
1 | 1410–1413 | `LicenseClient.validate_local / connection_check / renew / request` 全部改 no-op，`request` 直接回 `{'ok': True}` |
2 | 1416–1430 | `fetch_branding` 改为**离线**：不联网，`cached_branding/branding/_branding` 置空 → 广告数据不再刷新 |
3 | 1432–1433 | `is_trial` 恒 False，`trial_remaining` 恒 0 → 不再显示试用提示 |
4 | 1546–1556 | `restore / import_session / runtime_session` 返回**预置的假 auth**（`authorized:True` + 本地 ticket） → 不再走登录/授权窗 |
5 | 217–258 | `_quarantine_vaults` + `_make_client`：DPAPI 读不了就把旧凭据改名 `.vendor.bak` 再重建 → 换机不炸 |
6 | 141 / 152 / 169 | 启动后按窗口标题枚举，命中弹窗就 `PostMessageW(hwnd, WM_CLOSE)`；客户端 stdout/stderr 落盘 |
7 | 1602 | `LR.run(cfg, stop, visible=True)` —— 真正把运行时跑起来的那一句 |

**对 GPT 的要求**：新外壳不要重写这些逻辑，直接**复制**这 7 段，改成从你的入口调用。

---

## 3. 三条路线（按成本排序）

### 路线 A：保留现壳，只做“零提示”（0.5 天）

在现有 `启动V50（免授权）.cmd` 里把 patch 的旁路全部前置，并加强关窗：

- 启动前删掉三份 `device.dpapi`（或交给 `_quarantine_vaults`）；
- 启动后 3 秒内轮询枚举窗口，命中 `授权/激活/试用/公告/交流群` 等标题直接 `WM_CLOSE`；
- 结果：你不再看到授权框和广告框，但启动器还是它的 Tk 界面（能看到但一闪而过）。

**限制**：治标。窗口仍会闪一下，且依赖窗口标题匹配（标题换词就漏）。

### 路线 B：自研薄壳（推荐）—— 分 B1 / B2 两步走

**目标**：用户**不再看到 V50 的任何界面**（授权框、广告框、Tk 主窗）。
**注意**：`client.dll` 要留着；要换掉的只是 `TFDLauncher.exe` 的**界面层**。

#### B1（稳，约 1 天）—— 壳自己做，后台仍留一个无窗口的 `TFDLauncher.exe`

```
<你的壳>.py（UI + 编排，你自己的）
  ├─ 复制 patch 的 §2 七段（授权旁路 + 关窗 + Popen 接管 + client 流落盘）
  ├─ 启动 TFDLauncher.exe，立刻隐藏主窗（SW_HIDE / 最小化）
  ├─ 3 秒内轮询枚举窗口，命中“授权/激活/试用/公告/交流群/TFD”就 WM_CLOSE
  ├─ 读 client.txt → 校验 M1-Win64-Shipping.exe 存在
  ├─ 桥走 bridge_override.txt → offset_rework/old_bridge_v30_bt.js
  └─ 显示“启动/停止/日志/退出”四件事就够了
```

代价：任务管理器里还有一个 `TFDLauncher.exe` 进程（无窗口）。**这是目前唯一有把握的形态。**

#### B2（未验证，去掉那个进程）—— 纯 `python314 + client.dll`

```
<你的壳>.py
  ├─ 不启 TFDLauncher.exe
  ├─ sys.path 指向 <RUNTIME>\unpacked，直接 import client.dll 里的模块
  ├─ 同样复制 §2 七段
  └─ LR.run(cfg, stop, visible=?)
```

**风险（写给你，不要当成你的 bug）**：`client.dll` 是 Nuitka 编译的**主程序模块**，通常不能被外部 Python 进程当普通模块 import，会在初始化顺序/入口依赖上失败。**这条路径我们没有验证过。** 若 import 失败，退回 B1，不要在这里耗时间。

#### 共用要点

1. **`visible` 参数要实测**：`visible=True` 是我们验证过的；`False` 是否等价于“无 UI”**未验证**，别假设。
2. **不要去掉 `client.dll`**：`LR.run` 来自它。外壳只是换了“谁来调用”。
3. **日志必须留**：`events.jsonl` + `patch_v50.log` + `client_out.log` 三份。
4. **首次运行要校验**：`bridge_ready ≤2s`、`native_title_creation_error` 出现、`native_account_loaded ≈24s`。
5. **顺序**：先把 B1 做到验收表全绿，再碰 B2。**B2 失败不影响 B1 交付。**

### 路线 C：连 `client.dll` 一起换（2–4 周，不推荐现在做）

前提是 GPW 已经能接住 `procedure 1 / 2010 / 30004`（见 SYNC 文档 §4），否则会出现“壳换了、游戏也拉起来了、依然零入站”。风险点：`launcherAuthentication` 与授权链耦合，摘掉内核后要自己补。

---

## 4. 验收标准（B1 必过；全绿之后再谈 B2）

| # | 检查 | 判据 |
|---|---|---|
1 | 无授权提示 | 启动到标题页全程无“授权/激活/试用”窗口 |
2 | 无广告 | 无 `group:1131987001` 相关弹窗、无联网请求 |
3 | 无 V50 界面 | 用户视野内不出现任何 Tk 主窗/弹窗（B1 允许后台进程存在） |
4 | 能出画面 | `native_title_creation_error` 出现，`native_account_loaded` 24.x |
5 | 能创角 | 创角页可交互，提交后**本轮不退出**（`created=false` 导致 exit 3 是另一个 bug，见 SYNC §8） |
6 | 可回滚 | 一条命令切回 `启动V50（免授权）.cmd` |

---

## 5. 回滚方案（必须写进壳里）

```
壳启动前：备份 data/launcher/launcher-settings.json → .shell-bak
壳退出时：恢复 settings，删除自己生成的临时 ticket
回滚命令：直接跑原 启动V50（免授权）.cmd（不依赖新壳任何文件）
```

---

## 6. 别做的事

- **不要改 `branding.json` 里的数字**（Ed25519 签名，改了就验签失败，可能反而弹错）；
- **不要指望删 `client.dll` 就“更干净”**（它同时是服务端和启动链驱动）；
- **不要把 `visible=False` 当成“一定无 UI”**（未验证，先测）；
- **不要用 `print` 调试**（启动器进程 stdout 是 DEVNULL 历史包袱，用文件日志）；
- **不要在壳里直连游戏**（`Popen(M1-Win64-Shipping.exe)` = 15 秒自退，已验证）。
