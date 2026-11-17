# 本轮验证结果

日期：2026-11-17。范围：GPW 自有服务，测试资料；不是游戏运行。

- `dotnet build GpwOffline.Core.csproj -c Release --configfile NuGet.Config`：0警告、0错误。
- `dotnet bin/Release/net9.0/GpwOffline.Core.dll --self-test checks/self-test.json`：20通过、0失败。
- 正向被测程序集SHA-256：`748722DFED9975582A405F20AE5BDB6CE26B37B9A6CFAAEED4E2DCC1DDB241F7`。
- 原生apphost实际执行 `--help`，退出0，正确显示GPW署名和L1限制。
- 自测驱动真实子进程和独立实现的测试端TCP分帧；实际文件持久化、句柄锁提交故障、进程中断、恢复和到期均被运行验证。
- 独立变异副本将修订号不相等拒绝改成仅拒绝负值：16通过、4失败，退出1。陈旧写入和并发丢失更新均被抓住；这是预期负向结果，不是生产检查失败被改称通过。
- 本轮登记的30个只读输入SHA全部未变；不是对整个磁盘或全部游戏资源的完整性证明。
- 构建恢复配置确认外部包0个，包路径在F盘app内。未联网安装。
- Craft最终构建检查通过，截图检查失败；未生成图片。没有UI，截图不适用，但不将Craft总体检查标成通过。

正向、负向原始结果分别为 `self-test.json`、`negative-revision.json`，变异检查判定为 `mutation-verdict.json`；原代码摘要保存在 `../evidence/source-manifest.json`。变异副本保留于被Git忽略的 `checks/mutation`，不混入产品源码或发行物。

尚未验证：完整真实游戏业务契约、游戏进程与GPW连接、可操作场景、真实游戏保存与重进、全游戏链第三方依赖移除、虚拟机当前隔离与图形能力、断电可靠性和生产负载。下一项工作是合法本地接入接口及115/116完整字节/客户端行为对照，不能用更多自测数量替代它。
