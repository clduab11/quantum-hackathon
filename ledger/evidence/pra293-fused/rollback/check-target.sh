#!/usr/bin/env bash
# Exit 0 only if ZIP is archive-identical to submission-008 (pra280-rustad, Schur dqi).
# Usage: bash check-target.sh ZIP
set -euo pipefail
test "$(sha256sum "$1" | cut -d' ' -f1)" = 8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21
