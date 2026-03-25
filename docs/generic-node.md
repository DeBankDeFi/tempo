# Tempo 通用节点支持方案

## 目标

为 Tempo 节点实现 `trace_debankBlock` RPC，接入通用节点数据管线：

```
Tempo 节点 (trace_debankBlock RPC)
       ↓ HTTP
background-tracer (已有 sidecar)
       ↓                    ↓
   S3 上传                Kafka 发布
  (header/stateDiff/     (BlockChangeNotify)
   blockFile/validation)
       ↓                    ↓
   leafage-evm          DeBankCore
  (state query)      (blockfile traces)
```

## 实现状态

### 已完成

**新增文件**:
- `crates/debank-rpc/src/debank_trace.rs` — DeBank 类型定义（BlockStorageDiff, BlockFile, DebankOutPut 等）+ trace 树构建 + state diff 提取
- `crates/debank-rpc/src/state_diff_db.rs` — StateDiffTraceDB 双写数据库（记录 EVM state 变化用于 diff 提取）
- `crates/debank-rpc/src/trace_block.rs` — `trace_debankBlock` RPC 实现

**修改文件**:
- `crates/debank-rpc/src/lib.rs` — 新增 DebankTraceApi trait
- `crates/debank-rpc/Cargo.toml` — 添加 alloy-rlp, md-5, sha1, reth-chainspec 等依赖
- `crates/node/src/node.rs` — 注册 trace_debankBlock RPC

**编译通过**: `cargo check -p tempo-node` 零 warning 零 error。

### trace_debankBlock 执行流程

```
1. recovered_block(block_id) → DebankBlock + Header

2. block == 0 → genesis 特殊处理
   从 chain_spec.genesis() 构建 synthetic txs/traces + state_diff

3. block_receipts(block_id) → Vec<DebankTransaction>

4. parent.state_root == block.state_root → 空 state_diff（无状态变化）

5. spawn_blocking_io_fut:
   a. state_at_block_id(parent) × 2 → pre_db + StateDiffTraceDB(db)
   b. 对每笔 tx:
      - TracingInspector(parity + SSTORE filter) + TempoEvm handler
      - eth_api.inspect() → ResultAndState
      - commit state
      - build_debank_traces(CallTraceArena) → traces/events
   c. get_storage_diffs_from_cache(diff.cache, pre_db) → RLP-encoded state_diff

6. 组装 DebankOutPut { block_file, header, state_diff, validation_hash }
```

### 关键设计决策

**state_diff 包含完整状态变化（含 fee）**:
`eth_api.inspect()` 走 `TempoEvm::transact_raw()` → `inner.inspect_tx()` → 完整 TempoEvmHandler 路径（`validate_against_state_and_deduct_caller` + `reimburse_caller`）。handler 层的 fee 操作（TIP-20 storage 修改、fee Transfer log）包含在 `ResultAndState` 中，state_diff 和 events 自动完整。

这与 `pre_traceMany` 不同 — pre_traceMany 走 `prepare_call_env` → `inspect()` 路径（eth_call 模式），handler 的 fee 逻辑被跳过。

**AA tx (type=0x76) 的 DebankTransaction 字段来源**:

`to_addr` 和 `input` 对 AA tx 与普通 tx 表现不同：

| 字段 | 来源 | 普通 tx | AA tx (0x76) |
|------|------|--------|-------------|
| to_addr | `ReceiptResponse::to()` | tx.to = 合约地址 | receipt.to = 解包后的实际调用目标 |
| input | `Transaction::input()` | tx.input = call data | TempoTxEnvelope trait 返回 AA 内部调用数据（非信封 payload） |

`eth_getBlockByNumber` 返回 AA 信封层原始数据（to=null, input=短 AA payload），而 debankBlock 返回解包后的业务数据。这是 Tempo 的 `Transaction` trait 实现决定的行为（reth-x 无 AA tx，不存在此差异）。DeBankCore 需要解包后的数据，当前行为正确。

**Revert tx 的 fee log 获取**:

成功 tx: fee log 在 `ExecutionResult::Success { logs }` 中，直接可得。
Revert tx: `ExecutionResult::Revert` 没有 logs 字段。handler 的 fee log 存在 `TempoEvm.logs` 中，但 `inspect()` 后 EVM 被丢弃。实际通过 `eth_getTransactionReceipt`（已存储的 receipt）的 logs 补回，使用 `serde_json::from_value::<Vec<alloy_rpc_types_eth::Log>>` 反序列化。

**trace/event 分类: per-node success + receipt status 修正**:

`build_debank_traces()` 内部按 `CallTraceNode.trace.success` 分类 traces/events 到 success 或 error 列表。组装 block_file 时根据 receipt status 做两种修正：

1. **成功 tx (status=0x1)**: 保留 per-node 分类。仅修正 AA tx (0x76) 的根 trace — AA tx 的根 trace 被 `CallTraceArena` 标记为 `success=false`（handler 包装），但 tx 实际成功。将 root trace (`trace_address=[]`) 及其直属 events 从 error 列表移到 success 列表，内部 revert 子调用（try/catch 场景）保留在 error 列表。与 reth-x 行为一致。
2. **失败 tx (status=0x0)**: 所有 traces/events 归入 error 列表。

**与 reth-x 的差异**:

| 项 | reth-x | Tempo |
|---|--------|-------|
| 区块重放 | `EvmFactory::create_tracer().try_trace_many()` | 手动循环 + `inspect()` + `commit()` |
| 错误处理 | iterator 返回 None 停止 | `?` 直接返回错误（一致） |
| pre_db | 两次 `state_at_block_id` | 同上（一致） |
| fee 处理 | 标准以太坊（无特殊） | TempoEvmHandler 自动处理 TIP-20 fee |
| revert tx fee log | 无此问题 | 从 receipt serde 反序列化补回 |
| trace 分类 | CallTraceArena success 标志 | receipt status 最终决定 |
| AA tx | 无 | to_addr/input 来自解包后数据 |
| exclude_precompile_calls | `false`（完整调用链） | `true`（与 trace_transaction 一致）⚠️ 待讨论 |
| deposit_nonce | OP Stack 支持 | 不需要（非 OP Stack） |

**与 pipeline Go 版的字段兼容性**:

逐字段递归对比 pipeline (`/chaintable/pipeline/types/`) 与 Tempo 实现，结论:
- JSON 字段名: 全部一致（除 Header 的 `requestsHash` vs `requestsRoot`，reth 系通用差异，消费方不使用）
- 字段数量: 全部一致（BlockValidation 的 count 字段由 background-tracer 独立计算，不在 RPC 返回中）
- 数值类型: Go `*big.Int` vs Rust `u64`/`u128`，JSON 序列化结果一致

## 验证状态

已在 dev 环境 (blockchain-misc-x3, 镜像 `blockchain/tempo:5e3c190`) 完成验证。详见 `docs/test-plan-generic-node.md`，113/119 PASS，6 项待新镜像部署后验证。

| 验证项 | 状态 |
|--------|------|
| 字段完整性 (block/txs/traces/events/state_diff/header) | PASS (113/119) |
| traces 与 trace_transaction 逐字段对比 (11 字段 × 21 条) | PASS |
| events 与 eth_getTransactionReceipt.logs 数量一致 | PASS (含 fee log) |
| revert tx error_traces/error_events 分类 | PASS |
| state_diff RLP 解码 (hash/parent_hash/new_accounts/storage_diffs/new_codes) | PASS |
| genesis/空块/CREATE 块/AA tx 块/最新块 | PASS |
| 性能 (单次调用 12ms) | PASS |
| background-tracer dry-run | 未执行 (需 binary 部署) |

## 部署

### Dev 环境 (已完成)

- 机器: blockchain-misc-x3
- 数据: `/data/tempo/` (snapshot 导入, 20G)
- 镜像: `blockchain/tempo:5e3c190` (CI 自动构建)
- 端口: 8566 (HTTP RPC)
- docker-compose: `/data/tempo/docker-compose.yml`

### 生产部署步骤

1. 合并 `feature/debank_rpc` → `debank` 分支
2. 创建 release tag → CI 构建镜像 (amd64 + arm64)
3. 更新线上 2 台机器 docker compose (172.22.141.54 / 172.22.179.114)
4. 验证 `trace_debankBlock` RPC 可用
5. 部署 background-tracer sidecar (配置 Kafka/S3 + chain_id=4217)

## 待讨论 / TODO

### exclude_precompile_calls 设置 (CTO CR #1)

当前 `trace_block.rs:230` 设为 `true`，排除标准预编译 (0x01-0x09) 的 call trace，与 `trace_transaction` 行为一致。reth-x debankBlock 设为 `false`，因为 debankBlock 是给 DeBankCore 的完整数据导出，需要完整调用链。

**注意**: Tempo 自定义预编译 (TIP-20 0x20C0..., FeeManager 0xfeec..., StablecoinDEX 0xdec0...) **不受此设置影响**，它们不在 revm-inspectors 的标准预编译列表中。受影响的是 ecrecover/sha256/ripemd160 等标准预编译的 call trace。

**待确认**: 是否改为 `false` 与 reth-x 一致。改动为 1 行代码，trace 数量会增加（多出标准预编译调用），不会减少。

### per-trace storage_change 对预编译无效 (CTO CR #7)

`debank_trace.rs` 中 `self_storage_change` 通过检测 SSTORE opcode 设置。Tempo 自定义预编译（TIP-20、FeeManager 等）的 storage 修改直接在 Rust 代码中操作 state，不走 SSTORE opcode，因此调用预编译的 trace `storage_change=false`，即使预编译实际修改了 storage slot。

block 级 `storage_contracts`（从 `diff.cache` 提取）不受影响，能正确反映所有 storage 变化的合约地址。仅 per-trace 级信号对预编译调用无效。

**已知限制**，与 reth-x 行为一致（reth-x 标准预编译同样不走 SSTORE）。

### genesis native token 无实际意义 (CTO CR #11)

genesis 块创建了 `0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` native token 的 synthetic tx。Tempo 实际无 native token（gas 用 TIP-20 支付），该资产永远无转账。不影响功能，DeBankCore 链配置层面建议标注忽略此资产。
