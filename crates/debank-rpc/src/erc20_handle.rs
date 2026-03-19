use alloy_primitives::{Address, Bytes, U256};
use alloy_sol_types::{SolType, sol_data};
use revm::DatabaseRef;

use crate::types::{MultiCallErrorCode, SingleCallResult};

/// Sentinel address representing the native token as an ERC-20.
pub const NATIVE_TOKEN_ADDRESS: Address = Address::new([0xee; 20]);

/// Handles ERC-20 method calls to the native token sentinel address (`0xeeee...eeee`).
///
/// Simulates `balanceOf`, `totalSupply`, `decimals`, `name`, and `symbol`
/// by reading native balances directly from state.
pub fn eth_erc20_handle<DB: DatabaseRef>(state: &DB, input: Option<&[u8]>) -> SingleCallResult {
    let Some(data) = input else {
        return SingleCallResult {
            code: MultiCallErrorCode::CodeTxArgs as i32,
            err: "tx input missing".to_string(),
            ..Default::default()
        };
    };

    if data.len() < 4 {
        return SingleCallResult {
            code: MultiCallErrorCode::CodeTxArgs as i32,
            err: "tx input less than 4 bytes".to_string(),
            ..Default::default()
        };
    }

    let selector = &data[0..4];
    match selector {
        // balanceOf(address) = 0x70a08231
        [0x70, 0xa0, 0x82, 0x31] => {
            if data.len() < 36 {
                return SingleCallResult {
                    code: MultiCallErrorCode::CodeTxArgs as i32,
                    err: "balanceOf: input too short".to_string(),
                    ..Default::default()
                };
            }
            let mut addr_bytes = [0u8; 20];
            addr_bytes.copy_from_slice(&data[16..36]);
            let user_addr = Address::from(addr_bytes);
            let balance = state
                .basic_ref(user_addr)
                .ok()
                .flatten()
                .map(|acc| acc.balance)
                .unwrap_or_default();
            SingleCallResult {
                code: MultiCallErrorCode::Success as i32,
                err: String::new(),
                result: Bytes::from(balance.to_be_bytes_vec()),
                ..Default::default()
            }
        }
        // totalSupply() = 0x18160ddd
        [0x18, 0x16, 0x0d, 0xdd] => SingleCallResult {
            code: MultiCallErrorCode::Success as i32,
            err: String::new(),
            result: Bytes::from(U256::from(1u32).to_be_bytes_vec()),
            ..Default::default()
        },
        // decimals() = 0x313ce567
        [0x31, 0x3c, 0xe5, 0x67] => SingleCallResult {
            code: MultiCallErrorCode::Success as i32,
            err: String::new(),
            result: Bytes::from(U256::from(18u32).to_be_bytes_vec()),
            ..Default::default()
        },
        // name() = 0x06fdde03, symbol() = 0x95d89b41
        [0x06, 0xfd, 0xde, 0x03] | [0x95, 0xd8, 0x9b, 0x41] => SingleCallResult {
            code: MultiCallErrorCode::Success as i32,
            err: String::new(),
            result: Bytes::from(sol_data::String::abi_encode("ETH")),
            ..Default::default()
        },
        _ => SingleCallResult {
            code: MultiCallErrorCode::NativeMethodNotFound as i32,
            err: "method not found".to_string(),
            ..Default::default()
        },
    }
}
