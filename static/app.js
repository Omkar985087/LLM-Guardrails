/**
 * LLM Guardrails Gateway — Dashboard JavaScript
 *
 * Handles chat interaction, guardrail result rendering, and policy display.
 */

// ── DOM References ───────────────────────────────────────────────────────
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const charCount = document.getElementById("char-count");
const btnSend = document.getElementById("btn-send");
const btnClearChat = document.getElementById("btn-clear-chat");
const btnReloadPolicy = document.getElementById("btn-reload-policy");
const btnTogglePolicy = document.getElementById("btn-toggle-policy");
const guardrailResults = document.getElementById("guardrail-results");
const policyContent = document.getElementById("policy-content");

// ── State ────────────────────────────────────────────────────────────────
let isLoading = false;
let welcomeVisible = true;
let cachedEvaluationData = null;

// ── Init ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    loadPolicy();
    setupEventListeners();
    setupMetricsEventListeners();
    autoResize(chatInput);
});

function setupEventListeners() {
    // Chat form submission
    chatForm.addEventListener("submit", handleSubmit);

    // Auto-resize textarea
    chatInput.addEventListener("input", () => {
        autoResize(chatInput);
        charCount.textContent = `${chatInput.value.length} / 4000`;
    });

    // Enter to send (Shift+Enter for newline)
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit"));
        }
    });

    // Clear chat
    btnClearChat.addEventListener("click", clearChat);

    // Reload policy
    btnReloadPolicy.addEventListener("click", reloadPolicy);

    // Toggle policy panel
    btnTogglePolicy.addEventListener("click", togglePolicyPanel);

    // Test prompt buttons
    document.addEventListener("click", (e) => {
        if (e.target.classList.contains("test-prompt-btn")) {
            const prompt = e.target.getAttribute("data-prompt");
            chatInput.value = prompt;
            autoResize(chatInput);
            charCount.textContent = `${prompt.length} / 4000`;
            chatForm.dispatchEvent(new Event("submit"));
        }
    });
}

// ── Chat Submission ──────────────────────────────────────────────────────
async function handleSubmit(e) {
    e.preventDefault();
    const prompt = chatInput.value.trim();
    if (!prompt || isLoading) return;

    // Remove welcome message
    if (welcomeVisible) {
        const welcome = chatMessages.querySelector(".welcome-message");
        if (welcome) welcome.remove();
        welcomeVisible = false;
    }

    // Add user bubble
    addChatBubble(prompt, "user");

    // Clear input
    chatInput.value = "";
    autoResize(chatInput);
    charCount.textContent = "0 / 4000";

    // Show loading
    isLoading = true;
    btnSend.disabled = true;
    const loadingEl = addLoadingIndicator();

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt }),
        });

        const data = await response.json();

        // Remove loading
        loadingEl.remove();

        // Handle response based on status
        if (data.status === "passed") {
            addChatBubble(data.response, "assistant");
        } else if (data.status === "blocked") {
            addChatBubble(data.message || "Request blocked by guardrails.", "blocked");
        } else if (data.status === "filtered") {
            addChatBubble(data.message || "Response filtered by guardrails.", "filtered");
        } else if (data.status === "error") {
            addChatBubble(data.message || "LLM provider error occurred.", "error");
        } else {
            addChatBubble(data.message || "Unexpected response status.", "error");
        }

        // Update guardrail results panel
        renderGuardrailResults(data);

    } catch (err) {
        loadingEl.remove();
        addChatBubble(`Error: ${err.message}`, "error");
    } finally {
        isLoading = false;
        btnSend.disabled = false;
        chatInput.focus();
    }
}

// ── Chat Bubble Helpers ──────────────────────────────────────────────────
function addChatBubble(text, type) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${type}`;

    let label = "";
    if (type === "assistant") label = "Assistant";
    else if (type === "blocked") label = "🚫 Blocked";
    else if (type === "filtered") label = "⚠️ Filtered";
    else if (type === "error") label = "⚠️ Provider Error";

    if (label) {
        bubble.innerHTML = `<span class="bubble-label">${label}</span>${escapeHtml(text)}`;
    } else {
        bubble.textContent = text;
    }

    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return bubble;
}

function addLoadingIndicator() {
    const el = document.createElement("div");
    el.className = "chat-loading";
    el.innerHTML = `
        <div class="loading-dots">
            <span></span><span></span><span></span>
        </div>
        Running guardrails…
    `;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return el;
}

// ── Guardrail Results Rendering ──────────────────────────────────────────
function renderGuardrailResults(data) {
    guardrailResults.innerHTML = "";

    // Overall status badge
    const statusHtml = createStatusBadge(data.status);
    guardrailResults.innerHTML += statusHtml;

    // Input guardrails section
    if (data.input_guardrails && data.input_guardrails.length > 0) {
        const section = createGuardrailSection("Input Guardrails", data.input_guardrails);
        guardrailResults.appendChild(section);
    }

    // Output guardrails section
    if (data.output_guardrails && data.output_guardrails.length > 0) {
        const section = createGuardrailSection("Output Guardrails", data.output_guardrails);
        guardrailResults.appendChild(section);
    }

    // Retries badge
    if (data.retries_used > 0) {
        const retriesEl = document.createElement("div");
        retriesEl.className = "retries-badge";
        retriesEl.textContent = `🔄 ${data.retries_used} retry(ies) used`;
        guardrailResults.appendChild(retriesEl);
    }
}

function createStatusBadge(status) {
    const colors = {
        passed: { bg: "var(--accent-green-soft)", border: "rgba(52,211,153,0.2)", color: "var(--accent-green)", icon: "✅", label: "All Checks Passed" },
        blocked: { bg: "var(--accent-red-soft)", border: "rgba(248,113,113,0.2)", color: "var(--accent-red)", icon: "🚫", label: "Request Blocked" },
        filtered: { bg: "var(--accent-amber-soft)", border: "rgba(251,191,36,0.2)", color: "var(--accent-amber)", icon: "⚠️", label: "Response Filtered" },
        error: { bg: "var(--accent-red-soft)", border: "rgba(248,113,113,0.3)", color: "var(--accent-red)", icon: "⚠️", label: "Provider Error" },
    };
    const c = colors[status] || colors.passed;
    return `
        <div style="
            display: flex; align-items: center; gap: 0.5rem;
            padding: 0.6rem 0.85rem; margin-bottom: 0.85rem;
            background: ${c.bg}; border: 1px solid ${c.border};
            border-radius: var(--radius-sm); font-size: 0.8rem;
            font-weight: 600; color: ${c.color};
            animation: fadeInUp 0.3s ease-out;
        ">
            <span>${c.icon}</span> ${c.label}
        </div>
    `;
}

function createGuardrailSection(title, checks) {
    const section = document.createElement("div");
    section.className = "guardrail-section";

    const titleEl = document.createElement("div");
    titleEl.className = "guardrail-section-title";
    titleEl.textContent = title;
    section.appendChild(titleEl);

    checks.forEach((check) => {
        const item = document.createElement("div");
        item.className = "check-item";

        const icon = document.createElement("div");
        icon.className = `check-icon ${check.passed ? "pass" : "fail"}`;
        icon.textContent = check.passed ? "✓" : "✗";

        const details = document.createElement("div");
        details.className = "check-details";

        const name = document.createElement("div");
        name.className = "check-name";
        name.textContent = check.check_name;

        details.appendChild(name);

        if (check.message) {
            const msg = document.createElement("div");
            msg.className = "check-message";
            msg.textContent = check.message;
            details.appendChild(msg);
        }

        item.appendChild(icon);
        item.appendChild(details);
        section.appendChild(item);
    });

    return section;
}

// ── Policy Panel ─────────────────────────────────────────────────────────
async function loadPolicy() {
    try {
        const res = await fetch("/policy");
        const policy = await res.json();
        renderPolicy(policy);
    } catch (err) {
        policyContent.innerHTML = `<div class="loading-state">Failed to load policy</div>`;
    }
}

function renderPolicy(policy) {
    policyContent.innerHTML = "";

    // Input guardrails
    const inputGroup = createPolicyGroup("Input Guardrails", [
        { label: "PII Detection", enabled: policy.input_guardrails?.pii_detection?.enabled },
        { label: "Prompt Injection", enabled: policy.input_guardrails?.prompt_injection?.enabled },
        { label: `Max Length: ${policy.input_guardrails?.max_input_length || "N/A"}` },
    ]);
    policyContent.appendChild(inputGroup);

    // Output guardrails
    const outputGroup = createPolicyGroup("Output Guardrails", [
        { label: "Toxicity Check", enabled: policy.output_guardrails?.toxicity_check?.enabled },
        { label: "Topic Adherence", enabled: policy.output_guardrails?.topic_adherence?.enabled },
        { label: "Schema Validation", enabled: policy.output_guardrails?.schema_validation?.enabled },
        { label: `Max Length: ${policy.output_guardrails?.max_output_length || "N/A"}` },
    ]);
    policyContent.appendChild(outputGroup);

    // Mandatory rules
    if (policy.content_policies?.mandatory_rules?.length) {
        const rulesGroup = document.createElement("div");
        rulesGroup.className = "policy-group";
        const title = document.createElement("div");
        title.className = "policy-group-title";
        title.textContent = "Mandatory Rules";
        rulesGroup.appendChild(title);

        policy.content_policies.mandatory_rules.forEach((rule) => {
            const ruleEl = document.createElement("div");
            ruleEl.className = "policy-rule";
            ruleEl.textContent = rule;
            rulesGroup.appendChild(ruleEl);
        });
        policyContent.appendChild(rulesGroup);
    }

    // LLM settings
    const llmGroup = createPolicyGroup("LLM Settings", [
        { label: `Model: ${policy.llm?.model || "N/A"}` },
        { label: `Temperature: ${policy.llm?.temperature ?? "N/A"}` },
        { label: `Max Tokens: ${policy.llm?.max_output_tokens || "N/A"}` },
        { label: "Retry on Violation", enabled: policy.llm?.retry_on_output_violation },
    ]);
    policyContent.appendChild(llmGroup);
}

function createPolicyGroup(title, items) {
    const group = document.createElement("div");
    group.className = "policy-group";

    const titleEl = document.createElement("div");
    titleEl.className = "policy-group-title";
    titleEl.textContent = title;
    group.appendChild(titleEl);

    items.forEach((item) => {
        const el = document.createElement("div");
        el.className = "policy-item";

        if (item.enabled !== undefined) {
            const badge = document.createElement("span");
            badge.className = `policy-badge ${item.enabled ? "on" : "off"}`;
            badge.textContent = item.enabled ? "ON" : "OFF";
            el.appendChild(badge);
        }

        const label = document.createElement("span");
        label.textContent = item.label;
        el.appendChild(label);

        group.appendChild(el);
    });

    return group;
}

async function reloadPolicy() {
    try {
        const res = await fetch("/reload-policy", { method: "POST" });
        const data = await res.json();
        if (data.status === "reloaded") {
            showToast("Policy reloaded successfully!", "success");
            loadPolicy();
        } else {
            showToast("Failed to reload policy", "error");
        }
    } catch (err) {
        showToast(`Error: ${err.message}`, "error");
    }
}

function togglePolicyPanel() {
    const isCollapsed = policyContent.classList.contains("collapsed");
    if (isCollapsed) {
        policyContent.classList.remove("collapsed");
        policyContent.classList.add("expanded");
        btnTogglePolicy.textContent = "Collapse";
    } else {
        policyContent.classList.add("collapsed");
        policyContent.classList.remove("expanded");
        btnTogglePolicy.textContent = "Expand";
    }
}

// ── Utility Functions ────────────────────────────────────────────────────
function clearChat() {
    chatMessages.innerHTML = "";
    welcomeVisible = false;
    guardrailResults.innerHTML = `
        <div class="empty-state">
            <p>Send a message to see guardrail check results here.</p>
        </div>
    `;
}

function autoResize(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(10px)";
        toast.style.transition = "all 0.3s ease-out";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ── Evaluation & Metrics Dashboard Logic ─────────────────────────────────

function setupMetricsEventListeners() {
    const tabBtnChat = document.getElementById("tab-btn-chat");
    const tabBtnMetrics = document.getElementById("tab-btn-metrics");
    const btnRunBenchmark = document.getElementById("btn-run-benchmark");
    const cmSelect = document.getElementById("cm-category-select");

    if (tabBtnChat && tabBtnMetrics) {
        tabBtnChat.addEventListener("click", () => switchTab("chat"));
        tabBtnMetrics.addEventListener("click", () => {
            switchTab("metrics");
            if (!cachedEvaluationData) {
                loadEvaluationResults();
            }
        });
    }

    if (btnRunBenchmark) {
        btnRunBenchmark.addEventListener("click", handleRunBenchmark);
    }

    if (cmSelect) {
        cmSelect.addEventListener("change", (e) => {
            if (cachedEvaluationData) {
                renderConfusionMatrix(cachedEvaluationData, e.target.value);
            }
        });
    }
}

function switchTab(tabName) {
    const tabBtnChat = document.getElementById("tab-btn-chat");
    const tabBtnMetrics = document.getElementById("tab-btn-metrics");
    const viewChat = document.getElementById("view-chat");
    const viewMetrics = document.getElementById("view-metrics");

    if (tabName === "chat") {
        tabBtnChat.classList.add("active");
        tabBtnMetrics.classList.remove("active");
        viewChat.classList.remove("hidden");
        viewMetrics.classList.add("hidden");
    } else {
        tabBtnMetrics.classList.add("active");
        tabBtnChat.classList.remove("active");
        viewMetrics.classList.remove("hidden");
        viewChat.classList.add("hidden");
    }
}

async function loadEvaluationResults() {
    try {
        const res = await fetch("/evaluation/results");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        cachedEvaluationData = data;
        renderEvaluationResults(data);
    } catch (err) {
        showToast(`Failed to load evaluation metrics: ${err.message}`, "error");
    }
}

async function handleRunBenchmark() {
    const btn = document.getElementById("btn-run-benchmark");
    if (!btn) return;

    btn.disabled = true;
    btn.classList.add("loading");
    const originalText = btn.innerHTML;
    btn.innerHTML = `<span class="status-dot"></span><span>Evaluating…</span>`;

    try {
        const res = await fetch("/evaluation/run", { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        cachedEvaluationData = data;
        renderEvaluationResults(data);
        showToast("Benchmark completed successfully!", "success");
    } catch (err) {
        showToast(`Benchmark error: ${err.message}`, "error");
    } finally {
        btn.disabled = false;
        btn.classList.remove("loading");
        btn.innerHTML = originalText;
    }
}

function renderEvaluationResults(data) {
    if (!data || !data.summary) return;

    // 1. Meta banner
    const metaTimestamp = document.getElementById("meta-eval-timestamp");
    const metaCases = document.getElementById("meta-eval-cases");
    if (metaTimestamp && data.metadata?.timestamp) {
        const d = new Date(data.metadata.timestamp);
        metaTimestamp.textContent = `⏱️ Evaluated: ${d.toLocaleTimeString()} (${d.toLocaleDateString()})`;
    }
    if (metaCases && data.metadata?.total_test_cases) {
        metaCases.textContent = `📁 ${data.metadata.total_test_cases} Labeled Cases`;
    }

    // 2. KPI Cards
    const kpiAcc = document.getElementById("kpi-accuracy");
    const kpiAccSub = document.getElementById("kpi-accuracy-sub");
    if (kpiAcc) kpiAcc.textContent = `${data.summary.overall_accuracy_pct ?? "--"}%`;
    if (kpiAccSub) kpiAccSub.textContent = `${data.summary.total_correct} / ${data.summary.total_evaluated} correct`;

    const kpiF1 = document.getElementById("kpi-macro-f1");
    const kpiF1Sub = document.getElementById("kpi-macro-f1-sub");
    if (kpiF1) kpiF1.textContent = data.summary.overall_macro_f1 != null ? data.summary.overall_macro_f1.toFixed(4) : "N/A";
    if (kpiF1Sub) kpiF1Sub.textContent = data.summary.overall_macro_f1_pct != null ? `${data.summary.overall_macro_f1_pct}% macro-avg` : "Unweighted across categories";

    const kpiBlock = document.getElementById("kpi-block-rate");
    const kpiBlockSub = document.getElementById("kpi-block-rate-sub");
    if (kpiBlock) kpiBlock.textContent = `${data.request_level?.requests_blocked_pct ?? "--"}%`;
    if (kpiBlockSub) kpiBlockSub.textContent = `${data.request_level?.requests_blocked ?? 0} blocked · ${data.request_level?.requests_allowed ?? 0} allowed`;

    const kpiLat = document.getElementById("kpi-latency");
    const kpiLatSub = document.getElementById("kpi-latency-sub");
    if (kpiLat && data.latency) {
        kpiLat.textContent = `${data.latency.mean_ms} ms`;
        kpiLatSub.textContent = `P50: ${data.latency.median_ms}ms · P95: ${data.latency.p95_ms}ms`;
    }

    // 3. F1 Comparison Chart
    renderF1Chart(data.categories || {});

    // 4. Confusion Matrix Dropdown & Visualizer
    populateCategoryDropdown(data.categories || {});
    const cmSelect = document.getElementById("cm-category-select");
    const selectedCat = cmSelect ? cmSelect.value : "OVERALL";
    renderConfusionMatrix(data, selectedCat);

    // 5. Full Metrics Table
    renderMetricsTable(data);
}

function renderF1Chart(categories) {
    const container = document.getElementById("f1-chart-container");
    if (!container) return;

    container.innerHTML = "";
    const categoryLabels = {
        prompt_injection: "Prompt Injection",
        pii_detection: "PII Detection",
        max_length: "Max Length",
        blocked_topic: "Blocked Topics",
        blocked_phrase: "Blocked Phrases",
        toxicity: "Toxicity Check",
        topic_adherence: "Topic Adherence",
        schema_validation: "Schema Validation",
        output_length: "Output Length",
    };

    Object.entries(categories).forEach(([key, catData]) => {
        const row = document.createElement("div");
        row.className = "chart-bar-row";

        const label = document.createElement("div");
        label.className = "chart-bar-label";
        label.textContent = categoryLabels[key] || key;
        label.title = label.textContent;

        const track = document.createElement("div");
        track.className = "chart-bar-track";

        const f1Pct = catData.metrics?.f1_score_pct;
        const fill = document.createElement("div");
        fill.className = "chart-bar-fill";
        fill.style.width = f1Pct != null ? `${Math.min(100, Math.max(0, f1Pct))}%` : "0%";
        if (f1Pct == null) {
            fill.style.background = "rgba(255, 255, 255, 0.1)";
        }

        track.appendChild(fill);

        const val = document.createElement("div");
        val.className = "chart-bar-val";
        val.textContent = f1Pct != null ? `${f1Pct}%` : "N/A";
        if (f1Pct == null) val.style.color = "var(--text-muted)";

        row.appendChild(label);
        row.appendChild(track);
        row.appendChild(val);
        container.appendChild(row);
    });
}

function populateCategoryDropdown(categories) {
    const select = document.getElementById("cm-category-select");
    if (!select) return;

    const currentVal = select.value;
    select.innerHTML = `<option value="OVERALL">Overall Requests (All)</option>`;

    const categoryLabels = {
        prompt_injection: "Prompt Injection",
        pii_detection: "PII Detection",
        max_length: "Max Input Length",
        blocked_topic: "Blocked Topics",
        blocked_phrase: "Blocked Phrases",
        toxicity: "Toxicity Check",
        topic_adherence: "Topic Adherence",
        schema_validation: "Schema Validation",
        output_length: "Max Output Length",
    };

    Object.entries(categories).forEach(([key, catData]) => {
        const total = catData.confusion_matrix?.total || 0;
        const opt = document.createElement("option");
        opt.value = key;
        opt.textContent = `${categoryLabels[key] || key} (${total})`;
        select.appendChild(opt);
    });

    if (currentVal) select.value = currentVal;
}

function renderConfusionMatrix(data, categoryKey) {
    let cm = null;
    let metrics = null;

    if (categoryKey === "OVERALL" || !data.categories?.[categoryKey]) {
        cm = data.request_level?.confusion_matrix || { tp: 0, tn: 0, fp: 0, fn: 0 };
        metrics = data.request_level?.metrics || {};
    } else {
        const cat = data.categories[categoryKey];
        cm = cat.confusion_matrix || { tp: 0, tn: 0, fp: 0, fn: 0 };
        metrics = cat.metrics || {};
    }

    const valTp = document.getElementById("cm-val-tp");
    const valFn = document.getElementById("cm-val-fn");
    const valFp = document.getElementById("cm-val-fp");
    const valTn = document.getElementById("cm-val-tn");
    const footer = document.getElementById("cm-footer-rates");

    if (valTp) valTp.textContent = cm.tp ?? 0;
    if (valFn) valFn.textContent = cm.fn ?? 0;
    if (valFp) valFp.textContent = cm.fp ?? 0;
    if (valTn) valTn.textContent = cm.tn ?? 0;

    if (footer) {
        const fprStr = metrics.fpr_pct != null ? `${metrics.fpr_pct}%` : "N/A";
        const fnrStr = metrics.fnr_pct != null ? `${metrics.fnr_pct}%` : "N/A";
        const specStr = metrics.specificity_pct != null ? `${metrics.specificity_pct}%` : "N/A";
        footer.innerHTML = `<span>FPR: <strong>${fprStr}</strong></span> · <span>FNR: <strong>${fnrStr}</strong></span> · <span>Specificity: <strong>${specStr}</strong></span>`;
    }
}

function renderMetricsTable(data) {
    const tbody = document.getElementById("metrics-table-body");
    if (!tbody) return;

    tbody.innerHTML = "";

    const categoryLabels = {
        prompt_injection: "Prompt Injection",
        pii_detection: "PII Detection",
        max_length: "Max Input Length",
        blocked_topic: "Blocked Topics",
        blocked_phrase: "Blocked Phrases",
        toxicity: "Toxicity Check",
        topic_adherence: "Topic Adherence",
        schema_validation: "Schema Validation",
        output_length: "Max Output Length",
    };

    const categories = data.categories || {};

    Object.entries(categories).forEach(([key, catData]) => {
        const cm = catData.confusion_matrix || {};
        const met = catData.metrics || {};
        const tr = document.createElement("tr");

        const fmt = (v) => v != null ? `${v}%` : "—";

        tr.innerHTML = `
            <td><strong>${categoryLabels[key] || key}</strong></td>
            <td><span class="badge-type">${catData.type || "input"}</span></td>
            <td><span class="badge-status ${catData.enabled ? 'active' : 'disabled'}">${catData.enabled ? 'Active' : 'Disabled'}</span></td>
            <td>${cm.total ?? 0}</td>
            <td><span style="color:var(--accent-green);font-weight:600">${cm.tp ?? 0}</span></td>
            <td><span style="color:var(--accent-cyan);font-weight:600">${cm.tn ?? 0}</span></td>
            <td><span style="color:var(--accent-amber);font-weight:600">${cm.fp ?? 0}</span></td>
            <td><span style="color:var(--accent-red);font-weight:600">${cm.fn ?? 0}</span></td>
            <td>${fmt(met.accuracy_pct)}</td>
            <td>${fmt(met.precision_pct)}</td>
            <td>${fmt(met.recall_pct)}</td>
            <td><strong>${fmt(met.f1_score_pct)}</strong></td>
            <td>${fmt(met.specificity_pct)}</td>
            <td>${fmt(met.fpr_pct)}</td>
            <td>${fmt(met.fnr_pct)}</td>
        `;
        tbody.appendChild(tr);
    });

    // Append OVERALL summary row
    const req = data.request_level || {};
    const reqCm = req.confusion_matrix || {};
    const reqMet = req.metrics || {};
    const fmt = (v) => v != null ? `${v}%` : "—";

    const trOverall = document.createElement("tr");
    trOverall.className = "row-overall";
    trOverall.innerHTML = `
        <td>🛡️ OVERALL PIPELINE</td>
        <td><span class="badge-type">Pipeline</span></td>
        <td><span class="badge-status active">Active</span></td>
        <td>${reqCm.total ?? 0}</td>
        <td><span style="color:var(--accent-green)">${reqCm.tp ?? 0}</span></td>
        <td><span style="color:var(--accent-cyan)">${reqCm.tn ?? 0}</span></td>
        <td><span style="color:var(--accent-amber)">${reqCm.fp ?? 0}</span></td>
        <td><span style="color:var(--accent-red)">${reqCm.fn ?? 0}</span></td>
        <td>${fmt(reqMet.accuracy_pct)}</td>
        <td>${fmt(reqMet.precision_pct)}</td>
        <td>${fmt(reqMet.recall_pct)}</td>
        <td><strong>${fmt(reqMet.f1_score_pct)}</strong></td>
        <td>${fmt(reqMet.specificity_pct)}</td>
        <td>${fmt(reqMet.fpr_pct)}</td>
        <td>${fmt(reqMet.fnr_pct)}</td>
    `;
    tbody.appendChild(trOverall);
}
