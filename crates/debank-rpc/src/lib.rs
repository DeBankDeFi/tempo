//! DeBank custom RPC extensions for Tempo.
//!
//! Provides `pre_traceMany` and `eth_multiCall` endpoints.

pub mod erc20_handle;
pub mod multi_call;
pub mod pre;
pub mod types;

// Re-export key types for registration
pub use multi_call::DebankEthExt;
pub use pre::PreApi;
pub use types::{MultiCallResp, PreResult};

use alloy_eips::BlockId;
use alloy_rpc_types_eth::{BlockOverrides, state::StateOverride};
use jsonrpsee::core::RpcResult;

/// RPC trait for `pre` namespace.
#[jsonrpsee::proc_macros::rpc(server, namespace = "pre")]
pub trait DebankPreApi<TxReq> {
    /// Execute multiple transactions sequentially, returning execution traces for each.
    #[method(name = "traceMany")]
    async fn trace_many(
        &self,
        transactions: Vec<TxReq>,
        block_id: Option<BlockId>,
        state_overrides: Option<StateOverride>,
        block_overrides: Option<Box<BlockOverrides>>,
    ) -> RpcResult<Vec<PreResult>>;
}

/// RPC trait extending `eth` namespace with `multiCall`.
#[jsonrpsee::proc_macros::rpc(server, namespace = "eth")]
pub trait DebankEthExtApi<TxReq> {
    /// Execute multiple calls in a single request, returning results for each.
    #[method(name = "multiCall")]
    async fn multi_call(
        &self,
        requests: Vec<TxReq>,
        block_number: Option<BlockId>,
        fast_fail: Option<bool>,
        use_parallel: Option<bool>,
        disable_cache: Option<bool>,
        state_overrides: Option<StateOverride>,
        block_overrides: Option<Box<BlockOverrides>>,
    ) -> RpcResult<MultiCallResp>;
}
