#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
rustup target add wasm32-unknown-unknown
if ! command -v wasm-bindgen >/dev/null 2>&1; then
  cargo install wasm-bindgen-cli --version 0.2.104 --locked
fi
RUSTFLAGS="${RUSTFLAGS:-} -C link-arg=-zstack-size=33554432" CARGO_TARGET_DIR=target/wasm cargo build --locked --release --target wasm32-unknown-unknown --no-default-features --features wasm --lib
wasm-bindgen target/wasm/wasm32-unknown-unknown/release/ifx_core.wasm --target web --out-dir pkg --out-name ifx_core
