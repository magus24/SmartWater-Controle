/*
 * static/app-shim.js — слой данных для статической версии (GitHub Pages).
 *
 * В статической сборке бэкенда нет, поэтому перехватываем fetch запросов
 * к /api/* и отдаём заранее сгенерированные JSON-файлы из docs/data/.
 * Симуляция утечки считается прямо в браузере по той же логике,
 * что и на сервере (logic.py).
 */

(function () {
    const DATA = 'data/';

    // Базовый URL считаем от расположения самого скрипта:
    // это работает и на Pages (/<repo>/), и при локальном открытии.
    const selfSrc = (typeof document !== 'undefined' && document.currentScript && document.currentScript.src) || '';
    const BASE = selfSrc ? selfSrc.replace(/static\/app-shim\.js.*$/, '') : './';

    const REPO_PREFIX = (function () {
        try {
            const u = new URL(BASE, location.href);
            return /\.github\.io$/i.test(u.hostname) ? u.pathname.replace(/\/+$/, '') : '';
        } catch (e) {
            return '';
        }
    })();

    const state = {
        network: null,     // нормальное состояние сети (из data/network.json)
        current: null,     // текущее состояние (после симуляции)
        history: [],
        anomalies: [],
        stats: null,
        pipesMeta: {}
    };

    const rnd = (a, b) => a + Math.random() * (b - a);
    const round2 = (v) => Math.round(v * 100) / 100;
    const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    const cache = {};

    async function loadStatic(name) {
        if (cache[name]) return cache[name];
        const res = await fetch(new URL(DATA + name, new URL(BASE, location.href)).href);
        if (!res.ok) throw new Error('Static file not found: ' + name);
        cache[name] = await res.json();
        return cache[name];
    }

    function json(body) {
        return new Response(JSON.stringify(body), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    function routeMidpoint(route) {
        if (!route || !route.length) return { lat: 0, lng: 0 };
        if (route.length === 1) return { lat: route[0][0], lng: route[0][1] };

        let total = 0;
        const segs = [];
        for (let i = 0; i < route.length - 1; i++) {
            const a = route[i], b = route[i + 1];
            const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
            segs.push({ a, b, len });
            total += len;
        }
        const half = total / 2;
        let acc = 0;
        for (const s of segs) {
            if (acc + s.len >= half) {
                const t = s.len ? (half - acc) / s.len : 0;
                return {
                    lat: s.a[0] + (s.b[0] - s.a[0]) * t,
                    lng: s.a[1] + (s.b[1] - s.a[1]) * t
                };
            }
            acc += s.len;
        }
        const last = route[route.length - 1];
        return { lat: last[0], lng: last[1] };
    }

    function pressureStatus(current, baseline) {
        const delta = baseline - current;
        if (delta >= 1.2) return 'critical';
        if (delta >= 0.6) return 'warning';
        return 'normal';
    }

    function buildIncident(network, pipeId, sensors) {
        const pipe = network.pipes.find((p) => p.id === pipeId) || { id: pipeId, name: 'Quvur ' + pipeId };
        const affected = sensors
            .slice()
            .sort((a, b) => (b.baseline_pressure - b.current_pressure) - (a.baseline_pressure - a.current_pressure))
            .slice(0, 5);

        const avgDrop = affected.reduce((s, x) => s + (x.baseline_pressure - x.current_pressure), 0) / Math.max(1, affected.length);
        const confidence = Math.min(98, Math.max(62, Math.round(70 + avgDrop * 12)));
        const severity = avgDrop >= 1.35 ? 'critical' : (avgDrop >= 0.8 ? 'high' : 'medium');

        const reasons = affected.slice(0, 3).map(
            (s) => s.id + ': bosim ' + round2(s.baseline_pressure - s.current_pressure) + ' bar ga pasaydi'
        );
        reasons.push('Anomaliya «' + pipe.name + '» quvuri atrofida aniqlandi');
        reasons.push('Yaqin atrofidagi datchiklar bosim pasayishini tasdiqlamoqda');

        return {
            title: 'Tasodifiy sizib chiqish (Simulyatsiya)',
            severity: severity,
            confidence: confidence,
            pipe_id: pipe.id,
            pipe_name: pipe.name,
            road_hint: pipe.road_hint || null,
            suspected_location: routeMidpoint(pipe.coordinates || pipe.route || []),
            reasons: reasons,
            summary:
                'AI «' + pipe.name + '» hududida beqaror bosimni aniqladi. ' +
                'Quvur bo‘ylab datchiklarda sezilarli bosim pasayishi qayd etildi. ' +
                'Ehtimoliy sizib chiqish yuz bergan.',
            suggested_action:
                'Belgilangan hududni tekshirish uchun mobil guruh yuborilsin. ' +
                'Agar bosim pasayishda davom etsa, quvur tarmog‘i izolyatsiya qilinsin. ' +
                'Yaqin atrofdagi klapanlar va ulanishlar tekshirilsin.'
        };
    }

    function simulate() {
        const net = JSON.parse(JSON.stringify(state.network));

        const sensorPipeIds = {};
        net.sensors.forEach((s) => { if (s.pipe_id) sensorPipeIds[s.pipe_id] = true; });
        const candidatePipes = net.pipes.filter((p) => sensorPipeIds[p.id]);
        const target = pick(candidatePipes.length ? candidatePipes : net.pipes);
        const drop = rnd(1.4, 2.4);

        const affected = [];
        net.sensors.forEach((s) => {
            if (s.pipe_id !== target.id) {
                const noise = round2(rnd(-0.06, 0.06));
                s.current_pressure = round2(Math.max(3, s.baseline_pressure + noise));
                s.delta = round2(s.current_pressure - s.baseline_pressure);
                s.status = pressureStatus(s.current_pressure, s.baseline_pressure);
                return;
            }
            const current = round2(Math.max(3, s.baseline_pressure - drop + rnd(-0.08, 0.08)));
            s.current_pressure = current;
            s.delta = round2(current - s.baseline_pressure);
            s.status = pressureStatus(current, s.baseline_pressure);
            affected.push(s);
        });

        net.pipes.forEach((p) => { p.status = p.id === target.id ? 'anomaly' : 'normal'; });
        net.incident = buildIncident(net, target.id, affected);
        net.simulation = { active: true, scenario_key: 'random_leak' };
        state.current = net;

        // Пишем событие в локальный журнал ИИ (для страницы /ai-history)
        const now = new Date().toISOString();
        const meta = state.pipesMeta[target.id] || { name: target.name, road_hint: target.road_hint, baseline: 7.0 };
        const devPct = round2((drop / meta.baseline) * 100 * -1);
        state.history.unshift({
            id: Math.random().toString(16).slice(2, 10),
            pipe_id: target.id,
            timestamp: now,
            expected_pressure: meta.baseline,
            actual_pressure: round2(Math.max(3, meta.baseline - drop)),
            deviation_percent: devPct,
            status: 'anomaly',
            ai_confidence: net.incident.confidence,
            ai_score: 0.72,
            ai_explanation: 'Bosim keskin pasaydi — model uni sizib chiqish belgisi deb baholadi.'
        });
        state.anomalies.unshift({
            incident_id: Math.random().toString(16).slice(2, 10),
            pipe_id: net.incident.pipe_id,
            pipe_name: net.incident.pipe_name,
            detected_at: now,
            severity: net.incident.severity,
            confidence: net.incident.confidence,
            reasons: net.incident.reasons,
            summary: net.incident.summary,
            status: 'New',
            ai_confidence: net.incident.confidence,
            ai_score: 0.72,
            explanation: 'Static build: lokal AI verdicti (browserda hisoblandi).'
        });
        if (state.stats) {
            state.stats.anomalies = state.anomalies.length;
            state.stats.historical_records = 1250000 + state.history.length;
        }

        return net;
    }

    function reset() {
        state.current = JSON.parse(JSON.stringify(state.network));
        state.current.simulation = { active: false, scenario_key: null };
        return state.current;
    }

    function historySlice() {
        return state.history
            .slice()
            .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
            .slice(0, 50);
    }

    async function ensureBase() {
        if (state.network) return;
        state.network = await loadStatic('network.json');
        state.current = JSON.parse(JSON.stringify(state.network));
        state.history = await loadStatic('pressure-history.json');
        state.anomalies = await loadStatic('anomalies.json');
        state.stats = await loadStatic('dashboard-stats.json');
        state.pipesMeta = await loadStatic('pipes-meta.json');
    }

    async function handle(url) {
        await ensureBase();
        const u = new URL(url, location.href);
        let p = u.pathname;
        if (REPO_PREFIX && p.indexOf(REPO_PREFIX + '/api/') === 0) p = p.slice(REPO_PREFIX.length);
        p = p.replace(/\/+$/, '') || '/';

        if (p === '/api/network') return json(state.current);
        if (p === '/api/simulate') {
            await sleep(900);
            const net = simulate();
            return json({ ok: true, scenario: net.incident.title, network: net });
        }
        if (p === '/api/reset') {
            const net = reset();
            return json({ ok: true, network: net });
        }
        if (p === '/api/dashboard-stats') return json(state.stats);
        if (p === '/api/pressure-history') return json(historySlice());
        if (p === '/api/anomalies') return json(state.anomalies);

        if (p.startsWith('/api/pressure-history/')) {
            const pipeId = decodeURIComponent(p.slice('/api/pressure-history/'.length));
            const pipe = state.network.pipes.find((x) => x.id === pipeId) || {};
            const meta = state.pipesMeta[pipeId] || {};
            const history = state.history
                .filter((r) => r.pipe_id === pipeId)
                .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            return json({
                pipe: {
                    id: pipeId,
                    name: meta.name || pipe.name || ('Quvur ' + pipeId),
                    road_hint: meta.road_hint || pipe.road_hint || 'Asosiy trassa',
                    baseline: meta.baseline || 7.0
                },
                history: history
            });
        }

        return new Response('{"error":"not found"}', { status: 404, headers: { 'Content-Type': 'application/json' } });
    }

    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const raw = typeof input === 'string' ? input : (input && input.url) || '';
        const isApi = raw.indexOf('/api/') !== -1;
        if (!isApi) return nativeFetch(input, init);

        const method = ((init && init.method) || 'GET').toUpperCase();
        void method;
        return handle(raw).catch((err) => {
            console.error('[static] API so\'rovi bajarilmadi:', err);
            return nativeFetch(input, init);
        });
    };

    window.SW_STATIC_MODE = true;
})();
