# 第一业务：装备仓库转移

## 证据与实现之间的边界

原始 V15 ZIP SHA-256：`e0047fe9df5f9c5efff103e0527d1ab9d9a4f84b0cd7b7310b4b380e55b0d14d`。

旧工程 `reports/v15-deep-research/evidence/protocol-declarations.json` 的 `assets\session-rpc-20261031.json` 条目明确声明：

| 声明事实 | GPW 使用方式 | 尚未验证 |
|---|---|---|
| 115 = MoveEquipmentToWareHouse，116 = TakeOutFromWareHouse | 选择同一业务职责，提供入库/取回事务 | 真实游戏调用及网络程序号映射 |
| 请求 AccountUid:i64，ItemUidBoxesInfo:M1ItemBoxesInfo | 业务需区分资料归属和物品集合 | UID 映射、完整集合元素、编码、失败语义 |
| 响应 Notification:i32、ItemUidBoxesInfo | 不生成游戏响应，不解释 Notification 值 | 真正响应与库存通知的顺序 |
| M1InventoryUpdateNoti 有 InventoryRevision | GPW 自行采用乐观并发；明确为设计选择 | 游戏修订号与存储版本的准确关系 |

本轮没有复制私有实现、结构偏移、脚本、游戏资源或模板数据。对外层程序的 Craft 入口反编译只确认启动包装层；Ghidra 失败，内置反编译结果不能补齐业务线协议。没有据此估造报文。

Round 2 的 13 次诊断分配、8 次资料观察回调不能证明世界可运行；Round 3 合成整数编码不作为 V15 编码使用；Round 4 健康服务不是本次业务成功依据。旧工程未作产品架构复制。

## GPW 自有线协议 v1

这是供未来适配器调用的本机内部协议，**不能直接连接原游戏**。

8 字节头：ASCII `GPW1`（4字节），JSON UTF-8 字节数（小端有符号32位，2–65536）。随后是一个 JSON 对象。允许分片、合包，拒绝其他魔数、过大长度、截断、重复 JSON 键、未知属性和不递增的请求 id。连接空闲/读写期限为 5 秒，最多16连接。所有数值限制是 GPW 策略，不是游戏常量。

通用字段：`protocol:"GPW.local/1"`、正整数 `id`、`op`。成功响应 `ok:true,code:"ok",data:{...}`；失败 `ok:false,code:错误码`。请求已解析时响应携带 id；无法解析/无有效关联时 id 为0。协议版本不匹配拒绝；GPW版本不等于游戏Build。

| op | 必要输入（除通用字段） | 行为 |
|---|---|---|
| profile.create | profileUid GUID、name、inventoryCapacity、warehouseCapacity | 创建空白 GPW 资料；容量各1–128，不创建游戏角色 |
| session.open | profileUid | 创建32随机字节本地会话，返回到期时间；不写盘，不发官方票据 |
| session.close | profileUid、session | 撤销当前本地会话 |
| profile.read | profileUid、session | 返回实际装备位置、修订号与存储代次 |
| equipment.provision | profileUid、session、expectedRevision、equipment | 显式开发模式导入 GPW 自有数据，每项 uid/templateId/location/equipped；全量验证后提交 |
| equipment.move | profileUid、session、expectedRevision、operationUid GUID、itemUids GUID数组、destination | destination 为 inventory/warehouse，单次1–256件；原子转移 |
| world.reserve | 无 | 始终拒绝 world_runtime_unimplemented；没有伪造世界分配 |

仓库操作提交前检查：会话归属和有效期 → 操作编号与内容回执 → 当前修订号 → 每件物品归属、当前位置、穿戴状态 → 目标容量。成功只修改位置、修订号与回执，不改变物品 UID/模板/总数；任一步失败不更改文件。重复操作按最初提交结果返回，不假装它是当前资料最新快照；客户端可再次 profile.read。

回执内容摘要包含资料、期望修订、排序后的物品集合和目标位置；顺序变化视为同请求。每资料最多10000条回执，达到上限拒绝新转移，不静默清除幂等保障。需要将来设计有确认语义的回执归档。

## 存储事务

`GPW.owned-save/1` 与 `GPW.snapshot/1` 为独立格式。全量候选状态先校验，写同卷临时文件、Flush(true)，再原子替换当前快照并保留上一提交；成功后才发布内存状态。故障不会提前发布内存状态。工作区句柄锁拒绝第二写者；不根据磁盘 PID 杀进程。

SHA-256用于损坏检测，不是防篡改签名、加密或许可证。每个物品 UID 全库唯一；容量、位置、穿戴关系、资料 ID、回执对象均在读取与写入时验证。没有迁移或读取 V15 schema22。快照上限32MiB，资料数上限1000；当前是小规模本地核心，不承诺高频大规模游戏存档性能。
