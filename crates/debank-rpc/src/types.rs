use alloy_primitives::{Bytes, B256};
use alloy_rpc_types_eth::Log;
use alloy_rpc_types_trace::parity::LocalizedTransactionTrace;
use serde::{Deserialize, Serialize};

// ========== pre_traceMany types ==========

#[repr(i64)]
#[derive(Clone, Eq, PartialEq, Debug, Deserialize)]
pub enum PreErrorCode {
    UnKnown = 1000,
    InsufficientBalane = 1001,
    Reverted = 1002,
}

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct PreError {
    pub code: i64,
    pub msg: String,
}

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct PreResult {
    pub trace: Vec<LocalizedTransactionTrace>,
    pub logs: Vec<Log>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<PreError>,
    #[serde(rename = "gasUsed")]
    pub gas_used: u64,
}

impl From<PreError> for PreResult {
    fn from(error: PreError) -> Self {
        Self {
            trace: vec![],
            logs: vec![],
            error: Some(error),
            gas_used: 0,
        }
    }
}

// ========== eth_multiCall types ==========

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SingleCallResult {
    pub code: i32,
    pub err: String,
    pub from_cache: bool,
    pub result: Bytes,
    pub gas_used: i64,
    pub time_cost: f64,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MultiCallStats {
    pub block_num: u64,
    pub block_hash: B256,
    pub block_time: u64,
    pub success: bool,
    pub cache_enabled: bool,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MultiCallResp {
    pub results: Vec<SingleCallResult>,
    pub stats: MultiCallStats,
}

#[repr(i32)]
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MultiCallErrorCode {
    Success = 0,
    CodeTxArgs = -40000,
    NativeMethodNotFound = -40001,
    #[allow(dead_code)]
    NativeMethodInput = -40002,
    #[allow(dead_code)]
    NativeMethodInputAddress = -40003,
    #[allow(dead_code)]
    NativeMethodOutput = -40010,
    #[allow(dead_code)]
    NativeMethodStateError = -40011,
    #[allow(dead_code)]
    MessageExecuting = -40012,
    EVMCancelled = -40013,
    EVMReverted = -40014,
    #[allow(dead_code)]
    EVMFastFailed = -40015,
    #[allow(dead_code)]
    UnderlyingDB = -40020,
    #[allow(dead_code)]
    LoadingState = -40021,
}
