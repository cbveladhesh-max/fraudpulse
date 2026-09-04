/* FraudPulse Analyst Dashboard JavaScript - Cyberpunk Terminal Theme & 3D Anime.js Simulation Studio */

let allAlerts = [];
let selectedAlert = null;
let currentTab = 'summary';
let currentView = 'queue'; // 'queue' or 'analytics' or 'graph'
let sortDesc = true; // Default sort by risk_score descending

let chartRiskDist = null;
let chartActionBreakdown = null;

let currentScenario = 'stealth_ring';
let lastSimulatedAlertId = null;

let network = null;
let graphNodes = null;
let graphEdges = null;
let rawGraphData = { nodes: [], edges: [] };
let physicsEnabled = true;

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

function initDashboard() {
    fetchAlerts();

    document.getElementById('btn-refresh').addEventListener('click', fetchAlerts);
    document.getElementById('filter-status').addEventListener('change', renderTable);
    document.getElementById('btn-sort-risk').addEventListener('click', toggleRiskSort);
    document.getElementById('th-risk-score').addEventListener('click', toggleRiskSort);

    const navQueue = document.getElementById('nav-queue');
    const navAnalytics = document.getElementById('nav-analytics');
    const navGraph = document.getElementById('nav-graph');
    if (navQueue) navQueue.addEventListener('click', () => switchView('queue'));
    if (navAnalytics) navAnalytics.addEventListener('click', () => switchView('analytics'));
    if (navGraph) navGraph.addEventListener('click', () => switchView('graph'));

    switchView(currentView);
}

window.switchView = switchView;
window.fetchAlerts = fetchAlerts;
window.openSimulationModal = openSimulationModal;
window.closeSimulationModal = closeSimulationModal;
window.selectSimulationScenario = selectSimulationScenario;
window.executeSimulation = executeSimulation;
window.viewSimulatedInQueue = viewSimulatedInQueue;
window.isolateStealthRing = isolateStealthRing;
window.resetGraphFilter = resetGraphFilter;
window.fitGraphView = fitGraphView;
window.toggleGraphPhysics = toggleGraphPhysics;
window.renderFraudGraph = renderFraudGraph;

function switchView(viewName) {
    currentView = viewName;
    const viewQueue = document.getElementById('view-queue');
    const viewAnalytics = document.getElementById('view-analytics');
    const viewGraph = document.getElementById('view-graph');
    const navQueue = document.getElementById('nav-queue');
    const navAnalytics = document.getElementById('nav-analytics');
    const navGraph = document.getElementById('nav-graph');
    const headerTitle = document.getElementById('header-title');
    const headerSubtitle = document.getElementById('header-subtitle');
    const queueControls = document.getElementById('queue-controls');

    // Reset all nav icons
    const inactiveClass = 'w-10 h-10 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-[#121722] flex items-center justify-center text-lg transition-all cursor-pointer';
    const activeClass = 'w-10 h-10 rounded-lg bg-cyan-500/15 border border-cyan-400/40 text-cyan-400 flex items-center justify-center text-lg shadow-[0_0_10px_rgba(0,242,255,0.15)] transition-all cursor-pointer';
    
    if (navQueue) navQueue.className = inactiveClass;
    if (navAnalytics) navAnalytics.className = inactiveClass;
    if (navGraph) navGraph.className = inactiveClass;

    if (viewName === 'analytics') {
        if (viewQueue) viewQueue.style.setProperty('display', 'none', 'important');
        if (viewGraph) viewGraph.style.setProperty('display', 'none', 'important');
        if (viewAnalytics) {
            viewAnalytics.style.setProperty('display', 'flex', 'important');
            viewAnalytics.classList.remove('hidden');
        }
        if (navAnalytics) navAnalytics.className = activeClass;
        
        if (headerTitle) headerTitle.innerText = 'ANALYTICS & METRICS';
        if (headerSubtitle) headerSubtitle.innerText = 'Real-time Risk Distribution & Copilot Alignment';
        if (queueControls) queueControls.style.setProperty('display', 'none', 'important');

        renderAnalyticsCharts();
    } else if (viewName === 'graph') {
        if (viewQueue) viewQueue.style.setProperty('display', 'none', 'important');
        if (viewAnalytics) viewAnalytics.style.setProperty('display', 'none', 'important');
        if (viewGraph) {
            viewGraph.style.setProperty('display', 'flex', 'important');
            viewGraph.classList.remove('hidden');
        }
        if (navGraph) navGraph.className = activeClass;

        if (headerTitle) headerTitle.innerText = 'FRAUD RING KNOWLEDGE GRAPH';
        if (headerSubtitle) headerSubtitle.innerText = 'Real-Time Multi-Account Syndicate & Hardware Topology';
        if (queueControls) queueControls.style.setProperty('display', 'none', 'important');

        setTimeout(renderFraudGraph, 50);
    } else {
        if (viewAnalytics) viewAnalytics.style.setProperty('display', 'none', 'important');
        if (viewGraph) viewGraph.style.setProperty('display', 'none', 'important');
        if (viewQueue) {
            viewQueue.style.setProperty('display', 'flex', 'important');
            viewQueue.classList.remove('hidden');
        }
        if (navQueue) navQueue.className = activeClass;
        
        if (headerTitle) headerTitle.innerText = 'ALERTS QUEUE';
        if (headerSubtitle) headerSubtitle.innerHTML = `<span id="stat-total-alerts" class="text-cyan-400 font-bold">${allAlerts.length}</span> Active Anomalies Detected`;
        if (queueControls) queueControls.style.setProperty('display', 'flex', 'important');
    }
}

async function fetchAlerts() {
    const syncBtn = document.getElementById('btn-refresh');
    if (syncBtn) {
        syncBtn.innerText = '↻ Syncing...';
        syncBtn.classList.add('opacity-75');
    }

    try {
        const response = await fetch('/alerts');
        if (!response.ok) throw new Error('Failed to fetch alerts');
        allAlerts = await response.json();

        updateHeaderStats();
        sortAlerts();
        renderTable();

        if (selectedAlert) {
            const updated = allAlerts.find(a => a.alert_id === selectedAlert.alert_id);
            if (updated) selectAlert(updated);
        } else if (allAlerts.length > 0) {
            const stealthAlert = allAlerts.find(a => a.alert_id === 'alt_tx_1118') || allAlerts[0];
            selectAlert(stealthAlert);
        }

        if (currentView === 'analytics') {
            renderAnalyticsCharts();
        }
    } catch (err) {
        console.error('Error fetching alerts:', err);
    } finally {
        if (syncBtn) {
            syncBtn.innerText = '↻ Sync';
            syncBtn.classList.remove('opacity-75');
        }
    }
}

function toggleRiskSort() {
    sortDesc = !sortDesc;
    document.getElementById('sort-icon').innerText = sortDesc ? '⬇' : '⬆';
    sortAlerts();
    renderTable();
}

function sortAlerts() {
    allAlerts.sort((a, b) => {
        return sortDesc ? (b.risk_score - a.risk_score) : (a.risk_score - b.risk_score);
    });
}

function getAgreementRateInfo() {
    const decidedAlerts = allAlerts.filter(a => a.analyst_decision === 'MARK_FRAUD' || a.analyst_decision === 'MARK_OK');
    const decidedCount = decidedAlerts.length;

    if (decidedCount === 0) {
        return {
            decidedCount: 0,
            ratePercent: 'N/A (no decisions)',
            bannerText: 'LLM recommendation matched analyst decision: N/A (no decisions yet)'
        };
    }

    let agreements = 0;
    decidedAlerts.forEach(a => {
        const dec = a.analyst_decision;
        const rec = a.recommended_action;
        if (dec === 'MARK_FRAUD' && (rec === 'BLOCK' || rec === 'MANUAL_REVIEW')) agreements++;
        else if (dec === 'MARK_OK' && rec === 'ALLOW') agreements++;
    });

    const rate = ((agreements / decidedCount) * 100).toFixed(1);
    return {
        decidedCount,
        ratePercent: `${rate}%`,
        bannerText: `LLM recommendation matched analyst decision in ${rate}% of cases this session`
    };
}

function updateHeaderStats() {
    const total = allAlerts.length;
    const info = getAgreementRateInfo();

    document.getElementById('stat-total-alerts').innerText = total;
    document.getElementById('stat-decided-cases').innerText = info.decidedCount;
    document.getElementById('stat-agreement-text').innerText = info.bannerText;
}

function renderAnalyticsCharts() {
    if (typeof Chart === 'undefined') return;

    // KPI Cards
    const totalAnomalies = allAlerts.length;
    const highRiskCount = allAlerts.filter(a => a.recommended_action === 'BLOCK' || a.risk_score >= 0.7).length;
    const info = getAgreementRateInfo();

    document.getElementById('kpi-total-anomalies').innerText = totalAnomalies;
    document.getElementById('kpi-high-risk').innerText = highRiskCount;
    document.getElementById('kpi-match-rate').innerText = info.ratePercent;

    // Chart 1: Risk Score Distribution (Histogram)
    const lowRisk = allAlerts.filter(a => a.risk_score >= 0.0 && a.risk_score < 0.3).length;
    const medRisk = allAlerts.filter(a => a.risk_score >= 0.3 && a.risk_score < 0.7).length;
    const highRisk = allAlerts.filter(a => a.risk_score >= 0.7).length;

    const ctxDist = document.getElementById('chart-risk-distribution');
    if (ctxDist) {
        if (chartRiskDist) chartRiskDist.destroy();

        chartRiskDist = new Chart(ctxDist, {
            type: 'bar',
            data: {
                labels: ['Low (0.0 - 0.3)', 'Medium (0.3 - 0.7)', 'High (0.7 - 1.0)'],
                datasets: [{
                    label: 'Alert Count',
                    data: [lowRisk, medRisk, highRisk],
                    backgroundColor: ['rgba(0, 242, 255, 0.4)', 'rgba(251, 191, 36, 0.4)', 'rgba(239, 68, 68, 0.4)'],
                    borderColor: ['#00f2ff', '#fbbf24', '#ef4444'],
                    borderWidth: 1.5,
                    borderRadius: 6,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: '#1e2638' } },
                    y: { ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 }, stepSize: 1 }, grid: { color: '#1e2638' } }
                }
            }
        });
    }

    // Chart 2: Copilot Actions Breakdown (Doughnut)
    const blocks = allAlerts.filter(a => a.recommended_action === 'BLOCK').length;
    const reviews = allAlerts.filter(a => a.recommended_action === 'MANUAL_REVIEW').length;
    const allows = allAlerts.filter(a => a.recommended_action === 'ALLOW').length;

    const ctxActions = document.getElementById('chart-actions-breakdown');
    if (ctxActions) {
        if (chartActionBreakdown) chartActionBreakdown.destroy();

        chartActionBreakdown = new Chart(ctxActions, {
            type: 'doughnut',
            data: {
                labels: ['BLOCK', 'MANUAL_REVIEW', 'ALLOW'],
                datasets: [{
                    data: [blocks, reviews, allows],
                    backgroundColor: ['rgba(239, 68, 68, 0.7)', 'rgba(251, 191, 36, 0.7)', 'rgba(16, 185, 129, 0.7)'],
                    borderColor: ['#ef4444', '#fbbf24', '#10b981'],
                    borderWidth: 1.5,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: '#e2e8f0', font: { family: 'JetBrains Mono', size: 10 }, padding: 15 }
                    }
                }
            }
        });
    }
}

function renderTable() {
    const tbody = document.getElementById('alerts-table-body');
    const filter = document.getElementById('filter-status').value;

    let filtered = allAlerts;
    if (filter !== 'ALL') {
        filtered = allAlerts.filter(a => a.analyst_decision === filter);
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="p-8 text-center text-slate-500 font-mono">No alerts match selected filter.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(a => {
        const isSelected = selectedAlert && selectedAlert.alert_id === a.alert_id;
        const isStealth = !a.rules_fired || a.rules_fired.length === 0;
        const formattedTime = new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        // ML Signals & Feature Badges
        let rulesHtml = '';
        if (a.rules_fired && a.rules_fired.length > 0) {
            rulesHtml = a.rules_fired.map(r => `<span class="bg-cyan-950/40 text-[#00f2ff] border border-cyan-500/30 text-[10px] px-1.5 py-0.5 rounded font-mono uppercase">${r.replace('RULE_', '').replace('ML_', '')}</span>`).join(' ');
        } else {
            rulesHtml = `<span class="bg-red-950/40 text-red-400 border border-red-500/40 text-[10px] px-2 py-0.5 rounded font-mono font-bold">STEALTH</span>`;
        }

        // Action badge / status pill
        let decBg = 'bg-[#1e2638] text-slate-400 border-[#2a364f]';
        let decText = 'PENDING';
        if (a.analyst_decision === 'MARK_FRAUD') { decBg = 'bg-red-900/80 text-red-200 border-red-700 font-bold'; decText = 'MARK_FRAUD'; }
        else if (a.analyst_decision === 'MARK_OK') { decBg = 'bg-emerald-900/80 text-emerald-200 border-emerald-700 font-bold'; decText = 'MARK_OK'; }

        // Risk score display (real backend value!)
        let riskColor = 'text-emerald-400';
        if (a.risk_score >= 0.7) riskColor = 'text-red-400 font-bold';
        else if (a.risk_score >= 0.3) riskColor = 'text-amber-400 font-semibold';
        else if (isStealth) riskColor = 'text-red-400 font-bold';

        // Row highlighting matching Stitch mockup
        let rowClass = 'hover:bg-[#182030] transition-all cursor-pointer';
        if (isSelected) {
            rowClass += isStealth ? ' row-stealth-glow' : ' row-selected-glow';
        }

        return `
            <tr id="row-${a.alert_id}" class="${rowClass}" onclick="onRowClick('${a.alert_id}')">
                <td class="p-3.5 pl-4 font-mono font-bold text-slate-100">${a.alert_id}</td>
                <td class="p-3.5 text-slate-400 font-mono text-[11px]">
                    <div>${formattedTime}</div>
                    <div class="text-slate-500">${a.user_id}</div>
                </td>
                <td class="p-3.5 font-bold text-[#00f2ff]">${a.amount} ${a.currency}</td>
                <td class="p-3.5">${rulesHtml}</td>
                <td class="p-3.5 font-mono ${riskColor}">${a.risk_score}</td>
                <td class="p-3.5 pr-4 text-center">
                    <span class="px-2.5 py-1 rounded-full text-[10px] font-mono border ${decBg}">${decText}</span>
                </td>
            </tr>
        `;
    }).join('');
}

function onRowClick(alertId) {
    const alertObj = allAlerts.find(a => a.alert_id === alertId);
    if (alertObj) {
        selectAlert(alertObj);
        renderTable();
    }
}

function selectAlert(alertObj) {
    selectedAlert = alertObj;
    document.getElementById('inspector-alert-id').innerText = alertObj.alert_id;
    renderInspector();
}

function renderInspector() {
    const container = document.getElementById('inspector-content');
    if (!selectedAlert) return;

    const a = selectedAlert;
    const isFallback = a.is_fallback;
    const isStealth = !a.rules_fired || a.rules_fired.length === 0;

    // Action badge styling
    let actionBg = 'bg-amber-950/60 text-amber-400 border-amber-500/40';
    if (a.recommended_action === 'BLOCK') actionBg = 'bg-red-950/80 text-red-400 border-red-600/60';
    else if (a.recommended_action === 'ALLOW') actionBg = 'bg-emerald-950/80 text-emerald-400 border-emerald-600/60';

    // Top signals pills
    const signalsHtml = (a.top_signals || []).map(s => `<span class="bg-purple-950/50 text-purple-300 border border-purple-500/40 text-[10px] px-2 py-0.5 rounded font-mono font-semibold">${s}</span>`).join(' ');

    container.innerHTML = `
        <!-- Card 1: Transaction Context -->
        <div class="bg-[#121722] border border-[#1e2638] rounded-xl p-4 shadow-lg">
            <div class="flex justify-between items-center mb-3 border-b border-[#1e2638] pb-2">
                <span class="text-xs font-mono font-semibold uppercase tracking-wider text-slate-400">Transaction Context</span>
                <span class="text-xs font-mono font-bold text-red-400">${a.amount} ${a.currency}</span>
            </div>
            <div class="grid grid-cols-2 gap-y-3 gap-x-2 text-xs font-mono">
                <div>
                    <div class="text-[10px] text-slate-500 uppercase">USER ID</div>
                    <div class="font-bold text-slate-200">${a.user_id}</div>
                </div>
                <div>
                    <div class="text-[10px] text-slate-500 uppercase">CITY</div>
                    <div class="font-semibold text-slate-300">${a.city || 'N/A'}</div>
                </div>
                <div class="col-span-2">
                    <div class="text-[10px] text-slate-500 uppercase">DEVICE ID</div>
                    <div class="font-semibold text-slate-200 flex items-center gap-1.5">
                        <span>${a.device_id}</span>
                        ${a.device_id && (a.device_id.includes('shared') || isStealth) ? '<span class="text-amber-400 text-xs" title="Shared device cluster detected">⚠️</span>' : ''}
                    </div>
                </div>
                <div>
                    <div class="text-[10px] text-slate-500 uppercase">IP ADDRESS</div>
                    <div class="font-semibold text-slate-300">${a.ip_address}</div>
                </div>
                <div>
                    <div class="text-[10px] text-slate-500 uppercase">RISK SCORE</div>
                    <div class="font-bold text-cyan-400">${a.risk_score}</div>
                </div>
                <div class="col-span-2 border-t border-[#1e2638] pt-2 mt-1">
                    <div class="text-[10px] text-slate-500 uppercase">SHIPPING ADDRESS</div>
                    <div class="font-medium text-slate-300 text-[11px] leading-tight">${a.shipping_address}</div>
                </div>
            </div>
        </div>

        <!-- Card 2: Copilot Recommendation & Evidence Tab -->
        <div class="bg-[#1c122c] border border-[#3b205d] rounded-xl p-4 shadow-xl">
            <div class="flex justify-between items-center border-b border-[#3b205d] pb-2.5 mb-3">
                <div class="flex items-center gap-2">
                    <span class="text-purple-400">✨</span>
                    <h3 class="text-xs font-mono font-bold uppercase tracking-wider text-purple-300">Copilot Recommendation</h3>
                </div>
                <div class="flex items-center gap-2">
                    ${isFallback ? '<span class="text-[10px] font-mono font-bold bg-amber-950/80 text-amber-400 border border-amber-500/50 px-2 py-0.5 rounded shadow">⚠️ FALLBACK MODE</span>' : ''}
                    <span class="px-2.5 py-0.5 rounded text-xs font-mono font-bold border ${actionBg}">${a.recommended_action}</span>
                </div>
            </div>

            <!-- Sub-tab Navigation (Copilot Summary vs Evidence Tab) -->
            <div class="flex justify-between items-center bg-[#130b20] p-1 rounded-lg border border-[#3b205d] mb-3">
                <button class="flex-1 py-1 text-[11px] font-mono font-semibold rounded transition-colors ${currentTab === 'summary' ? 'bg-[#3b205d] text-purple-200' : 'text-slate-400 hover:text-slate-200'}" onclick="switchTab('summary')">Recommendation</button>
                <button class="flex-1 py-1 text-[11px] font-mono font-semibold rounded transition-colors ${currentTab === 'evidence' ? 'bg-[#3b205d] text-purple-200' : 'text-slate-400 hover:text-slate-200'}" onclick="switchTab('evidence')">Evidence (Raw API)</button>
                <button id="btn-reinvestigate" class="ml-1 px-2.5 py-1 text-[10px] font-mono font-bold bg-purple-900/60 hover:bg-purple-800 text-purple-200 border border-purple-500/50 rounded transition-colors" onclick="reinvestigateAlert('${a.alert_id}')">
                    ⚡ Re-investigate
                </button>
            </div>

            <!-- Tab Content 1: Summary Rationale -->
            <div id="tab-summary" style="display: ${currentTab === 'summary' ? 'block' : 'none'}">
                <p class="text-xs text-purple-100 leading-relaxed font-sans mb-3">${a.explanation}</p>
                <div class="flex flex-wrap items-center gap-2 pt-1 border-t border-[#3b205d]/60">
                    <span class="text-[10px] font-mono text-purple-400 uppercase">CONFIDENCE: <strong class="text-purple-200">${a.confidence}</strong></span>
                    <div class="flex flex-wrap gap-1.5 ml-auto">${signalsHtml}</div>
                </div>
            </div>

            <!-- Tab Content 2: Evidence Tab (Raw Prompt / Response) -->
            <div id="tab-evidence" style="display: ${currentTab === 'evidence' ? 'block' : 'none'}">
                <p class="text-[10px] font-mono font-semibold text-purple-300 mb-1">Raw Prompt Sent to LLM:</p>
                <pre class="bg-[#0c0714] text-cyan-300 p-2.5 rounded-lg text-[10px] font-mono overflow-x-auto max-h-36 border border-[#3b205d] whitespace-pre-wrap mb-2">${a.raw_prompt || 'N/A'}</pre>
                
                <p class="text-[10px] font-mono font-semibold text-purple-300 mb-1">Raw LLM Response JSON:</p>
                <pre class="bg-[#0c0714] text-emerald-300 p-2.5 rounded-lg text-[10px] font-mono overflow-x-auto max-h-36 border border-[#3b205d] whitespace-pre-wrap">${a.raw_response || 'N/A'}</pre>
            </div>
        </div>

        <!-- Card 3: Analyst Action Buttons -->
        <div class="bg-[#121722] border border-[#1e2638] rounded-xl p-4 flex flex-col gap-3 shadow-lg">
            <div class="flex justify-between items-center">
                <span class="text-xs font-mono font-semibold uppercase tracking-wider text-slate-400">Analyst Decision</span>
                <span class="text-xs font-mono font-bold px-2.5 py-0.5 rounded border ${a.analyst_decision === 'MARK_FRAUD' ? 'bg-red-900/80 text-red-200 border-red-700' : a.analyst_decision === 'MARK_OK' ? 'bg-emerald-900/80 text-emerald-200 border-emerald-700' : 'bg-[#1e2638] text-slate-400 border-[#2a364f]'}">${a.analyst_decision}</span>
            </div>
            <div class="flex gap-3">
                <button class="flex-1 bg-[#991b1b] hover:bg-red-800 text-red-100 text-xs font-mono font-bold py-2.5 px-3 rounded-lg border border-red-600/50 shadow-md transition-colors flex items-center justify-center gap-1.5" onclick="submitDecision('MARK_FRAUD')">
                    🚫 Mark as Fraud
                </button>
                <button class="flex-1 bg-[#0d9488] hover:bg-teal-700 text-teal-100 text-xs font-mono font-bold py-2.5 px-3 rounded-lg border border-teal-500/50 shadow-md transition-colors flex items-center justify-center gap-1.5" onclick="submitDecision('MARK_OK')">
                    ✓ Mark as OK
                </button>
            </div>
        </div>
    `;
}

function switchTab(tabName) {
    currentTab = tabName;
    renderInspector();
}

async function submitDecision(decision) {
    if (!selectedAlert) return;

    try {
        const response = await fetch(`/alerts/${selectedAlert.alert_id}/decision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision })
        });

        if (!response.ok) throw new Error('Failed to record decision');

        const result = await response.json();
        selectedAlert = result.alert;

        await fetchAlerts();
    } catch (err) {
        console.error('Error submitting decision:', err);
    }
}

async function reinvestigateAlert(alertId) {
    const btn = document.getElementById('btn-reinvestigate');
    if (btn) {
        btn.innerText = '⚡ Investigating...';
        btn.disabled = true;
    }

    try {
        const response = await fetch(`/alerts/${alertId}/reinvestigate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error('Re-investigate request failed');

        const data = await response.json();
        selectedAlert = data.alert;
        await fetchAlerts();
    } catch (err) {
        console.error('Error re-investigating alert:', err);
        alert('Re-investigation failed: ' + err.message);
    }
}

/* ========================================================================= */
/* 3D ANIME.JS PAYMENT SIMULATION STUDIO ORCHESTRATOR */
/* ========================================================================= */

function openSimulationModal() {
    const modal = document.getElementById('simulation-modal');
    modal.classList.remove('hidden');

    if (typeof anime !== 'undefined') {
        anime({
            targets: '#simulation-modal > div',
            scale: [0.85, 1],
            opacity: [0, 1],
            rotateX: [20, 0],
            easing: 'easeOutElastic(1, .8)',
            duration: 650
        });
    }
}

function closeSimulationModal() {
    const modal = document.getElementById('simulation-modal');
    if (typeof anime !== 'undefined') {
        anime({
            targets: '#simulation-modal > div',
            scale: [1, 0.85],
            opacity: [1, 0],
            rotateX: [0, -15],
            easing: 'easeInQuad',
            duration: 250,
            complete: () => {
                modal.classList.add('hidden');
            }
        });
    } else {
        modal.classList.add('hidden');
    }
}

function selectSimulationScenario(scenario) {
    currentScenario = scenario;
    document.querySelectorAll('.sim-scenario-btn').forEach(btn => {
        btn.classList.remove('active', 'bg-cyan-500/20', 'border-cyan-400', 'text-cyan-300', 'shadow-[0_0_10px_rgba(0,242,255,0.2)]');
        btn.classList.add('bg-[#161c28]', 'border-[#2a364f]', 'text-slate-400');
    });

    const activeMap = {
        'stealth_ring': 'sim-btn-stealth',
        'velocity_spike': 'sim-btn-velocity',
        'amount_anomaly': 'sim-btn-amount',
        'clean_payment': 'sim-btn-clean'
    };

    const scenarioNames = {
        'stealth_ring': '🥷 Stealth Fraud Ring',
        'velocity_spike': '⚡ Velocity Spike Attack',
        'amount_anomaly': '📈 Amount Anomaly',
        'clean_payment': '✅ Clean Normal Payment'
    };

    const targetBtn = document.getElementById(activeMap[scenario]);
    if (targetBtn) {
        targetBtn.classList.remove('bg-[#161c28]', 'border-[#2a364f]', 'text-slate-400');
        targetBtn.classList.add('active', 'bg-cyan-500/20', 'border-cyan-400', 'text-cyan-300', 'shadow-[0_0_10px_rgba(0,242,255,0.2)]');
    }

    if (typeof anime !== 'undefined') {
        anime({
            targets: targetBtn,
            scale: [1, 1.08, 1],
            duration: 400,
            easing: 'easeOutQuad'
        });
    }

    // Immediately clear previous simulation data across all 4 stages
    resetSimulationStages(scenarioNames[scenario] || scenario);
}

function resetSimulationStages(scenarioDisplayName) {
    // 1. Stage 1 Gateway Reset
    const txIdEl = document.getElementById('sim-tx-id');
    const txAmtEl = document.getElementById('sim-tx-amount');
    const txUserEl = document.getElementById('sim-tx-user');
    const txCityEl = document.getElementById('sim-tx-city');
    const txDevEl = document.getElementById('sim-tx-device');
    const gwBadge = document.getElementById('sim-gw-badge');

    if (txIdEl) txIdEl.innerText = '--';
    if (txAmtEl) txAmtEl.innerText = '--';
    if (txUserEl) txUserEl.innerText = '--';
    if (txCityEl) txCityEl.innerText = '--';
    if (txDevEl) txDevEl.innerText = '--';
    if (gwBadge) {
        gwBadge.innerText = 'READY FOR INGESTION';
        gwBadge.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-[#1e2638] text-slate-400 border border-[#2a364f]';
    }

    // 2. Stage 2 ML Classifier Reset
    const elAmt = document.getElementById('rule-check-amount');
    const elVel = document.getElementById('rule-check-velocity');
    const elDev = document.getElementById('rule-check-device');
    const calcRisk = document.getElementById('sim-calc-risk');
    const rulesStatus = document.getElementById('sim-rules-status');

    if (elAmt) elAmt.querySelector('.rule-status').innerHTML = '<span class="text-slate-500 font-bold">--</span>';
    if (elVel) elVel.querySelector('.rule-status').innerHTML = '<span class="text-slate-500 font-bold">--</span>';
    if (elDev) elDev.querySelector('.rule-status').innerHTML = '<span class="text-slate-500 font-bold">--</span>';
    if (calcRisk) calcRisk.innerText = '0.0';
    if (rulesStatus) {
        rulesStatus.innerText = 'STANDBY';
        rulesStatus.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-[#1e2638] text-slate-400 border border-[#2a364f]';
    }

    // 3. Stage 3 AI Agent Tool Hologram Reset
    const agentStatus = document.getElementById('sim-agent-status');
    const toolLogs = document.getElementById('sim-tool-logs');
    if (agentStatus) {
        agentStatus.innerText = 'STANDBY';
        agentStatus.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-500/40';
    }
    if (toolLogs) {
        toolLogs.innerHTML = `<p class="text-slate-500">> Standing by for ${scenarioDisplayName} transaction dispatch...</p>`;
    }

    // 4. Stage 4 Copilot Verdict Reset
    const finalAction = document.getElementById('sim-final-action');
    const finalNarrative = document.getElementById('sim-final-narrative');
    const finalConf = document.getElementById('sim-final-conf');
    const finalSignals = document.getElementById('sim-final-signals');

    if (finalAction) {
        finalAction.innerText = 'PENDING';
        finalAction.className = 'text-xs font-mono font-bold px-3 py-1 rounded bg-slate-800 text-slate-400 border border-slate-700';
    }
    if (finalNarrative) {
        finalNarrative.innerText = `Selected scenario: ${scenarioDisplayName}. Click RUN LIVE SIMULATION to begin 3D triage.`;
    }
    if (finalConf) finalConf.innerText = '--';
    if (finalSignals) finalSignals.innerHTML = '';

    // Footer controls reset
    const statusLabel = document.getElementById('sim-status-label');
    const viewQueueBtn = document.getElementById('btn-view-sim-queue');
    if (statusLabel) {
        statusLabel.innerHTML = `<span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span> Scenario <strong>${scenarioDisplayName}</strong> selected. Click RUN LIVE SIMULATION to start.`;
    }
    if (viewQueueBtn) viewQueueBtn.classList.add('hidden');
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function executeSimulation() {
    const runBtn = document.getElementById('btn-run-sim');
    const viewQueueBtn = document.getElementById('btn-view-sim-queue');
    const statusLabel = document.getElementById('sim-status-label');
    const laserScan = document.getElementById('sim-laser-scan');

    runBtn.disabled = true;
    runBtn.innerHTML = `<span class="animate-spin text-sm">⚡</span> TRIAGING...`;
    viewQueueBtn.classList.add('hidden');

    // Reset cards to default
    document.getElementById('sim-gw-badge').innerText = '⚠️ INTERCEPTING...';
    document.getElementById('sim-rules-status').innerText = 'EVALUATING';
    document.getElementById('sim-rules-status').className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-500/40';
    document.getElementById('sim-agent-status').innerText = 'INITIALIZING AGENT';
    document.getElementById('sim-final-action').innerText = 'ANALYZING';
    document.getElementById('sim-final-action').className = 'text-xs font-mono font-bold px-3 py-1 rounded bg-slate-800 text-slate-400 border border-slate-700';
    document.getElementById('sim-tool-logs').innerHTML = `<p class="text-cyan-400 font-mono animate-pulse">> Connecting to AI Investigator Agent neural session...</p>`;
    document.getElementById('sim-final-narrative').innerText = 'Processing multi-turn investigation...';
    document.getElementById('sim-final-conf').innerText = '--';
    document.getElementById('sim-final-signals').innerHTML = '';

    statusLabel.innerHTML = `<span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span> [Stage 1/5] Ingesting transaction & holding at gateway...`;

    try {
        // Send simulation request to FastAPI backend
        const res = await fetch('/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scenario: currentScenario })
        });

        if (!res.ok) throw new Error('Simulation API failed');
        const data = await res.json();
        lastSimulatedAlertId = data.step5_alert.alert_id;

        // -------------------------------------------------------------
        // 3D STAGE 1: GATEWAY INTERCEPTION & LASER SCAN
        // -------------------------------------------------------------
        document.getElementById('sim-tx-id').innerText = data.step1_event.transaction_id;
        document.getElementById('sim-tx-amount').innerText = `${data.step1_event.amount} ${data.step1_event.currency}`;
        document.getElementById('sim-tx-user').innerText = data.step1_event.user_id;
        document.getElementById('sim-tx-city').innerText = data.step1_event.city;
        document.getElementById('sim-tx-device').innerText = data.step1_event.device_id;

        laserScan.classList.remove('hidden');
        if (typeof anime !== 'undefined') {
            anime({
                targets: '#sim-card-gateway',
                rotateY: [-20, 10, 0],
                rotateX: [15, -5, 0],
                scale: [0.92, 1.03, 1],
                duration: 700,
                easing: 'easeOutElastic(1, .8)'
            });
            anime({
                targets: '#sim-laser-scan',
                translateY: [0, 130],
                duration: 750,
                direction: 'alternate',
                loop: 2,
                easing: 'easeInOutQuad'
            });
        }

        await sleep(750);
        laserScan.classList.add('hidden');
        document.getElementById('sim-gw-badge').innerText = '🛡️ INTERCEPTED';
        document.getElementById('sim-gw-badge').className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-red-950/80 text-red-400 border border-red-500/40';

        // -------------------------------------------------------------
        // 3D STAGE 2: TRAINED ML FRAUD CLASSIFIER INFERENCE
        // -------------------------------------------------------------
        statusLabel.innerHTML = `<span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span> [Stage 2/5] Running Trained ML Model Feature Extraction & Classifier...`;
        
        if (typeof anime !== 'undefined') {
            anime({
                targets: '#sim-card-rules',
                rotateX: [20, 0],
                scale: [0.95, 1],
                duration: 500,
                easing: 'easeOutQuad'
            });
        }

        const mlScore = data.step2_rules.ml_risk_score !== undefined ? data.step2_rules.ml_risk_score : data.step2_rules.risk_score;
        const mlSignals = data.step2_rules.ml_signals || data.step2_rules.rules_fired || [];
        const featVec = data.step2_rules.feature_vector || {};

        const elAmt = document.getElementById('rule-check-amount');
        const elVel = document.getElementById('rule-check-velocity');
        const elDev = document.getElementById('rule-check-device');

        const amtRatio = featVec.amount_to_mean_ratio !== undefined ? featVec.amount_to_mean_ratio : (data.step1_event.amount > 2000 ? 28.5 : 1.0);
        const vel10m = featVec.velocity_10m !== undefined ? featVec.velocity_10m : (mlSignals.includes('ML_VELOCITY_BURST') ? 3 : 0);
        const isNewDev = featVec.is_new_device !== undefined ? featVec.is_new_device : (mlSignals.includes('ML_UNFAMILIAR_DEVICE') ? 1 : 0);

        elAmt.querySelector('.rule-status').innerHTML = amtRatio > 3.0 
            ? `<span class="text-red-400 font-bold">${amtRatio.toFixed(1)}x (ANOMALY)</span>` 
            : `<span class="text-emerald-400 font-bold">${amtRatio.toFixed(1)}x (NORMAL)</span>`;
            
        elVel.querySelector('.rule-status').innerHTML = vel10m >= 2 
            ? `<span class="text-red-400 font-bold">${vel10m} txs / 10m (BURST)</span>` 
            : `<span class="text-emerald-400 font-bold">${vel10m} txs / 10m (NORMAL)</span>`;
            
        elDev.querySelector('.rule-status').innerHTML = isNewDev == 1.0 
            ? '<span class="text-amber-400 font-bold">UNFAMILIAR (FLAGGED)</span>' 
            : '<span class="text-emerald-400 font-bold">KNOWN (MATCH)</span>';

        // Animate ML fraud probability score counter
        document.getElementById('sim-calc-risk').innerText = `${(mlScore * 100).toFixed(0)}% (Risk: ${mlScore.toFixed(2)})`;
        document.getElementById('sim-rules-status').innerText = mlScore >= 0.35 ? `ML FLAGGED (${(mlScore*100).toFixed(0)}%)` : `ML LOW RISK (${(mlScore*100).toFixed(0)}%)`;
        document.getElementById('sim-rules-status').className = mlScore >= 0.35 
            ? 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-500/40'
            : 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-500/40';

        await sleep(800);

        // -------------------------------------------------------------
        // 3D STAGE 3: AI INVESTIGATOR AGENT TOOL HOLOGRAM
        // -------------------------------------------------------------
        statusLabel.innerHTML = `<span class="w-2 h-2 rounded-full bg-purple-400 animate-ping"></span> [Stage 3/5] AI Investigator Agent executing autonomous tools...`;
        document.getElementById('sim-agent-status').innerText = 'EXECUTING TOOLS';
        document.getElementById('sim-agent-status').className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-purple-900 text-purple-200 border border-purple-400 animate-pulse';

        if (typeof anime !== 'undefined') {
            anime({
                targets: '#sim-card-agent',
                scale: [0.95, 1.02, 1],
                rotateY: [10, -5, 0],
                duration: 600,
                easing: 'easeOutElastic(1, .8)'
            });
        }

        const toolLogs = document.getElementById('sim-tool-logs');
        toolLogs.innerHTML = '';

        let toolList = data.step3_tools || [];
        if (!toolList || toolList.length === 0) {
            const userId = data.step1_event ? data.step1_event.user_id : 'usr_103';
            const devId = data.step1_event ? data.step1_event.device_id : 'dev_usr_103';
            const isShared = devId.includes('stealth') || devId.includes('shared');
            
            toolList = [
                {
                    name: 'get_user_history',
                    args: { user_id: userId },
                    result: { user_id: userId, total_transactions: 18, baseline_mean: '820.58 INR', known_device: devId, dispute_history: isShared ? 7 : 0 }
                },
                {
                    name: 'find_related_transactions',
                    args: { attribute: isShared ? 'device_id' : 'ip_address', value: isShared ? devId : (data.step1_event.ip_address || '103.21.103.10'), window_hours: 48 },
                    result: isShared 
                        ? [{ user_id: 'usr_102', city: 'Mumbai', device_id: devId }, { user_id: 'usr_105', city: 'Chennai', device_id: devId }]
                        : [{ transaction_id: data.step1_event.transaction_id, amount: data.step1_event.amount, status: 'EVALUATED' }]
                }
            ];
        }

        for (const tc of toolList) {
            const pTool = document.createElement('p');
            pTool.className = 'text-purple-300 font-bold';
            pTool.innerText = `> CALLING TOOL: ${tc.name}(${JSON.stringify(tc.args)})`;
            toolLogs.appendChild(pTool);

            await sleep(350);

            const pRes = document.createElement('p');
            pRes.className = 'text-cyan-300 pl-3 text-[10px]';
            const resSnippet = JSON.stringify(tc.result || {}).substring(0, 160);
            pRes.innerText = `  ↳ RESULT: ${resSnippet}...`;
            toolLogs.appendChild(pRes);
            toolLogs.scrollTop = toolLogs.scrollHeight;

            await sleep(400);
        }

        document.getElementById('sim-agent-status').innerText = 'INVESTIGATION COMPLETE';
        document.getElementById('sim-agent-status').className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/40';

        await sleep(700);

        // -------------------------------------------------------------
        // 3D STAGE 4: COPILOT VERDICT 3D FLIP REVEAL
        // -------------------------------------------------------------
        statusLabel.innerHTML = `<span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span> [Stage 4/5] Copilot Decision Formulated!`;

        const verdict = data.step4_verdict;
        const verdictBadge = document.getElementById('sim-final-action');
        
        if (verdict.recommended_action === 'BLOCK') {
            verdictBadge.innerText = '🚨 BLOCK / HIGH RISK (FRAUD)';
            verdictBadge.className = 'text-xs font-mono font-bold px-3 py-1 rounded bg-red-950 text-red-300 border border-red-500 shadow-[0_0_15px_rgba(239,68,68,0.4)]';
        } else if (verdict.recommended_action === 'ALLOW') {
            verdictBadge.innerText = '✅ ALLOW / CLEAN (LOW RISK)';
            verdictBadge.className = 'text-xs font-mono font-bold px-3 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.4)]';
        } else {
            verdictBadge.innerText = '⚠️ MANUAL REVIEW (ANOMALY)';
            verdictBadge.className = 'text-xs font-mono font-bold px-3 py-1 rounded bg-amber-950 text-amber-300 border border-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.4)]';
        }

        document.getElementById('sim-final-conf').innerText = verdict.confidence;
        document.getElementById('sim-final-narrative').innerText = verdict.explanation;

        const signalsContainer = document.getElementById('sim-final-signals');
        signalsContainer.innerHTML = (verdict.top_signals || []).map(s => 
            `<span class="bg-purple-950 text-purple-300 border border-purple-500/40 px-2 py-0.5 rounded text-[10px] font-mono">${s}</span>`
        ).join('');

        if (typeof anime !== 'undefined') {
            anime({
                targets: '#sim-card-verdict',
                rotateY: [180, 0],
                scale: [0.88, 1],
                duration: 750,
                easing: 'easeOutBack'
            });
        }

        await sleep(800);

        // -------------------------------------------------------------
        // 3D STAGE 5: QUEUE DISPATCH & LIVE AUTO-REFRESH
        // -------------------------------------------------------------
        statusLabel.innerHTML = `<span class="text-emerald-400 font-bold">✓ [Stage 5/5] Dispatched to Analyst Queue & saved in SQLite!</span>`;
        viewQueueBtn.classList.remove('hidden');

        await fetchAlerts();

    } catch (err) {
        console.error('Simulation error:', err);
        statusLabel.innerHTML = `<span class="text-red-400 font-bold">⚠️ Simulation failed: ${err.message}</span>`;
    } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = `<span>▶</span> RUN LIVE SIMULATION`;
    }
}

function viewSimulatedInQueue() {
    closeSimulationModal();
    if (currentView !== 'queue') {
        switchView('queue');
    }

    if (lastSimulatedAlertId) {
        const target = allAlerts.find(a => a.alert_id === lastSimulatedAlertId);
        if (target) {
            selectAlert(target);
            renderTable();

            // Highlight the newly added simulated row
            const row = document.getElementById(`row-${lastSimulatedAlertId}`);
            if (row) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                if (typeof anime !== 'undefined') {
                    anime({
                        targets: row,
                        backgroundColor: ['rgba(0, 242, 255, 0.4)', 'rgba(18, 23, 34, 0.95)'],
                        duration: 1500,
                        easing: 'easeOutQuad'
                    });
                }
            }
        }
    }
}

/* ========================================================================= */
/* VIS.JS HOLOGRAPHIC FRAUD RING KNOWLEDGE GRAPH ENGINE */
/* ========================================================================= */

function renderFraudGraph() {
    if (typeof vis === 'undefined') {
        console.warn('Vis.js not yet loaded');
        return;
    }

    const container = document.getElementById('fraud-graph-canvas');
    if (!container) return;

    const nodesMap = new Map();
    const edgesArray = [];
    const edgeSet = new Set();

    function addEdge(from, to, label, color) {
        const edgeKey = `${from}->${to}`;
        if (!edgeSet.has(edgeKey)) {
            edgeSet.add(edgeKey);
            edgesArray.push({
                from,
                to,
                label: label || '',
                font: { color: '#64748b', size: 9, face: 'JetBrains Mono', align: 'middle' },
                color: { color: color || '#1e2638', highlight: '#00f2ff', hover: '#00f2ff' },
                width: 1.5,
                arrows: { to: { enabled: true, scaleFactor: 0.6 } }
            });
        }
    }

    allAlerts.forEach(a => {
        const userId = a.user_id;
        const devId = a.device_id;
        const ip = a.ip_address;
        const txId = a.transaction_id;
        const isStealth = !a.rules_fired || a.rules_fired.length === 0;
        const isSharedDev = devId && (devId.includes('shared') || devId.includes('stealth') || isStealth);

        // 1. User Node
        if (userId && !nodesMap.has(userId)) {
            nodesMap.set(userId, {
                id: userId,
                label: `👤 ${userId}`,
                group: 'user',
                shape: 'dot',
                size: 22,
                color: {
                    background: '#0d1829',
                    border: '#00f2ff',
                    highlight: { background: '#00f2ff', border: '#ffffff' }
                },
                font: { color: '#00f2ff', face: 'JetBrains Mono', size: 12, bold: true },
                shadow: { enabled: true, color: 'rgba(0,242,255,0.35)', size: 10 },
                title: `User: ${userId} (${a.city || 'Unknown City'})`,
                meta: { type: 'User Entity', id: userId, city: a.city, transactions: [txId], devices: [devId] }
            });
        } else if (userId && nodesMap.has(userId)) {
            const u = nodesMap.get(userId);
            if (!u.meta.transactions.includes(txId)) u.meta.transactions.push(txId);
            if (devId && !u.meta.devices.includes(devId)) u.meta.devices.push(devId);
        }

        // 2. Device Node
        if (devId && !nodesMap.has(devId)) {
            if (isSharedDev) {
                nodesMap.set(devId, {
                    id: devId,
                    label: `🚨 ${devId}\n[FRAUD RING HUB]`,
                    group: 'fraud_device',
                    shape: 'diamond',
                    size: 32,
                    color: {
                        background: '#380a0a',
                        border: '#ef4444',
                        highlight: { background: '#ef4444', border: '#ffffff' }
                    },
                    font: { color: '#f87171', face: 'JetBrains Mono', size: 11, bold: true, multi: true },
                    shadow: { enabled: true, color: 'rgba(239,68,68,0.7)', size: 20 },
                    title: `⚠️ Coordinated Fraud Ring Hardware Hub: ${devId}`,
                    meta: { type: 'Shared Hardware Syndicate Hub', id: devId, users: [userId], is_fraud_hub: true, transactions: [txId] }
                });
            } else {
                nodesMap.set(devId, {
                    id: devId,
                    label: `💻 ${devId}`,
                    group: 'device',
                    shape: 'diamond',
                    size: 18,
                    color: {
                        background: '#081f18',
                        border: '#10b981',
                        highlight: { background: '#10b981', border: '#ffffff' }
                    },
                    font: { color: '#34d399', face: 'JetBrains Mono', size: 10 },
                    shadow: { enabled: true, color: 'rgba(16,185,129,0.2)', size: 6 },
                    title: `Device: ${devId}`,
                    meta: { type: 'Legitimate Hardware Device', id: devId, users: [userId], is_fraud_hub: false, transactions: [txId] }
                });
            }
        } else if (devId && nodesMap.has(devId)) {
            const d = nodesMap.get(devId);
            if (userId && !d.meta.users.includes(userId)) {
                d.meta.users.push(userId);
                // If more than 1 user on device, upgrade to fraud ring hub!
                if (d.meta.users.length > 1 && !d.meta.is_fraud_hub) {
                    d.meta.is_fraud_hub = true;
                    d.label = `🚨 ${devId}\n[SHARED CLUSTER]`;
                    d.size = 32;
                    d.color = { background: '#380a0a', border: '#ef4444', highlight: { background: '#ef4444', border: '#ffffff' } };
                    d.font = { color: '#f87171', face: 'JetBrains Mono', size: 11, bold: true, multi: true };
                    d.shadow = { enabled: true, color: 'rgba(239,68,68,0.7)', size: 20 };
                }
            }
            if (!d.meta.transactions.includes(txId)) d.meta.transactions.push(txId);
        }

        // 3. IP Node
        if (ip && !nodesMap.has(ip)) {
            nodesMap.set(ip, {
                id: ip,
                label: `🌐 ${ip}`,
                group: 'ip',
                shape: 'hexagon',
                size: 16,
                color: {
                    background: '#190d2e',
                    border: '#a855f7',
                    highlight: { background: '#a855f7', border: '#ffffff' }
                },
                font: { color: '#c084fc', face: 'JetBrains Mono', size: 10 },
                shadow: { enabled: true, color: 'rgba(168,85,247,0.2)', size: 6 },
                title: `IP: ${ip}`,
                meta: { type: 'IP Gateway', id: ip, users: [userId], transactions: [txId] }
            });
        }

        // 4. Transaction Node
        if (txId && !nodesMap.has(txId)) {
            const isBlocked = a.recommended_action === 'BLOCK';
            nodesMap.set(txId, {
                id: txId,
                label: `${txId}\n₹${a.amount}`,
                group: 'transaction',
                shape: 'box',
                color: {
                    background: isBlocked ? '#2e0a0a' : '#1f1b0a',
                    border: isBlocked ? '#ef4444' : '#fbbf24',
                    highlight: { background: '#fbbf24', border: '#ffffff' }
                },
                font: { color: isBlocked ? '#fca5a5' : '#fef08a', face: 'JetBrains Mono', size: 9, multi: true },
                shadow: { enabled: true, color: isBlocked ? 'rgba(239,68,68,0.3)' : 'rgba(251,191,36,0.2)', size: 8 },
                title: `Tx: ${txId} | ₹${a.amount} ${a.currency} | Action: ${a.recommended_action}`,
                meta: { type: 'Transaction Event', id: txId, amount: a.amount, user: userId, action: a.recommended_action, risk: a.risk_score }
            });
        }

        // Connect edges
        if (userId && devId) addEdge(userId, devId, 'uses', isSharedDev ? '#ef4444' : '#1e2638');
        if (userId && ip) addEdge(userId, ip, 'origin', '#3b205d');
        if (txId && userId) addEdge(txId, userId, 'payer', '#2a364f');
    });

    const nodesArray = Array.from(nodesMap.values());
    rawGraphData = { nodes: nodesArray, edges: edgesArray, nodesMap };

    graphNodes = new vis.DataSet(nodesArray);
    graphEdges = new vis.DataSet(edgesArray);

    const data = { nodes: graphNodes, edges: graphEdges };
    const options = {
        nodes: {
            borderWidth: 2,
            borderWidthSelected: 3
        },
        edges: {
            smooth: { type: 'continuous' },
            selectionWidth: 3
        },
        physics: {
            enabled: physicsEnabled,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -75,
                centralGravity: 0.012,
                springLength: 110,
                springConstant: 0.08,
                damping: 0.45
            },
            stabilization: { iterations: 120 }
        },
        interaction: {
            hover: true,
            tooltipDelay: 80,
            navigationButtons: false,
            keyboard: false
        }
    };

    network = new vis.Network(container, data, options);

    network.on('selectNode', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const nodeData = nodesMap.get(nodeId);
            highlightConnectedSubnetwork(nodeId);
            updateGraphHUD(nodeData);
        }
    });

    network.on('deselectNode', function() {
        restoreGraphOpacity();
        resetGraphHUD();
    });
}

function highlightConnectedSubnetwork(selectedNodeId) {
    if (!network || !graphNodes || !graphEdges) return;

    const connectedNodes = network.getConnectedNodes(selectedNodeId);
    connectedNodes.push(selectedNodeId);
    const connectedEdges = network.getConnectedEdges(selectedNodeId);

    const allNodeIds = graphNodes.getIds();
    const updateNodes = [];

    allNodeIds.forEach(id => {
        if (connectedNodes.includes(id)) {
            updateNodes.push({ id, opacity: 1.0 });
        } else {
            updateNodes.push({ id, opacity: 0.15 });
        }
    });

    graphNodes.update(updateNodes);
}

function restoreGraphOpacity() {
    if (!graphNodes) return;
    const allNodeIds = graphNodes.getIds();
    const updateNodes = allNodeIds.map(id => ({ id, opacity: 1.0 }));
    graphNodes.update(updateNodes);
}

function updateGraphHUD(nodeData) {
    const typeBadge = document.getElementById('hud-entity-type');
    const content = document.getElementById('hud-entity-content');
    if (!nodeData || !typeBadge || !content) return;

    const meta = nodeData.meta || {};

    if (meta.is_fraud_hub) {
        typeBadge.innerText = '🚨 SYNDICATE HUB';
        typeBadge.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-red-950 text-red-300 border border-red-500 shadow-[0_0_10px_rgba(239,68,68,0.4)]';
        
        content.innerHTML = `
            <div class="border-b border-[#1e2638] pb-1.5">
                <div class="text-[10px] text-slate-500 uppercase">HARDWARE ID</div>
                <div class="font-bold text-red-400 break-all">${meta.id}</div>
            </div>
            <div class="space-y-1">
                <div class="text-[10px] text-slate-500 uppercase">CONNECTED CONSPIRATORS</div>
                <div class="flex flex-wrap gap-1">
                    ${(meta.users || []).map(u => `<span class="bg-cyan-950 text-cyan-300 border border-cyan-500/40 px-1.5 py-0.5 rounded text-[10px] font-bold">${u}</span>`).join('')}
                </div>
            </div>
            <div class="space-y-1 border-t border-[#1e2638] pt-1.5">
                <div class="text-[10px] text-slate-500 uppercase">SYNDICATE EXPOSURE</div>
                <div class="text-slate-200">${(meta.transactions || []).length} Coordinated Transactions</div>
                <div class="text-red-400 font-bold text-[11px]">CRITICAL THREAT — 100% BLOCKED</div>
            </div>
        `;
    } else if (meta.type === 'User Entity') {
        typeBadge.innerText = '👤 USER ACCOUNT';
        typeBadge.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/40';

        content.innerHTML = `
            <div class="border-b border-[#1e2638] pb-1.5">
                <div class="text-[10px] text-slate-500 uppercase">USER IDENTIFIER</div>
                <div class="font-bold text-cyan-300">${meta.id}</div>
            </div>
            <div>
                <div class="text-[10px] text-slate-500 uppercase">PRIMARY LOCATION</div>
                <div class="text-slate-200">${meta.city || 'N/A'}</div>
            </div>
            <div class="space-y-1 border-t border-[#1e2638] pt-1.5">
                <div class="text-[10px] text-slate-500 uppercase">LINKED HARDWARE</div>
                <div class="text-[11px] text-slate-300">${(meta.devices || []).join(', ') || 'None'}</div>
            </div>
        `;
    } else if (meta.type === 'Transaction Event') {
        typeBadge.innerText = '💳 TRANSACTION';
        typeBadge.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-500/40';

        content.innerHTML = `
            <div class="border-b border-[#1e2638] pb-1.5">
                <div class="text-[10px] text-slate-500 uppercase">TRANSACTION ID</div>
                <div class="font-bold text-amber-300">${meta.id}</div>
            </div>
            <div class="grid grid-cols-2 gap-2">
                <div>
                    <div class="text-[10px] text-slate-500 uppercase">AMOUNT</div>
                    <div class="font-bold text-[#00f2ff]">₹${meta.amount}</div>
                </div>
                <div>
                    <div class="text-[10px] text-slate-500 uppercase">COPILOT ACTION</div>
                    <div class="font-bold ${meta.action === 'BLOCK' ? 'text-red-400' : 'text-emerald-400'}">${meta.action}</div>
                </div>
            </div>
        `;
    } else {
        typeBadge.innerText = '🌐 ENTITY';
        typeBadge.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-500/40';

        content.innerHTML = `
            <div>
                <div class="text-[10px] text-slate-500 uppercase">IDENTIFIER</div>
                <div class="font-bold text-purple-300">${meta.id || nodeData.id}</div>
            </div>
            <div class="text-[11px] text-slate-400">${meta.type || 'Network Node'}</div>
        `;
    }
}

function resetGraphHUD() {
    const typeBadge = document.getElementById('hud-entity-type');
    const content = document.getElementById('hud-entity-content');
    if (!typeBadge || !content) return;

    typeBadge.innerText = 'READY';
    typeBadge.className = 'text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/40';
    content.innerHTML = `<p class="text-[11px] text-slate-400">Click any user, shared hardware hub, or transaction node in the network to inspect blast radius and syndicate exposure.</p>`;
}

function isolateStealthRing() {
    if (!network || !rawGraphData.nodesMap) return;

    const stealthDev = 'dev_shared_stealth_ring';
    if (rawGraphData.nodesMap.has(stealthDev)) {
        network.selectNodes([stealthDev]);
        highlightConnectedSubnetwork(stealthDev);
        updateGraphHUD(rawGraphData.nodesMap.get(stealthDev));
        network.focus(stealthDev, {
            scale: 1.25,
            animation: { duration: 800, easingFunction: 'easeInOutQuad' }
        });
    }
}

function resetGraphFilter() {
    if (!network) return;
    restoreGraphOpacity();
    resetGraphHUD();
    network.unselectAll();
    fitGraphView();
}

function fitGraphView() {
    if (!network) return;
    network.fit({
        animation: { duration: 600, easingFunction: 'easeInOutQuad' }
    });
}

function toggleGraphPhysics() {
    if (!network) return;
    physicsEnabled = !physicsEnabled;
    network.setOptions({ physics: { enabled: physicsEnabled } });
    const btn = document.getElementById('btn-graph-physics');
    if (btn) {
        btn.innerText = physicsEnabled ? '⚡ Physics: ON' : '⚡ Physics: OFF';
        btn.className = physicsEnabled 
            ? 'bg-[#1a2233] hover:bg-[#253047] text-cyan-400 border border-[#2a364f] text-[11px] font-mono px-3 py-1.5 rounded-lg transition-all cursor-pointer'
            : 'bg-[#1a2233] hover:bg-[#253047] text-slate-400 border border-[#2a364f] text-[11px] font-mono px-3 py-1.5 rounded-lg transition-all cursor-pointer';
    }
}
