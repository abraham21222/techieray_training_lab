#!/bin/bash
set -euo pipefail
cat <<'EOF' > /workspace/answer.json
{
  "url": "https://votes.parliament.uk/votes/lords/division/3307",
  "no_official_source": false,
  "confidence": "verified",
  "title": "UK upper chamber backs, by a large majority, amendment to data bill requiring AI firms to disclose copyrighted material "
}
EOF
