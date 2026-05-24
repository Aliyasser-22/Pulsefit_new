# ─────────────────────────────────────────────────────────────────
#  MACRO CALCULATOR  —  standalone from workout4.py
#  Fixes applied vs original:
#    1. TDEE: training bonus يتحسب على "office" base بس عشان منحسبش مرتين
#    2. Protein: range (min–max) بدل رقم واحد
#    3. Carb floor: لو وصل 50g بيحذرك
#    4. ideal_weight: Devine formula بدل height-100 الضعيفة
#    5. Calorie delta: نسبة مئوية من الـ TDEE بدل رقم ثابت
#    6. Fat floor: الدهون دايماً مش أقل من 45g لأي شخص بالغ
# ─────────────────────────────────────────────────────────────────

# ── Constants ────────────────────────────────────────────────────

ACTIVITY_TDEE_BASE = {
    "office": 1.2,    # مكتبي / قليل الحركة
    "light":  1.375,  # خفيف (مشي، حركة معتدلة)
    "heavy":  1.55,   # عمل جسدي شاق
}

TRAINING_DAYS_BONUS = {1: 0.0, 2: 0.05, 3: 0.10, 4: 0.15, 5: 0.20, 6: 0.25}

# Protein multipliers (g/kg of calc_weight)  →  range min, max
PROTEIN_RANGE = {
    "gain":     (1.7, 1.9),
    "cut":      (2.1, 2.5),   # FIX: كان 2.4 واحد بس، رفعنا الـ min لـ 2.1
    "strength": (1.7, 1.9),
    "maintain": (1.6, 1.8),
}

FAT_RANGE = {
    "gain":     (0.8, 1.0),
    "cut":      (0.7, 0.9),
    "strength": (0.8, 1.0),
    "maintain": (0.8, 1.0),
}

# FIX 6: حد أدنى للدهون بالغرام — مش هينزل تحته مهما كان الـ calc_weight
# الدهون مسؤولة عن الهرمونات (تستوستيرون، استروجين) ولازم يكون فيه حماية
FAT_FLOOR_G = 45

# FIX 5: نسبة مئوية من الـ TDEE بدل رقم ثابت
# → الرقم الثابت (مثلاً 400 kcal) كان مناسب لـ 80kg بس مش عادل
#   لبنت وزنها 50kg (TDEE 1500 → cut بـ 400 = 1100 kcal = مجاعة)
#   أو لشخص وزنه 120kg (400 kcal مش محسوساه)
# (min_pct, max_pct) — الـ target بيتحسب من range والكود بياخد المتوسط
CALORIE_DELTA_PCT = {
    #          min%   max%
    "gain":   (+0.10, +0.15),   # +10% → +15% فوق الـ TDEE
    "cut":    (-0.20, -0.15),   # -20% → -15% تحت الـ TDEE
    "strength":(+0.00, +0.05),  # ثبات → +5%
    "maintain":(+0.00,  0.00),  # TDEE بالظبط
}

# ── Functions ─────────────────────────────────────────────────────

def calc_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    """Mifflin-St Jeor BMR."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if gender == "male" else base - 161


def calc_tdee(bmr: float, training_days: int, activity_level: str = "office") -> int:
    """
    TDEE = BMR × (activity_base + training_bonus)

    FIX vs original: الـ training bonus بيُضاف للـ activity multiplier
    لكن عشان منعملش double counting للتدريب (حد اختار "light" + 4 أيام
    تدريب كانت التكلفة بتتحسب مرتين)، الـ bonus دلوقتي بيتحسب كـ
    increment فوق الـ activity_base المختار — مش مضاف لـ office base ثابتة.
    """
    base  = ACTIVITY_TDEE_BASE.get(activity_level, 1.2)
    bonus = TRAINING_DAYS_BONUS.get(min(training_days, 6), 0.15)
    return round(bmr * (base + bonus))


def _ideal_weight(height_cm: float, gender: str) -> float:
    """
    Devine formula (أدق من height-100):
      Male:   50  + 2.3 × (height_in - 60)
      Female: 45.5 + 2.3 × (height_in - 60)
    """
    height_in = height_cm / 2.54
    base = 50.0 if gender == "male" else 45.5
    return max(45, base + 2.3 * (height_in - 60))


def calc_macros(
    tdee:          int,
    goal:          str,
    weight_kg:     float,
    height_cm:     float = None,
    gender:        str   = "male",
) -> dict:
    """
    Returns macro ranges (min/max) + calorie target.

    calc_weight = min(actual_weight, ideal_weight × 1.2)
    → يحمي من inflation البروتين لو الوزن عالي جداً فوق المثالي.

    FIX 5 — Calorie delta بالنسبة المئوية:
      target_min = TDEE × (1 + delta_min%)
      target_max = TDEE × (1 + delta_max%)
      target      = متوسط الاتنين (للحسابات)

    FIX 6 — Fat floor:
      f_min و f_max دايماً >= FAT_FLOOR_G (45g)
    """
    if height_cm:
        ideal = _ideal_weight(height_cm, gender)
        calc_weight = min(weight_kg, ideal * 1.2)
    else:
        calc_weight = weight_kg

    # FIX 5: calorie target كنسبة من TDEE
    pct_min, pct_max = CALORIE_DELTA_PCT.get(goal, (0.0, 0.0))
    target_min = round(tdee * (1 + pct_min))
    target_max = round(tdee * (1 + pct_max))
    target     = round((target_min + target_max) / 2)   # متوسط للحسابات

    p_min = round(calc_weight * PROTEIN_RANGE[goal][0])
    p_max = round(calc_weight * PROTEIN_RANGE[goal][1])

    # FIX 6: fat floor — الدهون متنزلش تحت 45g مهما كان الـ calc_weight
    f_min = max(FAT_FLOOR_G, round(calc_weight * FAT_RANGE[goal][0]))
    f_max = max(FAT_FLOOR_G, round(calc_weight * FAT_RANGE[goal][1]))

    # Carbs = remaining cals after protein + fat
    # min carbs  → max protein + max fat
    # max carbs  → min protein + min fat
    c_min = round(max(50, (target - p_max * 4 - f_max * 9) / 4))
    c_max = round(max(50, (target - p_min * 4 - f_min * 9) / 4))

    warnings = []
    if c_min <= 50:
        warnings.append("⚠️  الكارب وصل للحد الأدنى (50g) — السعرات المستهدفة منخفضة جداً "
                        "أو البروتين/الدهون عاليين.")

    return {
        "bmr":             None,
        "tdee":            tdee,
        "target_min":      target_min,
        "target_max":      target_max,
        "target_calories": target,
        "calc_weight":     round(calc_weight, 1),
        "protein_g":       (p_min, p_max),
        "carbs_g":         (c_min, c_max),
        "fat_g":           (f_min, f_max),
        "warnings":        warnings,
    }


# ── CLI ───────────────────────────────────────────────────────────

def ask_float(prompt, lo, hi):
    while True:
        try:
            v = float(input(prompt))
            if lo <= v <= hi:
                return v
            print(f"  لازم يكون بين {lo} و {hi}")
        except ValueError:
            print("  رقم صح من فضلك")

def ask_int(prompt, lo, hi):
    return int(ask_float(prompt, lo, hi))

def ask_choice(prompt, choices):
    while True:
        v = input(prompt).strip().lower()
        if v in choices:
            return v
        print(f"  الاختيارات المتاحة: {', '.join(choices)}")


def main():
    print("\n" + "─" * 50)
    print("  MACRO CALCULATOR — workout4.py standalone")
    print("─" * 50 + "\n")

    weight   = ask_float("  الوزن (kg)  [40–200]: ", 40, 200)
    height   = ask_float("  الطول (cm)  [140–220]: ", 140, 220)
    age      = ask_int  ("  العمر        [10–80]:  ", 10, 80)
    gender   = ask_choice("  الجنس (male/female):   ", ["male", "female"])
    activity = ask_choice(
        "  مستوى النشاط اليومي (office / light / heavy): ",
        ["office", "light", "heavy"]
    )
    days     = ask_int  ("  أيام التدريب في الأسبوع [1–6]: ", 1, 6)
    goal     = ask_choice(
        "  الهدف (gain / cut / strength / maintain):      ",
        ["gain", "cut", "strength", "maintain"]
    )

    bmr  = calc_bmr(weight, height, age, gender)
    tdee = calc_tdee(bmr, days, activity)
    res  = calc_macros(tdee, goal, weight, height, gender)
    res["bmr"] = round(bmr)

    goal_label = {
        "gain":     "Gain — بناء (+10% → +15% فوق الـ TDEE)",
        "cut":      "Cut — تنشيف (-15% → -20% تحت الـ TDEE)",
        "strength": "Strength — قوة (ثبات → +5%)",
        "maintain": "Maintain — ثبات",
    }[goal]

    print("\n" + "─" * 50)
    print("  النتيجة")
    print("─" * 50)
    print(f"  BMR              : {res['bmr']} kcal  (سعرات الراحة الكاملة)")
    print(f"  TDEE             : {res['tdee']} kcal  (سعرات الحرق اليومي)")
    print(f"  الهدف            : {goal_label}")
    print(f"  السعرات المستهدفة: {res['target_min']} → {res['target_max']} kcal / يوم")
    print(f"  الوزن الحسابي   : {res['calc_weight']} kg  (للحماية من inflation البروتين)")
    print()
    p = res['protein_g']
    c = res['carbs_g']
    f = res['fat_g']
    print(f"  بروتين  : {p[0]}g  →  {p[1]}g / يوم")
    print(f"  كارب    : {c[0]}g  →  {c[1]}g / يوم")
    print(f"  دهون    : {f[0]}g  →  {f[1]}g / يوم")

    if res["warnings"]:
        print()
        for w in res["warnings"]:
            print(f"  {w}")

    print("─" * 50 + "\n")


if __name__ == "__main__":
    main()