# GPW Offline Core

**GPW · 第一后裔离线运行系统 — by 狗屁王_official**

非官方、免费、自主实现的本地核心开发版。本项目不是 NEXON 官方软件，与游戏开发商和发行商无隶属关系。

**目前达到 L1，尚不是可玩版本。** 已实现并测试的是独立装备仓库事务与本地资料持久化；尚无已验证的游戏线协议适配器，不能据此宣称 L2、L3、L4 或 L5。当前核心不启动、不加载也不依赖 TFD-Offline.exe，但整套游戏脱离第三方后的 L6 仍未验收。

## 已经能做什么

- 新建 GPW 本地资料，建立/过期/注销本地会话；会话与资料绑定。
- 装备整批入库与取回：归属、穿戴、容量、修订号检查；失败不部分提交。
- 持久化操作回执：同请求重试只返回已提交结果，同操作编号更改内容被拒绝。
- 同一存档独占写入；并发请求通过修订号拒绝丢失更新。
- 已确认提交后中断进程，再启动仍能读回装备位置与回执。
- SHA-256 完整性检查、原子文件替换、上一提交快照、显式选择代次恢复，保留恢复前文件。
- 只读核对当前游戏两个可执行文件的身份；匹配不代表可运行或协议兼容。

第一业务依据是旧 V15 证据中 115/116 的装备仓库操作声明。**这里的 UID、容量规则、错误码、JSON 和 GPW1 帧均为 GPW 自有设计，不是恢复出的游戏报文。** 没有把声明的内存偏移当成网络布局。详见 [契约与来源](CONTRACT.md)、[验收与剩余职责](STATUS.md)。

## 本地构建与验证

当前工程在 `F:\Codex\tfd-offline-2\app`，它有独立 Git 仓库和空工程基线。建议目录 `F:\Codex\GPW-Offline-Core` 不在本次写入范围内，未擅自迁移。旧项目、原始游戏和参考样本仅只读使用。

使用机器已有 .NET SDK 9.0.306；无 NuGet 包、没有联网安装。包路径固定在本工程 `.nuget/packages`，构建产物在 `bin`/`obj`。操作系统上的既有 SDK 位于 C 盘，不是新安装的依赖。

在工程目录 PowerShell 中运行：

```powershell
$env:DOTNET_CLI_HOME = "$PWD\.dotnet"
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_ADD_GLOBAL_TOOLS_TO_PATH = 'false'
dotnet build GpwOffline.Core.csproj -c Release --configfile NuGet.Config
dotnet bin/Release/net9.0/GpwOffline.Core.dll --self-test checks/self-test.json
```

`build.ps1` 提供同样的本地构建步骤。本机执行策略拒绝直接运行 PowerShell 脚本，本轮直接执行上述构建命令，未修改执行策略。首次 SDK 初始化输出报告了开发证书初始化；程序不使用 HTTPS，之后显式禁用了 SDK 自动证书和 PATH 初始化，未调整系统信任或防护设置。

自测会启动真实子进程，使用真实回环 TCP 和实际文件存储；20 项通过的范围是 **GPW 自有服务＋测试数据**。没有调用游戏、没有真实账号数据，也没有以 move/act/hud 代替业务测试。每次自测的数据独立保存，结果包含被测程序集摘要。

## 核心入口

```powershell
dotnet bin/Release/net9.0/GpwOffline.Core.dll init --workspace local-player
dotnet bin/Release/net9.0/GpwOffline.Core.dll serve --workspace local-player --seconds 60
dotnet bin/Release/net9.0/GpwOffline.Core.dll inspect --workspace local-player
```

服务只监听 `127.0.0.1`，默认随机端口，启动行输出端口、进程号和明确的未接入游戏状态。运行时间必须显式指定，范围 1–3600 秒；Ctrl+C 可正常停止。此限制属于开发期运行管理，不是游戏时长或付费授权。数据只能落在本工程 `data/<名称>`；拒绝路径穿越、外部路径和已存在的链接。

服务是单用户本地工具，**同机进程可以选择本地资料**；本地会话只做会话生命周期与资料关联，不承诺抵御同机恶意进程，也不认证官方账号。无 CDK、机器码、云端租约或在线许可证。

开发数据需显式加 `--allow-provisioning` 才允许 `equipment.provision`；它不代表游戏奖励、游戏初始资料或真实物品模板。默认关闭。未实现世界实例时明确拒绝 `world.reserve`，不会返回虚构的 Oid、地址或分配成功。

## 恢复

停止服务后先执行 `recovery-info --workspace 名称`，查看可恢复代次；再执行 `recover-previous --workspace 名称 --generation 代次`。恢复会回退到该快照，快照之后的提交不在恢复结果内，所有进程内会话失效。损坏文件会保留为 `pre-recovery-*`，不会静默恢复或覆盖成空存档。

上一代快照是基础恢复能力，不等于完整备份策略；可在核心停止后备份整个自有工作区。当前验证覆盖进程中断，不包括断电、磁盘硬件故障或跨设备迁移。内容目录、官方游戏资源、第三方账号库和角色存档均未导入。

## 检查限制

Craft `rebuild_check` 已识别 .NET 工程并通过构建，但要求截图而失败。该项目无图形界面；`--screenshot` 明确退出 2，不生成伪造图片。Craft 的截图检查未通过，不能报告为全部验收通过。源码、业务验证和受保护输入摘要见 `checks`、`evidence`。

本工程没有包含原游戏资源或第三方私有实现，所以不适用“包含游戏原文件”的分发声明。维护者署名保留；未发布为正式可玩版本。
