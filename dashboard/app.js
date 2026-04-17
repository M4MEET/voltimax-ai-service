/* ── Global Chart defaults ────────────────────────────────────────────────── */
Chart.defaults.font.family = "-apple-system, 'Inter', sans-serif";

/* ── State ───────────────────────────────────────────────────────────────── */
const state = {
    apiKey:        '',
    days:          7,
    section:       'overview',
    convSkip:      0,
    convLimit:     20,
    convTotal:     0,
    convTopic:     '',
    charts:        {},
    refreshTimer:  null,
};

const API = window.location.origin;

/* ── XSS-safe helper ─────────────────────────────────────────────────────── */
// All user-supplied or API-supplied strings go through esc() before innerHTML use.
function esc(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/* ── Toast notifications ─────────────────────────────────────────────────── */
function showToast(message, type = 'error') {
    const toast = document.createElement('div');
    toast.style.cssText = [
        'position:fixed',
        'top:20px',
        'right:20px',
        'z-index:200',
        'padding:10px 18px',
        'border-radius:999px',
        'font-size:13px',
        'font-weight:500',
        'color:#fff',
        'box-shadow:0 4px 16px rgba(0,0,0,0.18)',
        'transform:translateX(120%)',
        'transition:transform 0.3s cubic-bezier(0.34,1.56,0.64,1)',
        'pointer-events:none',
        'white-space:nowrap',
        type === 'error'
            ? 'background:linear-gradient(135deg,#ef4444,#dc2626)'
            : 'background:linear-gradient(135deg,#10b981,#059669)',
    ].join(';');
    toast.textContent = message;
    document.body.appendChild(toast);

    // Slide in
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.style.transform = 'translateX(0)';
        });
    });

    // Auto-dismiss after 3 s
    setTimeout(() => {
        toast.style.transform = 'translateX(120%)';
        setTimeout(() => toast.remove(), 320);
    }, 3000);
}

/* ── Animated number counter ─────────────────────────────────────────────── */
/**
 * Animates a numeric value from 0 to `target` over `duration` ms.
 * Handles plain integers and percentages (e.g. "73%").
 * Skips animation for non-numeric display values like '—'.
 */
function animateCounter(el, displayValue, duration = 800) {
    const percentMatch = String(displayValue).match(/^([\d.]+)%$/);
    const numMatch     = String(displayValue).match(/^[\d,]+(\.\d+)?$/);

    if (percentMatch) {
        const target = parseFloat(percentMatch[1]);
        const start  = performance.now();
        function step(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased    = 1 - Math.pow(1 - progress, 3); // ease-out cubic
            el.textContent = Math.round(target * eased) + '%';
            if (progress < 1) requestAnimationFrame(step);
            else              el.textContent = displayValue; // ensure exact final value
        }
        requestAnimationFrame(step);

    } else if (numMatch) {
        // Strip commas to get raw number
        const target = parseFloat(String(displayValue).replace(/,/g, ''));
        const start  = performance.now();
        function step(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased    = 1 - Math.pow(1 - progress, 3);
            el.textContent = Math.round(target * eased).toLocaleString();
            if (progress < 1) requestAnimationFrame(step);
            else              el.textContent = displayValue;
        }
        requestAnimationFrame(step);

    } else {
        // Non-numeric (e.g. '—') — set immediately, no animation
        el.textContent = displayValue;
    }
}

/* ── API ─────────────────────────────────────────────────────────────────── */
async function apiFetch(path, params = {}) {
    const url = new URL(API + path);
    Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
    const res = await fetch(url, { headers: { 'X-Dashboard-Key': state.apiKey } });
    if (res.status === 401) throw new Error('Unauthorized');
    if (!res.ok) {
        showToast('Failed to load data');
        throw new Error(`HTTP ${res.status}`);
    }
    return res.json();
}

async function adminFetch(method, path, body) {
    const opts = {
        method,
        headers: { 'X-Dashboard-Key': state.apiKey },
    };
    if (body !== undefined) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(API + path, opts);
    if (res.status === 401) throw new Error('Unauthorized');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.status === 204 ? null : res.json();
}

/* ── Auto-refresh ────────────────────────────────────────────────────────── */
function startAutoRefresh() {
    clearAutoRefresh();
    state.refreshTimer = setInterval(() => loadSection(state.section), 60_000);
}

function clearAutoRefresh() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
        state.refreshTimer = null;
    }
}

/* ── Login ───────────────────────────────────────────────────────────────── */
document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const key = document.getElementById('api-key-input').value.trim();
    const errEl = document.getElementById('login-error');
    if (!key) return;
    errEl.textContent = '';
    state.apiKey = key;
    try {
        await apiFetch('/api/analytics/overview', { days: 7 });
        localStorage.setItem('vtx_dash_key', key);
        showApp();
    } catch {
        errEl.textContent = 'Invalid API key. Please try again.';
        state.apiKey = '';
    }
});

function showApp() {
    document.getElementById('login').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    loadSection('overview');
    startAutoRefresh();
}

document.getElementById('logout-btn').addEventListener('click', () => {
    clearAutoRefresh();
    localStorage.removeItem('vtx_dash_key');
    document.getElementById('app').classList.add('hidden');
    document.getElementById('login').classList.remove('hidden');
    document.getElementById('api-key-input').value = '';
    state.apiKey = '';
});

window.addEventListener('DOMContentLoaded', async () => {
    const saved = localStorage.getItem('vtx_dash_key');
    if (saved) {
        state.apiKey = saved;
        try {
            await apiFetch('/api/analytics/overview', { days: 7 });
            showApp();
        } catch {
            localStorage.removeItem('vtx_dash_key');
            state.apiKey = '';
        }
    }
});

/* ── Navigation ──────────────────────────────────────────────────────────── */
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        loadSection(link.dataset.section);
    });
});

document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.days = parseInt(btn.dataset.days);
        loadSection(state.section);
    });
});

document.getElementById('refresh-btn').addEventListener('click', () => loadSection(state.section));

function loadSection(name) {
    state.section = name;
    document.querySelectorAll('.section').forEach(s => {
        s.classList.add('hidden');
        s.classList.remove('section--visible');
    });
    const target = document.getElementById('section-' + name);
    if (!target) { console.error('Unknown section:', name); return; }
    target.classList.remove('hidden');
    // Trigger fade-in on next frame so the class swap is painted first
    requestAnimationFrame(() => target.classList.add('section--visible'));

    document.getElementById('section-title').textContent =
        ({ 'llm-config': 'LLM Config', 'topics-config': 'Topics', knowledge: 'Knowledge Base' }[name])
        || name.charAt(0).toUpperCase() + name.slice(1);

    const noPeriod = ['llm-config', 'topics-config', 'knowledge'];
    document.querySelector('.period-btns').style.display = noPeriod.includes(name) ? 'none' : '';

    ({ overview: loadOverview, topics: loadTopics, conversations: loadConversations,
       feedback: loadFeedback, costs: loadCosts,
       'llm-config': loadLlmConfig, 'topics-config': loadTopicsConfig, knowledge: loadKnowledge })[name]?.();
}

/* ── Spinner ─────────────────────────────────────────────────────────────── */
function spinning(on) {
    document.getElementById('refresh-btn').classList.toggle('spinning', on);
}

/* ── Formatters ──────────────────────────────────────────────────────────── */
function fmt(n) { return n == null ? '—' : Number(n).toLocaleString(); }
function fmtDate(s) {
    if (!s) return '—';
    return new Date(s).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });
}
function starsStr(avg) {
    const full = Math.round(avg || 0);
    return '★'.repeat(full) + '☆'.repeat(5 - full);
}

/* ── Loading skeletons ───────────────────────────────────────────────────── */
function showKpiSkeletons() {
    const grid = document.getElementById('kpi-grid');
    grid.textContent = '';
    for (let i = 0; i < 6; i++) {
        const card = document.createElement('div');
        card.className = 'skeleton kpi-card';
        grid.appendChild(card);
    }
}

/* ── Overview ────────────────────────────────────────────────────────────── */
async function loadOverview() {
    spinning(true);
    showKpiSkeletons();
    try {
        const [ov, esc_data, rat] = await Promise.all([
            apiFetch('/api/analytics/overview', { days: state.days }),
            apiFetch('/api/analytics/escalations', { days: state.days }),
            apiFetch('/api/analytics/ratings', { days: state.days }),
        ]);
        renderKpis(ov);
        renderEscalations(esc_data);
        renderRatingChart('rating-chart', 'rating-summary', rat);
    } catch (err) { console.error(err); }
    spinning(false);
}

function renderKpis(ov) {
    const grid = document.getElementById('kpi-grid');
    grid.textContent = ''; // remove skeletons

    const cards = [
        { label: 'Total Chats',        value: fmt(ov.total_chats),                sub: 'Last ' + ov.period_days + ' days',  color: '' },
        { label: 'Active Now',         value: fmt(ov.active_now),                 sub: 'Live sessions',                      color: 'green' },
        { label: 'Escalation Rate',    value: (ov.escalation_rate ?? 0) + '%',    sub: 'Chats escalated to human',           color: ov.escalation_rate > 20 ? 'red' : 'yellow' },
        { label: 'AI Resolution Rate', value: (ov.ai_resolution_rate ?? 0) + '%', sub: 'Resolved by AI',                    color: 'green' },
        { label: 'Tickets Created',    value: fmt(ov.tickets_created),            sub: 'Support tickets opened',             color: '' },
        { label: 'Token Usage',        value: fmt(ov.token_usage),                sub: 'Total LLM tokens consumed',          color: '' },
    ];

    cards.forEach(c => {
        const card = document.createElement('div');
        card.className = 'kpi-card' + (c.color ? ' ' + c.color : '');

        const lbl = document.createElement('div');
        lbl.className = 'kpi-card__label';
        lbl.textContent = c.label;

        const val = document.createElement('div');
        val.className = 'kpi-card__value';
        // Start at '0' and animate to actual value
        val.textContent = '0';
        animateCounter(val, c.value);

        const sub = document.createElement('div');
        sub.className = 'kpi-card__sub';
        sub.textContent = c.sub;

        card.append(lbl, val, sub);
        grid.appendChild(card);
    });
}

function renderEscalations(list) {
    const el = document.getElementById('escalation-list');
    el.textContent = '';
    if (!list.length) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = 'No escalations in this period.';
        el.appendChild(empty);
        return;
    }

    const reasonMap = {
        ai_detected:      'AI detected frustration',
        user_not_helpful: 'User asked for human',
        ticket_created:   'Ticket created',
    };

    const max = list[0].count || 1;
    list.forEach(r => {
        const row = document.createElement('div');
        row.className = 'esc-row';

        const label = document.createElement('div');
        label.className = 'esc-label';
        label.textContent = reasonMap[r._id] || r._id || 'Unknown';

        const barWrap = document.createElement('div');
        barWrap.className = 'esc-bar-wrap';
        const bar = document.createElement('div');
        bar.className = 'esc-bar';
        bar.style.width = Math.round(r.count / max * 100) + '%';
        barWrap.appendChild(bar);

        const count = document.createElement('div');
        count.className = 'esc-count';
        count.textContent = r.count;

        row.append(label, barWrap, count);
        el.appendChild(row);
    });
}

/* ── Topics ──────────────────────────────────────────────────────────────── */
async function loadTopics() {
    spinning(true);
    try {
        const data = await apiFetch('/api/analytics/topics', { days: state.days });
        renderTopicsChart(data);
    } catch (err) { console.error(err); }
    spinning(false);
}

function renderTopicsChart(data) {
    destroyChart('topics-chart');
    const canvas = document.getElementById('topics-chart');
    const ctx = canvas.getContext('2d');

    // Build gradient for primary dataset (blue-purple)
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.offsetHeight || 300);
    gradient.addColorStop(0, 'rgba(91,110,245,0.85)');
    gradient.addColorStop(1, 'rgba(91,110,245,0.35)');

    state.charts['topics-chart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(r => r._id || 'unknown'),
            datasets: [
                {
                    label: 'Total',
                    data: data.map(r => r.count),
                    backgroundColor: gradient,
                    borderRadius: 6,
                    borderSkipped: false,
                },
                {
                    label: 'Escalated',
                    data: data.map(r => r.escalated || 0),
                    backgroundColor: '#ef4444aa',
                    borderRadius: 6,
                    borderSkipped: false,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label(ctx) {
                            return ` ${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString()}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 11 } },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: '#f0f0f0' },
                    ticks: { font: { size: 11 } },
                },
            },
        },
    });
}

/* ── Conversations ───────────────────────────────────────────────────────── */
async function loadConversations(reset = true) {
    if (reset) state.convSkip = 0;
    spinning(true);
    try {
        const data = await apiFetch('/api/analytics/conversations', {
            skip:  state.convSkip,
            limit: state.convLimit,
            topic: state.convTopic || null,
        });
        state.convTotal = data.total;
        renderConversationsTable(data.sessions || []);
        renderPagination();
        populateTopicFilter(data.sessions || []);
    } catch (err) { console.error(err); }
    spinning(false);
}

function renderConversationsTable(sessions) {
    const tbody = document.getElementById('conversations-body');
    tbody.textContent = '';

    if (!sessions.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 6;
        td.innerHTML = '<div class="empty">No conversations found.</div>';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    sessions.forEach(s => {
        const tr = document.createElement('tr');

        // Customer cell
        const tdCustomer = document.createElement('td');
        const name = document.createElement('div');
        name.textContent = s.customer_name || '—';
        const email = document.createElement('div');
        email.style.cssText = 'font-size:11px;color:var(--text-muted)';
        email.textContent = s.customer_email || '';
        tdCustomer.append(name, email);

        // Topic
        const tdTopic = document.createElement('td');
        tdTopic.textContent = s.topic_id || '—';

        // Status badge
        const tdStatus = document.createElement('td');
        const badge = document.createElement('span');
        const status = s.status || 'active';
        badge.className = 'badge badge--' + status;
        badge.textContent = status;
        tdStatus.appendChild(badge);

        // Messages
        const tdMsgs = document.createElement('td');
        tdMsgs.style.textAlign = 'center';
        tdMsgs.textContent = s.message_count || 0;

        // Date
        const tdDate = document.createElement('td');
        tdDate.textContent = fmtDate(s.created_at);

        // Transcript button
        const tdBtn = document.createElement('td');
        const btn = document.createElement('button');
        btn.className = 'view-btn';
        btn.textContent = 'Transcript';
        btn.addEventListener('click', () => openTranscript(s.id));
        tdBtn.appendChild(btn);

        tr.append(tdCustomer, tdTopic, tdStatus, tdMsgs, tdDate, tdBtn);
        tbody.appendChild(tr);
    });
}

function renderPagination() {
    const el = document.getElementById('conversations-pagination');
    el.textContent = '';

    const page = Math.floor(state.convSkip / state.convLimit) + 1;
    const pages = Math.ceil(state.convTotal / state.convLimit) || 1;

    const prev = document.createElement('button');
    prev.className = 'page-btn';
    prev.textContent = '← Prev';
    prev.disabled = state.convSkip === 0;
    prev.addEventListener('click', () => {
        state.convSkip = Math.max(0, state.convSkip - state.convLimit);
        loadConversations(false);
    });

    const info = document.createElement('span');
    info.className = 'page-info';
    info.textContent = 'Page ' + page + ' of ' + pages + ' (' + state.convTotal + ' total)';

    const next = document.createElement('button');
    next.className = 'page-btn';
    next.textContent = 'Next →';
    next.disabled = state.convSkip + state.convLimit >= state.convTotal;
    next.addEventListener('click', () => {
        state.convSkip += state.convLimit;
        loadConversations(false);
    });

    el.append(prev, info, next);
}

function populateTopicFilter(sessions) {
    const sel = document.getElementById('topic-filter');
    if (sel.options.length > 1) return;
    const topics = [...new Set(sessions.map(s => s.topic_id).filter(Boolean))];
    topics.forEach(t => {
        const o = document.createElement('option');
        o.value = t;
        o.textContent = t;
        sel.appendChild(o);
    });
    sel.addEventListener('change', () => {
        state.convTopic = sel.value;
        loadConversations(true);
    });
}

/* ── Transcript modal ────────────────────────────────────────────────────── */
async function openTranscript(sessionId) {
    try {
        const data = await apiFetch('/api/analytics/conversation/' + encodeURIComponent(sessionId));
        const session = data.session || {};
        const msgs = data.messages || [];

        document.getElementById('modal-title').textContent =
            (session.customer_name || 'Unknown') + ' — ' + (session.topic_id || 'Chat');
        document.getElementById('modal-sub').textContent =
            (session.customer_email || '') + ' · ' + fmtDate(session.created_at);

        const body = document.getElementById('modal-body');
        body.textContent = '';

        if (!msgs.length) {
            const empty = document.createElement('div');
            empty.className = 'empty';
            empty.textContent = 'No messages.';
            body.appendChild(empty);
        } else {
            msgs.forEach(m => {
                const isUser = m.role === 'user';
                const wrapper = document.createElement('div');
                wrapper.className = 'tx-msg tx-msg--' + (isUser ? 'user' : 'ai');

                const inner = document.createElement('div');

                const bubble = document.createElement('div');
                bubble.className = 'tx-bubble';
                bubble.textContent = m.content;

                const label = document.createElement('div');
                label.className = 'tx-label';
                label.textContent = fmtDate(m.created_at);

                inner.append(bubble, label);
                wrapper.appendChild(inner);
                body.appendChild(wrapper);
            });
        }

        document.getElementById('modal').classList.remove('hidden');
    } catch (err) { console.error(err); }
}

document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal').classList.add('hidden');
});
document.getElementById('modal-backdrop').addEventListener('click', () => {
    document.getElementById('modal').classList.add('hidden');
});

/* ── Feedback ────────────────────────────────────────────────────────────── */
async function loadFeedback() {
    spinning(true);
    try {
        const [fb, rat] = await Promise.all([
            apiFetch('/api/analytics/feedback', { days: state.days }),
            apiFetch('/api/analytics/ratings',  { days: state.days }),
        ]);
        renderFeedback(fb);
        renderRatingChart('rating-chart2', 'rating-summary2', rat);
    } catch (err) { console.error(err); }
    spinning(false);
}

/* ── Center-text plugin for doughnut chart ────────────────────────────────── */
const doughnutCenterTextPlugin = {
    id: 'doughnutCenterText',
    afterDraw(chart) {
        if (chart.config.type !== 'doughnut') return;
        const centerText = chart.config.options?.plugins?.doughnutCenterText;
        if (!centerText?.text) return;

        const { ctx, chartArea: { left, right, top, bottom } } = chart;
        const cx = (left + right) / 2;
        const cy = (top + bottom) / 2;

        ctx.save();
        ctx.font = `700 ${centerText.fontSize || 22}px ${Chart.defaults.font.family}`;
        ctx.fillStyle = centerText.color || '#111';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(centerText.text, cx, cy - 8);

        if (centerText.subText) {
            ctx.font = `400 ${centerText.subFontSize || 11}px ${Chart.defaults.font.family}`;
            ctx.fillStyle = centerText.subColor || '#888';
            ctx.fillText(centerText.subText, cx, cy + 14);
        }
        ctx.restore();
    },
};
Chart.register(doughnutCenterTextPlugin);

function renderFeedback(fb) {
    const el = document.getElementById('feedback-stats');
    el.textContent = '';

    [
        { icon: '👍', num: fb.up,                     label: 'Helpful' },
        { icon: '👎', num: fb.down,                    label: 'Not helpful' },
        { icon: '📊', num: fb.satisfaction_rate + '%', label: 'Satisfaction' },
    ].forEach(({ icon, num, label }) => {
        const stat = document.createElement('div');
        stat.className = 'fb-stat';

        const ico = document.createElement('div');
        ico.className = 'fb-stat__icon';
        ico.textContent = icon;

        const n = document.createElement('div');
        n.className = 'fb-stat__num';
        n.textContent = num;

        const lbl = document.createElement('div');
        lbl.className = 'fb-stat__label';
        lbl.textContent = label;

        stat.append(ico, n, lbl);
        el.appendChild(stat);
    });

    destroyChart('feedback-chart');
    if (!fb.total) return;

    const satisfactionPct = fb.satisfaction_rate ?? 0;
    const ctx = document.getElementById('feedback-chart').getContext('2d');
    state.charts['feedback-chart'] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Helpful 👍', 'Not helpful 👎'],
            datasets: [{
                data: [fb.up, fb.down],
                backgroundColor: ['#10b981', '#ef4444'],
                borderWidth: 0,
                spacing: 4,
            }],
        },
        options: {
            responsive: true,
            cutout: '65%',
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label(ctx) {
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct   = total ? Math.round(ctx.parsed / total * 100) : 0;
                            return ` ${ctx.label}: ${ctx.parsed.toLocaleString()} (${pct}%)`;
                        },
                    },
                },
                doughnutCenterText: {
                    text:        satisfactionPct + '%',
                    fontSize:    22,
                    color:       '#111',
                    subText:     'satisfaction',
                    subFontSize: 11,
                    subColor:    '#888',
                },
            },
        },
    });
}

function renderRatingChart(chartId, summaryId, rat) {
    const avg   = rat.avg_rating || 0;
    const total = rat.total || 0;
    const sumEl = document.getElementById(summaryId);
    sumEl.textContent = '';

    if (!total) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = 'No ratings yet.';
        sumEl.appendChild(empty);
    } else {
        const avgEl = document.createElement('div');
        avgEl.className = 'rating-avg';
        avgEl.textContent = avg.toFixed(1);

        const right = document.createElement('div');

        const starsEl = document.createElement('div');
        starsEl.className = 'rating-stars';
        starsEl.textContent = starsStr(avg);

        const countEl = document.createElement('div');
        countEl.className = 'rating-count';
        countEl.textContent = total + ' ratings';

        right.append(starsEl, countEl);
        sumEl.append(avgEl, right);
    }

    destroyChart(chartId);
    if (!total) return;

    const dist   = rat.distribution || {};
    const canvas = document.getElementById(chartId);
    const ctx    = canvas.getContext('2d');

    // Horizontal gradient: amber → yellow
    const gradient = ctx.createLinearGradient(0, 0, canvas.offsetWidth || 300, 0);
    gradient.addColorStop(0, '#f59e0b');
    gradient.addColorStop(1, '#fbbf24');

    state.charts[chartId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['5★', '4★', '3★', '2★', '1★'],
            datasets: [{
                data: [5, 4, 3, 2, 1].map(n => dist[String(n)] || 0),
                backgroundColor: gradient,
                borderRadius: 6,
                borderSkipped: false,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label(ctx) {
                            return ` ${ctx.parsed.x.toLocaleString()} ratings`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: '#f0f0f0' },
                    ticks: { font: { size: 11 } },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 11 } },
                },
            },
        },
    });
}

/* ── Costs ───────────────────────────────────────────────────────────────── */
async function loadCosts() {
    spinning(true);
    try {
        const data = await apiFetch('/api/analytics/costs', { days: state.days });
        const providers = data.providers || [];
        const tbody = document.getElementById('costs-body');
        tbody.textContent = '';

        if (!providers.length) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 4;
            td.innerHTML = '<div class="empty">No cost data.</div>';
            tr.appendChild(td);
            tbody.appendChild(tr);
            spinning(false);
            return;
        }

        providers.forEach(p => {
            const tr = document.createElement('tr');

            const tdProvider = document.createElement('td');
            const strong = document.createElement('strong');
            strong.textContent = p.provider;
            tdProvider.appendChild(strong);

            const tdSessions = document.createElement('td');
            tdSessions.textContent = fmt(p.session_count);

            const tdTokens = document.createElement('td');
            tdTokens.textContent = fmt(p.total_tokens);

            const tdCost = document.createElement('td');
            const costStrong = document.createElement('strong');
            costStrong.textContent = '$' + (p.estimated_cost || 0).toFixed(2);
            tdCost.appendChild(costStrong);

            tr.append(tdProvider, tdSessions, tdTokens, tdCost);
            tbody.appendChild(tr);
        });

        // Total row
        const totalCost     = providers.reduce((s, p) => s + (p.estimated_cost  || 0), 0);
        const totalSessions = providers.reduce((s, p) => s + (p.session_count   || 0), 0);
        const totalTokens   = providers.reduce((s, p) => s + (p.total_tokens    || 0), 0);

        const trTotal = document.createElement('tr');
        trTotal.style.cssText = 'font-weight:700;background:#fafafa;border-top:2px solid var(--border)';

        ['Total', fmt(totalSessions), fmt(totalTokens), '$' + totalCost.toFixed(2)].forEach(text => {
            const td = document.createElement('td');
            td.textContent = text;
            trTotal.appendChild(td);
        });
        tbody.appendChild(trTotal);
    } catch (err) { console.error(err); }
    spinning(false);
}

/* ── Chart cleanup ───────────────────────────────────────────────────────── */
function destroyChart(id) {
    if (state.charts[id]) { state.charts[id].destroy(); delete state.charts[id]; }
}

/* ── LLM Config ──────────────────────────────────────────────────────────── */
const LLM_PROVIDERS = ['openai', 'anthropic', 'google', 'mistral', 'custom'];
const LLM_LABELS    = { openai:'OpenAI', anthropic:'Anthropic (Claude)', google:'Google (Gemini)', mistral:'Mistral', custom:'Custom (OpenAI-compatible)' };
const LLM_MODELS    = {
    openai:    ['gpt-4o','gpt-4o-mini','gpt-4-turbo','gpt-3.5-turbo'],
    anthropic: ['claude-opus-4-6','claude-sonnet-4-6','claude-haiku-4-5-20251001'],
    google:    ['gemini-1.5-pro','gemini-1.5-flash','gemini-2.0-flash'],
    mistral:   ['mistral-large-latest','mistral-small-latest','open-mistral-7b'],
    custom:    [],
};
let llmData = {};

async function loadLlmConfig() {
    spinning(true);
    const body = document.getElementById('llm-config-body');
    body.textContent = '';
    try {
        llmData = await apiFetch('/api/admin/config/llm');
        renderLlmConfig(llmData);
    } catch (err) {
        body.innerHTML = '<div class="empty">Failed to load LLM config: ' + esc(err.message) + '</div>';
    }
    spinning(false);
}

function renderLlmConfig(data) {
    const body = document.getElementById('llm-config-body');
    body.textContent = '';

    LLM_PROVIDERS.forEach(name => {
        const cfg = data[name] || { api_key:'', default_model:'', base_url:'', enabled:false };
        const card = document.createElement('div');
        card.className = 'cfg-provider-card';
        card.dataset.provider = name;

        const hdr = document.createElement('div');
        hdr.className = 'cfg-provider-hdr';

        const lbl = document.createElement('span');
        lbl.className = 'cfg-provider-label';
        lbl.textContent = LLM_LABELS[name] || name;

        const toggle = document.createElement('label');
        toggle.className = 'cfg-toggle';
        const chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.checked = cfg.enabled !== false;
        chk.dataset.field = 'enabled';
        chk.dataset.provider = name;
        const slider = document.createElement('span');
        slider.className = 'cfg-toggle__slider';
        toggle.append(chk, slider);

        hdr.append(lbl, toggle);
        card.appendChild(hdr);

        const fields = document.createElement('div');
        fields.className = 'cfg-provider-fields';

        // API Key field
        const keyRow = document.createElement('div');
        keyRow.className = 'cfg-field-row';
        const keyLabel = document.createElement('label');
        keyLabel.textContent = 'API Key';
        const keyInput = document.createElement('input');
        keyInput.type = 'password';
        keyInput.className = 'cfg-input';
        keyInput.placeholder = cfg.api_key === '***' ? '(saved — enter new key to change)' : 'Enter API key…';
        keyInput.value = '';
        keyInput.dataset.field = 'api_key';
        keyInput.dataset.provider = name;
        keyRow.append(keyLabel, keyInput);
        fields.appendChild(keyRow);

        // Model field
        const modelRow = document.createElement('div');
        modelRow.className = 'cfg-field-row';
        const modelLabel = document.createElement('label');
        modelLabel.textContent = 'Default Model';
        const models = LLM_MODELS[name];
        let modelInput;
        if (models && models.length) {
            modelInput = document.createElement('select');
            modelInput.className = 'cfg-input';
            models.forEach(m => {
                const o = document.createElement('option');
                o.value = m;
                o.textContent = m;
                if (m === cfg.default_model) o.selected = true;
                modelInput.appendChild(o);
            });
        } else {
            modelInput = document.createElement('input');
            modelInput.type = 'text';
            modelInput.className = 'cfg-input';
            modelInput.placeholder = 'e.g. llama3';
            modelInput.value = cfg.default_model || '';
        }
        modelInput.dataset.field = 'default_model';
        modelInput.dataset.provider = name;
        modelRow.append(modelLabel, modelInput);
        fields.appendChild(modelRow);

        // Base URL (custom only)
        if (name === 'custom') {
            const urlRow = document.createElement('div');
            urlRow.className = 'cfg-field-row';
            const urlLabel = document.createElement('label');
            urlLabel.textContent = 'Base URL';
            const urlInput = document.createElement('input');
            urlInput.type = 'text';
            urlInput.className = 'cfg-input';
            urlInput.placeholder = 'http://localhost:11434/v1';
            urlInput.value = cfg.base_url || '';
            urlInput.dataset.field = 'base_url';
            urlInput.dataset.provider = name;
            urlRow.append(urlLabel, urlInput);
            fields.appendChild(urlRow);
        }

        card.appendChild(fields);
        body.appendChild(card);
    });
}

function collectLlmFormData() {
    const result = {};
    LLM_PROVIDERS.forEach(name => {
        const card = document.querySelector(`.cfg-provider-card[data-provider="${name}"]`);
        if (!card) return;
        const enabledEl  = card.querySelector('[data-field="enabled"]');
        const apiKeyEl   = card.querySelector('[data-field="api_key"]');
        const modelEl    = card.querySelector('[data-field="default_model"]');
        const baseUrlEl  = card.querySelector('[data-field="base_url"]');
        result[name] = {
            enabled:       enabledEl  ? enabledEl.checked   : false,
            api_key:       apiKeyEl   ? apiKeyEl.value       : '',
            default_model: modelEl    ? modelEl.value        : '',
            base_url:      baseUrlEl  ? baseUrlEl.value      : '',
        };
    });
    return result;
}

document.getElementById('llm-save-btn').addEventListener('click', async () => {
    const btn = document.getElementById('llm-save-btn');
    btn.textContent = 'Saving…';
    btn.disabled = true;
    try {
        const payload = collectLlmFormData();
        await adminFetch('PUT', '/api/admin/config/llm', payload);
        showToast('LLM configuration saved!', 'success');
        await loadLlmConfig();
    } catch (err) {
        showToast('Save failed: ' + err.message);
    } finally {
        btn.textContent = 'Save Changes';
        btn.disabled = false;
    }
});

/* ── Topics Config ───────────────────────────────────────────────────────── */
let topicsData = [];

async function loadTopicsConfig() {
    spinning(true);
    const body = document.getElementById('topics-config-body');
    body.textContent = '';
    try {
        topicsData = await apiFetch('/api/admin/topics');
        renderTopicsConfig();
    } catch (err) {
        body.innerHTML = '<div class="empty">Failed to load topics: ' + esc(err.message) + '</div>';
    }
    spinning(false);
}

function renderTopicsConfig() {
    const body = document.getElementById('topics-config-body');
    body.textContent = '';

    if (!topicsData.length) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = 'No topics defined. Click "+ Add Topic" to create one.';
        body.appendChild(empty);
        return;
    }

    topicsData.forEach((topic, ti) => {
        const card = document.createElement('div');
        card.className = 'cfg-topic-card';

        const hdr = document.createElement('div');
        hdr.className = 'cfg-topic-hdr';
        hdr.textContent = (topic.icon || '💬') + ' ' + (topic.title || 'Untitled');

        const del = document.createElement('button');
        del.className = 'cfg-del-btn';
        del.textContent = 'Delete';
        del.addEventListener('click', () => {
            topicsData.splice(ti, 1);
            renderTopicsConfig();
        });
        hdr.appendChild(del);
        card.appendChild(hdr);

        const fields = document.createElement('div');
        fields.className = 'cfg-topic-fields';

        [
            { label:'Topic ID',    field:'id',          type:'text',   placeholder:'e.g. order_status' },
            { label:'Title',       field:'title',        type:'text',   placeholder:'Display name' },
            { label:'Icon',        field:'icon',         type:'text',   placeholder:'emoji, e.g. 📦' },
            { label:'Description', field:'description',  type:'text',   placeholder:'Short description' },
        ].forEach(({ label, field, type, placeholder }) => {
            const row = document.createElement('div');
            row.className = 'cfg-field-row';
            const lbl = document.createElement('label');
            lbl.textContent = label;
            const inp = document.createElement('input');
            inp.type = type;
            inp.className = 'cfg-input';
            inp.placeholder = placeholder;
            inp.value = topic[field] || '';
            inp.addEventListener('input', () => { topic[field] = inp.value; hdr.textContent = (topic.icon || '💬') + ' ' + (topic.title || 'Untitled'); hdr.appendChild(del); });
            row.append(lbl, inp);
            fields.appendChild(row);
        });

        // Visibility select
        const visRow = document.createElement('div');
        visRow.className = 'cfg-field-row';
        const visLabel = document.createElement('label');
        visLabel.textContent = 'Visibility';
        const visSel = document.createElement('select');
        visSel.className = 'cfg-input';
        [['always','Always visible'],['has_orders','Customers with orders'],['is_b2b','B2B only'],['is_guest','Guests only']].forEach(([v,l]) => {
            const o = document.createElement('option');
            o.value = v; o.textContent = l;
            if (v === topic.visibility) o.selected = true;
            visSel.appendChild(o);
        });
        visSel.addEventListener('change', () => topic.visibility = visSel.value);
        visRow.append(visLabel, visSel);
        fields.appendChild(visRow);

        // LLM provider select
        const llmRow = document.createElement('div');
        llmRow.className = 'cfg-field-row';
        const llmLabel = document.createElement('label');
        llmLabel.textContent = 'LLM Provider';
        const llmSel = document.createElement('select');
        llmSel.className = 'cfg-input';
        [['', 'Inherit / default'], ...LLM_PROVIDERS.map(p => [p, LLM_LABELS[p] || p])].forEach(([v,l]) => {
            const o = document.createElement('option');
            o.value = v; o.textContent = l;
            if (v === (topic.llm_provider || '')) o.selected = true;
            llmSel.appendChild(o);
        });
        llmSel.addEventListener('change', () => topic.llm_provider = llmSel.value || null);
        llmRow.append(llmLabel, llmSel);
        fields.appendChild(llmRow);

        card.appendChild(fields);
        body.appendChild(card);
    });
}

document.getElementById('topic-add-btn').addEventListener('click', () => {
    topicsData.push({ id: 'topic_' + Date.now(), title: 'New Topic', icon: '💬', description: '', visibility: 'always', llm_provider: null, sub_cards: [] });
    renderTopicsConfig();
});

document.getElementById('topic-save-btn').addEventListener('click', async () => {
    const btn = document.getElementById('topic-save-btn');
    btn.textContent = 'Saving…';
    btn.disabled = true;
    try {
        await adminFetch('PUT', '/api/admin/topics', topicsData);
        showToast('Topics saved!', 'success');
        await loadTopicsConfig();
    } catch (err) {
        showToast('Save failed: ' + err.message);
    } finally {
        btn.textContent = 'Save';
        btn.disabled = false;
    }
});

/* ── Knowledge Base ──────────────────────────────────────────────────────── */
async function loadKnowledge() {
    spinning(true);
    try {
        const status = await apiFetch('/api/admin/knowledge/status');
        renderKbStatus(status);
        renderKbSources(status.sources || []);
    } catch (err) {
        document.getElementById('kb-status-body').innerHTML = '<div class="empty">Failed: ' + esc(err.message) + '</div>';
    }
    spinning(false);
}

function renderKbStatus(status) {
    const body = document.getElementById('kb-status-body');
    body.textContent = '';
    const sources = (status.sources || []).length;
    const vectors = status.total_vectors || 0;
    const qa = status.total_qa_pairs || 0;
    [
        [sources, 'sources indexed'],
        [vectors, 'vectors'],
        [qa, 'Q&A pairs'],
    ].forEach(([num, label]) => {
        const stat = document.createElement('div');
        stat.className = 'kb-stat';
        const n = document.createElement('strong');
        n.textContent = fmt(num);
        const l = document.createElement('span');
        l.textContent = label;
        stat.append(n, l);
        body.appendChild(stat);
    });
}

function renderKbSources(sources) {
    const tbody = document.getElementById('kb-sources-body');
    tbody.textContent = '';
    if (!sources.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 5;
        td.innerHTML = '<div class="empty">No sources indexed yet.</div>';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }
    sources.forEach(src => {
        const tr = document.createElement('tr');
        [src.name || '—', src.source_type || '—', fmt(src.chunk_count), fmtDate(src.created_at)].forEach(text => {
            const td = document.createElement('td');
            td.textContent = text;
            tr.appendChild(td);
        });
        const tdBtn = document.createElement('td');
        const btn = document.createElement('button');
        btn.className = 'view-btn';
        btn.style.background = 'var(--danger-light)';
        btn.style.color = 'var(--danger-dark)';
        btn.textContent = 'Delete';
        btn.addEventListener('click', async () => {
            if (!confirm('Delete this source?')) return;
            try {
                await adminFetch('DELETE', '/api/knowledge/' + encodeURIComponent(src.id));
                await loadKnowledge();
                showToast('Source deleted', 'success');
            } catch (err) { showToast('Delete failed: ' + err.message); }
        });
        tdBtn.appendChild(btn);
        tr.appendChild(tdBtn);
        tbody.appendChild(tr);
    });
}

document.getElementById('cms-sync-btn').addEventListener('click', async () => {
    const btn = document.getElementById('cms-sync-btn');
    const statusEl = document.getElementById('cms-sync-body');
    btn.textContent = 'Syncing…';
    btn.disabled = true;
    try {
        const data = await adminFetch('POST', '/api/admin/knowledge/sync-cms');
        statusEl.innerHTML = '<p style="color:var(--success)">✓ Synced ' + esc(String(data.sources_synced || 0)) + ' sources, ' + esc(String(data.total_chunks || 0)) + ' chunks.</p>';
        showToast('CMS sync complete!', 'success');
        await loadKnowledge();
    } catch (err) {
        statusEl.innerHTML = '<p style="color:var(--danger)">Sync failed: ' + esc(err.message) + '</p>';
        showToast('CMS sync failed: ' + err.message);
    } finally {
        btn.textContent = 'Sync Now';
        btn.disabled = false;
    }
});

document.getElementById('kb-file-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const statusEl = document.getElementById('kb-upload-body');
    statusEl.innerHTML = '<p style="color:var(--text-muted)">Uploading ' + esc(file.name) + '…</p>';
    try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(API + '/api/knowledge/upload', {
            method: 'POST',
            headers: { 'X-Dashboard-Key': state.apiKey },
            body: form,
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        statusEl.innerHTML = '<p style="color:var(--success)">✓ Indexed "' + esc(file.name) + '" — ' + (data.chunk_count || 0) + ' chunks.</p>';
        showToast('File indexed!', 'success');
        await loadKnowledge();
    } catch (err) {
        statusEl.innerHTML = '<p style="color:var(--danger)">Upload failed: ' + esc(err.message) + '</p>';
        showToast('Upload failed: ' + err.message);
    } finally {
        e.target.value = '';
    }
});
