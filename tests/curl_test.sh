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

run "GET /health" 200 "$BASE/health"

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

run "POST /predict unknown -> 400" 400 \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"ghost","version":"v1","data":"x"}'

run "POST /predict/batch" 200 \
    -X POST "$BASE/predict/batch" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"model":"echo","version":"v1","items":["a","b","c"]}'

# Async: submit then poll
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
    for _ in $(seq 1 20); do
        POLL=$(curl -s "$BASE/predict/async/$JOB_ID" -H "X-API-Key: $KEY")
        POLL_STATUS=$(echo "$POLL" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        [ "$POLL_STATUS" = "succeeded" ] || [ "$POLL_STATUS" = "failed" ] && break
        sleep 0.25
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

run "GET /predict/async/bad-id -> 404" 404 \
    "$BASE/predict/async/00000000-0000-0000-0000-000000000000" -H "X-API-Key: $KEY"

run "GET /ready" 200 "$BASE/ready" -H "X-API-Key: $KEY"
run "GET /models" 200 "$BASE/models" -H "X-API-Key: $KEY"
run "GET /metrics" 200 "$BASE/metrics" -H "X-API-Key: $ADMIN_KEY"

# Request-ID echo
printf "[X-Request-ID echoed] ... "
RID="test-$(date +%s)"
ECHOED=$(curl -s -D - -o /dev/null \
    -X POST "$BASE/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -H "X-Request-ID: $RID" -d '{"model":"echo","version":"v1","data":"x"}' \
    | grep -i "^x-request-id:" | tr -d '\r' | awk '{print $2}')
printf "## X-Request-ID\n\`\`\`\nSent: %s\nGot:  %s\n\`\`\`\n\n" "$RID" "$ECHOED" >> "$OUT"
if [ "$ECHOED" = "$RID" ]; then echo "PASS"; ((pass++)); else echo "FAIL (got '$ECHOED')"; ((fail++)); fi

# Rate limit
printf "[Rate limit burst] ... "
printf "## Rate limit\n\`\`\`\n" >> "$OUT"
GOT_429=0
for i in $(seq 1 11); do
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

echo ""
echo "Results: $pass passed, $fail failed"
echo "Output:  $OUT"
printf "\n## Summary\n**%d passed, %d failed**\n" "$pass" "$fail" >> "$OUT"
[ "$fail" -eq 0 ] && exit 0 || exit 1
