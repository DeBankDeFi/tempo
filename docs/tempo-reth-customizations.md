# Tempo 基于 Reth 的改造分析

> Tempo 是一条专注于稳定币支付的区块链，基于 [Reth SDK](https://github.com/paradigmxyz/reth) 构建。
> 当前锁定 Reth commit `72d0e04`，引用 119 个 reth crate。
> 官方文档: https://docs.tempo.xyz/

## 目录

- [一、架构概览](#一架构概览)
- [二、共识层 — Threshold Simplex 替换 PoS](#二共识层--threshold-simplex-替换-pos)
- [三、交易类型 — TempoTransaction (Type 0x76)](#三交易类型--tempotransaction-type-0x76)
- [四、EVM 改造](#四evm-改造)
  - [4.1 自定义 EVM 配置](#41-自定义-evm-配置)
  - [4.2 TIP-1000 Gas 参数重定义](#42-tip-1000-gas-参数重定义t1-hardfork)
  - [4.3 自定义预编译合约 (9 个)](#43-自定义预编译合约-9-个)
  - [4.4 Gas 费收取流程](#44-gas-费收取流程)
  - [4.5 Fee AMM 机制](#45-fee-amm-机制)
  - [4.6 TIP-20 代币标准](#46-tip-20-代币标准)
- [五、Payload 构建 — 双通道出块](#五payload-构建--双通道出块)
- [六、交易池 — 双池架构](#六交易池--双池架构)
- [七、链规范 & Hardfork](#七链规范--hardfork)
- [八、节点组装 & 自定义 RPC](#八节点组装--自定义-rpc)
- [九、Sidecar 辅助服务](#九sidecar-辅助服务)
- [十、工具链 & 运维](#十工具链--运维)

---

## 一、架构概览

Tempo 复用 Reth 的存储、EVM 执行框架、RPC 基础设施和 P2P 网络层，在其上替换/定制了共识、交易类型、预编译、出块逻辑和交易池。架构上类似 OP Stack 使用 Reth 的方式。

```
┌─────────────────────────────────────────┐
│   Commonware Consensus Engine           │  独立 tokio runtime
│   (Threshold Simplex + BLS12-381 DKG)   │
└──────────────────┬──────────────────────┘
                   │ Engine API (forkchoice update)
┌──────────────────▼──────────────────────┐
│   Reth Execution Layer                  │
│   ┌──────────┐ ┌──────────┐ ┌────────┐ │
│   │TempoEVM  │ │TempoPool │ │Payload │ │  自定义组件
│   │+预编译    │ │ 双池架构  │ │双通道   │ │
│   └──────────┘ └──────────┘ └────────┘ │
│   ┌──────────┐ ┌──────────┐ ┌────────┐ │
│   │ Storage  │ │ Network  │ │  RPC   │ │  复用 Reth
│   │ (MDBX)   │ │ (devp2p) │ │(jsonrpc)│ │
│   └──────────┘ └──────────┘ └────────┘ │
└─────────────────────────────────────────┘
```

**节点组装** (`crates/node/src/node.rs`):

```rust
ComponentsBuilder::default()
    .pool(TempoPoolBuilder)           // 自定义双池
    .executor(TempoExecutorBuilder)   // 自定义 EVM + 预编译
    .payload(TempoPayloadBuilder)     // 双通道出块
    .consensus(TempoConsensusBuilder) // Simplex 共识验证
    .network(EthereumNetworkBuilder)  // 复用以太坊 P2P
```

---

## 二、共识层 -- Threshold Simplex 替换 PoS

Reth 默认使用以太坊 Beacon Chain PoS，Tempo 完全替换为 Commonware 的 Threshold Simplex BFT 共识。

| 方面 | Reth 默认 | Tempo 改造 |
|------|-----------|-----------|
| 共识算法 | Beacon Chain PoS | Threshold Simplex BFT（亚秒级最终性） |
| 密码学 | BLS12-381（验证者签名） | BLS12-381 **门限签名** + Ed25519 节点身份 |
| 验证者管理 | 信标链质押合约 | DKG（分布式密钥生成）按 epoch 轮换 |
| 运行架构 | 共识+执行合一 | 独立 tokio runtime，通过 Engine API 与 Reth 执行层通信 |
| 最终性 | 2 epoch (~12.8 min) | 亚秒级 |

### 核心组件

**共识引擎** (`crates/commonware-node/`):
- **Engine** (`consensus/engine.rs`) — 编排所有共识子组件
- **Application Automaton** (`consensus/application/`) — 向 Reth 提议 payload 并验证区块
- **Executor** (`executor/mod.rs`) — 发送 finalized block 的 forkchoice update 给 Reth 执行层
- **Marshal** — 区块交付和最终排序
- **Epoch Manager** (`epoch/manager/`) — 管理 epoch 生命周期和验证者集合

**DKG 分布式密钥生成** (`crates/dkg-onchain-artifacts/`, `crates/commonware-node/src/dkg/`):
- epoch 边界执行 DKG ceremony，为新验证者集合生成 BLS12-381 门限密钥
- 支持 full DKG（新多项式）和 resharing（复用现有多项式）
- 链上存储 `OnchainDkgOutcome`（epoch、shared public polynomial、下一轮验证者集合）

**SubBlock 机制** (`crates/primitives/src/subblock.rs`):
- 验证者产出子块，在共识最终确认前快速预确认交易
- 子块消耗 shared gas lane 的 gas 配额
- 通过 `SubBlockMetadata` 系统交易编码在区块中

**共识验证规则** (`crates/consensus/src/lib.rs`):
- 时间戳允许 3 秒未来偏差 (`ALLOWED_FUTURE_BLOCK_TIME_SECONDS`)
- Shared gas limit = 总 gas limit / 10 (`TEMPO_SHARED_GAS_DIVISOR`)
- Extra data 上限 10 KiB
- 区块末尾必须包含固定数量和顺序的系统交易

**P2P 通道注册**（基于 Commonware P2P）:
- Votes、Certificates、Resolver、Broadcaster、Marshal、DKG、Subblocks

---

## 三、交易类型 -- TempoTransaction (Type 0x76)

在标准以太坊交易类型之外，Tempo 新增原生 AA 交易类型。

### 交易信封 (TempoTxEnvelope)

```
crates/primitives/src/transaction/envelope.rs
```

| Type ID | 类型 | 说明 |
|---------|------|------|
| 0x00 | Legacy | 标准 |
| 0x01 | EIP-2930 | 标准 |
| 0x02 | EIP-1559 | 标准 |
| 0x04 | EIP-7702 | 标准 |
| **0x76** | **TempoTransaction** | **Tempo 原生 AA 交易** |

### TempoTransaction 核心字段

```
crates/primitives/src/transaction/tempo_transaction.rs
```

| 特性 | 字段 | 说明 |
|------|------|------|
| 批量调用 | `calls: Vec<Call>` | 单笔交易原子执行多个调用（payroll、结算、退款） |
| 2D Nonce | `nonce_key: U256` + `nonce: u64` | key=0 为协议 nonce，key>0 用户自定义（并行执行） |
| 过期 Nonce | `nonce_key = U256::MAX` | TIP-1009，30 秒环形缓冲区防重放，无需顺序 nonce |
| Fee 代付 | `fee_payer_signature: Option<Signature>` | 第三方 secp256k1 签名代付 gas |
| 定时交易 | `valid_before` / `valid_after` | 协议级时间窗口约束 |
| Fee Token | `fee_token: Option<Address>` | 指定用哪个稳定币支付 gas |
| 密钥授权 | `key_authorization: Option<SignedKeyAuthorization>` | 为账户添加访问密钥（含过期时间、支出限额） |
| Tempo 授权列表 | `tempo_authorization_list` | EIP-7702 变体，支持多种签名类型 |

**Call 结构**:
```rust
pub struct Call {
    pub to: TxKind,   // 调用目标
    pub value: U256,  // 转账金额
    pub input: Bytes, // calldata
}
```

**验证规则**: calls 非空；仅第一个 call 可以是 CREATE；后续必须是 CALL；`valid_before > valid_after`。

### 多签名类型系统

```
crates/primitives/src/transaction/tt_signature.rs
```

| 类型 | 长度 | 用途 |
|------|------|------|
| `Secp256k1` | 65 bytes | 标准 ECDSA |
| `P256` | 129 bytes | WebAuthn/安全芯片兼容 (r, s, pubkey_x, pubkey_y, pre_hash) |
| `WebAuthn` | 可变 (最大 2KB) | 含 authenticator data 的完整 WebAuthn 签名 |
| `Keychain` | 嵌套 | 通过 AccountKeychain 预编译的访问密钥签名，包裹上述任一类型 |

**签名验证额外 gas 开销**:
- P256: +5,000
- WebAuthn: +5,000 + calldata tokens x 16
- Keychain: 内层签名开销 + 900 (COLD_SLOAD + processing)

### 密钥授权 (Access Keys)

```
crates/primitives/src/transaction/key_authorization.rs
```

协议级账户抽象：让 root key（如硬件钱包）在交易中授权 access key（如手机 Passkey）给其他设备使用。

```rust
pub struct KeyAuthorization {
    pub chain_id: u64,
    pub key_type: SignatureType,       // Secp256k1 / P256 / WebAuthn
    pub key_id: Address,              // 公钥派生地址
    pub expiry: Option<u64>,          // Unix 时间戳 (None = 永不过期)
    pub limits: Option<Vec<TokenLimit>>, // 支出限额 (None = 无限)
}
```

典型用途：
- **设备授权** — root key 存冷钱包，给手机颁发 P256/WebAuthn access key（生物识别签名），日常小额支付不暴露 root key
- **权限限制** — access key 可设 TIP20 支出限额和过期时间，泄露损失有限
- **撤销** — root key 可随时通过 AccountKeychain 预编译撤销任何 access key

### Gas 余额计算

```rust
// 稳定币 gas 余额 = token 余额 (6 位小数) x 缩放因子 / gas_price
pub const TEMPO_GAS_PRICE_SCALING_FACTOR: U256 = 10^12;
// attodollars (10^-18) 转换为 microdollars (10^-6)
```

---

## 四、EVM 改造

### 4.1 自定义 EVM 配置

```
crates/evm/    — TempoEvmConfig, TempoBlockEnv, 区块执行上下文
crates/revm/   — TempoEvm, TempoTxEnv, 自定义 handler 和指令
```

| 方面 | 标准 Reth | Tempo |
|------|-----------|-------|
| Block Env | 秒级时间戳 | `TempoBlockEnv` 毫秒精度 (`timestamp_millis_part` 0-999) |
| Gas Limit | 单一 `gas_limit` | 双 gas limit: `general_gas_limit` + `shared_gas_limit` |
| 手续费 | ETH 原生代币 | 多稳定币 via TIP20 + FeeManager + AMM |
| Nonce | 1D 顺序 | 2D nonce + 过期 nonce |
| 签名验证 | Secp256k1 only | Secp256k1 / P256 / WebAuthn / Keychain |
| 自定义操作码 | 无 | `MILLIS_TIMESTAMP (0x4F)` 返回毫秒时间戳（T1C 后禁用） |
| Ommers | 支持 | 无（finality-based 共识） |

**TempoContext** (`crates/revm/src/evm.rs`):
```rust
type TempoContext<DB> = Context<TempoBlockEnv, TempoTxEnv, CfgEnv<TempoHardfork>, DB>
```

**TempoTxEnv** 扩展字段 (`crates/revm/src/tx.rs`):
- `fee_token` — fee token 地址
- `is_system_tx` — 系统交易标记
- `fee_payer` — 解析后的代付者地址
- `tempo_tx_env` (boxed) — AA 特性：多签名、时间约束、批量调用、2D nonce、子块标记、密钥授权

**Fee Token 推断优先级** (`crates/revm/src/common.rs`):

无 fee_payer 时按以下优先级确定 fee token，在第一个明确设置的层级停下，若该层级校验失败（非 USD TIP20 / 余额不足 / AMM 流动性不足）则交易直接失败，不继续向下：

1. 交易显式指定 `fee_token` 字段
2. 账户级别在 FeeManager 合约中存储的 fee token 偏好（`setUserToken`）
3. TIP20 交易推断 — 做 transfer/transferWithMemo/distributeReward 时直接用对应 TIP20 代币扣 gas（如转 12 USD，对方可能只收到 11.9，差额用于 gas）
4. StablecoinDEX swap 的输入代币
5. 回退到 `DEFAULT_FEE_TOKEN` (pathUSD, `0x20C0000000000000000000000000000000000000`)

每一层级的校验：
- 支付 gas 的 token 必须是 TIP20 且货币符号为 USD
- 用户必须拥有足够的 token 余额
- 若需 AMM swap（user_token != validator_token），必须有足够流动性

**TempoInvalidTransaction** — 30+ 错误变体，覆盖签名验证、时间约束、fee 支付、nonce 错误、密钥授权、子块限制等。

### 4.2 TIP-1000 Gas 参数重定义（T1 hardfork+）

```
crates/revm/src/gas_params.rs
```

| 操作 | 以太坊标准 | Tempo (T1+) |
|------|-----------|-------------|
| SSTORE set (无预加载) | 20,000 | **250,000** |
| CREATE / CREATE2 | 32,000 | **500,000** |
| 新账户开销 | 25,000 | **250,000** |
| Code deposit | 200/byte | **1,000/byte** |
| EIP-7702 auth per empty account | 25,000 | **12,500** |
| Auth account creation (ID 255) | - | **250,000** |

设计意图：大幅提高存储和合约部署 gas 成本，引导链的使用向支付场景倾斜。

### 4.3 自定义预编译合约 (9 个)

```
crates/precompiles/         — 预编译实现
crates/precompiles-macros/  — #[contract] 宏、Storable 派生宏
```

所有预编译通过 `tempo_precompile!` 宏包装，强制：仅允许 direct call（禁止 delegatecall）、自动初始化存储上下文、gas/refund 追踪。

| 地址 | 名称 | 用途 |
|------|------|------|
| `0x20C0...` (动态前缀) | **TIP20Token** | 原生 ERC20 实现：transfer、approve、balanceOf、角色管理 (PAUSE/ISSUER/BURN_BLOCKED)、暂停、奖励分发、transferWithMemo、合规策略联动 |
| `0x20FC0000...` | **TIP20Factory** | TIP20 代币创建工厂 |
| `0x403C0000...` | **TIP403Registry** | 基于角色的访问控制策略注册表（WHITELIST / BLACKLIST / ORACLE），支持策略复合 (TIP-1015) |
| `0xfeec0000...` | **TipFeeManager** | 手续费路由：用户 fee token 偏好存储、fee 收取、内置固定汇率 AMM（1:1 减 30bps 手续费，手续费归 LP）兑换到验证者偏好代币、手续费分发 |
| `0xdec00000...` | **StablecoinDEX** | 稳定币交易所：CLOB（中央限价订单簿）、tick-based 定价、价格-时间优先、最小订单 $100、限价单、市价 swap |
| `0x4E4F4E43...` | **NonceManager** | 2D nonce 存储 `mapping[address][nonce_key] = nonce`；过期 nonce 环形缓冲区（30 万容量、30 秒驱逐、gas 13,000） |
| `0xCCCCCCCC...00` | **ValidatorConfig** | 验证者元数据（fee recipient 等） |
| `0xCCCCCCCC...01` | **ValidatorConfigV2** | 升级版验证者配置（T1C+） |
| `0xAAAAAAAA...` | **AccountKeychain** | 账户密钥管理：root/access key 层级、支出限额 (TokenLimit)、密钥过期、签名验证与 keychain recovery |

**存储系统** (`crates/precompiles-macros/`):
- `#[contract]` 宏 — 自动生成 Solidity 兼容的 slot 分配和 getter/setter
- `#[derive(Storable)]` — 多 slot 结构体序列化
- `StorageCtx` — 线程本地上下文，追踪 gas、refund、static call 限制

### 4.4 Gas 费收取流程

```
crates/revm/src/handler.rs
crates/precompiles/src/tip_fee_manager/mod.rs
crates/precompiles/src/tip_fee_manager/amm.rs
```

每笔交易的 gas 费收取分三步：

```
交易执行前 (validate_tx_against_state)
│ 1. 确定 fee_token（按 4.1 节优先级）
│ 2. 确定 fee_payer（sender 或 fee_payer_signature 指定的代付者）
│ 3. collect_fee_pre_tx()
│    └─ 从 fee_payer 的 TIP20 余额预扣 max_fee (gas_limit x gas_price / SCALING_FACTOR)
│
▼ 交易执行（EVM）
│
▼ 交易执行后 (collect_fee_post_tx)
  1. 计算 actual_spending = gas_used x effective_gas_price
  2. refund = 预扣 - actual_spending → 退还到 fee_payer 的 TIP20 余额
  3. 若 user_token != validator_token → 通过 Fee AMM 把 actual_spending swap 成 validator_token
  4. accumulated_fees[validator][validator_token] += swap 后金额
  5. distribute_fees()（系统交易触发）→ 转到 validator 地址
```

**Gas 代付 (fee_payer_signature)**：第三方通过 secp256k1 签名代付 gas。签名内容为 `keccak256(MAGIC(0x78) || chain_id || sender || tx_hash)`，绑定到特定发送者和特定交易，不可重放。典型场景：用户 onboarding（新用户无余额时 App 代付）、商家补贴手续费。

### 4.5 Fee AMM 机制

内置在 TipFeeManager 预编译中，用于 user_token != validator_token 时自动兑换。

**核心特性**：
- **固定汇率 1:1**（减手续费），无价格发现、无预言机
- fee swap: `amount_out = amount_in x 0.997`（30 bps 手续费留在池子 reserve 里，归 LP）
- rebalance_swap: 反向操作（存入 validator_token 取出 user_token），15 bps 手续费，无套利经济激励
- 所有 fee token 强制 USD 计价，验证者通过 `setValidatorToken` 设置偏好（不可在自己出块时更改）

**流动性模型**：
- 任何人可调用 `mint()` 注入 validator_token 提供流动性
- LP 收益来自 30 bps 手续费（以 reserve 增长形式体现，`burn()` 时按份额取回）
- 协议不保证流动性，实际 LP 来源：Tempo 团队/基金会、验证者自身、token 发行方
- 流动性不足时该 token pair 的交易被拒（`InsufficientAmmLiquidity`）

**脱锚风险**：无预言机意味着固定 1:1 汇率不随市场变化。若某 USD 稳定币脱锚至 $0.70，攻击者可用脱锚币按面值付 gas（实际成本打 7 折），LP 承担损失。防线依赖 TIP403 合规策略（发行方暂停/冻结脱锚币）。

### 4.6 TIP-20 代币标准

所有 fee token 必须符合 TIP-20 标准，相比 ERC-20 的增强：

| 特性 | 说明 |
|------|------|
| **TIP-403 合规策略** | 每个 TIP20 绑定一个 policyId（注册在 TIP403Registry），转账时自动检查黑/白名单。发行方可 `pause()` 全局冻结代币 |
| **转账备注 (memo)** | `transferWithMemo(to, amount, memo)` 支持附带备注（订单 ID、invoice 等） |
| **法币符号 (currency)** | 每个 token 指定锚定法币（USD / EUR 等），仅 USD 代币可用于支付 gas |
| **角色管理** | PAUSE_ROLE（暂停）、ISSUER_ROLE（铸币）、BURN_BLOCKED_ROLE 等内置角色 |
| **奖励分发** | `distributeReward()` 内置奖励机制 |

TIP20 代币地址以 `0x20C0` 为前缀，一个币种 = 一个固定地址，其余额、角色、策略全部存储在该地址的 EVM storage slot 中。

---

## 五、Payload 构建 -- 双通道出块

```
crates/payload/builder/src/lib.rs
```

Tempo 实现严格的双通道 gas 分配，为 TIP-20 支付交易保留专用通道：

```
Block Gas Limit = 500M (TIP-1010)
├── Shared Lane (subblocks):   50M  (block_gas_limit / 10)
└── Non-Shared Lane:           450M
    ├── General Lane:           30M  (非支付交易上限)
    └── Payment Lane:          ~420M (TIP-20 支付交易专用)
```

### 支付交易分类（两级）

| 级别 | 用途 | 规则 |
|------|------|------|
| **v1** (共识级) | 区块验证时检查 `general_gas_limit` | `to` 地址前缀为 `0x20c0`（TIP20）；AA 交易所有 calls 都指向 TIP20 |
| **v2** (构建级) | 入池和出块时使用，更严格 | v1 + calldata 必须匹配已知 TIP20 支付方法选择器和 ABI 编码长度（防 DoS） |

### 出块流程

1. 计算各通道 gas 配额
2. 从交易池迭代交易：
   - 非支付交易超过 `general_gas_limit` 则标记无效
   - 支付交易使用 payment lane 配额
3. 处理 subblocks（消耗 shared gas）
4. 执行系统交易（始终成功）

### 监控指标

- `payment_transactions` — 支付交易计数
- `general_gas_used_last` / `payment_gas_used_last` — 各通道 gas 使用
- `general_gas_limit_last` / `payment_gas_limit_last` / `shared_gas_limit_last` — 各通道配额

---

## 六、交易池 -- 双池架构

```
crates/transaction-pool/src/lib.rs
crates/transaction-pool/src/tempo_pool.rs
crates/transaction-pool/src/tt_2d_pool.rs
```

### 双池路由

| 池 | 路由条件 | 数据结构 |
|----|---------|---------|
| **Protocol Pool** | `nonce_key == 0` 的 AA 交易 + 所有标准以太坊交易 | Reth 标准 `Pool<TempoTransactionValidator>` |
| **AA 2D Pool** | `nonce_key > 0` 的 AA 交易（含过期 nonce） | 自定义 `AA2dPool`，按 `(address, nonce_key)` 独立排序 |

出块时通过 `MergeBestTransactions` 迭代器按优先级合并两个池的交易流。

### AA 2D Pool 特性

- 按 `(address, nonce_key)` 独立管理 nonce 序列
- 过期 nonce 交易 (`nonce_key == U256::MAX`) 无顺序依赖
- 价格替换需满足 `PriceBumpConfig`
- Per-sender 交易数量限制（防 DoS）
- 最低优先级优先驱逐

### AMM 流动性缓存

```
crates/transaction-pool/src/amm.rs
```

`AmmLiquidityCache` 用于入池时判断用户 fee token 是否可兑换：

- 缓存最近 10 个区块的验证者代币偏好
- 入池检查：用户 fee token 是否有足够 AMM 流动性兑换为某个验证者偏好代币
- 若 user_token == validator_token 直接通过
- 新区块/reorg 时刷新缓存

### 池驱逐逻辑（6 类事件触发）

```
crates/transaction-pool/src/tempo_pool.rs — evict_invalidated_transactions()
```

| 事件 | 说明 |
|------|------|
| Keychain 密钥撤销 | 关联交易驱逐 |
| 支出限额更新 | 重新验证限额 |
| 支出限额消耗 | 从链上重读剩余额度 |
| 验证者代币偏好变更 | 仅在**无**验证者接受该代币时驱逐（避免大规模误驱逐） |
| 黑名单添加 (TIP403) | 检查 sender + fee manager 是否被新增黑名单 |
| 白名单移除 | fee payer 或 fee manager 被移出白名单时驱逐 |

### 池维护任务

节点启动时 spawn 专用 task (`txpool maintenance - tempo pool`)：
- 清理过期 AA 交易
- 同步 2D nonce 状态
- 刷新 AMM 缓存
- 处理 keychain 撤销

---

## 七、链规范 & Hardfork

```
crates/chainspec/src/hardfork.rs  — T0-T3 定义
crates/chainspec/src/spec.rs      — TempoChainSpec, TempoGenesisInfo
```

### 硬分叉序列

| Hardfork | Mainnet 时间 | 关键变更 |
|----------|-------------|---------|
| **T0** | Genesis | 初始状态 |
| **T1** | 2026-02-12 | 过期 nonce (TIP-1009)、TIP-1000 gas 参数 |
| **T1A** | 2026-02-12 | 移除 EIP-7825 单笔 gas 上限、General gas limit 固定 30M |
| **T1B** | 2026-02-23 | 密钥授权 gas 计算调整 |
| **T1C** | 2026-03-12 | ValidatorConfigV2、禁用 MILLIS_TIMESTAMP 操作码、Keychain V2 (type 0x04) |
| **T2** | 2026-03-31 | TIP-1015 复合转账策略、nonce key gas 增加 2x WARM_SLOAD |
| **T3** | 未定 | - |

所有 hardfork 底层映射到 revm `SpecId::OSAKA`，仅作为 Tempo 语义层的分叉激活点。激活方式仅支持 timestamp（无 block number）。

### 经济参数

| 参数 | T0 | T1+ |
|------|-----|------|
| Base Fee | 10^10 attodollars | 2x10^10 attodollars |
| General Gas Limit | 动态计算 | 固定 30M |
| Max TX Gas Limit | EIP-7825 Osaka (16.7M) | 30M |

### 网络

| 网络 | Chain ID | 名称 |
|------|----------|------|
| Mainnet | 4217 | Presto |
| Moderato | 42431 | Moderato |
| Testnet | 42429 | Andantino |

### TempoHeader 扩展

```rust
pub struct TempoHeader {
    pub general_gas_limit: u64,       // 非支付 gas 上限
    pub shared_gas_limit: u64,        // subblock gas 上限，预确认时每个验证者 gas_limit 上限
    pub timestamp_millis_part: u64,   // 亚秒精度 (0-999 ms) tempo 是 0.5s 出块，eth 标准 header 精度不够。
    pub inner: Header,                // 标准以太坊 header
}
```

---

## 八、节点组装 & 自定义 RPC

### 入口

```
bin/tempo/src/main.rs — 主入口，双 runtime 启动
bin/tempo/src/tempo_cmd.rs — CLI 子命令
```

**启动流程**:
1. 提取验证者密钥 → 配置 subblock 过滤
2. 启用 discv5 节点发现
3. 启动 Reth 节点（EVM + RPC + 网络）
4. 独立线程启动 Commonware 共识引擎
5. 两者通过 Engine API 通信

**运行模式**:
- 验证者模式：完整共识参与
- `--follow` / `--follow=auto`：跳过共识，跟随远程链
- `--dev`：开发模式，跳过共识

### CLI 子命令

```
consensus add-validator        — 添加验证者到合约
consensus rotate-validator     — 轮换到新身份
consensus generate-private-key — 生成 ed25519 密钥
consensus calculate-public-key — 派生公钥
consensus validators-info      — 查询验证者状态
init-from-binary-dump          — 从二进制快照加载状态
add / update / remove / list   — 扩展管理
```

### 自定义 RPC 命名空间

```
crates/node/src/rpc/
```

**`admin_`**:
- `admin_validatorKey()` — 返回节点 ed25519 公钥

**`consensus_`**:
- `consensus_getFinalization(query)` — 按高度查询 finalization
- `consensus_getLatest()` — 当前共识状态快照
- `consensus_subscribe()` — 订阅共识事件流 (Notarized / Finalized / Nullified)
- `consensus_getIdentityTransitionProof(from_epoch, full)` — DKG 身份转换证明

**`token_`** (未完成):
- `token_getRoleHistory(pagination)` — TIP20 角色变更历史
- `token_getTokens(pagination)` — 所有 TIP20 代币
- `token_getTokensByAddress(address, pagination)` — 地址关联代币

**`eth_` 扩展** (未完成):
- `eth_getTransactions(filter, pagination)` — 带过滤的分页交易查询

### 核心 Eth API 改造 (TempoEthApi)

| 改造点 | 说明 |
|--------|------|
| `eth_getBalance` | 返回占位值 `4242...U256`（Tempo 无原生代币） |
| `caller_gas_allowance` | 基于 fee token 余额 x 缩放因子 / gas_price 计算可支付 gas |
| `create_txn_env` | 2D nonce 处理：过期 nonce → nonce=0；2D nonce → 从 NONCE_PRECOMPILE 读取 |
| `pending_block_kind` | 返回 None（无法本地构建 pending block，需要共识数据） |
| SubBlock 广播 | 验证者密钥过滤防 DoS，仅转发匹配当前验证者的 subblock 交易 |
| Receipt 转换 | `TempoReceiptConverter`：提取 fee_token 和 fee_payer（假设非免费交易的最后一条 log 是 fee transfer 到 TIPFeeManager） |

### 共识层关键 CLI 参数

```
crates/commonware-node/src/args.rs — 50+ 可调参数
```

| 类别 | 关键参数 | 默认值 |
|------|---------|--------|
| 身份 | `--consensus.signing-key` | 必填（ed25519 私钥文件路径） |
| 身份 | `--consensus.signing-share` | 可选（BLS12-381 门限签名份额） |
| 网络 | `--consensus.listen-address` | 127.0.0.1:8000 |
| 出块 | `--consensus.time-to-prepare-proposal-transactions` | 200ms |
| 出块 | `--consensus.minimum-time-before-propose` | 450ms |
| 出块 | `--consensus.time-to-build-subblock` | 100ms |
| 超时 | `--consensus.wait-for-proposal` | 1200ms |
| 超时 | `--consensus.wait-for-notarizations` | 2s |
| 活性 | `--consensus.inactive-views-until-leader-skip` | 32 |
| 子块 | `--consensus.enable-subblocks` | false |
| 同步 | `--consensus.backfill-frequency` | 8 req/s |
| 心跳 | `--consensus.fcu-heartbeat-interval` | 5min |
| 拜占庭 | `--consensus.time-to-unblock-byzantine-peer` | 4h |
| 开发 | `--consensus.use-local-defaults` | false（启用后降低超时、放宽 IP 限制） |

### 共识事件 Feed

```
crates/commonware-node/src/feed/ — Actor 模式
```

共识层通过 Feed 模块将 Notarization/Finalization 事件暴露给 RPC 层：
- **Mailbox** 接收共识 `Activity` 消息（Reporter trait）
- **Actor** 处理事件、解析区块、按轮次排序后广播
- **FeedStateHandle** 为 RPC handler 提供只读状态（最新 notarized/finalized 区块、事件订阅）
- 维护跨 epoch 的验证者身份转换缓存（供轻客户端验证）

### Validator V1→V2 合约自动切换

```
crates/commonware-node/src/validators.rs
```

共识层读取链上验证者配置时自动选择合约版本：
- **V1** (`ValidatorConfig`): 简单注册表，`publicKey` + `active` + `inbound/outbound`
- **V2** (`ValidatorConfigV2`, T1C+): 增加 `addedAtHeight` / `deactivatedAtHeight` 生命周期追踪、ed25519 签名所有权证明
- 自动切换逻辑：检查 T2 hardfork 是否激活 → V2 合约是否已初始化 → 初始化高度 <= 当前区块

---

## 九、Sidecar 辅助服务

```
bin/tempo-sidecar/
```

tempo-sidecar 是节点伴生服务，包含 4 个组件：

| 组件 | 用途 |
|------|------|
| **FeeAMMMonitor** | 监控 Fee AMM 池子 reserve，暴露 Prometheus 指标（轮询间隔 5s） |
| **SimpleArb** | **内置套利 bot**，监控 TIP20Factory 和 FeeAMM 事件，自动调用 `rebalanceSwap` 平衡池子 |
| **SyntheticLoad** | 合成负载生成器，多钱包 Zipf 分布的 TIP-20 转账（压测用） |
| **TxLatencyMonitor** | 交易延迟追踪，WebSocket 订阅 pending tx → 计算提交到上链的 histogram |

> **SimpleArb 解答了 Fee AMM 再平衡的问题**：官方提供了自动化套利 bot 作为基础设施，确保池子不会长期失衡。

---

## 十、工具链 & 运维

| 模块 | 路径 | 说明 |

| 模块 | 路径 | 说明 |
|------|------|------|
| **Alloy SDK** | `crates/alloy/` | `TempoNetwork` 类型定义、`TempoTransactionRequest` 构建器、Nonce Filler（Random2D / Expiring / NonceKey）、Provider 扩展（keychain 查询） |
| **系统合约** | `crates/contracts/` | 预部署 Multicall3、Permit2、CreateX、Safe Deployer、Arachnid CREATE2 Factory |
| **Validator Config 签名** | `crates/validator-config/` | ed25519 签名构造/验证（addValidator / rotateValidator 的消息哈希和签名校验） |
| **Faucet** | `crates/faucet/` | 测试网水龙头 |
| **扩展系统** | `crates/ext/` | CLI 插件系统：从 GitHub releases 下载扩展、minisign 签名验证、注册表管理、Claude Code skill 集成 |
| **Telemetry** | `crates/telemetry-util/` | 结构化日志工具（错误链格式化、Duration 格式化）；OTLP 日志导出、Prometheus metrics push |
| **E2E 测试** | `crates/e2e/` | 确定性集成测试：模拟 P2P 网络 + DKG ceremony + 共识活性 + 验证者迁移（V1→V2） |
| **Bench** | `bin/tempo-bench/` | Max-TPS 基准测试：支持 TIP-20 转账 / DEX 下单 / ERC-20 转账混合负载、3 种 nonce 策略 |
| **tempoup** | `tempoup/` | 官方安装器：`curl -L https://tempo.xyz/install \| bash`，GPG 签名验证，自动配置 shell PATH |
| **xtask** | `xtask/` | 构建任务：生成 genesis.json（含 DKG outcome）、devnet/localnet Docker Compose、state bloat 测试数据 |
| **TIPs** | `tips/` | 协议改进提案（18 个，见下节） |
| **contrib** | `contrib/` | Grafana 监控面板、Prometheus 配置、bench Docker Compose 栈、交叉编译 Dockerfile |

### Alloy SDK 示例

```
crates/alloy/examples/
├── batch_payments.rs      — 单笔交易批量支付
├── transfer.rs            — 单笔转账
├── transfer_with_memo.rs  — 带 memo 转账
├── mint_tokens.rs         — 铸币
├── burn_tokens.rs         — 销毁
├── get_block_number.rs    — 查询区块高度
├── get_balance.rs         — 查询余额
└── watch_transfers.rs     — 监听转账事件
```

### TIPs 协议提案概览

```
tips/
```

**已激活（Mainnet T1-T2）**:

| TIP | 名称 | 要点 |
|-----|------|------|
| 1000 | State Creation Cost Increase | SSTORE 250k gas、CREATE 500k gas、防状态膨胀（1TB 攻击成本 ~$50M） |
| 1009 | Expiring Nonces | `nonce_key=MAX` 触发 30 秒环形缓冲区、无需顺序 nonce |
| 1010 | Mainnet Gas Parameters | 总 500M gas、Base fee 2x10^10、TIP-20 转账 ~50k gas ≈ 0.1 美分 |
| 1015 | Compound Transfer Policies | 复合策略：`senderPolicyId` + `recipientPolicyId` + `mintRecipientPolicyId` |
| 1036 | T2 Bug Fixes | 13 项审计修复（tx.origin 校验、自我代付拒绝、DEX pause 检查等） |

**Draft/未来**:

| TIP | 名称 | 要点 |
|-----|------|------|
| 1001 | Place-only Mode | StablecoinDEX 平滑 quote token 过渡（新交易对先建流动性再切换） |
| 1011 | Enhanced Access Key Permissions | 周期性支出限额自动重置（订阅模型）、目标地址白名单 |
| 1017 | Validator Config V2 | 生命周期追踪、ed25519 所有权证明、公钥永久保留 |
| **1022** | **Virtual Addresses** | **TIP-20 存款自动转发**：虚拟地址 `[masterId][MAGIC][userTag]`、预编译级别原子转发、消除 sweep 交易 |

> TIP-1022 是重要的未来特性 -- 为交易所/支付平台提供协议级虚拟存款地址，无需 sweep 交易即可自动归集。

---

## 总结

Tempo 在 Reth 之上做了**全栈级别的深度改造**，核心目标是将通用 EVM 链改造为**稳定币支付专用链**：

| 层级 | 复用 Reth | Tempo 定制 |
|------|-----------|-----------|
| **共识** | - | Threshold Simplex BFT + DKG（完全替换） |
| **交易类型** | Legacy/EIP-2930/1559/7702 | TempoTransaction (0x76): 批量调用、2D nonce、多签名、fee 代付、定时交易 |
| **EVM** | 基础 revm 执行框架 | 自定义 gas 参数、双 gas limit、毫秒时间戳、fee token 推断、9 个预编译 |
| **预编译** | 标准以太坊预编译 | TIP20 代币、合规策略、Fee AMM、2D Nonce、Keychain AA |
| **出块** | 基础 payload builder 框架 | 双通道出块（支付 vs 通用），v1/v2 支付分类 |
| **交易池** | 基础 Pool 框架 | 双池架构 (Protocol + AA 2D)，AMM 流动性缓存，6 类驱逐逻辑 |
| **链规范** | ChainSpec 框架 | 自定义 hardfork (T0-T3)，无原生代币，timestamp-only 激活 |
| **RPC** | jsonrpc 框架 | 4 个自定义命名空间，eth_getBalance 重写，fee token gas 计算 |
| **网络** | devp2p (完全复用) | - |
| **存储** | MDBX (完全复用) | - |
| **Sidecar** | - | FeeAMM 监控、SimpleArb（池子自动再平衡）、合成负载、延迟追踪 |
| **工具链** | - | tempoup 安装器、xtask genesis 生成、bench Max-TPS、Grafana 监控 |
