# Tempo DeBank Custom RPC Design Document

## 1. Background

Tempo 是 Stripe + Paradigm 联合孵化的支付专用 L1（2026-03-18 主网上线），基于 Reth SDK 构建。DeBank 需要在 Tempo 节点上提供两个自定义 RPC 端点：`pre_traceMany` 和 `eth_multiCall`，用于交易预执行追踪和批量合约调用。

## 2. Architecture

### 2.1 Mega-reth 模式

采用与 mega-reth 相同的隔离模式：在 Tempo 仓库中创建独立的 `crates/debank-rpc/` crate，通过 `NodeAddOns::launch_add_ons()` 闭包注册自定义 RPC。不修改任何 reth 核心 crate，所有 DeBank 代码隔离在独立 crate 中。

优势：
- 与 reth 核心零耦合，后续 rebase upstream 冲突最小
- 不需要改 `RethRpcModule` 枚举、`rpc-builder`、`rpc-eth-api` 核心 trait
- 可独立编译和测试

### 2.2 仓库关系

```
tempoxyz/tempo (upstream)
  └── DeBankDeFi/tempo (fork, branch: debank)
        └── crates/debank-rpc/  (新增)
```

### 2.3 版本依赖

| 组件 | 版本 |
|------|------|
| reth | rev `a0b0d88` (v1.11.3) |
| revm | 36.0.0 |
| alloy | 1.6.1 |
| jsonrpsee | 0.26.0 |
| revm-inspectors | 0.36.1 |

### 2.4 参考实现来源

| 用途 | 来源 | revm 版本 |
|------|------|-----------|
| `pre_traceMany` 实现 | debankdefi/reth v1.6.0 | 27.0.3 |
| `eth_multiCall` 实现 | debankdefi/reth v1.6.0 | 27.0.3 |
| RPC 注册模式 | chaintable/mega-reth | 33.1.0 |

无现成的 revm 36 兼容版本，需从 revm 27 适配移植。

## 3. Crate Structure

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

## 4. RPC Interface

### 4.1 `pre_traceMany`

**Wire format**: `pre_traceMany`

```
Namespace: pre
Method:    traceMany
```

**Parameters** (positional):
| # | 名称 | 类型 | 必填 |
|---|------|------|------|
| 0 | transactions | `Vec<TransactionRequest>` | Y |
| 1 | block_id | `BlockId` | N (default: latest) |
| 2 | state_overrides | `StateOverride` | N |
| 3 | block_overrides | `BlockOverrides` | N |

**返回**: `Vec<PreResult>`

```json
{
  "trace": [LocalizedTransactionTrace, ...],
  "logs": [Log, ...],
  "error": { "code": 1000, "msg": "..." } | null,
  "gasUsed": 21000
}
```

**语义**:
- 在指定 block 的 parent state 上顺序执行交易
- 每笔 tx 执行后 commit state，后续 tx 可见前序 tx 的状态变更
- 使用 parity tracing inspector 采集 trace
- state_overrides 仅对首笔 tx 生效（`.take()` 语义）

**错误码** (`PreErrorCode`):
| 值 | 含义 |
|----|------|
| 1000 | Unknown (EVM 执行异常) |
| 1001 | InsufficientBalance (Halt) |
| 1002 | Reverted |

### 4.2 `eth_multiCall`

**Wire format**: `eth_multiCall`

```
Namespace: eth
Method:    multiCall
```

**Parameters** (positional):
| # | 名称 | 类型 | 必填 |
|---|------|------|------|
| 0 | requests | `Vec<TransactionRequest>` | Y |
| 1 | block_number | `BlockId` | N (default: latest) |
| 2 | fast_fail | `bool` | N (default: false) |
| 3 | use_parallel | `bool` | N (保留，未使用) |
| 4 | disable_cache | `bool` | N (default: false) |
| 5 | state_overrides | `StateOverride` | N |
| 6 | block_overrides | `BlockOverrides` | N |

**返回**: `MultiCallResp`

```json
{
  "results": [{
    "code": 0,
    "err": "",
    "fromCache": false,
    "result": "0x...",
    "gasUsed": 21000,
    "timeCost": 0.001
  }, ...],
  "stats": {
    "blockNum": 123456,
    "blockHash": "0x...",
    "blockTime": 1710000000,
    "success": true,
    "cacheEnabled": true
  }
}
```

**语义**:
- 在指定 block state 上独立执行每笔 call（不 commit，互不影响）
- `fast_fail=true` 时，首次失败后所有后续 call 返回相同错误
- `to == 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` 走 native token ERC-20 模拟
- state_overrides 仅对首笔非 native token call 生效

**错误码** (`MultiCallErrorCode`):
| 值 | 含义 |
|----|------|
| 0 | Success |
| -40000 | CodeTxArgs (参数错误) |
| -40001 | NativeMethodNotFound |
| -40013 | EVMCancelled (Halt) |
| -40014 | EVMReverted |

## 5. Native Token ERC-20 Simulation

对 `0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` 地址的调用拦截处理，不经过 EVM：

| Selector | 方法 | 返回 |
|----------|------|------|
| `0x70a08231` | `balanceOf(address)` | 账户 native balance (U256) |
| `0x18160ddd` | `totalSupply()` | 1 |
| `0x313ce567` | `decimals()` | 18 |
| `0x06fdde03` | `name()` | ABI encode "ETH" |
| `0x95d89b41` | `symbol()` | ABI encode "ETH" |

**Tempo 特殊性**: Tempo 的 gas 用 USDC/USDT 支付，native balance 可能始终为 0，但接口保持一致。

## 6. RPC Registration

注册位置：`crates/node/src/node.rs` `TempoAddOns::launch_add_ons`

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

- `PreApi`: `merge_configured` — 无条件注册（独立 `pre` namespace）
- `DebankEthExt`: `merge_if_module_configured(Eth)` — 仅当 `eth` 模块启用时注册（扩展 `eth` namespace）

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

`TraceExt` 展开为: `LoadTransaction + LoadBlock + SpawnBlocking + Trace + Call`

依赖链：`Call` → `LoadState`（提供 `evm_env_at`）、`SpawnBlocking`（提供 `spawn_with_state_at_block`）

### DebankEthExt

```rust
impl<Eth> DebankEthExt<Eth>
where
    Eth: EthApiTypes + EthCall + 'static,
    RpcTxReq<Eth::NetworkTypes>: AsRef<TransactionRequest>,
```

`EthCall` 展开为: `EstimateCall + Call + LoadPendingBlock + LoadBlock + FullEthApiTypes`

额外约束 `AsRef<TransactionRequest>` 用于 native token 地址检测（访问 `.to` 字段和 `.input`）。

## 8. Dependencies

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

所有依赖均通过 workspace 统一管理，与 Tempo 主项目版本一致。

## 9. Key Design Decisions

以下决策点是从 debankdefi/reth (revm 27) 移植到 Tempo reth (revm 36) 过程中的非直觉适配，不能直接复制原始代码。

### 9.1 `inspect_commit` 不存在 → inspect + commit 两步

debankdefi/reth 在 `Trace` trait 上添加了自定义的 `inspect_commit` 方法（内部调 `evm_with_env_and_inspector` + `transact_commit`）。Tempo 依赖的 reth rev `a0b0d88` 没有这个方法。

**方案**: 调 `Trace::inspect(&mut db, evm_env, tx_env, &mut inspector)` 拿到 `ResultAndState { result, state }`，再 `db.commit(state)` 手动提交。

关键点：`inspect` 签名 `fn inspect<DB>(db: DB, ...)` 接受泛型 DB，传 `&mut db`（可变借用）后所有权仍在调用方，函数返回后可继续调 `db.commit()`。inspector 同理用 `&mut inspector` 传入，返回后仍可调 `inspector.into_parity_builder()` 提取 trace。

### 9.2 `StateCacheDb` 底层类型变更

debankdefi/reth: `StateCacheDb = CacheDB<StateProviderDatabase<...>>`
Tempo reth: `StateCacheDb = State<StateProviderDatabase<StateProviderTraitObjWrapper>>`

两者都实现 `Database` + `DatabaseCommit`，但 `State::commit()` 内部走 `apply_transition()`（维护 bundle state），而 `CacheDB::commit()` 直接修改内存 map。代码层面透明，但状态管理机制不同。

### 9.3 `ExecutionResult` 结构变化

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

### 9.4 `TransactionRequest::to()` 语义变更

alloy 旧版: `to(&self) -> Option<Address>` 是 getter
alloy 1.6.1: `to(self, addr: Address) -> Self` 是 builder 方法（消费 self）

**方案**: 改用字段访问 `.to`（类型 `Option<TxKind>`）+ `TxKind::to(&self) -> Option<&Address>` 方法。返回 `Option<&Address>` 而非 `Option<Address>`，与 sentinel 地址比较时需加 `&`。

### 9.5 RPC Server Trait 的 async_trait 要求

jsonrpsee 0.26 生成的 Server trait 内部使用 `#[async_trait]`。实现 Server trait 时必须标注 `#[async_trait::async_trait]`，否则报 "lifetime parameters or bounds do not match" 错误。

参考 Tempo 已有实现（如 `TempoAdminApiServer`）确认此模式。

### 9.6 RPC Trait 泛型约束

debankdefi/reth 使用 `TxReq: RpcObject` 约束 RPC trait 泛型参数。Tempo 的 reth 版本无 `RpcObject` trait。

**方案**: RPC trait 仅声明 `<TxReq>` 无显式约束，jsonrpsee proc macro 在生成 `*Server` trait 时自动添加 `DeserializeOwned + Clone + Send + Sync + 'static`。impl 侧通过 `RpcTxReq<Eth::NetworkTypes>` 绑定具体类型（对 Tempo 即 `TempoTransactionRequest`）。

### 9.7 `Output::into_data()` 返回值变更

revm 27: `Output::into_data() -> (Bytes, Option<Address>)` — 元组
revm 36: `Output::into_data() -> Bytes` — 直接返回 Bytes

debankdefi/reth 写的 `output.into_data().0.into()` 改为 `output.into_data()`。

### 9.8 `BlockId` 类型推断歧义

debankdefi/reth: `block.parent_hash().into()` — `B256 → BlockId` 隐式转换
Tempo reth: `B256 → BlockId` 存在多种 `Into` 实现（hash / number），编译器无法推断

**方案**: 使用显式构造 `BlockId::hash(block.parent_hash())`。

### 9.9 `evm_env_at` 的 Trait 归属

`evm_env_at` 在 Tempo reth 中定义在 `LoadState` trait 上。依赖链：
```
TraceExt
  └── Trace: LoadState + Call
                └── LoadState::evm_env_at()
```

保持 `Eth: TraceExt` 约束即可覆盖，但原因链与 debankdefi/reth 版本不同（后者的 `evm_env_at` 可能在不同 trait 上）。

## 10. Remaining Work

- [ ] CI/CD: `.github/workflows/build.debank.yml` — multi-arch Docker image 构建 + ECR 推送
- [ ] `cargo build --release` 全量编译
- [ ] 测试网连接验证 (Chain ID 42431)
- [ ] RPC 功能测试: `pre_traceMany` / `eth_multiCall` / `0xeeee` 地址
