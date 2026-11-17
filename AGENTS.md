# GPW Offline Core

- 署名固定为 GPW Offline / 狗屁王_official；不是官方软件。
- 仅修改当前app内。原游戏、V15、旧工程、capture均只读；不启动未知样本、游戏、桥接或另一个Craft。
- 当前是.NET无GUI服务工程，不是macroquad游戏；不制作move/act/hud或伪截图。
- GPW.local/1是自有契约。未取得真实完整字节与客户端实证前，不声明游戏兼容，不把115/116业务意图当网络实现。
- 世界实例未实现时必须拒绝，不能发成功分配或伪造Oid。
- 构建与依赖保持F盘本工程；不联网restore，NuGet源为空。
- 任何持久化改动都通过实际进程/TCP/磁盘自测，保存scope与程序集SHA；不可把合成测试当L2–L5。

| 规则 | 由什么拦住 |
|---|---|
| 不允许陈旧写入/重复操作造成物品丢失或复制 | `--self-test` 的原子批次、并发与幂等测试；独立变异副本移除CAS后实际失败 |
| 不把世界未实现返回成功 | `unsupported_world_and_protocol_refused` 实际TCP测试 |
| 提交失败不发布内存状态 | `failed_disk_commit_does_not_publish_state` 用真实Windows文件锁制造提交故障 |
| 恢复点要明确，损坏不得静默清空 | checksum/显式恢复/重启读取验证 |
