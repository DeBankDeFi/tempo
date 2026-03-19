# Tempo DeBank Custom RPC Design Document

## 1. Overview

Tempo 是 Stripe + Paradigm 联合孵化的支付专用 L1（2026-03-18 主网上线），基于 Reth SDK 构建。DeBank 需要在 Tempo 节点上新增三种 JSON-RPC 方法，为链上资产分析、交易预执行和批量合约查询提供支持：

| 方法 | 用途 | 状态 |
|------|------|------|
| `trace_transaction` | EVM 事务追踪，返回完整调用栈 | reth 内置，无需实现 |
| `pre_traceMany` | EVM 预执行，顺序模拟 N 个 call，返回 trace + logs + gasUsed | 新增实现 |
| `eth_multiCall` | 批量执行 N 个 call，返回每个 call 的执行结果和错误信息 | 新增实现 |

## 2. RPC Methods

### 2.1 `trace_transaction`

#### 背景

涉及合约账户的交易可能很复杂——合约可能调用其他合约，产生庞大的调用链。为了获取涉及的合约地址、转账数量等交易细节，为用户链上资产分析提供支持，需要收集事务在 EVM 虚拟机执行过程中 call 和 create 的调用栈。

#### 业务场景

追踪用户 native token 的变化：如果 call 的 `value` 不为 0，表明发生了从 `from` 到 `to` 的 native token 转账。

示例：某笔 tx 最后一个 call 的 `value` 为 6073312650702477（约 0.006 ETH），表明用户地址收到该金额的 native token 转账。

#### 实现

**无需新增代码**。reth 内置 `trace_transaction` 方法（Parity trace 标准 API），启用 `trace` RPC 模块即可使用。

Request:
```json
{
    "jsonrpc": "2.0", "id": 1,
    "method": "trace_transaction",
    "params": ["0xa592d15f06a137128dac6c656d04cc2a236813b5564733e5cbf186e289344eda"]
}
```

Response: `Array<LocalizedTransactionTrace>`，每个 trace 包含 `action`（callType/from/to/value/gas/input）、`result`（gasUsed/output）、`subtraces`、`traceAddress` 等字段。

---

### 2.2 `pre_traceMany`

#### 背景

与合约交互并不像 EOA 转账那样简单明了。用户需要知道提交事务后自己的资产变化，以最大程度避免可能的风险。预执行在最新区块执行相关事务，并在 EVM 虚拟机执行过程中搜集 event log、call/create 调用栈以及实际 gas 消耗。

#### 业务场景

为用户提供预执行 tx 后的资产变化，并根据返回的 `gasUsed` 估算所需的 gasLimit（x4）：
- **trace 结果**：追踪 native token 的变化（同 `trace_transaction` 的 value 分析）
- **event log 结果**：追踪 ERC-20 token 的变化（Transfer 事件）

#### API 定义

**Wire format**: `pre_traceMany`

```
Namespace: pre
Method:    traceMany
```

**Parameters** (positional):

| # | 名称 | 类型 | 必填 | 说明 |
|---|------|------|------|------|
| 0 | transactions | `Vec<TransactionRequest>` | Y | tx 数组，结构同 `eth_call`，每个 tx 在指定高度的 state 上顺序执行 |
| 1 | block_id | `BlockId` | N | 默认 latest |
| 2 | state_overrides | `StateOverride` | N | 仅对首笔 tx 生效 |
| 3 | block_overrides | `BlockOverrides` | N | |

Request 示例:
```json
{
    "jsonrpc": "2.0", "id": 1,
    "method": "pre_traceMany",
    "params": [[
        {
            "chainId": 1,
            "from": "0x5853ed4f26a3fcea565b3fbc698bb19cdf6deb85",
            "to": "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
            "data": "0x5ae401dc...",
            "gas_price": "0x0",
            "nonce": "0xD36",
            "value": "0x0"
        }
    ]]
}
```

**Returns**: `Vec<PreResult>`

每个 PreResult 与输入 tx 数组一一对应：

| 字段 | 类型 | 说明 |
|------|------|------|
| trace | `Vec<LocalizedTransactionTrace>` | Parity 格式调用栈，追踪 native token 变化 |
| logs | `Vec<Log>` | Event log，追踪 ERC-20 token 变化 |
| error | `PreError \| null` | 执行错误信息 |
| gasUsed | `u64` | 实际消耗 gas，业务侧用于估算 gasLimit |

Response 示例:
```json
{
    "jsonrpc": "2.0", "id": 1,
    "result": [{
        "trace": [
            {
                "action": {
                    "callType": "call",
                    "from": "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
                    "to": "0x5853ed4f26a3fcea565b3fbc698bb19cdf6deb85",
                    "value": "0xd65434b5d543",
                    "gas": "0x7c07fffffffc7756",
                    "input": "0x"
                },
                "result": { "gasUsed": "0x0", "output": "0x" },
                "subtraces": 0,
                "traceAddress": [1, 2],
                "transactionHash": "0x0000...0000",
                "transactionPosition": 0,
                "type": "call"
            }
        ],
        "logs": [
            {
                "address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
                "topics": ["0x7fcf532c...", "0x00000000...68b3465833fb72a70ecdf485e0e4c7bd8665fc45"],
                "data": "0x0000000000000000000000000000000000000000000000000000d65434b5d543",
                "blockNumber": "0xf3bfe8",
                "logIndex": "0x6",
                "removed": false
            }
        ],
        "error": null,
        "gasUsed": 195350
    }]
}
```

**错误码** (`PreErrorCode`):

| 值 | 含义 |
|----|------|
| 1000 | Unknown (EVM 执行异常) |
| 1001 | InsufficientBalance (Halt) |
| 1002 | Reverted |

#### 执行语义

- 在指定 block 的 parent state 上顺序执行交易
- 每笔 tx 执行后 **commit state**，后续 tx 可见前序 tx 的状态变更
- 使用 `TracingInspector`（parity config）采集调用栈
- `state_overrides` 仅对首笔 tx 生效（`.take()` 语义）

---

### 2.3 `eth_multiCall`

#### 背景

新增的 `eth_multiCall` 解决链上 multicall 方案存在的问题：
1. **老区块兼容**：链上 multicall 方案不适用于 multicall 合约部署之前的老区块
2. **缓存友好**：链上 multicall 将多个入参聚合为一次 EVM 调用，不利于实现计算层缓存（如 `[A,B,C,D]` → `[B,A,C,D]` 无法命中缓存）
3. **延迟优化**：链上 multicall 在 EVM 里串行执行，调用数量多时耗时叠加

#### 业务场景

- **User Profile 加载**：单次加载产生大量节点请求，需要聚合请求减少网络 IO 和页面加载延时
- **统一接口**：统一 ERC-20 token 和 native token 的余额获取方式（`0xeeee` 地址模拟）
- **性能调优**：通过 `disableCache` / `useParallel` 参数 debug 性能表现

#### API 定义

**Wire format**: `eth_multiCall`

```
Namespace: eth
Method:    multiCall
```

**Parameters** (positional):

| # | 名称 | 类型 | 说明 |
|---|------|------|------|
| 0 | requests | `Vec<TransactionRequest>` | Call 数组，结构同 `eth_call`，`len >= 1` |
| 1 | block_number | `BlockId` | 指定区块，确保数据一致性 |
| 2 | fast_fail | `bool` | 任意 call 失败后快速返回（默认 false） |
| 3 | use_parallel | `bool` | 是否并行执行（默认 false，当前保留未实现） |
| 4 | disable_cache | `bool` | 禁用缓存，用于性能 debug（默认 false） |
| 5 | state_overrides | `StateOverride` | 仅首笔 call 生效 |
| 6 | block_overrides | `BlockOverrides` | |

Call 结构中 `gas` 字段限制单个 call 最大 gas 消耗，避免预期外的资源消耗。不指定时使用节点的 `globalGasCap`。

Request 示例:
```json
{
    "jsonrpc": "2.0", "id": 2,
    "method": "eth_multiCall",
    "params": [
        [
            {"to": "0xf824717e...", "data": "0x3fc1cc26..."},
            {"to": "0x8166994d...", "data": "0x93f1a40b..."},
            {"to": "0x49894fCC...", "data": "0x70a08231..."}
        ],
        "0x87e316...",
        false,
        true,
        true
    ]
}
```

**Returns**: `MultiCallResp`

| 字段 | 类型 | 说明 |
|------|------|------|
| results | `Vec<SingleCallResult>` | 与 calls 顺序一一对应 |
| stats | `MultiCallStats` | 本次请求的状态信息 |

SingleCallResult:

| 字段 | 类型 | 说明 |
|------|------|------|
| code | `i32` | 错误码，0 表示成功 |
| err | `String` | 错误描述 |
| result | `Bytes` | call 返回的原始编码数据，业务层 decode |
| fromCache | `bool` | 是否来自缓存 |
| gasUsed | `i64` | 本次 call 消耗的 gas |
| timeCost | `f64` | 执行耗时（秒） |

MultiCallStats:

| 字段 | 类型 | 说明 |
|------|------|------|
| blockNum | `u64` | 结果对应的区块号 |
| blockHash | `B256` | 结果对应的区块哈希 |
| blockTime | `u64` | 区块时间戳 |
| success | `bool` | 所有 call 都成功时为 true |
| cacheEnabled | `bool` | 缓存是否启用 |

**错误码** (`MultiCallErrorCode`):

| 值 | 名称 | 说明 |
|----|------|------|
| 0 | Success | 成功 |
| -40000 | CodeTxArgs | 参数错误 |
| -40001 | NativeMethodNotFound | native token 模拟方法不存在 |
| -40013 | EVMCancelled | EVM Halt |
| -40014 | EVMReverted | EVM Revert |
| -40015 | EVMFastFailed | fast_fail 触发的后续 call |

Response 示例:
```json
{
    "jsonrpc": "2.0", "id": 2,
    "result": {
        "results": [
            {"code": -40014, "err": "execution reverted", "fromCache": false, "result": "0x", "gasUsed": 0, "timeCost": 0.003416},
            {"code": 0, "err": "", "fromCache": false, "result": "0x00000000...", "gasUsed": 23794, "timeCost": 0.002786},
            {"code": 0, "err": "", "fromCache": false, "result": "0x00000000...", "gasUsed": 22718, "timeCost": 0.001404}
        ],
        "stats": {
            "blockNum": 12345678,
            "blockHash": "0x87e316...",
            "blockTime": 1648512415,
            "success": false,
            "cacheEnabled": false
        }
    }
}
```

#### 执行语义

- 在指定 block state 上**独立执行**每笔 call（不 commit，互不影响）
- `fast_fail=true` 时，首次失败后所有后续 call 复制相同错误结果
- `to == 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` 走 native token ERC-20 模拟（见下节）
- `state_overrides` 仅对首笔非 native token call 生效

---

## 3. Native Token ERC-20 Simulation

`eth_multiCall` 对 `0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` 地址的调用进行拦截，不经过 EVM 执行，直接读取链上 state 模拟 ERC-20 接口。统一 token 和 native 代币的余额获取方式。

| Selector | 方法 | 返回 |
|----------|------|------|
| `0x70a08231` | `balanceOf(address)` | 账户 native balance (U256, 32 bytes BE) |
| `0x18160ddd` | `totalSupply()` | 1 |
| `0x313ce567` | `decimals()` | 18 |
| `0x06fdde03` | `name()` | ABI encode "ETH" |
| `0x95d89b41` | `symbol()` | ABI encode "ETH" |

**Tempo 特殊性**: Tempo 的 gas 用 USDC/USDT 支付，native balance 可能始终为 0，但接口行为与其他链保持一致。

---

## 4. Architecture

### 4.1 Mega-reth 模式

采用与 mega-reth 相同的隔离模式：在 Tempo 仓库中创建独立的 `crates/debank-rpc/` crate，通过 `NodeAddOns::launch_add_ons()` 闭包注册自定义 RPC。不修改任何 reth 核心 crate，所有 DeBank 代码隔离在独立 crate 中。

优势：
- 与 reth 核心零耦合，后续 rebase upstream 冲突最小
- 不需要改 `RethRpcModule` 枚举、`rpc-builder`、`rpc-eth-api` 核心 trait
- 可独立编译和测试

### 4.2 仓库关系

```
tempoxyz/tempo (upstream)
  └── DeBankDeFi/tempo (fork, branch: debank)
        └── crates/debank-rpc/  (新增，650 行)
```

### 4.3 版本依赖

| 组件 | 版本 |
|------|------|
| reth | rev `a0b0d88` (v1.11.3) |
| revm | 36.0.0 |
| alloy | 1.6.1 |
| jsonrpsee | 0.26.0 |
| revm-inspectors | 0.36.1 |

### 4.4 参考实现来源

| 用途 | 来源 | revm 版本 |
|------|------|-----------|
| `pre_traceMany` 实现 | debankdefi/reth v1.6.0 | 27.0.3 |
| `eth_multiCall` 实现 | debankdefi/reth v1.6.0 | 27.0.3 |
| RPC 注册模式 | chaintable/mega-reth | 33.1.0 |

无现成的 revm 36 兼容版本，需从 revm 27 适配移植。

---

## 5. Crate Structure

```
crates/debank-rpc/          (650 行)
├── Cargo.toml              (41 行)
└── src/
    ├── lib.rs              (48 行)   RPC trait 定义 + re-export
    ├── types.rs            (98 行)   请求/响应类型定义
    ├── pre.rs              (185 行)  pre_traceMany 实现
    ├── multi_call.rs       (193 行)  eth_multiCall 实现
    └── erc20_handle.rs     (85 行)   0xeeee native token ERC-20 模拟
```

### Dependencies

```toml
# RPC framework
jsonrpsee = { features = ["server", "macros"] }
async-trait

# Alloy (types + ABI encoding)
alloy-consensus, alloy-eips, alloy-primitives
alloy-rpc-types-eth, alloy-rpc-types-trace, alloy-sol-types

# Reth (EVM + RPC infra)
reth-evm, reth-provider, reth-rpc-convert
reth-rpc-eth-api, reth-rpc-eth-types

# Revm (execution + tracing)
revm, revm-inspectors

# Misc
serde, futures
```

所有依赖通过 workspace 统一管理，与 Tempo 主项目版本一致。

---

## 6. RPC Registration

注册位置：`crates/node/src/node.rs` — `TempoAddOns::launch_add_ons` 闭包内

```rust
// DeBank custom RPCs
let pre_api = PreApi::new(eth_api.clone());
modules.merge_configured(pre_api.into_rpc())?;

let debank_eth_ext = DebankEthExt::new(eth_api);
modules.merge_if_module_configured(
    RethRpcModule::Eth,
    debank_eth_ext.into_rpc(),
)?;
```

| RPC | 注册方式 | 原因 |
|-----|---------|------|
| `PreApi` | `merge_configured` | 独立 `pre` namespace，无条件注册 |
| `DebankEthExt` | `merge_if_module_configured(Eth)` | 扩展 `eth` namespace，仅当 `eth` 模块启用时注册 |

---

## 7. Trait Bounds

### PreApi

```rust
// 内部方法
impl<Eth> PreApi<Eth>
where Eth: EthApiTypes + TraceExt + 'static

// Server trait
impl<Eth> DebankPreApiServer<RpcTxReq<Eth::NetworkTypes>> for PreApi<Eth>
where Eth: EthApiTypes + EthTransactions + TraceExt + 'static
```

`TraceExt` 展开: `LoadTransaction + LoadBlock + SpawnBlocking + Trace + Call`

依赖链：`Call` → `LoadState`（提供 `evm_env_at`）、`SpawnBlocking`（提供 `spawn_with_state_at_block`）

### DebankEthExt

```rust
impl<Eth> DebankEthExt<Eth>
where
    Eth: EthApiTypes + EthCall + 'static,
    RpcTxReq<Eth::NetworkTypes>: AsRef<TransactionRequest>,
```

`EthCall` 展开: `EstimateCall + Call + LoadPendingBlock + LoadBlock + FullEthApiTypes`

额外约束 `AsRef<TransactionRequest>` 用于 native token 地址检测（访问 `.to` 字段和 `.input`）。

---

## 8. Key Design Decisions

以下决策点是从 debankdefi/reth (revm 27) 移植到 Tempo reth (revm 36) 过程中的非直觉适配，不能直接复制原始代码。

### 8.1 `inspect_commit` 不存在 → inspect + commit 两步

debankdefi/reth 在 `Trace` trait 上添加了自定义的 `inspect_commit` 方法（内部调 `evm_with_env_and_inspector` + `transact_commit`）。Tempo 依赖的 reth rev `a0b0d88` 没有这个方法。

**方案**: 调 `Trace::inspect(&mut db, evm_env, tx_env, &mut inspector)` 拿到 `ResultAndState { result, state }`，再 `db.commit(state)` 手动提交。

关键点：`inspect` 签名 `fn inspect<DB>(db: DB, ...)` 接受泛型 DB，传 `&mut db`（可变借用）后所有权仍在调用方，函数返回后可继续调 `db.commit()`。inspector 同理用 `&mut inspector` 传入，返回后仍可调 `inspector.into_parity_builder()` 提取 trace。

### 8.2 `StateCacheDb` 底层类型变更

debankdefi/reth: `StateCacheDb = CacheDB<StateProviderDatabase<...>>`
Tempo reth: `StateCacheDb = State<StateProviderDatabase<StateProviderTraitObjWrapper>>`

两者都实现 `Database` + `DatabaseCommit`，但 `State::commit()` 内部走 `apply_transition()`（维护 bundle state），而 `CacheDB::commit()` 直接修改内存 map。代码层面透明，但状态管理机制不同。

### 8.3 `ExecutionResult` 结构变化

revm 27:
```rust
Success { reason, gas_used: u64, gas_refunded: u64, logs, output }
Revert  { gas_used: u64, output }
Halt    { reason, gas_used: u64 }
```

revm 36:
```rust
Success { reason, gas: ResultGas, logs, output }
Revert  { gas: ResultGas, logs, output }    // 新增 logs
Halt    { reason, gas: ResultGas, logs }    // 新增 logs
```

- `gas_used: u64` → `gas: ResultGas`，通过 `gas.used()` 获取 u64（内部计算 `max(spent - refunded, floor_gas)`）
- Revert/Halt 现在也携带 logs

另外，debankdefi/reth 原代码存在一个潜在 bug：match 消费 `res` 后又调 `res.logs()`（部分移动后使用）。本实现通过在 match arm 中直接解构 `logs: exec_logs` 规避。

### 8.4 `TransactionRequest::to()` 语义变更

alloy 旧版: `to(&self) -> Option<Address>` 是 getter
alloy 1.6.1: `to(self, addr: Address) -> Self` 是 builder 方法（消费 self）

**方案**: 改用字段访问 `.to`（类型 `Option<TxKind>`）+ `TxKind::to(&self) -> Option<&Address>` 方法。返回 `Option<&Address>` 而非 `Option<Address>`，与 sentinel 地址比较时需加 `&`。

### 8.5 RPC Server Trait 的 async_trait 要求

jsonrpsee 0.26 生成的 Server trait 内部使用 `#[async_trait]`。实现 Server trait 时必须标注 `#[async_trait::async_trait]`，否则报 "lifetime parameters or bounds do not match" 错误。

参考 Tempo 已有实现（如 `TempoAdminApiServer`）确认此模式。

### 8.6 RPC Trait 泛型约束

debankdefi/reth 使用 `TxReq: RpcObject` 约束 RPC trait 泛型参数。Tempo 的 reth 版本无 `RpcObject` trait。

**方案**: RPC trait 仅声明 `<TxReq>` 无显式约束，jsonrpsee proc macro 在生成 `*Server` trait 时自动添加 `DeserializeOwned + Clone + Send + Sync + 'static`。impl 侧通过 `RpcTxReq<Eth::NetworkTypes>` 绑定具体类型（对 Tempo 即 `TempoTransactionRequest`）。

### 8.7 `Output::into_data()` 返回值变更

revm 27: `Output::into_data() -> (Bytes, Option<Address>)` — 元组
revm 36: `Output::into_data() -> Bytes` — 直接返回 Bytes

debankdefi/reth 写的 `output.into_data().0.into()` 改为 `output.into_data()`。

### 8.8 `BlockId` 类型推断歧义

debankdefi/reth: `block.parent_hash().into()` — `B256 → BlockId` 隐式转换
Tempo reth: `B256 → BlockId` 存在多种 `Into` 实现（hash / number），编译器无法推断

**方案**: 使用显式构造 `BlockId::hash(block.parent_hash())`。

### 8.9 `evm_env_at` 的 Trait 归属

`evm_env_at` 在 Tempo reth 中定义在 `LoadState` trait 上。依赖链：
```
TraceExt
  └── Trace: LoadState + Call
                └── LoadState::evm_env_at()
```

保持 `Eth: TraceExt` 约束即可覆盖，但原因链与 debankdefi/reth 版本不同（后者的 `evm_env_at` 可能在不同 trait 上）。

---

## 9. Remaining Work

- [ ] CI/CD: `.github/workflows/build.debank.yml` — multi-arch Docker image 构建 + ECR 推送
- [ ] `cargo build --release` 全量编译
- [ ] 测试网连接验证 (Chain ID 42431)
- [ ] RPC 功能测试: `pre_traceMany` / `eth_multiCall` / `0xeeee` 地址
