#!/usr/bin/env bash
# Exit 0 only if ZIP is archive-identical to pra293-fused-invsqrt (#65: port invsqrt, fused dqi, rustad chemistry).
# Usage: bash check-target.sh ZIP
set -euo pipefail
test "$(sha256sum "$1" | cut -d' ' -f1)" = 22258bb57f1a711336567cb8771c7f88936d903af7727ab0bbd993fb72e5f27d
