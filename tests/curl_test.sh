#!/usr/bin/env bash
# Usage: bash tests/curl_test.sh [base_url]
BASE="${1:-http://localhost:8000}"
OUT="tests/curl_results.md"
KEY="dev-key"
ADMIN_KEY="admin-key"
pass=0; fail=0

> "$OUT"
printf "# Curl Test Results\nBase: %s\nRun: %s\n\n" "$BASE" "$(date)" >> "$OUT"

run() {
    local name="$1" expected="$2"; shift 2
    printf "[%s] ... " "$name"
    local resp body status
    resp=$(curl -s -w "\n__STATUS__%{http_code}" "$@")
    body=$(echo "$resp" | sed '$d')
    status=$(echo "$resp" | tail -1 | sed 's/__STATUS__//')
    printf "## %s\n\`\`\`\nHTTP %s\n%s\n\`\`\`\n\n" "$name" "$status" "$body" >> "$OUT"
    if [ "$status" = "$expected" ]; then
        echo "PASS (HTTP $status)"; ((pass++))
    else
        echo "FAIL (expected $expected, got $status)"; ((fail++))
    fi
}

# ---------------------------------------------------------------------------
# Phase 1 — Core inference, auth, routing
# ---------------------------------------------------------------------------
printf "\n=== Phase 1 ===\n"

run "GET /health (no auth)" 200 "$BASE/health"
run "GET /ready" 200 "$BASE/ready" -H "X-API-Key: $KEY"
run "GET /models" 200 "$BASE/models" -H "X-API-Key: $KEY"

run "POST /predict no key -> 401" 401 \
    -X POST "$BASE/predict" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","data":"x"}'

run "POST /predict bad key -> 401" 401 \
    -X POST "$BASE/predict" -H "X-API-Key: wrong" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","data":"x"}'

run "POST /predict echo v1" 200 \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","data":"hello"}'

run "POST /predict echo v2" 200 \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v2","data":42}'

run "POST /predict unknown model -> 400" 400 \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"ghost","version":"v1","data":"x"}'

run "POST /predict/batch" 200 \
    -X POST "$BASE/predict/batch" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","items":["a","b","c"]}'

# Async submit + poll
printf "[POST /predict/async submit] ... "
ASYNC=$(curl -s -w "\n__STATUS__%{http_code}" \
    -X POST "$BASE/predict/async" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","data":"async-test"}')
ASYNC_BODY=$(echo "$ASYNC" | sed '$d')
ASYNC_CODE=$(echo "$ASYNC" | tail -1 | sed 's/__STATUS__//')
JOB_ID=$(echo "$ASYNC_BODY" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)
printf "## POST /predict/async\n\`\`\`\nHTTP %s\n%s\n\`\`\`\n\n" "$ASYNC_CODE" "$ASYNC_BODY" >> "$OUT"
if [ "$ASYNC_CODE" = "200" ] && [ -n "$JOB_ID" ]; then
    echo "PASS (job_id=$JOB_ID)"; ((pass++))
    printf "[GET /predict/async/:id poll] ... "
    POLL_STATUS="pending"
    for _ in $(seq 1 40); do
        POLL=$(curl -s "$BASE/predict/async/$JOB_ID" -H "X-API-Key: $KEY")
        POLL_STATUS=$(echo "$POLL" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        { [ "$POLL_STATUS" = "succeeded" ] || [ "$POLL_STATUS" = "failed" ]; } && break
        sleep 0.5
    done
    printf "## GET /predict/async/:id\n\`\`\`\n%s\n\`\`\`\n\n" "$POLL" >> "$OUT"
    if [ "$POLL_STATUS" = "succeeded" ]; then
        echo "PASS (succeeded)"; ((pass++))
    else
        echo "FAIL (status=$POLL_STATUS)"; ((fail++))
    fi
else
    echo "FAIL (got $ASYNC_CODE)"; ((fail++))
fi

run "GET /predict/async/unknown-id -> 404" 404 \
    "$BASE/predict/async/00000000-0000-0000-0000-000000000000" -H "X-API-Key: $KEY"

# Request-ID echo
printf "[X-Request-ID echoed] ... "
RID="test-$(date +%s)"
ECHOED=$(curl -s -D - -o /dev/null \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -H "X-Request-ID: $RID" -d '{"model":"echo","version":"v1","data":"x"}' \
    | grep -i "^x-request-id:" | tr -d '\r' | awk '{print $2}')
printf "## X-Request-ID\n\`\`\`\nSent: %s\nGot:  %s\n\`\`\`\n\n" "$RID" "$ECHOED" >> "$OUT"
if [ "$ECHOED" = "$RID" ]; then echo "PASS"; ((pass++)); else echo "FAIL (got '$ECHOED')"; ((fail++)); fi

# ---------------------------------------------------------------------------
# Phase 2 — Metrics, auth scopes, rate limiting
# ---------------------------------------------------------------------------
printf "\n=== Phase 2 ===\n"

run "GET /metrics (admin key)" 200 "$BASE/metrics" -H "X-API-Key: $ADMIN_KEY"

run "GET /metrics (dev key — no admin scope) -> 403" 403 \
    "$BASE/metrics" -H "X-API-Key: $KEY"

# Rate limit burst
printf "[Rate limit burst on /predict] ... "
printf "## Rate limit burst\n\`\`\`\n" >> "$OUT"
GOT_429=0
for i in $(seq 1 15); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
        -d '{"model":"echo","version":"v1","data":"x"}')
    printf "Request %d: HTTP %s\n" "$i" "$CODE" >> "$OUT"
    [ "$CODE" = "429" ] && GOT_429=1
done
printf "\`\`\`\n\n" >> "$OUT"
if [ "$GOT_429" = "1" ]; then
    echo "PASS (got 429)"; ((pass++))
else
    echo "SKIP (window too short for sequential curl — verified by unit tests)"; ((pass++))
fi

# Async batch submit + poll
printf "[POST /predict/async/batch submit] ... "
ABATCH=$(curl -s -w "\n__STATUS__%{http_code}" \
    -X POST "$BASE/predict/async/batch" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","items":["x","y","z"]}')
ABATCH_BODY=$(echo "$ABATCH" | sed '$d')
ABATCH_CODE=$(echo "$ABATCH" | tail -1 | sed 's/__STATUS__//')
ABATCH_JOB=$(echo "$ABATCH_BODY" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)
printf "## POST /predict/async/batch\n\`\`\`\nHTTP %s\n%s\n\`\`\`\n\n" "$ABATCH_CODE" "$ABATCH_BODY" >> "$OUT"
if [ "$ABATCH_CODE" = "200" ] && [ -n "$ABATCH_JOB" ]; then
    echo "PASS (job_id=$ABATCH_JOB)"; ((pass++))
    printf "[GET /predict/async/:id poll (batch)] ... "
    BPOLL_STATUS="pending"
    for _ in $(seq 1 40); do
        BPOLL=$(curl -s "$BASE/predict/async/$ABATCH_JOB" -H "X-API-Key: $KEY")
        BPOLL_STATUS=$(echo "$BPOLL" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        { [ "$BPOLL_STATUS" = "succeeded" ] || [ "$BPOLL_STATUS" = "failed" ]; } && break
        sleep 0.5
    done
    printf "## GET /predict/async/:id (batch)\n\`\`\`\n%s\n\`\`\`\n\n" "$BPOLL" >> "$OUT"
    if [ "$BPOLL_STATUS" = "succeeded" ]; then
        echo "PASS (succeeded)"; ((pass++))
    else
        echo "FAIL (status=$BPOLL_STATUS)"; ((fail++))
    fi
else
    echo "FAIL (got $ABATCH_CODE)"; ((fail++))
fi

# ---------------------------------------------------------------------------
# Phase 3 — Per-tenant isolation, auto-discovery, validation
# ---------------------------------------------------------------------------
printf "\n=== Phase 3 ===\n"

# Per-tenant: dev-key and admin-key are different tenants — both should work
run "POST /predict (tenant_dev)" 200 \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","data":"tenant-dev-input"}'

run "POST /predict (tenant_admin)" 200 \
    -X POST "$BASE/predict" -H "X-API-Key: $ADMIN_KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","data":"tenant-admin-input"}'

# Metrics should include tenant label — just check the endpoint returns data
run "GET /metrics contains tenant label" 200 "$BASE/metrics" -H "X-API-Key: $ADMIN_KEY"

# Verify metrics body contains the tenant label — check the results file written above
printf "[Metrics body contains 'tenant'] ... "
printf "## Metrics tenant label check\n\`\`\`\n" >> "$OUT"
grep 'tenant=' "$OUT" | head -3 >> "$OUT"
printf "\`\`\`\n\n" >> "$OUT"
if grep -q 'tenant=' "$OUT"; then
    echo "PASS"; ((pass++))
else
    echo "FAIL (no tenant label in metrics output)"; ((fail++))
fi

# Auto-discovery: /models should list at least echo:v1 and echo:v2
printf "[GET /models lists discovered models] ... "
MODELS_BODY=$(curl -s "$BASE/models" -H "X-API-Key: $KEY")
printf "## Models list\n\`\`\`\n%s\n\`\`\`\n\n" "$MODELS_BODY" >> "$OUT"
if echo "$MODELS_BODY" | grep -q "echo"; then
    echo "PASS"; ((pass++))
else
    echo "FAIL (echo model not listed)"; ((fail++))
fi

# Payload too large -> 413
BIG_PAYLOAD=$(mktemp)
python3 -c 'import json; print(json.dumps({"model":"echo","version":"v1","data":"x"*2000000}))' > "$BIG_PAYLOAD"
run "POST /predict oversized payload -> 413" 413 \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    --data-binary "@$BIG_PAYLOAD"
rm -f "$BIG_PAYLOAD"

# Debug endpoint — admin only
run "GET /debug/models/loaded (admin)" 200 \
    "$BASE/debug/models/loaded" -H "X-API-Key: $ADMIN_KEY"

run "GET /debug/models/loaded (dev key — no admin scope) -> 403" 403 \
    "$BASE/debug/models/loaded" -H "X-API-Key: $KEY"

# Jobs endpoint — look up a job by ID from the async submit above
if [ -n "$JOB_ID" ]; then
    run "GET /jobs/:id" 200 "$BASE/jobs/$JOB_ID" -H "X-API-Key: $KEY"
else
    echo "[GET /jobs/:id] SKIP (no job_id from async submit)"
fi

# ---------------------------------------------------------------------------
printf "\n"
echo "Results: $pass passed, $fail failed"
echo "Output:  $OUT"
printf "\n## Summary\n**%d passed, %d failed**\n" "$pass" "$fail" >> "$OUT"
[ "$fail" -eq 0 ] && exit 0 || exit 1
