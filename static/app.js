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

// ── Init ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    loadPolicy();
    setupEventListeners();
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
        }

        // Update guardrail results panel
        renderGuardrailResults(data);

    } catch (err) {
        loadingEl.remove();
        addChatBubble(`Error: ${err.message}`, "blocked");
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
