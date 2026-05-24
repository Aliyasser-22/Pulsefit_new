// dashboard.js — PulseFit
// New: BMI card, calorie goal (Mifflin-St Jeor), macro breakdown bars

fetch('/api/get-plan')
  .then(r => r.json())
  .then(data => {
    const u = data.userData || {};
    const p = data.plan     || {};

    // ── STATS ROW ──────────────────────────────────────────
    if (u.weight) document.getElementById('stat-weight').textContent = u.weight;
    if (u.height) document.getElementById('stat-height').textContent = u.height;
    if (u.workoutDays) document.getElementById('stat-days').textContent = u.workoutDays + 'x / wk';
    if (u.level) document.getElementById('stat-level').textContent =
      u.level.charAt(0).toUpperCase() + u.level.slice(1);

    // ── WELCOME SUBTITLE ──────────────────────────────────
    if (u.goal) {
      const goals = { lose: 'Weight Loss', build: 'Muscle Building', maintain: 'Maintenance' };
      document.getElementById('welcome-sub').textContent =
        `Goal: ${goals[u.goal] || u.goal} · Let's get to work!`;
    }

    // ── BMI CALCULATION ────────────────────────────────────
    if (u.weight && u.height) {
      const h_m = u.height / 100;
      const bmi = (u.weight / (h_m * h_m)).toFixed(1);
      document.getElementById('stat-bmi').textContent = bmi;

      let bmiClass, bmiLabel;
      const b = parseFloat(bmi);
      if      (b < 18.5) { bmiClass = 'bmi-under';  bmiLabel = 'Underweight'; }
      else if (b < 25)   { bmiClass = 'bmi-normal'; bmiLabel = 'Healthy';     }
      else if (b < 30)   { bmiClass = 'bmi-over';   bmiLabel = 'Overweight';  }
      else               { bmiClass = 'bmi-obese';  bmiLabel = 'Obese';       }

      document.getElementById('bmi-card').classList.add(bmiClass);
      document.getElementById('bmi-badge').textContent = bmiLabel;
    }

    // ── CALORIE GOAL + MACRO RANGES (calories.py logic) ────
    if (u.weight && u.height && u.age && u.gender) {

      // ── 1. BMR (Mifflin-St Jeor) ───────────────────────
      const bmr = u.gender === 'male'
        ? 10 * u.weight + 6.25 * u.height - 5 * u.age + 5
        : 10 * u.weight + 6.25 * u.height - 5 * u.age - 161;

      // ── 2. TDEE (activity_base + training_bonus) ────────
      // Default activity base = "office" (1.2) — matches calories.py
      const activityBase = 1.2;
      const trainingBonus = { 1:0.00, 2:0.05, 3:0.10, 4:0.15, 5:0.20, 6:0.25 };
      const days = Math.min(parseInt(u.workoutDays) || 3, 6);
      const bonus = trainingBonus[days] ?? 0.15;
      const tdee = Math.round(bmr * (activityBase + bonus));

      // ── 3. Map questionnaire goal → calories.py goal ────
      const goalMap = { lose:'cut', build:'gain', maintain:'maintain', strength:'strength' };
      const calGoal = goalMap[u.goal] || 'maintain';

      // ── 4. Calorie target (midpoint of range) ───────────
      const calorieDelta = {
        gain:     [+0.10, +0.15],
        cut:      [-0.20, -0.15],
        strength: [+0.00, +0.05],
        maintain: [+0.00, +0.00],
      };
      const [pctMin, pctMax] = calorieDelta[calGoal] || [0, 0];
      const targetMin = Math.round(tdee * (1 + pctMin));
      const targetMax = Math.round(tdee * (1 + pctMax));
      const target    = Math.round((targetMin + targetMax) / 2);

      document.getElementById('cal-goal').textContent = target.toLocaleString();

      // ── 5. calc_weight (Devine formula cap) ─────────────
      const heightIn   = u.height / 2.54;
      const idealBase  = u.gender === 'male' ? 50.0 : 45.5;
      const idealWeight = Math.max(45, idealBase + 2.3 * (heightIn - 60));
      const calcWeight  = Math.min(u.weight, idealWeight * 1.2);

      // ── 6. Macro ranges ─────────────────────────────────
      const PROTEIN_RANGE = {
        gain:     [1.7, 1.9],
        cut:      [2.1, 2.5],
        strength: [1.7, 1.9],
        maintain: [1.6, 1.8],
      };
      const FAT_RANGE = {
        gain:     [0.8, 1.0],
        cut:      [0.7, 0.9],
        strength: [0.8, 1.0],
        maintain: [0.8, 1.0],
      };
      const FAT_FLOOR = 45;

      const [pRatMin, pRatMax] = PROTEIN_RANGE[calGoal] || [1.6, 1.8];
      const [fRatMin, fRatMax] = FAT_RANGE[calGoal]     || [0.8, 1.0];

      const pMin = Math.round(calcWeight * pRatMin);
      const pMax = Math.round(calcWeight * pRatMax);
      const fMin = Math.max(FAT_FLOOR, Math.round(calcWeight * fRatMin));
      const fMax = Math.max(FAT_FLOOR, Math.round(calcWeight * fRatMax));
      // Carbs = remaining cals  (min carbs → max prot+fat, and vice-versa)
      const cMin = Math.round(Math.max(50, (target - pMax * 4 - fMax * 9) / 4));
      const cMax = Math.round(Math.max(50, (target - pMin * 4 - fMin * 9) / 4));

      // ── 7. Display ranges ───────────────────────────────
      document.getElementById('grams-prot').textContent = `${pMin}–${pMax}g`;
      document.getElementById('grams-carb').textContent = `${cMin}–${cMax}g`;
      document.getElementById('grams-fat').textContent  = `${fMin}–${fMax}g`;

      // ── 8. Bars — use midpoint for visual width ──────────
      const pMid = (pMin + pMax) / 2;
      const cMid = (cMin + cMax) / 2;
      const fMid = (fMin + fMax) / 2;
      const protCal = pMid * 4;
      const carbCal = cMid * 4;
      const fatCal  = fMid * 9;
      const totalCal = protCal + carbCal + fatCal;

      setTimeout(() => {
        document.getElementById('bar-prot').style.width = Math.round(protCal / totalCal * 100) + '%';
        document.getElementById('bar-carb').style.width = Math.round(carbCal / totalCal * 100) + '%';
        document.getElementById('bar-fat').style.width  = Math.round(fatCal  / totalCal * 100) + '%';
      }, 150);
    }

    // ── USER INFO LIST ─────────────────────────────────────
    const infoDiv = document.getElementById('userInfo');
    if (u.weight || u.height) {
      const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : '—';
      const rows = [
        ['Gender',    cap(u.gender)],
        ['Age',       u.age      ? u.age      + ' yrs' : '—'],
        ['Weight',    u.weight   ? u.weight   + ' kg'  : '—'],
        ['Height',    u.height   ? u.height   + ' cm'  : '—'],
        ['Goal',      cap(u.goal)],
        ['Level',     cap(u.level)],
        ['Equipment', cap((u.equipment || '').replace(/_/g, ' '))],
        ['Volume',    cap(u.volume)],
      ];
      infoDiv.innerHTML = rows.map(([k, v]) => `
        <div class="info-row">
          <span class="info-label">${k}</span>
          <span class="info-val">${v}</span>
        </div>
      `).join('');
    } else {
      infoDiv.innerHTML = '<div class="empty-state">No data yet — complete the questionnaire first.</div>';
    }

    // ── PLAN SCHEDULE ──────────────────────────────────────
    const planDiv = document.getElementById('plan');
    if (p.schedule && p.schedule.length) {
      planDiv.innerHTML = p.schedule.map(d =>
        `<div class="schedule-item">${d}</div>`
      ).join('');
    } else {
      planDiv.innerHTML = '<div class="empty-state">No plan yet — <a href="/questionnaire" style="color:var(--accent)">complete the questionnaire</a>.</div>';
    }
  })
  .catch(() => {
    document.getElementById('userInfo').innerHTML =
      '<div class="empty-state">Could not load data.</div>';
    document.getElementById('plan').innerHTML =
      '<div class="empty-state">Could not load plan.</div>';
  });

// ── ACTIVITY SUMMARY ──────────────────────────────────────
fetch('/api/dashboard-summary')
  .then(r => r.json())
  .then(data => {
    document.getElementById('stat-streak').textContent = data.streak || 0;
    document.getElementById('next-workout').textContent = data.next_workout || '—';
    
    if (data.last_session) {
      document.getElementById('last-session-date').textContent = data.last_session.date;
      const exList = data.last_session.exercises || [];
      const exStr = exList.length > 0 ? exList.join(' • ') : 'No exercises logged';
      document.getElementById('last-session-exercises').textContent = exStr;
    } else {
      document.getElementById('last-session-date').textContent = 'No past sessions';
      document.getElementById('last-session-exercises').textContent = '—';
    }
  })
  .catch(err => console.error('Failed to load dashboard summary:', err));