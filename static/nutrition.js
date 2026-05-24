// nutrition.js

const MEALS = ['breakfast', 'lunch', 'dinner', 'snacks'];
const foodLog = { breakfast: [], lunch: [], dinner: [], snacks: [] };

// ── SUMMARY ──────────────────────────────────────────────────
function updateSummary() {
    let totalCal = 0, totalProt = 0, totalCarb = 0, totalFat = 0;
    MEALS.forEach(meal => {
        let mealCal = 0;
        foodLog[meal].forEach(item => {
            totalCal  += item.calories || 0;
            totalProt += item.protein  || 0;
            totalCarb += item.carbs    || 0;
            totalFat  += item.fat      || 0;
            mealCal   += item.calories || 0;
        });
        const subEl = document.getElementById(meal + 'Cal');
        if (subEl) subEl.textContent = Math.round(mealCal) + ' kcal logged';
    });
    document.getElementById('totalCal').textContent  = Math.round(totalCal);
    document.getElementById('totalProt').textContent = Math.round(totalProt) + 'g';
    document.getElementById('totalCarb').textContent = Math.round(totalCarb) + 'g';
    document.getElementById('totalFat').textContent  = Math.round(totalFat)  + 'g';
}

// ── MACROS ROW HTML ───────────────────────────────────────────
function buildMacrosHtml(f) {
    return `
        <div class="macros-row">
            <div class="macro-pill cal" ><span class="m-icon">🔥</span><span class="m-val">${Math.round(f.calories||0)}</span><span class="m-lbl">kcal</span></div>
            <div class="macro-pill prot"><span class="m-icon">💪</span><span class="m-val">${Math.round(f.protein||0)}g</span><span class="m-lbl">protein</span></div>
            <div class="macro-pill carb"><span class="m-icon">🍞</span><span class="m-val">${Math.round(f.carbs||0)}g</span><span class="m-lbl">carbs</span></div>
            <div class="macro-pill fat" ><span class="m-icon">🧈</span><span class="m-val">${Math.round(f.fat||0)}g</span><span class="m-lbl">fat</span></div>
        </div>
    `;
}

// ── RENDER LOG ITEM ───────────────────────────────────────────
function renderLogItem(meal, item) {
    const log = document.getElementById(meal + 'Log');
    if (!log) return;
    const div = document.createElement('div');
    div.className = 'log-item';
    div.innerHTML = `
        <span class="li-name">${item.name} <span style="color:#64748b;font-size:11px">(${item.grams}g)</span></span>
        <span class="li-cal">🔥 ${Math.round(item.calories)} kcal</span>
    `;
    log.appendChild(div);
}

// ── LOG SEARCHED FOOD ─────────────────────────────────────────
function logSearchedFood(meal, foodJson) {
    const food = typeof foodJson === 'string' ? JSON.parse(foodJson) : foodJson;
    foodLog[meal].push(food);
    renderLogItem(meal, food);
    updateSummary();
    const resultEl = document.getElementById(meal + 'Result');
    if (resultEl) resultEl.style.display = 'none';
    const csLog = document.getElementById(meal + 'CustomSection');
    if (csLog) csLog.style.display = 'none';
    const inputEl = document.getElementById(meal + 'Input');
    if (inputEl) inputEl.value = '';
    const gramsEl = document.getElementById(meal + 'Grams');
    if (gramsEl) gramsEl.value = '';
}

// ── SEARCH ────────────────────────────────────────────────────
async function searchFood(meal) {
    const inputEl  = document.getElementById(meal + 'Input');
    const gramsEl  = document.getElementById(meal + 'Grams');
    const resultEl = document.getElementById(meal + 'Result');
    const query    = (inputEl?.value || '').trim();
    const grams    = parseFloat(gramsEl?.value || 100);

    if (!query) {
        resultEl.style.display = 'block';
        resultEl.innerHTML = '<p style="color:#94a3b8">اكتب اسم الأكلة الأول</p>';
        return;
    }
    if (!grams || grams <= 0) {
        resultEl.style.display = 'block';
        resultEl.innerHTML = '<p style="color:#f87171">أدخل عدد الجرامات ❌</p>';
        return;
    }

    resultEl.style.display = 'block';
    resultEl.innerHTML = '<p style="color:#94a3b8">جاري البحث... لو مش في القاعدة هنسأل Groq AI</p>';

    try {
        const res  = await fetch('/api/food/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, grams })
        });
        const data = await res.json();

        if (!data.found) {
            const errMsg = data.groq_error || data.error
                || (data.ai_attempted
                    ? '🤖 الذكاء الاصطناعي ما لقاش الأكلة. أضفها يدوياً 👇'
                    : 'مفيش نتائج. أضف الأكلة يدوياً 👇');
            resultEl.innerHTML = `<p style="color:#fbbf24">${errMsg}</p>`;
            const customSection = document.getElementById(meal + 'CustomSection');
            if (customSection) {
                customSection.style.display = 'block';
                const nameEl = document.getElementById(meal + 'CustomName');
                if (nameEl && query) nameEl.value = query;
            }
            return;
        }
        const customSecFound = document.getElementById(meal + 'CustomSection');
        if (customSecFound) customSecFound.style.display = 'none';

        const aiBadge = data.match_type === 'groq'
            ? '<span style="color:#a78bfa;font-size:11px"> 🤖 من Groq AI</span>'
            : (data.match_type === 'db' || data.match_type === 'franco')
            ? '<span style="color:#34d399;font-size:11px"> 📋 من قاعدة البيانات</span>'
            : '';
        let html = `<p style="color:#94a3b8;font-size:12px;margin-bottom:10px">اختار الأكلة الصح 👇 (${Math.round(grams)}g)${aiBadge}</p>`;

        data.results.forEach((f, i) => {
            const safeFood = JSON.stringify({...f, grams}).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            html += `
                <div class="result-item" style="border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:10px;margin-bottom:8px;background:rgba(255,255,255,0.03)">
                    <div class="food-name" style="margin-bottom:6px">${f.name}</div>
                    ${buildMacrosHtml(f)}
                    <button class="btn-log" style="margin-top:8px" onclick='logSearchedFood("${meal}", ${JSON.stringify({...f, grams})})'>+ Log this food</button>
                </div>
            `;
        });

        resultEl.innerHTML = html;

    } catch (err) {
        resultEl.innerHTML = '<p style="color:#f87171">في مشكلة في السيرفر ❌</p>';
    }
}

// ── ADD CUSTOM FOOD ───────────────────────────────────────────
async function addCustomFood(meal) {
    const name     = (document.getElementById(meal + 'CustomName')?.value || '').trim();
    const calories = parseFloat(document.getElementById(meal + 'CustomCal')?.value  || 0);
    const protein  = parseFloat(document.getElementById(meal + 'CustomProt')?.value || 0);
    const carbs    = parseFloat(document.getElementById(meal + 'CustomCarb')?.value || 0);
    const fat      = parseFloat(document.getElementById(meal + 'CustomFat')?.value  || 0);
    const resultEl = document.getElementById(meal + 'CustomResult');

    if (!name) {
        resultEl.style.display = 'block';
        resultEl.innerHTML = '<p style="color:#f87171">اكتب اسم الأكلة أولاً ❌</p>';
        return;
    }
    if (!calories || calories <= 0) {
        resultEl.style.display = 'block';
        resultEl.innerHTML = '<p style="color:#f87171">أدخل سعرات صحيحة ❌</p>';
        return;
    }

    try {
        const res  = await fetch('/api/food/add-custom', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ meal, name, calories, protein, carbs, fat })
        });
        const data = await res.json();

        if (!res.ok) {
            resultEl.style.display = 'block';
            resultEl.innerHTML = `<p style="color:#f87171">${data.error || 'خطأ ❌'}</p>`;
            return;
        }

        const item = { name, calories, protein, carbs, fat, grams: '-' };
        foodLog[meal].push(item);
        renderLogItem(meal, { ...item, grams: 'custom' });
        updateSummary();

        resultEl.style.display = 'block';
        resultEl.innerHTML = `<p style="color:#34d399">✅ ${name} — ${Math.round(calories)} kcal added!</p>`;

        ['CustomName','CustomCal','CustomProt','CustomCarb','CustomFat'].forEach(s => {
            const el = document.getElementById(meal + s);
            if (el) el.value = '';
        });

        setTimeout(() => {
            resultEl.style.display = 'none';
            const csAdd = document.getElementById(meal + 'CustomSection');
            if (csAdd) csAdd.style.display = 'none';
        }, 2500);

    } catch {
        resultEl.style.display = 'block';
        resultEl.innerHTML = '<p style="color:#f87171">في مشكلة في السيرفر ❌</p>';
    }
}

function goBack() {
    window.location.href = '/dashboard';
}