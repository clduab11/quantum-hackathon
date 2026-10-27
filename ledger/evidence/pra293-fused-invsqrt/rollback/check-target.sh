#!/usr/bin/env bash
# Exit 0 only if ZIP is archive-identical to pra281-invsqrt-port (#62: port invsqrt, Schur dqi, rustad chemistry).
# Usage: bash check-target.sh ZIP
set -euo pipefail
test "$(sha256sum "$1" | cut -d' ' -f1)" = 5c8db085d18872b17dc16890a2afd6ea8b3c63d3dc513b853ba0ac20b797cecd
