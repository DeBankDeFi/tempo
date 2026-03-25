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

**与 reth-x 的差异**:
| 项 | reth-x | Tempo |
|---|--------|-------|
| 区块重放 | `EvmFactory::create_tracer().try_trace_many()` | 手动循环 + `inspect()` + `commit()` |
| 错误处理 | iterator 返回 None 停止 | `?` 直接返回错误（一致） |
| pre_db | 两次 `state_at_block_id` | 同上（一致） |
| fee 处理 | 标准以太坊（无特殊） | TempoEvmHandler 自动处理 TIP-20 fee |
| deposit_nonce | OP Stack 支持 | 不需要（非 OP Stack） |

## 待验证

部署后需验证：

### 1. 基础调用
```bash
curl -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"trace_debankBlock","params":["0x9a1eb0"],"id":1}' \
  http://data.tempo.blockchain
```

### 2. 字段完整性
- `block_file.block`: id/height/parent_id/timestamp
- `block_file.txs`: 数量 = eth_getBlockByNumber 的 tx 数
- `block_file.traces`: 与 trace_transaction 一致
- `block_file.events`: 数量 = receipt 总 logs 数（含 fee log）
- `state_diff`: RLP 可解码，new_accounts/storage_diffs 非空
- `validation_hash`: 非零

### 3. Fee log 验证
对同一 tx，`trace_debankBlock` 输出的 events 数量应等于 `eth_getTransactionReceipt` 的 logs 数量（含 handler 层 fee Transfer log）。

### 4. State diff 精确性
对比 `trace_debankBlock` 的 state_diff 中 new_codes 数量，确认只包含本 block 新部署的代码（不含已有代码）。

### 5. background-tracer 集成
```bash
background-tracer dry-run \
  --rpc-address=http://data.tempo.blockchain \
  --start-block=10000000 --end-block=10000005 \
  --max-task=1 --chain-id=4217 \
  --region=ap-northeast-1 \
  --nodex-bucket=test --chain-table-bucket=test
```

## 部署步骤

1. 在 blockchain-misc-x3 编译 `cargo build --release`
2. 构建镜像推送 ECR
3. 更新线上 docker compose 使用新镜像
4. 验证 `trace_debankBlock` RPC 可用
5. 部署 background-tracer sidecar（配置 Kafka/S3 + chain_id=4217）
