#!/bin/bash
set -euo pipefail
cat <<'EOF' > /workspace/answer.json
{
  "url": "https://congress.gov/bill/118th-congress/senate-bill/1626/text?s=3&r=24&q=%7B%22search%22%3A%22Artificial+Intelligence%22%7D",
  "no_official_source": false,
  "confidence": "verified",
  "title": "US bill would direct federal communications and trade regulators to write rules requiring companies to get parental cons"
}
EOF
