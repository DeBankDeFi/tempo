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
        }

        // Receipt statuses per tx — used to correct trace classification
        // (CallTraceArena may report success=false for AA tx wrapper even when tx succeeds)
        let tx_statuses: Vec<bool> = receipts.iter().map(|r| r.status()).collect();

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
                // (traces, error_traces, events, error_events, exec_log_count)
                let mut all_results: Vec<(Vec<DebankTrace>, Vec<DebankTrace>, Vec<DebankEvent>, Vec<DebankEvent>, usize)> = Vec::new();

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

                    let revm::context::result::ResultAndState { result: exec_result, state } = eth_api
                        .inspect(&mut diff_db, evm_env.clone(), tx_env, &mut inspector)?;
                    diff_db.commit(state);

                    // ExecutionResult.logs contains ALL logs (EVM + handler fee logs)
                    let exec_logs = exec_result.into_logs();

                    let arena = inspector.into_traces();
                    let (traces, error_traces, events, error_events) =
                        build_debank_traces(tx_hash, arena, &log_index);

                    // Inspector events only capture EVM-internal logs.
                    // exec_logs also includes handler-layer fee logs (transfer_fee_post_tx).
                    // Append the extra logs as fee events.
                    let evm_event_count = events.len() + error_events.len();
                    let exec_log_count = exec_logs.len();

                    all_results.push((traces, error_traces, events, error_events, exec_log_count));

                    // Build fee events from execution result logs beyond what inspector captured
                    if exec_log_count > evm_event_count {
                        let root_trace_id = all_results.last().unwrap().0
                            .first().map(|t| t.id.clone()).unwrap_or_default();

                        for log_offset in evm_event_count..exec_log_count {
                            let exec_log = &exec_logs[log_offset];
                            let selector = exec_log.topics().first()
                                .map(|h| h.to_string()).unwrap_or_default();
                            let topics = if exec_log.topics().len() > 1 {
                                exec_log.topics()[1..].iter().map(|h| h.to_string()).collect()
                            } else {
                                vec![]
                            };

                            let pos = all_results.last().unwrap().2.len() + (log_offset - evm_event_count);
                            let mut fee_event = DebankEvent {
                                contract_id: exec_log.address,
                                selector,
                                topics,
                                data: exec_log.data.data.clone(),
                                parent_trace_id: root_trace_id.clone(),
                                pos_in_parent_trace: pos,
                                idx: log_offset,
                                ..Default::default()
                            };
                            fee_event.id = fee_event.debank_id();
                            all_results.last_mut().unwrap().2.push(fee_event);
                        }
                    }
                }

                let change_addresses =
                    get_storage_contracts_from_cache(&diff_db.diff.cache);
                let state_diff =
                    get_storage_diffs_from_cache(diff_db.diff.cache, pre_db);
                Ok((all_results, state_diff, change_addresses))
            })
            .await?;

        // Assemble block file.
        // Use receipt status as the authoritative success indicator.
        // CallTraceArena may report success=false for AA tx wrappers even when
        // the tx actually succeeds (receipt status=0x1). In that case, merge
        // error_traces/error_events back into traces/events.
        for (idx, (mut trace, mut error_trace, mut event, mut error_event, _)) in
            traces_result.into_iter().enumerate()
        {
            let tx_success = tx_statuses.get(idx).copied().unwrap_or(true);
            if tx_success {
                // Tx succeeded: all traces/events go to success lists
                trace.extend(error_trace);
                event.extend(error_event);
                block_file.traces.extend(trace);
                block_file.events.extend(event);
            } else {
                // Tx failed: all traces/events go to error lists
                error_trace.extend(trace);
                error_event.extend(event);
                block_file.error_traces.extend(error_trace);
                block_file.error_events.extend(error_event);
            }
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
