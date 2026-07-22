/**
 * Inference Playground — Client Logic
 *
 * Features:
 * - Model selector (auto-loads from /models)
 * - Input modes: JSON, Text, CSV (upload or paste)
 * - Predict with latency measurement
 * - Latency benchmarking (p50/p95/p99)
 * - Request history (localStorage)
 * - Code snippet generation (curl, Python, JavaScript)
 */

(function () {
    "use strict";

    // ─── Constants ───────────────────────────────────────────────────────────────
    const HISTORY_KEY = "playground_history";
    const MAX_HISTORY = 50;

    // ─── DOM References ──────────────────────────────────────────────────────────
    const apiKeyInput = document.getElementById("api-key-input");
    const modelSelect = document.getElementById("model-select");
    const refreshModelsBtn = document.getElementById("refresh-models-btn");
    const predictBtn = document.getElementById("predict-btn");
    const benchmarkBtn = document.getElementById("benchmark-btn");
    const benchmarkCount = document.getElementById("benchmark-count");
    const responseStatus = document.getElementById("response-status");
    const responseLatency = document.getElementById("response-latency");
    const responseOutput = document.getElementById("response-output");
    const benchmarkSection = document.getElementById("benchmark-section");
    const benchCountEl = document.getElementById("bench-count");
    const benchP50 = document.getElementById("bench-p50");
    const benchP95 = document.getElementById("bench-p95");
    const benchP99 = document.getElementById("bench-p99");
    const snippetOutput = document.getElementById("snippet-output");
    const copySnippetBtn = document.getElementById("copy-snippet-btn");
    const historyList = document.getElementById("history-list");
    const clearHistoryBtn = document.getElementById("clear-history-btn");
    const csvFileInput = document.getElementById("csv-file-input");
    const csvDropZone = document.getElementById("csv-drop-zone");
    const csvFilename = document.getElementById("csv-filename");

    // ─── State ───────────────────────────────────────────────────────────────────
    let currentInputMode = "json";
    let currentSnippetLang = "curl";
    let csvFileData = null;

    // ─── Initialization ──────────────────────────────────────────────────────────
    function init() {
        loadModels();
        setupInputTabs();
        setupSnippetTabs();
        setupCSVUpload();
        renderHistory();

        predictBtn.addEventListener("click", handlePredict);
        benchmarkBtn.addEventListener("click", handleBenchmark);
        refreshModelsBtn.addEventListener("click", loadModels);
        copySnippetBtn.addEventListener("click", copySnippet);
        clearHistoryBtn.addEventListener("click", clearHistory);
    }

    // ─── Model Loading ───────────────────────────────────────────────────────────
    async function loadModels() {
        const apiKey = apiKeyInput.value.trim();
        if (!apiKey) {
            modelSelect.innerHTML = '<option value="">Enter API key first</option>';
            return;
        }

        try {
            const resp = await fetch("/models", {
                headers: { "X-API-Key": apiKey },
            });

            if (!resp.ok) {
                modelSelect.innerHTML = '<option value="">Failed to load models</option>';
                return;
            }

            const data = await resp.json();
            modelSelect.innerHTML = "";

            if (data.models && data.models.length > 0) {
                data.models.forEach(function (m) {
                    const opt = document.createElement("option");
                    opt.value = m.name + ":" + (m.version || "latest");
                    opt.textContent = m.name + " (" + (m.version || "latest") + ")";
                    modelSelect.appendChild(opt);
                });
            } else {
                modelSelect.innerHTML = '<option value="">No models available</option>';
            }

            updateSnippet();
        } catch (err) {
            modelSelect.innerHTML = '<option value="">Error: ' + err.message + "</option>";
        }
    }

    // ─── Input Tabs ──────────────────────────────────────────────────────────────
    function setupInputTabs() {
        var tabs = document.querySelectorAll(".tab-btn");
        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                tabs.forEach(function (t) { t.classList.remove("active"); });
                tab.classList.add("active");
                currentInputMode = tab.getAttribute("data-mode");

                document.getElementById("input-area-json").classList.toggle("hidden", currentInputMode !== "json");
                document.getElementById("input-area-text").classList.toggle("hidden", currentInputMode !== "text");
                document.getElementById("input-area-csv").classList.toggle("hidden", currentInputMode !== "csv");
                updateSnippet();
            });
        });
    }

    // ─── Snippet Tabs ────────────────────────────────────────────────────────────
    function setupSnippetTabs() {
        var tabs = document.querySelectorAll(".snippet-tab-btn");
        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                tabs.forEach(function (t) { t.classList.remove("active"); });
                tab.classList.add("active");
                currentSnippetLang = tab.getAttribute("data-lang");
                updateSnippet();
            });
        });
    }

    // ─── CSV Upload ──────────────────────────────────────────────────────────────
    function setupCSVUpload() {
        csvFileInput.addEventListener("change", function (e) {
            var file = e.target.files[0];
            if (file) { handleCSVFile(file); }
        });

        csvDropZone.addEventListener("dragover", function (e) {
            e.preventDefault();
            csvDropZone.classList.add("dragover");
        });

        csvDropZone.addEventListener("dragleave", function () {
            csvDropZone.classList.remove("dragover");
        });

        csvDropZone.addEventListener("drop", function (e) {
            e.preventDefault();
            csvDropZone.classList.remove("dragover");
            var file = e.dataTransfer.files[0];
            if (file && file.name.endsWith(".csv")) { handleCSVFile(file); }
        });
    }

    function handleCSVFile(file) {
        var reader = new FileReader();
        reader.onload = function (e) {
            csvFileData = e.target.result;
            csvFilename.textContent = file.name;
            document.getElementById("csv-input").value = csvFileData;
        };
        reader.readAsText(file);
    }

    function parseCSV(text) {
        var lines = text.trim().split("\n");
        if (lines.length < 2) return [];

        var headers = lines[0].split(",").map(function (h) { return h.trim(); });
        var rows = [];

        for (var i = 1; i < lines.length; i++) {
            var values = lines[i].split(",").map(function (v) { return v.trim(); });
            var row = {};
            headers.forEach(function (h, idx) {
                var val = values[idx] || "";
                // Try numeric conversion
                var num = Number(val);
                row[h] = isNaN(num) || val === "" ? val : num;
            });
            rows.push(row);
        }
        return rows;
    }

    // ─── Get Input Data ──────────────────────────────────────────────────────────
    function getInputData() {
        if (currentInputMode === "json") {
            var raw = document.getElementById("json-input").value.trim();
            if (!raw) return null;
            try {
                return JSON.parse(raw);
            } catch (e) {
                return raw; // Send as string if not valid JSON
            }
        } else if (currentInputMode === "text") {
            var text = document.getElementById("text-input").value.trim();
            return text || null;
        } else if (currentInputMode === "csv") {
            var csvText = document.getElementById("csv-input").value.trim();
            if (!csvText) return null;
            var rows = parseCSV(csvText);
            return rows.length === 1 ? rows[0] : rows;
        }
        return null;
    }

    // ─── Get Selected Model ──────────────────────────────────────────────────────
    function getSelectedModel() {
        var val = modelSelect.value;
        if (!val) return { name: null, version: null };
        var parts = val.split(":");
        return { name: parts[0], version: parts[1] || null };
    }

    // ─── Predict ─────────────────────────────────────────────────────────────────
    async function handlePredict() {
        var data = getInputData();
        if (data === null) {
            showResponse(null, "No input data", 0);
            return;
        }

        var model = getSelectedModel();
        if (!model.name) {
            showResponse(null, "No model selected", 0);
            return;
        }

        var apiKey = apiKeyInput.value.trim();
        if (!apiKey) {
            showResponse(null, "No API key", 0);
            return;
        }

        predictBtn.disabled = true;
        predictBtn.textContent = "...";

        try {
            var result = await sendPredict(model, data, apiKey);
            showResponse(result.status, result.body, result.latency);
            addToHistory(model, data, result);
            updateSnippet();
        } catch (err) {
            showResponse(0, "Network error: " + err.message, 0);
        } finally {
            predictBtn.disabled = false;
            predictBtn.textContent = "Predict";
        }
    }

    async function sendPredict(model, data, apiKey) {
        var body = {
            model: model.name,
            version: model.version,
            data: data,
        };

        var start = Date.now();
        var resp = await fetch("/predict", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-API-Key": apiKey,
            },
            body: JSON.stringify(body),
        });

        var latency = Date.now() - start;
        var responseBody = await resp.json();

        return {
            status: resp.status,
            body: responseBody,
            latency: latency,
        };
    }

    // ─── Display Response ────────────────────────────────────────────────────────
    function showResponse(status, body, latency) {
        if (status === 200) {
            responseStatus.textContent = "200 OK";
            responseStatus.className = "status-badge success";
        } else if (status === null || status === 0) {
            responseStatus.textContent = "Error";
            responseStatus.className = "status-badge error";
        } else {
            responseStatus.textContent = status + " Error";
            responseStatus.className = "status-badge error";
        }

        responseLatency.textContent = "Latency: " + latency + " ms";
        responseOutput.textContent = typeof body === "string" ? body : JSON.stringify(body, null, 2);
    }

    // ─── Benchmark ───────────────────────────────────────────────────────────────
    async function handleBenchmark() {
        var data = getInputData();
        if (data === null) {
            showResponse(null, "No input data for benchmark", 0);
            return;
        }

        var model = getSelectedModel();
        if (!model.name) {
            showResponse(null, "No model selected", 0);
            return;
        }

        var apiKey = apiKeyInput.value.trim();
        if (!apiKey) {
            showResponse(null, "No API key", 0);
            return;
        }

        var n = parseInt(benchmarkCount.value, 10) || 10;
        benchmarkBtn.disabled = true;
        benchmarkBtn.textContent = "Running...";

        var latencies = [];

        for (var i = 0; i < n; i++) {
            try {
                var result = await sendPredict(model, data, apiKey);
                latencies.push(result.latency);
            } catch (err) {
                latencies.push(-1);
            }
        }

        benchmarkBtn.disabled = false;
        benchmarkBtn.textContent = "Benchmark";

        // Filter successful requests
        var valid = latencies.filter(function (l) { return l >= 0; });
        if (valid.length === 0) {
            showResponse(null, "All benchmark requests failed", 0);
            return;
        }

        valid.sort(function (a, b) { return a - b; });

        var p50 = percentile(valid, 50);
        var p95 = percentile(valid, 95);
        var p99 = percentile(valid, 99);

        benchmarkSection.classList.remove("hidden");
        benchCountEl.textContent = valid.length + "/" + n;
        benchP50.textContent = p50.toFixed(1);
        benchP95.textContent = p95.toFixed(1);
        benchP99.textContent = p99.toFixed(1);
    }

    function percentile(sorted, pct) {
        var idx = Math.ceil((pct / 100) * sorted.length) - 1;
        return sorted[Math.max(0, idx)];
    }

    // ─── History ─────────────────────────────────────────────────────────────────
    function getHistory() {
        try {
            var raw = localStorage.getItem(HISTORY_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    }

    function saveHistory(history) {
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        } catch (e) {
            // localStorage full or unavailable — ignore
        }
    }

    function addToHistory(model, input, result) {
        var history = getHistory();
        history.unshift({
            model: model.name,
            version: model.version,
            input: input,
            output: result.body,
            status: result.status,
            latency: result.latency,
            timestamp: new Date().toISOString(),
        });

        if (history.length > MAX_HISTORY) {
            history = history.slice(0, MAX_HISTORY);
        }

        saveHistory(history);
        renderHistory();
    }

    function renderHistory() {
        var history = getHistory();

        if (history.length === 0) {
            historyList.innerHTML = '<p class="history-empty">No requests yet.</p>';
            return;
        }

        var html = "";
        history.forEach(function (item) {
            var time = new Date(item.timestamp).toLocaleTimeString();
            var inputStr = typeof item.input === "string" ? item.input : JSON.stringify(item.input);
            var outputStr = typeof item.output === "string" ? item.output : JSON.stringify(item.output);
            if (inputStr.length > 60) inputStr = inputStr.substring(0, 60) + "...";
            if (outputStr.length > 60) outputStr = outputStr.substring(0, 60) + "...";

            html += '<div class="history-item">' +
                '<div class="history-item-header">' +
                '<span class="model-name">' + escapeHTML(item.model) + " " + escapeHTML(item.version || "") + "</span>" +
                "<span>" + escapeHTML(time) + " · " + item.latency + " ms</span>" +
                "</div>" +
                '<div class="history-item-body">→ ' + escapeHTML(inputStr) + " → " + escapeHTML(outputStr) + "</div>" +
                "</div>";
        });

        historyList.innerHTML = html;
    }

    function clearHistory() {
        localStorage.removeItem(HISTORY_KEY);
        renderHistory();
    }

    // ─── Code Snippets ───────────────────────────────────────────────────────────
    function updateSnippet() {
        var model = getSelectedModel();
        var data = getInputData();
        var apiKey = apiKeyInput.value.trim() || "YOUR_API_KEY";

        if (!model.name || data === null) {
            snippetOutput.textContent = "Select a model and input data to generate snippets.";
            return;
        }

        var bodyObj = { model: model.name, version: model.version, data: data };
        var bodyJSON = JSON.stringify(bodyObj, null, 2);
        var bodyCompact = JSON.stringify(bodyObj);
        var origin = window.location.origin;

        if (currentSnippetLang === "curl") {
            snippetOutput.textContent = generateCurlSnippet(origin, apiKey, bodyCompact);
        } else if (currentSnippetLang === "python") {
            snippetOutput.textContent = generatePythonSnippet(origin, apiKey, bodyJSON);
        } else if (currentSnippetLang === "javascript") {
            snippetOutput.textContent = generateJSSnippet(origin, apiKey, bodyJSON);
        }
    }

    function generateCurlSnippet(origin, apiKey, body) {
        return 'curl -X POST ' + origin + '/predict \\\n' +
            '  -H "Content-Type: application/json" \\\n' +
            '  -H "X-API-Key: ' + apiKey + '" \\\n' +
            "  -d '" + body + "'";
    }

    function generatePythonSnippet(origin, apiKey, bodyJSON) {
        return 'import requests\n\n' +
            'response = requests.post(\n' +
            '    "' + origin + '/predict",\n' +
            '    headers={"X-API-Key": "' + apiKey + '"},\n' +
            '    json=' + bodyJSON.replace(/null/g, "None").replace(/true/g, "True").replace(/false/g, "False") + ',\n' +
            ')\n\n' +
            'print(response.json())';
    }

    function generateJSSnippet(origin, apiKey, bodyJSON) {
        return 'const response = await fetch("' + origin + '/predict", {\n' +
            '    method: "POST",\n' +
            '    headers: {\n' +
            '        "Content-Type": "application/json",\n' +
            '        "X-API-Key": "' + apiKey + '",\n' +
            '    },\n' +
            '    body: JSON.stringify(' + bodyJSON + '),\n' +
            '});\n\n' +
            'const data = await response.json();\n' +
            'console.log(data);';
    }

    function copySnippet() {
        var text = snippetOutput.textContent;
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text);
        }
    }

    // ─── Utilities ───────────────────────────────────────────────────────────────
    function escapeHTML(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ─── Boot ────────────────────────────────────────────────────────────────────
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
