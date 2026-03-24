//! `trace_debankBlock` RPC implementation.
//!
//! Replays all transactions in a block, collecting DeBank-format traces, events,
//! and state diffs for consumption by background-tracer → S3/Kafka → leafage-evm.

use alloy_consensus::{BlockHeader, Transaction, transaction::TxHashRef};
use alloy_eips::BlockId;
use alloy_primitives::B256;
use alloy_rpc_types_eth::Header;
use jsonrpsee::core::RpcResult;
use reth_chainspec::{EthChainSpec, EthereumHardforks};
use reth_primitives_traits::BlockBody;
use reth_provider::ChainSpecProvider;
use reth_rpc_eth_api::{
    EthApiTypes,
    helpers::{EthBlocks, EthTransactions, LoadBlock, LoadReceipt, LoadState, SpawnBlocking, TraceExt},
};
use reth_rpc_eth_types::{EthApiError, cache::db::StateProviderTraitObjWrapper};
use reth_revm::{State, database::StateProviderDatabase};
use revm::bytecode::opcode::OpCode;
use revm::DatabaseCommit;
use revm_inspectors::tracing::{OpcodeFilter, TracingInspector, TracingInspectorConfig};

use crate::debank_trace::*;
use crate::state_diff_db::StateDiffTraceDB;

/// `trace` namespace API implementation for `debankBlock`.
#[derive(Clone)]
pub struct DebankTraceBlock<Eth> {
    eth_api: Eth,
}

impl<Eth> DebankTraceBlock<Eth> {
    pub fn new(eth_api: Eth) -> Self {
        Self { eth_api }
    }
}

impl<Eth> DebankTraceBlock<Eth>
where
    Eth: EthApiTypes + EthBlocks + LoadBlock + LoadReceipt + LoadState + SpawnBlocking + TraceExt + 'static,
    Eth::Provider: ChainSpecProvider<ChainSpec: EthChainSpec + EthereumHardforks>,
{
    /// Build `DebankOutPut` for the given block.
    async fn trace_debank_block(&self, block_id: BlockId) -> Result<DebankOutPut, Eth::Error> {
        let block = self.eth_api.recovered_block(block_id).await?;
        let Some(block) = block else {
            return Err(EthApiError::HeaderNotFound(block_id).into());
        };

        let debank_block = DebankBlock {
            id: block.hash(),
            height: block.number(),
            parent_id: block.parent_hash(),
            base_fee_per_gas: block.base_fee_per_gas(),
            miner: block.beneficiary(),
            gas_limit: block.gas_limit(),
            gas_used: block.gas_used(),
            timestamp: block.timestamp(),
            process_start_timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis(),
        };

        let debank_header = Header {
            inner: alloy_consensus::Header {
                parent_hash: block.parent_hash(),
                ommers_hash: block.ommers_hash(),
                beneficiary: block.beneficiary(),
                state_root: block.state_root(),
                transactions_root: block.transactions_root(),
                receipts_root: block.receipts_root(),
                logs_bloom: block.logs_bloom(),
                difficulty: block.difficulty(),
                number: block.number(),
                gas_limit: block.gas_limit(),
                gas_used: block.gas_used(),
                timestamp: block.timestamp(),
                extra_data: block.extra_data().clone(),
                mix_hash: block.mix_hash().unwrap_or_default(),
                nonce: block.nonce().unwrap_or_default(),
                base_fee_per_gas: block.base_fee_per_gas(),
                withdrawals_root: block.withdrawals_root(),
                blob_gas_used: block.blob_gas_used(),
                excess_blob_gas: block.excess_blob_gas(),
                parent_beacon_block_root: block.parent_beacon_block_root(),
                requests_hash: block.requests_hash(),
            },
            hash: block.hash(),
            total_difficulty: None,
            size: None,
        };

        // Genesis block: synthetic txs from chain spec
        if block.number() == 0 {
            let chain_spec = self.eth_api.provider().chain_spec();
            let genesis = chain_spec.genesis();
            let mut state_diff: BlockStorageDiff = genesis.into();
            state_diff.hash = block.state_root();
            let (transactions, traces) = build_genesis_txs_and_traces(genesis);
            let block_file = BlockFile {
                block: debank_block,
                transactions,
                traces,
                storage_contracts: get_storage_contracts_from_genesis(genesis),
                ..Default::default()
            };
            let validation_hash = block_file.validation().validation_hash;
            return Ok(DebankOutPut {
                block_file,
                header: debank_header,
                state_diff: alloy_rlp::encode(state_diff).into(),
                validation_hash,
            });
        }

        // Build DebankTransactions from receipts
        use alloy_network::ReceiptResponse;

        let receipts = self.eth_api.block_receipts(block_id).await?;
        let Some(receipts) = receipts else {
            return Err(EthApiError::HeaderNotFound(block_id).into());
        };

        let block_txs = block.body().transactions();
        let mut debank_txs: Vec<DebankTransaction> = Vec::with_capacity(block_txs.len());
        // Track receipt log counts per tx for fee log append
        let mut receipt_log_counts: Vec<usize> = Vec::new();

        for index in 0..block_txs.len() {
            let tx = &block_txs[index];
            let receipt = &receipts[index];
            debank_txs.push(DebankTransaction {
                id: receipt.transaction_hash().to_string(),
                from: receipt.from(),
                to: receipt.to().unwrap_or_default(),
                gas_limit: tx.gas_limit(),
                gas_price: receipt.effective_gas_price(),
                gas_used: receipt.gas_used(),
                status: receipt.status(),
                gas_fee_cap: tx.max_fee_per_gas(),
                gas_tip_cap: tx.max_priority_fee_per_gas().unwrap_or_default(),
                input: tx.input().clone(),
                nonce: tx.nonce(),
                transaction_index: receipt.transaction_index().unwrap_or(0),
                value: tx.value(),
            });
            // Count receipt logs for this tx (for fee log detection later)
            // ReceiptResponse doesn't expose logs directly, so we count via
            // the difference after tracing
            receipt_log_counts.push(0); // TODO: populate from concrete receipt type
        }

        let parent_hash = block.parent_hash();
        let parent_block = self.eth_api.recovered_block(parent_hash.into()).await?;
        let Some(parent_block) = parent_block else {
            return Err(EthApiError::HeaderNotFound(block_id).into());
        };

        let mut block_file = BlockFile {
            block: debank_block,
            transactions: debank_txs,
            ..Default::default()
        };

        // Empty block shortcut
        if parent_block.state_root() == block.state_root() {
            let state_diff = BlockStorageDiff {
                hash: block.state_root(),
                parent_hash: parent_block.state_root(),
                ..Default::default()
            };
            let validation_hash = block_file.validation().validation_hash;
            return Ok(DebankOutPut {
                block_file,
                header: debank_header,
                state_diff: alloy_rlp::encode(state_diff).into(),
                validation_hash,
            });
        }

        // Prepare block replay
        let block_state_root = block.state_root();
        let parent_state_root = parent_block.state_root();

        // Collect tx hashes before move
        let tx_hashes: Vec<B256> = block_txs.iter().map(|tx| *tx.tx_hash()).collect();

        let (evm_env, _) = self.eth_api.evm_env_at(block_id).await?;

        let parent_block_id = BlockId::hash(parent_hash);

        let (traces_result, state_diff, change_addresses) = self
            .eth_api
            .spawn_blocking_io_fut(move |eth_api| async move {
                // Two independent state providers from the same parent block:
                // pre_db for diff comparison, db for tx execution
                let state1 = eth_api.state_at_block_id(parent_block_id).await?;
                let state2 = eth_api.state_at_block_id(parent_block_id).await?;

                let pre_db = State::builder()
                    .with_database(StateProviderDatabase::new(
                        StateProviderTraitObjWrapper(state1),
                    ))
                    .build();
                let cache_db = State::builder()
                    .with_database(StateProviderDatabase::new(
                        StateProviderTraitObjWrapper(state2),
                    ))
                    .build();
                let mut diff_db = StateDiffTraceDB::new(cache_db);

                let log_index = std::cell::RefCell::new(0usize);
                let mut all_results = Vec::new();

                for (idx, tx) in block.transactions_recovered().enumerate() {
                    let tx_hash = tx_hashes[idx];

                    let mut trace_cfg = TracingInspectorConfig::default_parity()
                        .set_steps(true)
                        .set_record_logs(true)
                        .set_exclude_precompile_calls(false);
                    trace_cfg.record_opcodes_filter =
                        Some(OpcodeFilter::new().enabled(OpCode::SSTORE));
                    let mut inspector = TracingInspector::new(trace_cfg);

                    let tx_env = reth_evm::ConfigureEvm::tx_env(
                        eth_api.evm_config(),
                        &tx,
                    );

                    let revm::context::result::ResultAndState { state, .. } = eth_api
                        .inspect(&mut diff_db, evm_env.clone(), tx_env, &mut inspector)?;
                    diff_db.commit(state);

                    let arena = inspector.into_traces();
                    let traces = build_debank_traces(tx_hash, arena, &log_index);
                    all_results.push(traces);
                }

                let change_addresses =
                    get_storage_contracts_from_cache(&diff_db.diff.cache);
                let state_diff =
                    get_storage_diffs_from_cache(diff_db.diff.cache, pre_db);
                Ok((all_results, state_diff, change_addresses))
            })
            .await?;

        // Assemble block file
        for (trace, error_trace, event, error_event) in traces_result {
            block_file.traces.extend(trace);
            block_file.error_traces.extend(error_trace);
            block_file.events.extend(event);
            block_file.error_events.extend(error_event);
        }

        let mut state_diff = state_diff;
        state_diff.hash = block_state_root;
        state_diff.parent_hash = parent_state_root;
        block_file.storage_contracts = change_addresses;

        let validation_hash = block_file.validation().validation_hash;
        Ok(DebankOutPut {
            block_file,
            header: debank_header,
            state_diff: alloy_rlp::encode(state_diff).into(),
            validation_hash,
        })
    }
}

// ---------------------------------------------------------------------------
// jsonrpsee server trait implementation
// ---------------------------------------------------------------------------

#[async_trait::async_trait]
impl<Eth> crate::DebankTraceApiServer for DebankTraceBlock<Eth>
where
    Eth: EthApiTypes + EthBlocks + EthTransactions + LoadBlock + LoadReceipt + LoadState + SpawnBlocking + TraceExt + 'static,
    Eth::Provider: ChainSpecProvider<ChainSpec: EthChainSpec + EthereumHardforks>,
{
    async fn trace_debank_block(&self, block_id: BlockId) -> RpcResult<DebankOutPut> {
        Self::trace_debank_block(self, block_id).await.map_err(Into::into)
    }
}

impl<Eth> std::fmt::Debug for DebankTraceBlock<Eth> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("DebankTraceBlock").finish_non_exhaustive()
    }
}
