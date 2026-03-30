# Upstream Merge Changelog: Tempo v1.4.3 -> v1.5.1

## Overview

- **Source**: [tempoxyz/tempo](https://github.com/tempoxyz/tempo) tag `v1.5.1` (commit `a5ea176b`)
- **Commits**: 86 commits (v1.4.3 -> v1.5.0: 81 commits, v1.5.0 -> v1.5.1: 5 hotfix commits)
- **Files changed**: 197 files (+17,024 / -5,320 lines)
- **Release path**: v1.5.1 is a hotfix branch off v1.5.0 (not on main)，修复关键内存安全问题

### Key Version Changes

| Dependency | v1.4.3 | v1.5.1 |
|---|---|---|
| workspace version | 1.4.3 | 1.5.1 |
| reth | rev `a0b0d88` | rev `72d0e04` |
| revm | 34.0.0 | 36.0.0 |
| alloy-evm | 0.27.3 | 0.29.2 |
| revm-inspectors | 0.34.2 | 0.36.1 |
| rust-version (MSRV) | 1.85.0 | 1.93.0 |
| edition | 2021 | 2024 |

---

## 1. CRITICAL: v1.5.1 Memory Safety Hotfixes

从 v1.5.0 分叉的 hotfix 分支，修复预编译存储层的内存安全问题。**必须优先合入。**

| Commit | Description |
|---|---|
| `7027926e` | fix(precompiles): limit dyn storage len to avoid OOM issues |
| `5f8f0290` | fix: tampered short-string state (字符串存储篡改防护) |
| `ea9759e1` | fix: bound dyn size via OOG (动态大小分配 gas 保护) |
| `47767f72` | fix: guard against `HashMap::with_capacity` (内存分配安全) |
| `a5ea176b` | chore: bump version to v1.5.1 |

**影响范围**: `crates/precompiles/src/storage/types/{bytes_like,vec,set}.rs`, `crates/node/tests/it/eth_call.rs`

---

## 2. Consensus & Validator (TIP-1017)

ValidatorConfigV2 是本次升级最大的功能变更，完全重新设计了验证器配置系统。

| Commit | Description |
|---|---|
| `3b4b1b71` | feat: validator config v2 all changes (#2910) |
| `e212d4d1` | feat(consensus): implement TIP 1017, ValConfigV2 (#2716) - **核心实现** |
| `eaffdbb0` | fix(consensus): snapshot V1 validator count during migration (#3147) |
| `82b3d2ac` | fix(dkg): ensure DKG not read past boundary (#3166) |
| `034d54d2` | fix(consensus): DKG ignores blocks from prior epochs (#3271) |
| `669a717b` | chore(consensus): only show network identity when entering epoch (#3201) |
| `244b712c` | feat: introduce consensus pubkey label for telemetry metrics (#3096) |
| `ee88a96c` | feat: tempo consensus validator CLI commands (#2841) |
| `d4d5581f` | feat(cli): allow add-validator and rotate-validator to sign inline (#3214) |
| `9bd49296` | chore: DKG e2e test for wiped consensus state (#3074) |
| `24dc3881` | test(invariants): improve ValidatorConfigV2 coverage (#3211) |
| `7b619478` | refactor(precompiles): remove unused get_validators from ValidatorConfigV2 (#3213) |

**影响范围**: `crates/commonware-node/`, `crates/precompiles/src/validator_config_v2/`, `crates/e2e/`, `bin/tempo/src/tempo_cmd.rs`

---

## 3. Hardfork Support

| Commit | Description |
|---|---|
| `2652835e` | feat(chainspec): add T3 hardfork (#3208) |
| `5e64ac69` | set T2 activation times for moderato and presto (#3251) |
| `9ca43fcf` | docs(tip-1036): T2 meta TIP (#3205) |

**影响范围**: `crates/chainspec/src/hardfork.rs`, `crates/chainspec/src/spec.rs`, genesis JSON files

---

## 4. Precompile & Security Fixes

| Commit | Description |
|---|---|
| `3c91efd3` | fix(precompiles): built-in support for ecrecover + keccak (#3155) |
| `d65bf399` | chore: failed-closed account keychain (#3250) - 安全强化 |
| `d92757bb` | fix(account-keychain): require tx.origin for admin ops on T2 (#3202) |
| `fe251e3d` | fix(precompiles): craft built-in policy types' data (#3203) |
| `7ee81506` | fix(tip403): reject legacy invalid policy types (#3188) |
| `b549b549` | fix(precompiles): properly handle T2 policy errors in dex (#3015) |
| `c4a64cbd` | feat(contracts): add is_* helpers for PolicyType enum (#2912) |
| `fdd11a42` | chore(precompiles): assert LIFO order in nested checkpoint usage (#3094) |
| `af26452a` | fix(tips): harden TempoStreamChannel close/tombstone and deposit checks (#3136) |
| `dc33be6a` | feat(alloy): add account keychain provider helpers (#3133) |

**影响范围**: `crates/precompiles/`, `crates/contracts/`, `crates/alloy/src/provider/`

---

## 5. Transaction Pool & Fee Management

| Commit | Description |
|---|---|
| `5355fd39` | fix(txpool): strict payment calldata validation in pool and builder (#3099) |
| `ec1cb4d0` | fix(txpool): deduplicate validator token changes using AddressMap (#3265) |
| `87af1246` | fix(fees): reject self-sponsored fee payer signatures (#3200) |
| `50d2eb17` | fix(pool): resolve compound policy sub-policy IDs for eviction checks (#3196) |
| `20aecec7` | fix: check 403 policy updates against fee manager (#3220) |
| `484fe2be` | fix(test): handle pool rejection in testnet (#3110) |
| `ebdf167a` | chore: DRY fn is_payment and rename to v1 (#3123) |

**影响范围**: `crates/transaction-pool/`, `crates/payload/builder/`

---

## 6. New Features

| Commit | Description |
|---|---|
| `bbce2e3b` | TIP 1022: Virtual forwarding addresses (#2852) |
| `56080311` | feat(chainspec): add no_std support (#3019) |
| `017fb86d` | feat(tempo-contracts): feature-gated serde support for sol! types (#3000) |
| `5f9e1758` | TIP-1028: Address-Level Receive Policies (#3051) - **已 revert** |

---

## 7. Dependency Updates

| Commit | Description |
|---|---|
| `9ff06331` | deps: update reth from main (2026-03-20) (#3241) - rev `72d0e04` |
| `2abd3b57` | chore: bump reth to 2a94eed (#3216) |
| `70f53d43` | chore: bump reth (#3160) |
| `260a49df` | chore: bump reth to latest tempo/v1.10.2 (#3117) |
| `41c3f791` | chore: bump reth to latest main (#3108) |
| `9fa73d89` | chore: bump revm-inspectors to 0.36.1 (#3142) |
| `241889fc` | fix: bump tar 0.4.44 -> 0.4.45 (RUSTSEC-2026-0067, RUSTSEC-2026-0068) (#3263) |
| `39109212` | chore(deps): allow aws-lc advisories and bump rustls-webpki (#3256) |

---

## 8. RPC & Refactoring

| Commit | Description |
|---|---|
| `4390c022` | refactor(rpc): remove unsafe is_t1c_active hack (#3255) |
| `f9d9acc6` | fix: provider output and correctly fetch chain ID (#3258) |
| `e16eec11` | docs(alloy): use Moderato RPC URLs in README examples (#3266) |
| `2d71f441` | refactor: remove newPayload call for proposed blocks (#3138) |
| `3861fac8` | chore(evm): use full path import for TIP_FEE_MANAGER_ADDRESS (#3054) |

---

## 9. Payload Builder & Observability

| Commit | Description |
|---|---|
| `2d0b4b6e` | feat(payload): emit per-lane gas metrics for block utilisation dashboard (#3190) |
| `bb956f26` | feat(payload): add pool fetch duration metric (#3121) |
| `89a6aee8` | feat(builder): add build outcome, failure, and subblock skip metrics (#3104) |

---

## 10. CI/CD & Tooling

| Commit | Description |
|---|---|
| `e0c74df5` | ci: add nightly reth dependency update workflow (#3068) - 新增 `.github/workflows/update-reth.yml` |
| `9d6d2b4b` | ci: add upstream reth diff summary to deps update PR (#3246) |
| `39d1a39d` | test(rpc): dedicate CI job for RPC matrix tests with retry logic (#3217) |
| `72629787` | test(rpc): add devnet test matrix (#3116) |
| `bc36ec0e` | ci(bench): tempo-bench samply & tracy profiling support (#3095) |
| `05642491` | feat: upload clickhouse benching runs (#3264) |
| `4a7822fe` | chore(ci): add timeouts on e2e tests, succeed flaky tests (#3197) |
| `0989bd3f` | test: disable retries in ci-flaky nextest profile (#3222) |
| `e387ca89` | fix(ci): increase timeout for benchmark to 5 hours (#3055) |
| `9612dd1c` | chore(ci): remove tons of Setting user token logs in bloat bench (#3073) |

---

## 11. Benchmarking

| Commit | Description |
|---|---|
| `54e136ec` | feat(bench): add --baseline-hardfork and --feature-hardfork flags (#3223) |
| `1a4e396a` | feat(bench): add --mpp-weight for MPP channels benchmarking (#3153) |
| `33d94fcf` | feat(bench): split failed vs timed out transaction counters (#3184) |
| `eecaea79` | chore(cli): add more progress logs to bloater tool (#3052) |

---

## 12. Documentation

| Commit | Description |
|---|---|
| `2362da37` | docs(precompiles): add comprehensive comments + tempo docs links (#2923) |
| `693d34ef` | docs(tip-1016): add 7702 delegation gas split and precompile coverage (#3091) |
| `42a44f30` | describe TIP process (#2909) |
| `0bc78a96` | docs(tip-1015): clarify mutability of compound policies (#3177) |

---

## 13. tempoup CLI Tool

| Commit | Description |
|---|---|
| `f88347b3` | fix(tempoup): move binary instead of overwriting for Linux (#3195) |
| `bb2036f5` | fix(tempoup): create TEMPO_DIR before writing env file (#3179) |
| `e8f7b612` | fix(tempoup): make it compatible with bash 3.3 (#3174) |
| `ed25d8e4` | fix(tempoup): install to ~/.tempo/bin and configure shell PATH (#3154) |
| `d10e5515` | fix(ext): do not call tempoup second time (#3158) |
| `93c4f258` | fix(ext): strip tempo- prefix from extension names (#3131) |

---

## 14. Reverted Changes

以下功能在 v1.4.3->v1.5.0 周期中被引入后又 revert，表明需要进一步完善：

| Commit | Description |
|---|---|
| `91404317` | revert: remove TIP-1028 from main (#3159) - Address-Level Receive Policies |
| `f42512d1` | revert: remove getFeeToken() view from IFeeManager (TIP-1007) (#2963) |

---

## 15. Version Bump Commits

| Commit | Description |
|---|---|
| `6d9f73c1` | chore: release v1.4.1 (#3089) |
| `e33d1650` | chore: bump version to v1.4.2 (#3145) |
| `a55f9b61` | chore: bump version to v1.5.0 (#3274) |

---

## DeBank Fork Impact Assessment

### 无冲突 (DeBank 纯新增)
- `crates/debank-rpc/` - 完整自定义 RPC 模块
- `Dockerfile.debank` - 自定义构建
- `.github/workflows/build.debank.yml`, `release.debank.yml` - CI/CD
- `docs/` - DeBank 文档

### 需要手动合并
- `Cargo.toml` - workspace members + deps (保留 debank-rpc)
- `crates/node/Cargo.toml` - debank-rpc dep
- `crates/node/src/node.rs` - DeBank RPC 注册代码

### 需要验证兼容性
- `crates/debank-rpc/` 依赖的 reth API (reth rev `a0b0d88` -> `72d0e04`) 可能有 breaking changes
- revm/revm-inspectors 版本升级后的 trait 兼容性
