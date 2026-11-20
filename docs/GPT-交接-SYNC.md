# 给 GPW 自研服务端 · 交接答复（2026-11-20）

读者：`F:\Codex\tfd-offline-2`（Rust 原型）+ `F:\Codex\TFD\rewrite`（Python 启动器）的作者/评审方
来源：本机 V50 工作台实测（GitHub `Auth3r/tfd-v50-workbench`，分支 `feat/auto-drive`，HEAD `6854546`）

> **配套文档**：`docs/GPT-交接-外壳与编排.md` —— 讲“界面层换成我们自己的、启动提示与推广窗口怎么不出现”。
> **分工**：本文件管**连接**（能不能进游戏），那份管**界面**。先连接，再界面。

---

## 0. 先说结论：你们卡的不是协议，是启动链

你们的包里已经有的东西比交接文档描述的更多：

- `rust/protocol.rs`：`0x7fff` 明文 / XOR 两种 transport、signed 变长整数、帧头布局常量（见 `rust/protocol.rs`）（signed32 request_id + signed16 procedure）；
- `rust/game_ingress.rs`：`30001` 握手、`procedure 1` 登录、`1003` 应答、30004 心跳路径；
- `rust/launch.rs:115`：`-LoginIP=127.0.0.1 -LoginPort=<port>`。

也就是说**帧层和登录层你们是有的**，但“真实客户端零入站”。原因不在协议，而在启动方式：

> **裸启 `M1-Win64-Shipping.exe`（哪怕参数正确）会在约 15 秒内自退，连不上任何端口。**

本机已实测确认（多次、可复现）。新版客户端在连接登录服之前，必须完成一串启动回调：平台配置（`local_platform_config`）、`launcherAuthentication`、标题创建等待（`native_title_creation_error` 之所以出现的前提）。这些回调由发布端运行时（`TFDLauncher.exe` + `unpacked/client.dll`）驱动；发布端一关，它们不会发生，客户端就在“初始化”阶段退出——这正是你们的“零入站”。（回调的精确地址见仓库内部文档，本文件不写地址。）

---

## 1. 我们掌握的可工作路径针对哪个 Build

| 项 | 值 |
|---|---|
| 新版客户端 | Build **26722146**，`M1-Win64-Shipping.exe` 228,682,760 B，sha256 `a601a30da965e1b0e7826ba52b957173f47ab41bb29273611cbc4c4ca95ce316` |
| 旧版客户端 | Build **26263743**，sha256 前缀 `c0147688`（原厂桥只对这条有效） |
| 启动器 | `TFDLauncher.exe` 111,265,055 B（sha256 `8226014c…`），`unpacked/client.dll` 28,953,600 B（`a14c1d64…`） |
| 内容表 | `unpacked/assets/content.sealed` 22,001,501 B（`3367a888…`） |

判定口径：`result.json.source_sha256` 前 16 位 `a601a30da965e1b0`。

---

## 2. 发布端关闭时，游戏靠什么“受支持的方式”选服务

**没有单独可用的受支持开关。** `-LoginIP/-LoginPort` 是真的，旧版离线私服也用（见《TFD-Offline 分析报告》§4），但它只解决“连哪里”，不解决“能不能活到连接那一步”。

我们目前可工作的组合（唯一验证过的）：

```
本地启动脚本（仓库根目录，文件名见 README）
  → TFDLauncher.exe（本机回环登录/会话服务 + 本地会话初始化）
  → 拉起 M1-Win64-Shipping.exe
  → 加载兼容桥（offset_rework/old_bridge_v30_bt.js，102,995 B）
  → 桥在游戏线程补上平台配置 / 标题创建 / 账号 load 三个回调
  → 客户端进入标题页，正常发起 ClientService 请求
```

**桥不是第三方程序，是启动链的一部分**：它补的正是发布端在本机被本地替代后缺失的那几个启动回调。少了它，客户端即使在跑，也停在黑屏（`native_title_creation_error` 永不出现）——这是黑屏的根因，我们已单独写过报告。

---

## 3. 区分“未采用地址 / 初始化提前退出 / 连接失败”的三条诊断

都非敏感、纯本机观测：

| 现象组合 | 判定 | 观察点 |
|---|---|---|
| 游戏进程存活 >60s，服务端 accept 计数 = 0 | **未采用地址**（或客户端根本没到连接阶段） | `Get-NetTCPConnection -OwningProcess <gamePid>`；服务端 accept 计数 |
| 进程在 ≤15s 内消失 | **初始化提前退出** | 进程退出码；`%LOCALAPPDATA%\M1\Saved\Logs\M1.log` 行数（我们这边只有 3 行就是典型） |
| accept > 0 但立刻 close / 帧解析失败 | **连接失败** | 首帧 `request_id` + `procedure`；我们的 `handshake_accepted` / `connection_rejected` 事件 |

我们判“进没进”的两个硬指标，可以直接借：

- `native_title_creation_error` **出现** = 标题建成、可交互；**不出现** = 黑屏局；
- `native_account_loaded` 的时间：正常 24.x 秒，黑屏局 34–41 秒。

---

## 4. 最早可独立验证的兼容边界

按依赖顺序，**只做这三条**就能自证“真实客户端能连上我”：

1. `ClientService procedure 1`（登录）：请求体 → 应答（你们 `login_wire.rs` 已有 1003 编码）；
2. `procedure 2010`（`client_state`）：客户端状态确认；
3. `procedure 30004`（心跳，每 5 秒一次，body 0 字节，`frame_mode 0x7fff`）。

跑到这里，判定标准是：**客户端停在标题页并持续发 30004，30 秒不退出**。

> 注意：`20000` 是聚合过程，不是单条业务；它内部按顺序串 `2201 → 123 → 3100 → 3400 → 1558 → 124 → 3201 → 1702 → 1705 → 1708 → 3651 → 3801`（进主城时）。我们的经验是：**`20000` 里任何一条应答体长度不对，整条连接被判 `truncated payload` 直接断**（`3801` 就缺 4 字节 i32）。所以别先做 `20000`。

---

## 5. 账号与存档：用哪个接口传，怎么断言“用的是旧档”

推荐边界：

```
launcher 侧：account_uid（32 hex）+ 只读存档副本路径
server 侧：session ticket（32 字节随机）绑定 account_uid
```

- **只读副本**：启动时把旧档 `characters.sqlite3` 复制到工作目录（copy-on-read），服务端只打开副本，永不写原档；
- **传递点**：登录应答里带 `session_token`，之后所有业务请求用 ticket 反查 `account_uid`；
- **断言（必须写进测试）**：
  1. `account_snapshot` 里 `CharacterList[0].CharacterTid` == 旧档 `characters.tid`；
  2. `SelectedCharacter` == 旧档 `account_character_selection.character_uid`；
  3. 旧档 `characters.updated_at` 与快照里的 `UpdatedAt` 一致；
  4. 原型默认角色（你们 2 级示例）的 tid 不得出现在快照里——出现即测试失败。

我们这边的对应表名（旧版真档结构，可直接对照）：`characters` / `account_character_selection` / `account_mastery` / `account_world_state` / `account_collections`(14 键) / `account_currencies`。

---

## 6. 只允许改一处：改 `launch.rs` 的启动方式

不要把精力再放在协议上。**先改启动**：

```
现状：launch.rs 直接 Popen(M1-Win64-Shipping.exe, -LoginIP=..., -LoginPort=...)
改为：经本地启动器启动（TFDLauncher.exe + 兼容桥），
      自研服务端只接管“内容层”，不接管启动链
```

观察点与判据：

| 观察点 | 通过判据 |
|---|---|
| 客户端进程存活 | >60s，且 `M1.log` 行数 > 100 |
| 服务端 accept | ≥1，首帧 `procedure = 1` |
| 标题 | 客户端出现标题页（我们靠 `native_title_creation_error` 判定） |
| 心跳 | 30004 每 5s 一条，连续 6 条 |

**这一条不改，后面所有协议工作都无法被验证**——这也是你们“零入站”的直接原因。

---

## 7. 分工建议：不要“换掉 V50”，而是分层

你们想“换成自己的”，方向对，但要分层，否则会重走我们踩过的坑：

| 层 | 谁做 | 说明 |
|---|---|---|
| 启动链（拉起 / 桥接 / 启动回调） | **沿用现有 V50 启动器 + 桥** | 重做成本极高，且已被本机实测证明可行（客户端 `.text` 区段完整可读） |
| 帧层 / 登录 / 会话 | **你们的 `protocol.rs` + `login_wire.rs`** | 已经写好了，接着补 2010/30004 |
| 内容层（任务/商店/邮件/副本…） | **你们的 `game_ingress.rs` + 业务内核** | 这是真正能并行分工的部分 |
| 存档格式 | **你们的 `GPW.snapshot/1`** | 但读旧档必须走“只读副本 + 断言” |

换句话说：**V50 的启动器是“电源”，你们的服务端是“内容”。** 现在你们把电源拔了去测内容，当然零入站。

---

## 8. 同步进度用的硬事实（可直接给模型当上下文）

```
仓库：https://github.com/Auth3r/tfd-v50-workbench （私有）
分支：feat/auto-drive   HEAD：6854546
关键提交：
  2229c37  创角跑通存档（3801/1701 请求体读空与短路应答 + v30 桥归档）
  aa0349f  客户端 stdout/stderr 落盘（C:\tfdwork\client_out.log）
  6854546  内容缺口评估（36 过程 / 14 集合）
新加（未提交）：CONTRACT.md / manifest.json / bootstrap.ps1 / selfcheck.ps1

协议资产：unpacked/assets/network-expansion.json → 36 procedures / 162 schemas
  ！ 1701 = CheckOntimeEvent（不是集合键）
  ！ 3801 = JumpingPeriodVaild（应答必须恰好 4 字节 i32）
  ！ 2006 = 创角提交（创意角色时发，body 4 字节）

关键启动回调（桥内按名称引用；地址见仓库内部文档）：
  platform_config     平台配置阶段（时间戳来源）
  direct_prep         launcherAuthentication（含 born+22s 门控）
  creation_submit     创角提交入口
  creation_2006_send  发送 2006 的函数
  title_wait          标题创建等待（黑屏局从未进入）
  account_load        账号 load 观测

时间线判据（run 目录 data/launcher/runs/<uid>/<runID>/events.jsonl）：
  正常局：game_process_started 0.9s → local_platform_config 4–6s → native_account_loaded 24.x
  黑屏局：local_platform_config 20–30.5s → native_account_loaded 34–41s，且无 native_title_creation_error
  桥加载：bridge_ready ≈1.2s（常量，与黑屏无关）

已知两个硬断点（我们还没修，你们也别重复踩）：
  ① 2006 提交时若库里已有同 Tid 角色 → 服务端回 created=false → 客户端断开 → exit_code=3
  ② 2006 之后进主城，20000 聚合链最后一条 3801 应答不足 4 字节 → connection_rejected truncated payload
```

---

## 9. 你们交接文档里那四个问题，逐条答复

1. **针对哪个 Build**：新版 26722146（`a601a30d…`）；旧版 26263743（`c0147688…`）只能用原厂桥。
2. **受支持的启动方式**：只有“经发布端运行时 + 兼容桥”这一条被验证过；`-LoginIP/-LoginPort` 是必要条件，不是充分条件。
3. **最早可独立验证的边界**：`procedure 1` → `2010` → `30004`；判据是客户端停在标题页并持续心跳。
4. **只做一处改动**：改 `launch.rs` 的启动方式（接启动器），观察 accept 计数与首帧 procedure。

---

## 10. 一个反面清单（别做）

- 不要试图只靠 `-LoginIP/-LoginPort` 裸启（15 秒自退，已验证）；
- 不要先做 `20000` 聚合（任何一条长度错都会被判坏包断连）；
- 不要从模块属性里 introspect `content_clock`（`1701` 用不到，我们探过 6 个模块全是空）；
- 不要把 `1701` 当内容集合键找 schema（它是过程，不是集合）；
- 不要用 36 角色时代的旧档直接喂新创角流程（会和新建角色冲突，我们已移走）。
