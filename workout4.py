"""
workout_recommender.py — AI Gym Trainer v4.0
Changes from v3.2:
  ── NEW SYSTEMS ──────────────────────────────────────────────────────────────
  1. Resistance Profile (Equipment Diversity)
     - Tracks equipment used per muscle per session
     - Penalty for repeated equipment, bonus for different resistance curve
     - Ensures stretch + peak contraction coverage within same muscle

  2. Fatigue Score System
     - Every exercise carries a fatigue_cost (auto-computed, override-able)
     - Auto-logic: free compound=3, machine compound=2, isolation=1
     - SESSION_FATIGUE_CAP enforced alongside SESSION_SETS_CAP
     - Deadlift/Squat can't fill a session to 18 sets anymore

  3. Hard Constraints
     - Mutually exclusive exercise pairs — never in same session
     - Blocked by level (beginner/intermediate get protected)
     - Separate from injury system — these are programming rules

  4. Scientific Tags (replaces "trending")
     - "trending" tag REMOVED from all exercises
     - New tags with real scoring weight:
         stretch_focused  → +4 (stretch-mediated hypertrophy)
         high_stability   → +2 late in session (CNS-fatigued)
         unilateral       → +3 if weak muscle or imbalance goal
         classic          → +1 (proven, baseline)
         strength         → +2 if goal == strength

  ── v4.0 UPDATES ───────────────────────────────────────────────────────
  5. NEW MUSCLES: lower_back, traps, forearms, adductors, abductors
  6. ACCESSORY GATEKEEPER: beginners blocked from accessory Isolation
  7. THIRD PASS OPTIMIZATION: balance high/low volume across groups
  8. SMALL MUSCLE FATIGUE: reduced to 1 for calves, abs, traps, forearms
"""

import json
import math
from pathlib import Path

# ─────────────────────────────────────────────
#  VOLUME TARGETS
# ─────────────────────────────────────────────
BASE_VOLUME = {
    "chest":     {"beginner": 10, "intermediate": 14, "advanced": 18},
    "back":      {"beginner": 10, "intermediate": 14, "advanced": 18},
    "shoulders": {"beginner": 7, "intermediate": 12, "advanced": 16},
    # Biceps beginner = 6: they receive heavy secondary volume from all back
    # pulling exercises (lat pulldown, rows). Net effective volume ≥10 sets/wk.
    "biceps":    {"beginner": 6,  "intermediate": 12, "advanced": 16},
    "triceps":   {"beginner": 10, "intermediate": 14, "advanced": 18},
    "legs":      {"beginner": 10, "intermediate": 14, "advanced": 18},
    "lower_back": {"beginner": 6,  "intermediate": 8,  "advanced": 10},
    "forearms":  {"beginner": 4,  "intermediate": 6,  "advanced": 8},
}

# GOAL_MODIFIER — strength modifier explanation:
#   strength goal does NOT need more volume — it needs heavier LOAD (≥80% 1RM per ACSM 2026).
#   The 0.75 modifier keeps set count lower so intensity can be maximised per set.
#   Volume reduction is intentional: quality > quantity for neural adaptation.
GOAL_MODIFIER     = {"gain": 1.0, "maintain": 0.85, "cut": 0.90, "strength": 0.75}
ACTIVITY_MODIFIER = {"office": 1.0, "light": 0.90, "heavy": 0.80}
DAYS_MODIFIER = {2: 0.60, 3: 0.75, 4: 0.85, 5: 1.0, 6: 1.15}
VOLUME_PREF_MODIFIER = {"low": 0.60, "medium": 1.0, "high": 1.30}
WORKSPACE_MODIFIER   = {"full_gym": 1.0, "dumbbells": 0.85, "home": 0.65}

# ─────────────────────────────────────────────
#  LOAD GUIDANCE  (ACSM 2026 Position Stand)
# ─────────────────────────────────────────────
# Maps goal → compound/isolation load recommendation as % of 1RM.
# Shown to user per exercise. NOT used computationally — purely instructional.
#
# Science basis (Currier et al., 2026):
#   Strength  → ≥80% 1RM (dose-response proven; heavier = more strength)
#   Gain      → 60–80% 1RM (full hypertrophy range — load doesn't matter as much as volume)
#   Cut       → 50–70% 1RM (higher reps, metabolic focus, muscle retention)
#   Maintain  → 60–75% 1RM (moderate, sustainable)
#
# Isolation exercises: always one tier lower than compounds
#   (less joint stability → heavier loads increase injury risk)

LOAD_GUIDANCE = {
    "gain": {
        "compound":  "65–80% 1RM  (6–8 reps — hypertrophy range)",
        "isolation": "55–70% 1RM  (8–12 reps — pump + volume)",
    },
    "strength": {
        "compound":  "≥80% 1RM  (3–5 reps — neural adaptation focus)",
        "isolation": "65–75% 1RM  (6–10 reps — joint-safe accessory work)",
    },
    "cut": {
        "compound":  "55–70% 1RM  (10–12 reps — muscle retention on deficit)",
        "isolation": "45–60% 1RM  (12–15 reps — metabolic stress, pump)",
    },
    "maintain": {
        "compound":  "60–75% 1RM  (8–10 reps — balanced stimulus)",
        "isolation": "50–65% 1RM  (10–15 reps — sustainable long-term)",
    },
}

def get_load_guidance(ex: dict, goal: str, workspace: str = "full_gym") -> str:
    """Return load guidance string for a single exercise."""
    key = "compound" if ex.get("compound", False) else "isolation"
    guidance = LOAD_GUIDANCE.get(goal, LOAD_GUIDANCE["maintain"])[key]
    
    # Fix 9: Dumbbells Workspace + Strength Goal
    if workspace == "dumbbells" and goal == "strength":
        guidance += " — use heaviest available dumbbell; track load in kg rather than % 1RM"
    
    return guidance

FEMALE_UPPER_BODY_MODIFIER = {"chest": 1.10, "shoulders": 1.15, "triceps": 1.10, "biceps": 1.05, "back": 1.0, "legs": 1.0}

def get_volume_target(muscle, level, goal, activity,
                      is_weak=False, single_leg_day=False, training_days=4, 
                      volume_pref="medium", workspace="full_gym", gender="male"):
    base   = BASE_VOLUME.get(muscle, {}).get(level, 10)
    if gender == "female":
        base = round(base * FEMALE_UPPER_BODY_MODIFIER.get(muscle, 1.0))
    target = base * GOAL_MODIFIER[goal] * ACTIVITY_MODIFIER[activity] * DAYS_MODIFIER.get(training_days, 1.0) * VOLUME_PREF_MODIFIER.get(volume_pref, 1.0) * WORKSPACE_MODIFIER.get(workspace, 1.0)
    if is_weak:
        target *= 1.35
    if single_leg_day and muscle == "legs":
        target *= 1.25
    # FIX 4: MRV Ceiling per Muscle
    max_cap = 20 if level != "advanced" else 24
    target = min(target, max_cap)
    # FIX B4: Add MEV floor to prevent volume from dropping below effective stimulus
    MEV_FLOOR = {"chest": 6, "back": 8, "shoulders": 6, "biceps": 4, "triceps": 6, "legs": 8, "lower_back": 4, "forearms": 2}
    mev = MEV_FLOOR.get(muscle, 4)
    return max(mev, round(target))

# ─────────────────────────────────────────────
#  INTERNAL RATIOS
# ─────────────────────────────────────────────
LEGS_INTERNAL_RATIO = {
    "quads": 0.32, "hamstrings": 0.20, "glutes": 0.22,
    "calves": 0.13, "abs": 0.13,
}

# lats + mid_back split the non-rear_delt budget equally
BACK_INTERNAL_RATIO = {
    "lats":     0.45,   # vertical pull — width
    "mid_back": 0.55,   # horizontal row — thickness
}
# rear_delt: fixed 1 exercise (sets_per_ex) unless back is weak
REAR_DELT_WEAK_RATIO = 0.20   # when back is weak, rear_delt gets 20% of total budget

# ─────────────────────────────────────────────
#  MUSCLE GROUP MAPPING
# ─────────────────────────────────────────────
MUSCLE_GROUP = {
    # Chest
    "chest_upper": "chest", "chest_mid": "chest",
    # Back — now 2 sub-muscles all map to "back" volume group
    "lats":      "back",    # vertical pull
    "mid_back":   "back",   # horizontal row
    # Shoulders
    "front_delt": "shoulders", "lateral_delt": "shoulders", "rear_delt": "shoulders",
    # Arms
    "biceps": "biceps", "triceps": "triceps",
    # Legs
    "quads": "legs", "hamstrings": "legs",
    "glutes": "legs", "calves": "legs", "abs": "legs",
    # NEW v4.0 - accessory muscles
    "lower_back": "lower_back",
    "traps": "traps",
    "forearms": "forearms",
    "adductors": "adductors",
    "abductors": "abductors",
}

MUSCLE_DISPLAY = {
    "chest": "Chest", "back": "Back", "shoulders": "Shoulders",
    "biceps": "Biceps", "triceps": "Triceps", "legs": "Legs",
    "chest_upper": "Chest (Upper)", "chest_mid": "Chest (Mid)",
    "lats":     "Lats",       # ← NEW
    "mid_back": "Mid Back",   # ← NEW
    "front_delt": "Front Delts", "lateral_delt": "Lateral Delts",
    "rear_delt": "Rear Delts", "quads": "Quads",
    "hamstrings": "Hamstrings", "glutes": "Glutes",
    "calves": "Calves", "abs": "Abs",
    "lower_back": "Lower Back",
    "traps": "Traps",
    "forearms": "Forearms",
    "adductors": "Adductors",
    "abductors": "Abductors",
}

# ─────────────────────────────────────────────
#  PROTOCOL
# ─────────────────────────────────────────────
# Base protocol per experience level.
# sets_per_ex is OVERRIDDEN per goal in get_sets_per_ex() below.
SETS_PROTOCOL = {
    "beginner":     {"sets": 3, "reps": "10-12", "failure": "RIR 3-4",
                     "note": "Focus on learning movement. Do not push to failure yet."},
    "intermediate": {"sets": 4, "reps": "8-12",  "failure": "Last set to technical failure",
                     "note": "Sets 1-3 stop at RIR 2. Last set push to technical failure."},
    "advanced":     {"sets": 5, "reps": "6-12",  "failure": "Last 1-2 sets true failure + optional intensifiers",
                     "note": "Can use drop sets, rest-pause, forced reps on final sets."},
}

# ── Goal-aware sets per exercise  (ACSM 2026) ────────────────────────────────
# Strength goal: 2–3 sets per exercise at ≥80% 1RM is optimal.
#   More sets = more fatigue without proportional strength gain at high loads.
# Hypertrophy (gain): 3–4 sets per exercise, dose-response up to ~18–20 sets/wk.
# Cut/Maintain: 2–3 sets — retain stimulus, manage total volume and recovery.
GOAL_SETS_PER_EX = {
    "beginner":     {"gain": 3, "strength": 2, "cut": 2, "maintain": 3},
    "intermediate": {"gain": 4, "strength": 3, "cut": 3, "maintain": 3},
    "advanced":     {"gain": 4, "strength": 3, "cut": 3, "maintain": 4},
}

def get_sets_per_ex(level: str, goal: str) -> int:
    """Return correct sets-per-exercise for this level + goal combination."""
    result = GOAL_SETS_PER_EX.get(level, GOAL_SETS_PER_EX["intermediate"]).get(goal, 3)
    if level == "beginner": result = max(result, 3)
    return result

# ── ROM guidance ────────────────────────────────────────────────────────────────
# ACSM 2026: "full range of motion" positively impacts strength.
# We flag exercises where partial ROM is a common mistake,
# so the output can warn the user.
PARTIAL_ROM_RISK = {
    "Barbell Back Squat":           "Go to at least parallel (thighs horizontal). Quarter squats do not build strength equally.",
    "Flat Barbell Bench Press":     "Touch the bar to the chest — do not stop 10cm above it.",
    "Flat Dumbbell Press":          "Lower until dumbbells reach chest level for full pec stretch.",
    "Incline Dumbbell Press":       "Full stretch at bottom — don't cut the ROM to protect shoulder.",
    "Lat Pulldown (Wide Grip)":     "Pull to upper chest and fully extend arms at top.",
    "Lat Pulldown (Underhand Grip)":"Pull to upper chest and fully extend arms at top.",
    "Leg Press":                    "Lower until knees reach ~90°. Do not lock knees at top.",
    "Romanian Deadlift (RDL)":      "Lower until you feel a strong hamstring stretch — not just to shin level.",
    "Lying Leg Curl":               "Full extension at the bottom — don't limit ROM to use heavier weight.",
    "Overhead Press (Barbell)":     "Lock out at top, lower to chin/upper chest level.",
    "Dips (Upright / Tricep Focused)": "Lower until upper arm is at least parallel to floor.",
    "Chest Dips (Forward Lean)":    "Lower until upper arm is at least parallel to floor.",
}

def get_rom_note(ex: dict) -> str | None:
    """Return ROM warning string for exercise, or None if no risk."""
    return PARTIAL_ROM_RISK.get(ex["name"])

def enrich_exercise(ex_dict: dict, source_ex: dict, goal: str, workspace: str = "full_gym") -> dict:
    """
    Add load_guidance and rom_note to an already-built exercise dict.
    Call this after constructing any exercise entry.
    ex_dict  : the dict being built (with sets, reps, etc.)
    source_ex: the raw EXERCISE_DB entry
    goal     : user goal string
    workspace: user's workspace for load guidance
    """
    ex_dict["load_guidance"] = get_load_guidance(source_ex, goal, workspace)
    rom = get_rom_note(source_ex)
    if rom:
        ex_dict["rom_note"] = rom
    return ex_dict
# ── Dynamic rest times ────────────────────────────────────────────────────────
REST_PROTOCOL = {
    "compound":  "2–3 min",
    "machine":   "90–120 sec",
    "isolation": "60–90 sec",
}

# ─────────────────────────────────────────────
#  FATIGUE COST SYSTEM  (Feature 2 + v4.0 update)
# ─────────────────────────────────────────────
# Auto-computed from compound + equipment flags.
# Can be overridden per exercise in EXERCISE_DB via "fatigue_cost" key.
#
# Auto-logic:
#   free-weight compound (barbell/dumbbell) → 3  (heavy CNS demand + stabilisers)
#   machine compound                        → 2  (fixed path, less stabiliser load)
#   isolation (any equipment)               → 1  (single-joint, low systemic fatigue)
#
# v4.0 UPDATE: small isolation muscles (forearms, calves, abs, traps) → 1 (default)
# they don't spike CNS fatigue like compounds do.
#
# Daily cap: SESSION_FATIGUE_CAP enforced ALONGSIDE SESSION_SETS_CAP.
# A session with 3 Deadlift sets (cost 9) + 3 Squat sets (cost 9) = 18 fatigue
# already hits the beginner cap before touching arms. This is correct.

SMALL_ISOLATION_MUSCLES = {"calves", "abs", "traps", "forearms", "adductors", "abductors", "lower_back"}

def compute_fatigue_cost(ex: dict) -> int:
    """Return fatigue cost for one exercise. Respects explicit override."""
    if "fatigue_cost" in ex:
        return ex["fatigue_cost"]
    # v4.0: check if small isolation muscle
    primary_muscles = list(ex.get("primary", {}).keys())
    if any(m in SMALL_ISOLATION_MUSCLES for m in primary_muscles):
        if not ex.get("compound", False):
            return 1  # small isolation muscles use less fatigue
    if not ex.get("compound", False):
        return 1                        # isolation
    if ex.get("equipment") in ("barbell", "dumbbell", "bodyweight"):
        return 3                        # free-weight compound
    return 2                            # machine / cable compound

SESSION_FATIGUE_CAP = {
    # Per session, total fatigue budget (sum of fatigue_cost × sets)
    "beginner":     {"cut": 24, "maintain": 28, "gain": 32, "strength": 28},
    "intermediate": {"cut": 30, "maintain": 36, "gain": 42, "strength": 36},
    "advanced":     {"cut": 36, "maintain": 44, "gain": 52, "strength": 44},
}

# ─────────────────────────────────────────────
#  HARD CONSTRAINTS  (Feature 3)
# ─────────────────────────────────────────────
# Pairs of exercises that MUST NOT appear in the same session.
# Format: {"exercises": (A, B), "levels": [...], "reason": "..."}
# "levels" = which experience levels the constraint applies to.
# Advanced athletes may handle both (e.g. Squat + Deadlift on same day).

HARD_CONSTRAINTS = [
    {
        "exercises": ("Barbell Back Squat", "Conventional Deadlift"),
        "levels":    ["beginner", "intermediate"],
        "reason":    "Both are high-CNS spinal-load compounds — same-session use "
                     "risks lower-back fatigue and form breakdown.",
    },
    {
        "exercises": ("Barbell Back Squat", "Trap Bar Deadlift"),
        "levels":    ["beginner"],
        "reason":    "Two heavy knee-dominant / hip-hinge hybrids is excessive for beginners.",
    },
    {
        "exercises": ("Barbell Back Squat", "Romanian Deadlift (RDL)"),
        "levels":    ["beginner"],
        "reason":    "Quad-dominant squat + hamstring-dominant RDL is fine for intermediate+, "
                     "but beginners lack the posterior chain endurance.",
    },
    {
        "exercises": ("Conventional Deadlift", "Sumo Deadlift"),
        "levels":    ["beginner", "intermediate", "advanced"],
        "reason":    "Two deadlift variations on the same day — one is always redundant.",
    },
    {
        "exercises": ("Incline Dumbbell Press", "Incline Barbell Press"),
        "levels":    ["beginner", "intermediate"],
        "reason":    "Same movement pattern, same resistance curve. Pick one pressing angle.",
    },
    {
        "exercises": ("Flat Dumbbell Press", "Flat Barbell Bench Press"),
        "levels":    ["beginner"],
        "reason":    "Same horizontal press pattern — redundant for beginners.",
    },
    {
        "exercises": ("Overhead Press (Barbell)", "Arnold Press"),
        "levels":    ["beginner", "intermediate"],
        "reason":    "Both are vertical press patterns — one is enough per session.",
    },
    {
        "exercises": ("Hip Thrust (Barbell)", "Sumo Deadlift"),
        "levels":    ["beginner"],
        "reason":    "Two heavy glute-dominant compound movements — too much posterior load.",
    },
    {
        "exercises": ("Barbell Back Squat", "Bulgarian Split Squat"),
        "levels":    ["beginner", "intermediate"],
        "reason":    "Extreme overlap of neurological demand and axial fatigue on the posterior chain.",
    },
    {
        "exercises": ("Overhead Press (Barbell)", "Incline Barbell Press"),
        "levels":    ["beginner", "intermediate"],
        "reason":    "Massive anterior deltoid overlap, pushing the joint into high impingement risk under heavy load.",
    },
    {
        "exercises": ("Conventional Deadlift", "Romanian Deadlift (RDL)"),
        "levels":    ["beginner", "intermediate"],
        "reason":    "Combined spinal erector fatigue elevates lumbar injury risk.",
    },
    {
        "exercises": ("Close Grip Bench Press", "Dips (Upright / Tricep Focused)"),
        "levels":    ["beginner", "intermediate"],
        "reason":    "Drives elbow flexor/extensor imbalance and elevates epicondyle stress.",
    },
    {
        "exercises": ("Barbell Back Squat", "Hack Squat (Machine)"),
        "levels":    ["beginner"],
        "reason":    "For beginners, one knee-dominant quad compound is sufficient.",
    },
]

def get_hard_blocked(session_names: list, level: str) -> set:
    """
    Given exercises already chosen this session, return set of exercise names
    that are now HARD BLOCKED due to constraint rules.
    """
    blocked = set()
    for constraint in HARD_CONSTRAINTS:
        if level not in constraint["levels"]:
            continue
        a, b = constraint["exercises"]
        if a in session_names:
            blocked.add(b)
        if b in session_names:
            blocked.add(a)
    return blocked

# ─────────────────────────────────────────────
#  DYNAMIC SETS ALLOCATOR (Feature 1)
# ─────────────────────────────────────────────
# Instead of fixed sets per level, allocate dynamically based on:
#   - Volume preference (Low/Medium/High)
#   - Remaining budget for the muscle
#   - Ensures no exercise gets only 1 set
# Range: 2-4 sets per exercise
DYNAMIC_SETS_RANGE = {
    "low":    {"min": 2, "max": 3},
    "medium": {"min": 2, "max": 4},
    "high":   {"min": 3, "max": 4},
}

def get_dynamic_sets(budget, volume_pref="medium", session_remaining=999):
    """
    Allocate sets for next exercise dynamically.
    - budget: remaining sets for this muscle
    - volume_pref: low/medium/high
    - session_remaining: how many sets left in session
    
    Rules:
      1. Never give 1 set (looks stupid)
      2. If budget == 1, merge with previous exercise or skip
      3. Respect volume_pref range (2-4 sets)
      4. Don't exceed session_remaining
    """
    if budget <= 1:
        return 0  # Can't allocate - will be handled by caller
    
    pref_range = DYNAMIC_SETS_RANGE.get(volume_pref, DYNAMIC_SETS_RANGE["medium"])
    min_sets = pref_range["min"]
    max_sets = pref_range["max"]
    
    # If budget is small, give it all (but at least min_sets)
    if budget <= max_sets:
        return max(min_sets, budget)
    
    # If budget is large, give max_sets
    return min(max_sets, budget, session_remaining)

def get_rest_time(ex, goal="maintain"):
    """Returns correct rest recommendation string for an exercise dict."""
    if not ex.get("compound", False):
        # Isolation exercises: 60-90 sec regardless of goal
        return REST_PROTOCOL["isolation"]
    if ex.get("equipment") == "machine":
        return REST_PROTOCOL["machine"]
    # Compound exercises: 2-3 min for gain/maintain, 3-5 min for strength
    if goal == "strength":
        return "3–5 min"
    return REST_PROTOCOL["compound"]

def get_reps(ex, goal):
    """
    Dynamic rep range based on exercise type and training goal.
    Replaces the static "8-12" that was the same for everyone.

    Science basis:
      Gain  → heavier loads, lower reps → more mechanical tension → better hypertrophy
      Cut   → moderate-high reps → more metabolic stress → muscle retention on deficit
      Maintain → middle ground

    Compound vs isolation:
      Compounds benefit more from lower rep ranges (can load heavier safely)
      Isolations are better at higher reps (less joint stress, better pump)
    """
    if ex.get("compound", False):
        if goal == "gain":
            return "6–12"      # hypertrophy focus: full range per Schoenfeld et al.
        elif goal == "cut":
            return "10–12"    # higher reps, maintains volume with lighter load
        elif goal == "strength":
            return "3–5"      # أقصى حمل للجهاز العصبي لاكتساب القوة
        else:
            return "8–10"     # balanced
    else:
        # isolation — always higher reps regardless of goal
        if goal == "gain":
            return "10–20"     # isolation for hypertrophy: higher reps, better pump, joint-safe
        elif goal == "cut":
            return "10–20"    # metabolic, pump-focused
        elif goal == "strength":
            return "8–12"     # العزل في القوة يفضل متوسط عشان حماية المفاصل
        else:
            return "10–15"

# ─────────────────────────────────────────────
#  SPLITS  (unchanged)
# ─────────────────────────────────────────────
SPLITS = {
    "full_body_2":        {"name": "Full Body (2x/week)", "days": 2,
        "schedule": [["chest","back","shoulders","biceps","triceps","legs"],
                     ["chest","back","shoulders","biceps","triceps","legs"]]},
    "upper_lower_2":      {"name": "Upper / Lower", "days": 2,
        "schedule": [["chest","back","shoulders","biceps","triceps"], ["legs"]]},
    "full_body_3":        {"name": "Full Body (3x/week)", "days": 3,
        "schedule": [["chest","back","shoulders","biceps","triceps","legs"]]*3},
    "ppl_3":              {"name": "Push / Pull / Legs", "days": 3,
        "schedule": [["chest","shoulders","triceps"],["back","biceps"],["legs"]]},
    "upper_lower_full_3": {"name": "Upper / Lower / Full Body", "days": 3,
        "schedule": [["chest","back","shoulders","biceps","triceps"],["legs"],
                     ["chest","back","shoulders","biceps","triceps","legs"]]},
    "upper_lower_4":      {"name": "Upper / Lower (2x each)", "days": 4,
        "schedule": [["chest","back","shoulders","biceps","triceps"],["legs"],
                     ["chest","back","shoulders","biceps","triceps"],["legs"]]},
    "ppl_full_4":         {"name": "PPL + Full Body", "days": 4,
        "schedule": [["chest","shoulders","triceps"],["back","biceps"],["legs"],
                     ["chest","back","shoulders","biceps","triceps","legs"]]},
    "bro_split_4":        {"name": "Bro Split (4 days)", "days": 4,
        "schedule": [["chest","triceps"],["back","biceps"],["shoulders"],["legs"]]},
    "ppl_upper_4":        {"name": "PPL + Upper (1 Leg Day)", "days": 4,
        "schedule": [["chest","shoulders","triceps"],["back","biceps"],["legs"],
                     ["chest","back","shoulders","biceps","triceps"]]},
    "bro_modified_4":     {"name": "Bro Split Modified (1 Leg Day)", "days": 4,
        "schedule": [["chest","biceps"],["back","triceps"],["legs"],
                     ["shoulders","biceps","triceps"]]},
    "pppp_legs_5":        {"name": "Push / Pull / Push / Pull / Legs (1 Leg Day)", "days": 5,
        "schedule": [["chest","shoulders","triceps"],["back","biceps"],
                     ["chest","shoulders","triceps"],["back","biceps"],["legs"]]},
    "ppl_ul_5":           {"name": "PPL + Upper / Lower", "days": 5,
        "schedule": [["chest","shoulders","triceps"],["back","biceps"],["legs"],
                     ["chest","back","shoulders","biceps","triceps"],["legs"]]},
    "bro_split_5":        {"name": "Bro Split (5 days)", "days": 5,
        "schedule": [["chest","triceps"],["back","biceps"],["legs"],
                     ["shoulders"],["biceps","triceps"]]},
    "arnold_5":           {"name": "Arnold Split", "days": 5,
        "schedule": [["chest","back"],["shoulders","biceps","triceps"],["legs"],
                     ["chest","back","shoulders"],["legs"]]},
    "strength_4":         {"name": "Strength Upper/Lower (Heavy/Vol)", "days": 4,
        "schedule": [["legs"], ["chest", "shoulders", "triceps"], ["legs", "back"], ["chest", "back", "shoulders", "biceps", "triceps"]]},
    "ppl_6":             {"name": "PPL (2x/week)", "days": 6,
        "schedule": [["chest","shoulders","triceps"],["back","biceps"],["legs"]]*2},
}

# ─────────────────────────────────────────────
#  DECISION TREE
# ─────────────────────────────────────────────
def select_split(days, level, weak_muscles, leg_days_pref=2, goal="maintain", injuries=None, gender="male"):
    reasoning = ""
    injuries = injuries or {}
    
    # FIX 1: Weak Legs Guard - if legs is weak and user wants 1 leg day, force 2
    if "legs" in weak_muscles and leg_days_pref == 1:
        leg_days_pref = 2
        reasoning = "Legs is weak → forced to 2 leg days; "
    
    # FIX 5: Beginner 6-Day Loophole
    if days == 6 and level == "beginner":
        days = 5
        reasoning = "Capped to 5 days — 6-day programs exceed beginner recovery capacity; "
    
    # FIX B1: Check lower back injury BEFORE the strength_4 early return
    injury_list = []
    if isinstance(injuries, dict):
        for v in injuries.values():
            if isinstance(v, list):
                injury_list.extend(v)
            else:
                injury_list.append(str(v))
    else:
        injury_list = [str(inj) for inj in (injuries or [])]
    
    lower_back_injured = any("lower back" in inj.lower() or 
                         "lower_back" in inj.lower() 
                         for inj in injury_list)
    
    # FORCE: strength goal + 4 days = strength_4 split (unless lower back injured)
    if goal == "strength" and days == 4:
        if lower_back_injured:
            reasoning += "Lower back injured → strength_4 blocked; "
        else:
            return "strength_4", "Strength goal + 4 days → forced to Strength Upper/Lower split"
    
    # FORCE: 6 days = ppl_6 split only
    if days == 6:
        return "ppl_6", "6-day program → PPL (2x/week) for maximum frequency"
    
    if leg_days_pref == 0:
        by_days = {2:["upper_lower_2"],3:["ppl_3"],
                   4:["bro_modified_4","ppl_upper_4"],5:["bro_split_5","pppp_legs_5"],
                   6:["ppl_6"]}
    elif leg_days_pref == 1:
        by_days = {2:["upper_lower_2"],3:["ppl_3"],
                   4:["ppl_upper_4","bro_modified_4"],5:["pppp_legs_5","bro_split_5"],
                   6:["ppl_6"]}
    else:
        # Strictly >= 2 leg days
        by_days = {2:["full_body_2"],
                   3:["full_body_3","upper_lower_full_3"],
                   4:["upper_lower_4","ppl_full_4","strength_4"],
                   5:["ppl_ul_5","arnold_5"],
                   6:["ppl_6"]}
    candidates = by_days.get(days, ["full_body_2"])
    
    # HARD FILTER FOR BRO SPLITS (Beginner/Intermediate)
    # Remove splits that train a muscle only 1x/week
    if level in ["beginner", "intermediate"]:
        low_frequency_splits = ["bro_split_4", "bro_modified_4", "bro_split_5", "ppl_3"]
        candidates = [c for c in candidates if c not in low_frequency_splits]
        if any(c in candidates for c in low_frequency_splits):
            reasoning = "Low-frequency splits restricted for your level; "

    if level == "beginner":
        if days <= 3:
            allowed = {
                2: ["full_body_2", "upper_lower_2"],
                3: ["full_body_3", "upper_lower_full_3"],
            }
        else:
            allowed = {
                4: ["upper_lower_4", "ppl_upper_4"],
                5: ["ppl_ul_5", "pppp_legs_5"],
            }
        filtered = [c for c in candidates if c in allowed.get(days, candidates)]
        if filtered:
            candidates = filtered
        elif days <= 3:
            candidates = ["full_body_3"]
        if not reasoning:
            reasoning = "Beginner level → high frequency splits prioritized"

    elif level == "intermediate":
        if days <= 3:
            preferred = {
                2: ["full_body_2", "upper_lower_2"],
                3: ["full_body_3", "upper_lower_full_3"],
            }
            filtered = [c for c in candidates if c in preferred.get(days, candidates)]
            if filtered:
                candidates = filtered
            else:
                candidates = preferred.get(days, ["full_body_3"])
        if not reasoning:
            reasoning = "Intermediate level → balanced frequency preferred"

    elif level == "advanced":
        preferred = {
            2: ["full_body_2"],
            3: ["ppl_3", "full_body_3"],
            4: ["upper_lower_4","ppl_full_4","ppl_upper_4"],
            5: ["ppl_ul_5","arnold_5","bro_split_5","pppp_legs_5"],
        }
        filtered = [c for c in candidates if c in preferred.get(days, candidates)]
        if filtered: candidates = filtered

    if not candidates:
        candidates = by_days.get(days, ["full_body_2"])

    high_freq = {
        "chest":     ["upper_lower_4","full_body_2","full_body_3","ppl_ul_5",
                      "upper_lower_2","ppl_upper_4","pppp_legs_5"],
        "back":      ["upper_lower_4","full_body_2","full_body_3","ppl_ul_5",
                      "upper_lower_2","ppl_upper_4","pppp_legs_5"],
        "shoulders": ["upper_lower_4","full_body_2","full_body_3","arnold_5",
                      "ppl_upper_4","pppp_legs_5"],
        "biceps":    ["arnold_5","upper_lower_4","full_body_3","bro_split_5","pppp_legs_5"],
        "triceps":   ["arnold_5","upper_lower_4","full_body_3","bro_split_5","pppp_legs_5"],
        "legs":      ["upper_lower_4","ppl_ul_5","full_body_3","arnold_5"],
    }
    scores = {c: 0 for c in candidates}
    for muscle in weak_muscles:
        for c in candidates:
            if c in high_freq.get(muscle, []):
                scores[c] += 2
    
    best_split = max(scores, key=scores.get)
    
    if reasoning:
        reasoning += f" → {best_split} selected based on weak muscle frequency"
    else:
        reasoning = f"{best_split} selected based on weak muscle frequency"
    
    return best_split, reasoning

# ─────────────────────────────────────────────
#  INJURY RESTRICTIONS
# ─────────────────────────────────────────────
INJURY_RESTRICTIONS = {
    "lower back": ["Conventional Deadlift","Barbell Row (Pendlay)","Barbell Back Squat",
                   "Romanian Deadlift (RDL)","Sumo Deadlift"],
    "knee":       ["Barbell Back Squat","Hack Squat","Leg Extension",
                   "Walking Lunge","Bulgarian Split Squat"],
    "shoulder":   ["Overhead Press","Arnold Press","Incline Barbell Press",
                   "Flat Barbell Bench Press","Landmine Press"],
    "wrist":      ["Barbell Curl","Skull Crusher","Close Grip Bench Press","Barbell Row (Pendlay)"],
    "elbow":      ["Skull Crusher","Close Grip Bench Press","Tricep Pushdown"],
    "hip":        ["Hip Thrust","Bulgarian Split Squat","Sumo Deadlift","Walking Lunge"],
    "neck":       ["Barbell Shrugs","Dumbbell Shrugs","Heavy Deadlifts"],
    "ankle":      ["Barbell Squat","Standing Calf Raise","Jump Squats"],
    "chest":      ["Dumbbell Fly","Cable Fly","Pec Deck"],
}

# ─────────────────────────────────────────────
#  WORKSPACE / EQUIPMENT
# ───────────────────────────────────────���─���───
# full_gym: all equipment available
# dumbbells: dumbbell + bodyweight only
# home: bodyweight only
WORKSPACE = "full_gym"  # default; can be overridden by profile

def allowed_equipment(level, workspace="full_gym"):
    """Filter equipment based on workspace and level."""
    if workspace == "home":
        return ["bodyweight"]
    elif workspace == "dumbbells":
        return ["dumbbell", "bodyweight"]
    else:  # full_gym
        if level == "beginner":
            return ["dumbbell","machine","cable","bodyweight","other"]
        return ["dumbbell","machine","cable","bodyweight","barbell","other"]

# ─────────────────────────────────────────────
#  EXERCISE DATABASE (v4.0 UPDATED)
# ─────────────────────────────────────────────
EXERCISE_DB = [
    # ── CHEST UPPER ──────────────────────────────────────────────────
    {"id":1,  "name":"Incline Dumbbell Press",
     "primary":{"chest_upper":1.0},"secondary":{"triceps":0.5,"front_delt":0.5},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["upper_chest","stretch_focused"]},
    {"id":2,  "name":"Incline Barbell Press",
     "primary":{"chest_upper":1.0},"secondary":{"triceps":0.5,"front_delt":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["upper_chest","strength"]},
    {"id":3,  "name":"Cable Fly Low to High",
     "primary":{"chest_upper":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["upper_chest","stretch_focused","high_stability"]},
    {"id":4,  "name":"Landmine Press",
     "primary":{"chest_upper":1.0},"secondary":{"front_delt":0.5,"triceps":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["upper_chest","shoulder_safe"]},
    # ── CHEST MID ────────────────────────────────────────────────────
    {"id":5,  "name":"Flat Dumbbell Press",
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5,"front_delt":0.5},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["classic","stretch_focused"]},
    {"id":6,  "name":"Flat Barbell Bench Press",
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5,"front_delt":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["classic","strength"]},
    {"id":7,  "name":"Cable Fly High to Low",
     "primary":{"chest_mid":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","high_stability"]},
    {"id":8,  "name":"Machine Chest Press",
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5},
     "equipment":"machine","level":["beginner","intermediate"],
     "compound":True,"tags":["high_stability","beginner_friendly"]},
    {"id":9,  "name":"Dumbbell Floor Press",
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5},
     "equipment":"dumbbell","level":["beginner","intermediate"],
     "compound":True,"tags":["no_bench_needed"]},
    {"id":10, "name":"Chest Dips (Forward Lean)",
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":True,"tags":["stretch_focused","classic"]},
    # ── LATS (vertical pull — width) ─────────────────────────────────
    {"id":11, "name":"Lat Pulldown (Wide Grip)",
     "primary":{"lats":1.0},"secondary":{"biceps":0.5},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["classic","width","stretch_focused"]},
    {"id":16, "name":"Pull-Up / Weighted Pull-Up",
     "primary":{"lats":1.0},"secondary":{"biceps":0.5},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":True,"tags":["classic","width","strength"]},
    {"id":64, "name":"Lat Pulldown (Underhand Grip)",
     "primary":{"lats":1.0},"secondary":{"biceps":0.6},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["width","stretch_focused"]},
    {"id":65, "name":"Straight Arm Pulldown",
     "primary":{"lats":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","mind_muscle"]},
    {"id":66, "name":"Machine Assisted Pull-Up",
     "primary":{"lats":1.0},"secondary":{"biceps":0.5},
     "equipment":"machine","level":["beginner","intermediate"],
     "compound":True,"tags":["width","high_stability","beginner_friendly"]},
    # ── MID BACK (horizontal row — thickness) ────────────────────────
    {"id":12, "name":"Seated Cable Row (Neutral Grip)",
     "primary":{"mid_back":1.0},"secondary":{"biceps":0.5,"lats":0.3},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["classic","stretch_focused"]},
    {"id":13, "name":"Single Arm Dumbbell Row",
     "primary":{"mid_back":1.0},"secondary":{"biceps":0.5,"lats":0.3},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["unilateral","stretch_focused"]},
    {"id":14, "name":"Chest-Supported Row (Machine)",
     "primary":{"mid_back":1.0},"secondary":{"biceps":0.5,"lats":0.3},
     "equipment":"machine","level":["beginner","intermediate"],
     "compound":True,"tags":["high_stability","beginner_friendly","lower_back_safe"]},
    {"id":15, "name":"Barbell Row (Pendlay)",
     "primary":{"mid_back":1.0},"secondary":{"biceps":0.5,"lats":0.3},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["strength","classic"]},
    {"id":17, "name":"Meadows Row",
     "primary":{"mid_back":1.0},"secondary":{"biceps":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["unilateral","stretch_focused"]},
    {"id":18, "name":"Trap Bar Deadlift",
     "primary":{"mid_back":1.0},"secondary":{"lats":0.3,"quads":0.5,"glutes":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["strength","lower_back_safe"],"fatigue_cost":3},
    {"id":19, "name":"Conventional Deadlift",
     "primary":{"mid_back":1.0},"secondary":{"lats":0.3,"hamstrings":0.5,"glutes":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["strength","classic"],"fatigue_cost":4},
    # ── REAR DELT ────────────────────────────────────────────────────
    {"id":26, "name":"Face Pull",
     "primary":{"rear_delt":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","posture","health"]},
    {"id":27, "name":"Rear Delt Cable Fly",
     "primary":{"rear_delt":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate"],
     "compound":False,"tags":["stretch_focused","high_stability"]},
    {"id":28, "name":"Reverse Pec Deck",
     "primary":{"rear_delt":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability"]},
    # ── FRONT DELT ───────────────────────────────────────────────────
    {"id":20, "name":"Seated DB Shoulder Press",
     "primary":{"front_delt":1.0},"secondary":{"triceps":0.5,"lateral_delt":0.5},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["classic","stretch_focused"]},
    {"id":67, "name":"Machine Shoulder Press",
     "primary":{"front_delt":1.0},"secondary":{"triceps":0.4,"lateral_delt":0.4},
     "equipment":"machine","level":["beginner","intermediate"],
     "compound":True,"tags":["high_stability","beginner_friendly"]},
    {"id":21, "name":"Overhead Press (Barbell)",
     "primary":{"front_delt":1.0},"secondary":{"triceps":0.5,"lateral_delt":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["classic","strength"]},
    {"id":22, "name":"Arnold Press",
     "primary":{"front_delt":1.0},"secondary":{"triceps":0.5,"lateral_delt":0.5},
     "equipment":"dumbbell","level":["intermediate","advanced"],
     "compound":True,"tags":["full_head_activation","stretch_focused"]},
    # ── LATERAL DELT ─────────────────────────────────────────────────
    {"id":87, "name":"Machine Lateral Raise",
     "primary":{"lateral_delt":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","stretch_focused"]},
    {"id":23, "name":"Cable Lateral Raise",
     "primary":{"lateral_delt":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","stretch_focused"]},
    {"id":24, "name":"DB Lateral Raise",
     "primary":{"lateral_delt":1.0},"secondary":{},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic"]},
    {"id":25, "name":"Landmine Lateral Raise",
     "primary":{"lateral_delt":1.0},"secondary":{},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":False,"tags":["stretch_focused"]},
    # ── BICEPS ───────────────────────────────────────────────────────
    {"id":29, "name":"Preacher Curl (Machine/EZ Bar)",
     "primary":{"biceps":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","peak_contraction"]},
    {"id":30, "name":"Hammer Curl",
     "primary":{"biceps":1.0},"secondary":{},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic","brachialis"]},
    {"id":31, "name":"Cable Curl (High Cable)",
     "primary":{"biceps":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","peak_contraction","stretch_focused"]},
    {"id":32, "name":"Incline Dumbbell Curl",
     "primary":{"biceps":1.0},"secondary":{},
     "equipment":"dumbbell","level":["intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","long_head"]},
    {"id":33, "name":"Barbell Curl",
     "primary":{"biceps":1.0},"secondary":{},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":False,"tags":["classic","strength"]},
{"id":34, "name":"Spider Curl",
     "primary":{"biceps":1.0},"secondary":{},
     "equipment":"dumbbell","level":["intermediate","advanced"],
     "compound":False,"tags":["peak_contraction","stretch_focused"]},
    {"id":90, "name":"Chin-Up (Bicep Focus)",
     "primary":{"biceps":1.0},"secondary":{"lats":0.5},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":True,"tags":["classic","bodyweight","home_back"]},
    {"id":91, "name":"Inverted Row (Supinated Grip)",
     "primary":{"biceps":1.0},"secondary":{"mid_back":0.6},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["bodyweight","home_back","stretch_focused"]},
    # ── TRICEPS ──────────────────────────────────────────────────────────
    {"id":37, "name":"Tricep Pushdown (Cable)",
     "primary":{"triceps":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic","lateral_head","high_stability"]},
    {"id":92, "name":"Overhead Tricep Extension (Cable)",
     "primary":{"triceps":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","long_head","high_stability"]},
    {"id":68, "name":"Tricep Pushdown (Rope)",
     "primary":{"triceps":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["lateral_head","high_stability"]},
    {"id":69, "name":"Overhead Tricep Extension (Dumbbell)",
     "primary":{"triceps":1.0},"secondary":{},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","long_head","beginner_friendly"]},
    {"id":93, "name":"Diamond Push-Up",
     "primary":{"triceps":1.0},"secondary":{},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic","bodyweight"]},
    {"id":94, "name":"Skull Crusher (EZ Bar)",
     "primary":{"triceps":1.0},"secondary":{},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","long_head","classic"]},
    {"id":95, "name":"Close Grip Bench Press",
     "primary":{"triceps":1.0},"secondary":{"chest_mid":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["strength","classic"]},
    {"id":96, "name":"Dips (Upright / Tricep Focused)",
     "primary":{"triceps":1.0},"secondary":{"chest_mid":0.5},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":True,"tags":["stretch_focused","classic"]},
    # ── QUADS ────────────────────────────────────────────────────────
    {"id":41, "name":"Leg Press",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["high_stability","classic"]},
    {"id":42, "name":"Goblet Squat",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["beginner_friendly","classic"]},
    {"id":43, "name":"Leg Extension",
     "primary":{"quads":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","stretch_focused"]},
    {"id":44, "name":"Walking Lunge",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["unilateral","functional"]},
    {"id":45, "name":"Barbell Back Squat",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5,"hamstrings":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["classic","strength"],"fatigue_cost":4},
    {"id":46, "name":"Hack Squat (Machine)",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5},
     "equipment":"machine","level":["intermediate","advanced"],
     "compound":True,"tags":["high_stability","stretch_focused"]},
    {"id":47, "name":"Bulgarian Split Squat",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5},
     "equipment":"dumbbell","level":["intermediate","advanced"],
     "compound":True,"tags":["unilateral","stretch_focused"]},
    # ── HAMSTRINGS ───────────────────────────────────────────────────
    {"id":48, "name":"Lying Leg Curl",
     "primary":{"hamstrings":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","classic"]},
    {"id":49, "name":"Romanian Deadlift (RDL)",
     "primary":{"hamstrings":1.0},"secondary":{"glutes":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["stretch_focused","classic"],"fatigue_cost":4},
    {"id":50, "name":"Single Leg RDL",
     "primary":{"hamstrings":1.0},"secondary":{"glutes":0.5},
     "equipment":"dumbbell","level":["intermediate","advanced"],
     "compound":True,"tags":["unilateral","stretch_focused","balance"]},
    {"id":51, "name":"Nordic Curl",
     "primary":{"hamstrings":1.0},"secondary":{},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","injury_prevention"]},
    # ── GLUTES ───────────────────────────────────────────────────────
    {"id":52, "name":"Hip Thrust (Barbell)",
     "primary":{"glutes":1.0},"secondary":{"hamstrings":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["classic","peak_contraction"]},
    {"id":53, "name":"Cable Pull-Through",
     "primary":{"glutes":1.0},"secondary":{"hamstrings":0.5},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["stretch_focused","high_stability"]},
    {"id":54, "name":"Sumo Deadlift",
     "primary":{"glutes":1.0},"secondary":{"hamstrings":0.5,"quads":0.5},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":True,"tags":["strength","inner_thigh"],"fatigue_cost":4},
    {"id":55, "name":"Dumbbell Glute Bridge",
     "primary":{"glutes":1.0},"secondary":{"hamstrings":0.5},
     "equipment":"dumbbell","level":["beginner","intermediate"],
     "compound":True,"tags":["beginner_friendly","peak_contraction"]},
    # ── CALVES ───────────────────────────────────────────────────────
    {"id":56, "name":"Seated Calf Raise",
     "primary":{"calves":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["soleus","high_stability"],"fatigue_cost":1},
    {"id":57, "name":"Standing Calf Raise",
     "primary":{"calves":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic","stretch_focused"],"fatigue_cost":1},
    {"id":58, "name":"Donkey Calf Raise",
     "primary":{"calves":1.0},"secondary":{},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":False,"tags":["stretch_focused"],"fatigue_cost":1},
    # ── ABS ──────────────────────────────────────────────────────────
    {"id":59, "name":"Cable Crunch",
     "primary":{"abs":1.0},"secondary":{},
     "equipment":"cable","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","weighted"],"fatigue_cost":1},
    {"id":60, "name":"Plank Variations",
     "primary":{"abs":1.0},"secondary":{},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic","core_stability"],"fatigue_cost":1},
    {"id":61, "name":"Hanging Leg Raise",
     "primary":{"abs":1.0},"secondary":{},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","lower_abs"],"fatigue_cost":1},
    {"id":62, "name":"Ab Wheel Rollout",
     "primary":{"abs":1.0},"secondary":{},
     "equipment":"other","level":["intermediate","advanced"],
     "compound":False,"tags":["stretch_focused","core_stability"],"fatigue_cost":1},
    {"id":63, "name":"Landmine Oblique Twist",
     "primary":{"abs":1.0},"secondary":{},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":False,"tags":["obliques"],"fatigue_cost":1},
    # ── BODYWEIGHT ADDITIONS ──────────────────────────────────────────
    {"id":70, "name":"Standard Push-Up",
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5,"front_delt":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["classic","bodyweight"]},
    {"id":71, "name":"Incline Push-Up (Hands on Chair/Bed)",
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5},
     "equipment":"bodyweight","level":["beginner"],
     "compound":True,"tags":["beginner_friendly","bodyweight"]},
    {"id":72, "name":"Pike Push-Up",
     "primary":{"front_delt":1.0},"secondary":{"triceps":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["bodyweight"]},
    {"id":73, "name":"Doorway / Towel Row (Inverted Row)",
     "primary":{"mid_back":1.0},"secondary":{"biceps":0.5,"lats":0.3},
     "equipment":"bodyweight","level":["beginner","intermediate"],
     "compound":True,"tags":["bodyweight","home_back"]},
    {"id":74, "name":"Superman Hold",
     "primary":{"mid_back":1.0},"secondary":{"rear_delt":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate"],
     "compound":False,"tags":["lower_back_safe","bodyweight"]},
    {"id":75, "name":"Bodyweight Squat",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate"],
     "compound":True,"tags":["classic","bodyweight"]},
    {"id":76, "name":"Bodyweight Glute Bridge",
     "primary":{"glutes":1.0},"secondary":{"hamstrings":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate"],
     "compound":True,"tags":["beginner_friendly","bodyweight"]},
    {"id":77, "name":"Bodyweight Walking Lunge",
     "primary":{"quads":1.0},"secondary":{"glutes":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate"],
     "compound":True,"tags":["unilateral","bodyweight"]},

    # ── NEW v4.0 MUSCLES ──────────────────────────────────────────
    # LOWER BACK
    {"id":80, "name":"Back Extensions (Hyperextensions)",
     "primary":{"lower_back":1.0},"secondary":{"glutes":0.3,"hamstrings":0.3},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["classic","high_stability","posture"]},
    # TRAPS
    {"id":81, "name":"Barbell Shrugs",
     "primary":{"traps":1.0},"secondary":{},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":False,"tags":["classic","strength"],"fatigue_cost":1},
    {"id":82, "name":"Dumbbell Shrugs",
     "primary":{"traps":1.0},"secondary":{},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic","high_stability"],"fatigue_cost":1},
    {"id":97, "name":"Decline Push-Up", 
     "primary":{"chest_upper":1.0},"secondary":{"triceps":0.5,"front_delt":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["stretch_focused","bodyweight"]},
    {"id":98, "name":"Archer Push-Up", 
     "primary":{"chest_mid":1.0},"secondary":{"triceps":0.5},
     "equipment":"bodyweight","level":["intermediate","advanced"],
     "compound":True,"tags":["unilateral","bodyweight"]},
    {"id":99, "name":"Glute Kickback (Bodyweight)", 
     "primary":{"glutes":1.0},"secondary":{"hamstrings":0.3},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["bodyweight","high_stability"],"fatigue_cost":1},
    {"id":100, "name":"Single-Leg Glute Bridge", 
     "primary":{"glutes":1.0},"secondary":{"hamstrings":0.5},
     "equipment":"bodyweight","level":["beginner","intermediate","advanced"],
     "compound":True,"tags":["unilateral","bodyweight"]},
    # FOREARMS
    {"id":83, "name":"Wrist Curls",
     "primary":{"forearms":1.0},"secondary":{},
     "equipment":"dumbbell","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["classic","high_stability"],"fatigue_cost":1},
    {"id":84, "name":"Reverse Barbell Curl",
     "primary":{"forearms":1.0},"secondary":{"biceps":0.3},
     "equipment":"barbell","level":["intermediate","advanced"],
     "compound":False,"tags":["classic","brachialis"],"fatigue_cost":1},
    # ADDUCTORS
    {"id":85, "name":"Adductor Machine",
     "primary":{"adductors":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","inner_thigh"],"fatigue_cost":1},
    # ABDUCTORS
    {"id":86, "name":"Abductor Machine",
     "primary":{"abductors":1.0},"secondary":{},
     "equipment":"machine","level":["beginner","intermediate","advanced"],
     "compound":False,"tags":["high_stability","outer_thigh"],"fatigue_cost":1},
]


# ─────────────────────────────────────────────
#  EXERCISE FILTER (v4.0 UPDATED)
# ─────────────────────────────────────────────
def get_blocked(injuries):
    blocked = []
    for injury in injuries:
        for key, names in INJURY_RESTRICTIONS.items():
            if key in injury.lower():
                blocked.extend(names)
    return blocked


# v4.0: ACCESSORY GATEKEEPER - muscles beginners should NOT directly train
BEGINNER_ACCESSORY_BLOCKED = {"forearms", "traps", "adductors", "abductors", "lower_back"}

def filter_for_muscle(muscle, level, blocked, weak, used_globally, workspace="full_gym",
                      session_equip_used=None, goal="maintain",
                      session_fatigue_so_far=0, session_names=None):
    """
    Returns exercises for a muscle, filtered and scored scientifically.
    
    v4.0 UPDATE: ACCESSORY GATEKEEPER
      - If experience == "beginner" and muscle in BEGINNER_ACCESSORY_BLOCKED,
        return empty list immediately.
      - Beginners get their accessory volume strictly from compound movements.

    Scoring system (replaces "trending"):
      +6  compound (compound-first is non-negotiable)
      +4  not used globally this week (exercise variation)
      +4  stretch_focused tag (stretch-mediated hypertrophy evidence)
      +3  unilateral tag — when parent muscle is in weak list
      +2  high_stability tag — weighted by session fatigue (more valuable late in session)
      +2  strength tag — when goal == "strength"
      +1  classic tag (proven baseline)
      -3  same equipment already used for this muscle today (Resistance Profile penalty)
      -2  hard_blocked by constraint (should be filtered out, but penalise as safety net)

    session_equip_used: dict {muscle_group: [equipment_types_used_today]}
    session_names:      list of exercise names already chosen this session (for hard constraints)
    session_fatigue_so_far: int, used to scale high_stability bonus
    """
    # v4.0: ACCESSORY GATEKEEPER
    if level == "beginner" and muscle in BEGINNER_ACCESSORY_BLOCKED:
        return []
    
    equip  = allowed_equipment(level, workspace)
    parent = MUSCLE_GROUP.get(muscle, muscle)
    hard_blocked = get_hard_blocked(session_names or [], level)

    candidates = [
        e for e in EXERCISE_DB
        if muscle in e["primary"]
        and level in e["level"]
        and e["equipment"] in equip
        and not any(b.lower() in e["name"].lower() for b in blocked)
        and e["name"] not in hard_blocked          # Hard Constraint enforcement
    ]

    # Equipment diversity: what's already been used for this muscle today?
    equip_used_today = (session_equip_used or {}).get(parent, [])

    # High stability: fixed +1 (machines/cables less CNS-taxing than free weights)
    # Unlike stretch, they don't offer unique hypertrophic stimulus — just low fatigue

    def score(ex):
        s = 0
        tags = ex.get("tags", [])

        # ── Compound-first: non-negotiable foundation ──────────────────
        if ex.get("compound", False):
            s += 6

        # ── Exercise variation (avoid repetition across the week) ──────
        if ex["name"] not in used_globally:
            s += 3

        # ── Stretch-mediated hypertrophy ─────────────────────────────
        if "stretch_focused" in tags:
            s += 5

        # ── Unilateral bonus for weak/imbalanced muscles ───────────────
        if "unilateral" in tags and parent in weak:
            s += 3

        # ── High stability: fixed +1 (just lower fatigue, not hypertrophic) ───
        if "high_stability" in tags:
            s += 1

        # ── Goal-specific bonuses ──────────────────────────────────────
        if goal == "strength" and "strength" in tags:
            s += 2

        # ── Classic: proven, baseline ─────────────────────────────────
        if "classic" in tags:
            s += 1

        # ── Resistance Profile: penalise same equipment curve ──────────
        # e.g., if dumbbell already chosen for chest → penalise next dumbbell
        if ex["equipment"] in equip_used_today:
            s -= 3

        return s

    return sorted(candidates, key=score, reverse=True)

# ─────────────────────────────────────────────
#  VALID SETS HELPER
# ─────────────────────────────────────────────
def get_valid_ex_sets(budget, sets_per_ex, max_allowed=999, volume_pref="medium"):
    """
    Feature 1: Dynamic Sets Allocator
    Uses get_dynamic_sets for flexible allocation based on volume preference.
    Falls back to sets_per_ex if dynamic allocation returns 0.
    """
    if budget <= 1 or max_allowed < 2:
        return 0
    
    # Use dynamic allocation based on volume preference
    dynamic = get_dynamic_sets(budget, volume_pref, max_allowed)
    if dynamic > 0:
        return dynamic
    
    # Fallback to original logic if dynamic returns 0
    if budget == sets_per_ex + 1:
        val = budget // 2
        return min(val, max_allowed)
    return min(sets_per_ex, budget, max_allowed)

# ─────────────────────────────────────────────
#  BUILD BACK EXERCISES
# ─────────────────────���─���─────────────────────
def build_back_exercises(back_sets_today, level, goal, blocked, weak, used, sets_per_ex,
                         session_remaining=999, workspace="full_gym", back_session_count=1,
                         volume_pref="medium", session_equip_used=None, session_fatigue=0,
                         session_names=None, fatigue_cap_remaining=999):
    """
    Distributes back budget across lats, mid_back.
    Now tracks equipment diversity (Resistance Profile) and fatigue cost.
    """
    result     = []
    names_used = []

    if back_sets_today <= 4:
        if back_session_count % 2 == 1:
            lats_sets = back_sets_today; mid_back_sets = 0
        else:
            lats_sets = 0; mid_back_sets = back_sets_today
    elif back_sets_today >= 6:
        lats_sets    = max(2, round(back_sets_today * BACK_INTERNAL_RATIO["lats"]))
        mid_back_sets = max(2, back_sets_today - lats_sets)
    else:
        if back_session_count % 2 == 1:
            lats_sets = back_sets_today; mid_back_sets = 0
        else:
            lats_sets = 0; mid_back_sets = back_sets_today

    sets_used    = [0]
    fatigue_used = [0]
    dynamic_sub_cap = {"beginner": 6, "intermediate": 8, "advanced": 10}.get(level, 8)
    if blocked: dynamic_sub_cap += 2

    def fill_sub(sub_muscle, budget):
        pool = filter_for_muscle(
            sub_muscle, level, blocked, weak, used, workspace,
            session_equip_used=session_equip_used,
            goal=goal,
            session_fatigue_so_far=session_fatigue + fatigue_used[0],
            session_names=(session_names or []) + [e["name"] for e in result],
        )
        pool = sorted(pool, key=lambda x: (0 if x["compound"] else 1))
        rem  = min(budget, dynamic_sub_cap)  # Cap allocation per sub-muscle
        for ex in pool:
            if rem <= 0: break
            if sets_used[0] >= session_remaining: break
            if fatigue_used[0] >= fatigue_cap_remaining: break
            if ex["name"] in names_used: continue
            # DYNAMIC HARD CONSTRAINT CHECK
            current_session_names = (session_names or []) + [e["name"] for e in result]
            if ex["name"] in get_hard_blocked(current_session_names, level):
                continue
            ex_sets = get_valid_ex_sets(rem, sets_per_ex, session_remaining - sets_used[0], volume_pref)
            if ex_sets == 0: break
            fc = compute_fatigue_cost(ex) * ex_sets
            if fatigue_used[0] + fc > fatigue_cap_remaining:
                # Try with fewer sets
                for try_sets in range(ex_sets - 1, 1, -1):
                    if compute_fatigue_cost(ex) * try_sets + fatigue_used[0] <= fatigue_cap_remaining:
                        ex_sets = try_sets; fc = compute_fatigue_cost(ex) * ex_sets; break
                else:
                    break
            result.append(enrich_exercise({
                "name": ex["name"], "primary": ex["primary"],
                "secondary": ex["secondary"], "equipment": ex["equipment"],
                "compound": ex["compound"],
                "sets": ex_sets, "reps": get_reps(ex, goal),
                "failure": SETS_PROTOCOL[level]["failure"], "tags": ex["tags"],
                "rest": get_rest_time(ex, goal),
                "fatigue_cost": compute_fatigue_cost(ex),
            }, ex, goal))
            names_used.append(ex["name"])
            # Update resistance profile
            if session_equip_used is not None:
                session_equip_used.setdefault("back", []).append(ex["equipment"])
            rem -= ex_sets; sets_used[0] += ex_sets; fatigue_used[0] += fc

    fill_sub("lats",     lats_sets)
    fill_sub("mid_back", mid_back_sets)
    return result

# ─────────────────────────────────────────────
#  SHOULDERS BALANCER
# ─────────────────────────────────────────────
def build_shoulders_exercises(total_sets, level, goal, blocked, weak, used, sets_per_ex,
                              session_remaining=999, sh_day_idx=0, workspace="full_gym",
                              volume_pref="medium", session_equip_used=None,
                              session_fatigue=0, session_names=None, fatigue_cap_remaining=999):
    """
    Alternates shoulder head focus across sessions.
    Now tracks equipment diversity and fatigue.
    """
    result, names_used = [], []
    sh_used    = [0]
    fat_used   = [0]
    dynamic_sub_cap = {"beginner": 6, "intermediate": 8, "advanced": 10}.get(level, 8)
    if blocked: dynamic_sub_cap += 2

    def fill_sub(sub, budget, max_press=False):
        if budget <= 0: return
        pool = filter_for_muscle(
            sub, level, blocked, weak, used, workspace,
            session_equip_used=session_equip_used,
            goal=goal,
            session_fatigue_so_far=session_fatigue + fat_used[0],
            session_names=(session_names or []) + [e["name"] for e in result],
        )
        
        # FIX LEAK C: Empty Shoulders fallback for Home/Beginner
        # If no exercises found (e.g., lateral_delt for home), substitute push exercises
        if not pool and sub == "lateral_delt":
            fallback_pool = filter_for_muscle(
                "front_delt", level, blocked, weak, used, workspace,
                session_equip_used=session_equip_used,
                goal=goal,
                session_fatigue_so_far=session_fatigue + fat_used[0],
                session_names=(session_names or []) + [e["name"] for e in result],
            )
            # Filter to compound push exercises only
            pool = [ex for ex in fallback_pool if ex.get("compound", False)]
        
        if max_press:
            # Max one press per session (OHP vs DB Press vs Machine Press)
            pc, filtered = 0, []
            for ex in pool:
                if ex.get("compound", False) and any(
                        t in ex["tags"] for t in ["classic","strength","full_head_activation","high_stability"]):
                    if pc >= 1: continue
                    pc += 1
                filtered.append(ex)
            pool = filtered
        rem = min(budget, dynamic_sub_cap)  # Cap allocation per sub-muscle
        for ex in pool:
            if rem <= 0 or sh_used[0] >= session_remaining: break
            if fat_used[0] >= fatigue_cap_remaining: break
            if ex["name"] in names_used: continue
            # DYNAMIC HARD CONSTRAINT CHECK
            current_session_names = (session_names or []) + [e["name"] for e in result]
            if ex["name"] in get_hard_blocked(current_session_names, level):
                continue
            ex_sets = get_valid_ex_sets(rem, sets_per_ex, session_remaining - sh_used[0], volume_pref)
            if ex_sets == 0: break
            fc = compute_fatigue_cost(ex) * ex_sets
            if fat_used[0] + fc > fatigue_cap_remaining:
                for try_sets in range(ex_sets - 1, 1, -1):
                    if compute_fatigue_cost(ex) * try_sets + fat_used[0] <= fatigue_cap_remaining:
                        ex_sets = try_sets; fc = compute_fatigue_cost(ex) * ex_sets; break
                else:
                    break
            result.append(enrich_exercise({"name": ex["name"], "primary": ex["primary"],
                "secondary": ex["secondary"], "equipment": ex["equipment"],
                "sets": ex_sets, "reps": get_reps(ex, goal),
                "failure": SETS_PROTOCOL[level]["failure"],
                "tags": ex["tags"], "compound": ex["compound"],
                "rest": get_rest_time(ex, goal),
                "fatigue_cost": compute_fatigue_cost(ex)}, ex, goal))
            names_used.append(ex["name"])
            if session_equip_used is not None:
                session_equip_used.setdefault("shoulders", []).append(ex["equipment"])
            rem -= ex_sets; sh_used[0] += ex_sets; fat_used[0] += fc

    if total_sets < 4:
        fill_sub("lateral_delt", total_sets)
    elif total_sets > sets_per_ex * 2:
        press_sets   = max(2, math.ceil(total_sets * 0.40))
        lateral_sets = max(2, math.ceil(total_sets * 0.35))
        rear_sets    = max(2, total_sets - press_sets - lateral_sets)
        fill_sub("front_delt",   press_sets,   max_press=True)
        fill_sub("lateral_delt", lateral_sets)
        fill_sub("rear_delt",    rear_sets)
    elif sh_day_idx % 2 == 0:
        press_sets   = max(2, total_sets // 2)
        lateral_sets = max(2, total_sets - press_sets)
        fill_sub("front_delt",   press_sets,   max_press=True)
        fill_sub("lateral_delt", lateral_sets)
    else:
        lateral_sets = max(2, total_sets // 2)
        rear_sets    = max(2, total_sets - lateral_sets)
        fill_sub("lateral_delt", lateral_sets)
        fill_sub("rear_delt",    rear_sets)

    return result

# ─────────────────────────────────────────────
#  CHEST ROTATION
# ─────────────────────────────────────────────
def build_chest_exercises(sets_today, level, goal, blocked, weak, used, sets_per_ex,
                          chest_day_idx, workspace="full_gym", volume_pref="medium",
                          session_equip_used=None, session_fatigue=0,
                          session_names=None, fatigue_cap_remaining=999):
    """
    Micro-Budgeting for Chest + Resistance Profile + Fatigue tracking.
    """
    if sets_today <= 4:
        sub_priority = ["chest_upper"] if chest_day_idx % 2 == 0 else ["chest_mid"]
    else:
        sub_priority = (["chest_upper","chest_mid"] if chest_day_idx % 2 == 0
                        else ["chest_mid","chest_upper"])

    result, names_used = [], []
    sets_remaining = sets_today
    fatigue_used   = 0
    
    dynamic_sub_cap = {"beginner": 6, "intermediate": 8, "advanced": 10}.get(level, 8)
    if blocked: dynamic_sub_cap += 2

    def fill_sub(sub, budget):
        nonlocal fatigue_used
        if budget <= 0: return
        pool = filter_for_muscle(
            sub, level, blocked, weak, used, workspace,
            session_equip_used=session_equip_used,
            goal=goal,
            session_fatigue_so_far=session_fatigue + fatigue_used,
            session_names=(session_names or []) + [e["name"] for e in result],
        )
        pool = sorted(pool, key=lambda x: (0 if x["compound"] else 1))
        rem = min(budget, dynamic_sub_cap)  # Cap allocation per sub-muscle
        for ex in pool:
            if rem <= 0: break
            if ex["name"] in names_used: continue
            # DYNAMIC HARD CONSTRAINT CHECK
            current_session_names = (session_names or []) + [e["name"] for e in result]
            if ex["name"] in get_hard_blocked(current_session_names, level):
                continue
            ex_sets = get_valid_ex_sets(rem, sets_per_ex, 999, volume_pref)
            if ex_sets == 0: break
            fc = compute_fatigue_cost(ex) * ex_sets
            if fatigue_used + fc > fatigue_cap_remaining:
                for try_sets in range(ex_sets - 1, 1, -1):
                    if compute_fatigue_cost(ex) * try_sets + fatigue_used <= fatigue_cap_remaining:
                        ex_sets = try_sets; fc = compute_fatigue_cost(ex) * ex_sets; break
                else:
                    break
            result.append(enrich_exercise({"name": ex["name"], "primary": ex["primary"],
                "secondary": ex["secondary"], "equipment": ex["equipment"],
                "sets": ex_sets, "reps": get_reps(ex, goal),
                "failure": SETS_PROTOCOL[level]["failure"],
                "tags": ex["tags"], "compound": ex["compound"],
                "rest": get_rest_time(ex, goal),
                "fatigue_cost": compute_fatigue_cost(ex)}, ex, goal))
            names_used.append(ex["name"])
            if session_equip_used is not None:
                session_equip_used.setdefault("chest", []).append(ex["equipment"])
            rem -= ex_sets; fatigue_used += fc

    for sub in sub_priority:
        fill_sub(sub, sets_remaining)
        sets_remaining = max(0, sets_remaining - dynamic_sub_cap)

    return result, sets_today - sets_remaining

# Mapping of major muscle groups to their connected accessory groups
SESSION_SETS_CAP = {
    "beginner":     {"cut": 12, "maintain": 14, "gain": 16, "strength": 14},
    "intermediate": {"cut": 14, "maintain": 16, "gain": 18, "strength": 16},
    "advanced":     {"cut": 16, "maintain": 18, "gain": 20, "strength": 18},
}

# Volume modifier: adjusts session cap based on training volume preference
# Low: no change (1.0x), Medium: +10% (1.1x), High: +20% (1.2x)
VOLUME_MODIFIER = {"low": 1.0, "medium": 1.1, "high": 1.2}
SESSION_FLOOR = 12  # minimum session cap regardless of calculations

# ─────────────────────────────────────────────
#  SECOND PASS - Fill Low Muscles
# ─────────────────────────────────────────────
def second_pass_fill_low_muscles(plan, profile, weekly_target, weekly_done, used_globally, blocked, sets_per_ex, volume_pref):
    """
    Feature 4: The Second Pass
    After schedule is complete, check volume report for LOW muscles.
    Try to add missing sets to days that:
      1. Already work that muscle
      2. Have remaining session capacity
    
    This ensures no muscle gets "shortchanged" due to allocation order.
    """
    level = profile["experience"]
    goal = profile["goal"]
    weak = profile.get("weak_muscles", [])
    workspace = profile.get("workspace", "full_gym")
    
    # MRV cap calculation
    mrv_cap = 24 if level == "advanced" else 20
    if profile.get("gender", "male") == "female":
        mrv_cap += 2

    
    # Calculate what's missing
    missing = {}
    for muscle in ["chest", "back", "shoulders", "biceps", "triceps", "legs", "forearms"]:
        if muscle not in weekly_target:
            continue  # Skip muscles not in weekly_target (e.g., forearms when not weak)
        target = weekly_target[muscle]
        done = weekly_done.get(muscle, 0)
        deficit = target - done
        if deficit >= 2:  # Only bother if missing at least 2 sets
            missing[muscle] = deficit
    
    if not missing:
        return plan  # Nothing to fix
    
    # Try to fill gaps
    for muscle, deficit in missing.items():
        remaining = deficit
        
        # Find days that work this muscle and have capacity
        for day in plan["workout_days"]:
            if remaining <= 0:
                break
            
            # Check if this day works the target muscle
            day_muscles = set()
            for ex in day["exercises"]:
                for m in ex["primary"]:
                    group = MUSCLE_GROUP.get(m, m)
                    day_muscles.add(group)
            
            if muscle not in day_muscles:
                continue  # This day doesn't work the target muscle
            
            # Check if day has capacity
            session_max = day.get("session_max", 999)
            current_sets = day.get("total_sets", 0)
            capacity = session_max - current_sets
            
            if capacity < 2:
                continue  # No room
            
            # MRV CEILING CHECK: Use weekly_done which already tracks all sets
            # Don't double-count by adding current day's sets
            current_weekly = weekly_done.get(muscle, 0)
            
            # Check if adding would exceed MRV cap
            if current_weekly >= mrv_cap:
                continue  # Already at or above MRV cap, skip
            
            # Try to add an exercise for this muscle
            current_sets = day.get("total_sets", 0)
            capacity = session_max - current_sets
            
            if capacity < 2:
                continue  # No room
            
            # Try to add an exercise for this muscle
            # Find a suitable exercise
            sub_muscles = [m for m, g in MUSCLE_GROUP.items() if g == muscle]
            candidates = []
            for sub in sub_muscles:
                for ex in filter_for_muscle(sub, level, blocked, weak, used_globally.get(muscle, []), workspace):
                    if ex["name"] not in [c["name"] for c in candidates]:
                        candidates.append(ex)
            
            # Sort: compound first, then prioritize exercises NOT used globally
            candidates = sorted(candidates, key=lambda x: (
                0 if x["compound"] else 1,
                0 if x["name"] not in used_globally.get(muscle, []) else 1
            ))
            
            # Find an exercise not already in this day
            day_ex_names = [ex["name"] for ex in day["exercises"]]
            
            # Feature 3: Exercise Memory - Two-pass approach
            # Pass 1: Try to find exercise NOT used globally AND NOT in this day
            # Pass 2: If all exercises used globally, allow repetition but still avoid same day
            selected_ex = None
            
            # Pass 1: Prefer exercises not used globally
            for ex in candidates:
                if ex["name"] in day_ex_names:
                    continue  # Skip if already in this day
                if ex["name"] in used_globally.get(muscle, []):
                    continue  # Skip if used globally (prefer new exercises)
                selected_ex = ex
                break
            
            # Pass 2: If no new exercise found, allow repetition (but still avoid same day)
            if not selected_ex:
                for ex in candidates:
                    if ex["name"] in day_ex_names:
                        continue  # Still skip if already in this day
                    selected_ex = ex
                    break
            
            if selected_ex:
                # Calculate how many sets to add
                add_sets = min(remaining, capacity, 4)  # Max 4 sets per exercise
                add_sets = max(2, add_sets)  # At least 2 sets
                
                # MRV CEILING: clamp to not exceed cap
                max_allowed_by_mrv = mrv_cap - current_weekly
                if add_sets > max_allowed_by_mrv:
                    if max_allowed_by_mrv < 2:
                        continue  # Can't add without exceeding MRV
                    add_sets = max_allowed_by_mrv
                
                if add_sets <= capacity:
                    # Add the exercise
                    new_ex = {
                        "name": selected_ex["name"],
                        "primary": selected_ex["primary"],
                        "secondary": selected_ex["secondary"],
                        "equipment": selected_ex["equipment"],
                        "compound": selected_ex["compound"],
                        "sets": add_sets,
                        "reps": get_reps(selected_ex, goal),
                        "failure": SETS_PROTOCOL[level]["failure"],
                        "tags": selected_ex["tags"],
                        "rest": get_rest_time(selected_ex, goal),
                    }
                    
                    day["exercises"].append(new_ex)
                    day["total_sets"] += add_sets
                    used_globally[muscle] = used_globally.get(muscle, []) + [selected_ex["name"]]
                    
                    remaining -= add_sets
    
    return plan

# ─────────────────────────────────────────────
#  SESSION PADDING - Guarantee minimum workout length
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
#  SESSION PADDING - Guarantee minimum workout length
# ─────────────────────────────────────────────
def pad_short_sessions(plan, profile, blocked, used_globally):
    level = profile["experience"]
    goal = profile["goal"]
    weak = profile.get("weak_muscles", [])
    workspace = profile.get("workspace", "full_gym")
    
    # MRV cap for padding
    mrv_cap = 24 if level == "advanced" else 20
    if profile.get("gender", "male") == "female":
        mrv_cap += 2

    
    # Calculate current weekly sets from the plan before padding
    # FIX LEAK B: Track abs and calves independently from legs
    running_weekly = {}
    for day in plan["workout_days"]:
        for ex in day.get("exercises", []):
            for m in ex["primary"]:
                # FIX LEAK B (Real Fix): Track small muscles independently instead of mapping to macro-groups
                if m in ("abs", "calves", "forearms", "traps", "lower_back"):
                    group = m
                else:
                    group = MUSCLE_GROUP.get(m, m)
                running_weekly[group] = running_weekly.get(group, 0) + ex["sets"]
    
    allow_forearms = ("arms" in weak or "forearms" in weak or level == "advanced")
    
    # ضفنا العضلات الضعيفة (أو اللي ناقصة حجم) في أولويات الـ Padding
    padding_priority = [m for m in weak if m not in ("abs", "calves", "forearms")]
    padding_priority.extend(["abs", "calves"])
    
    if allow_forearms:
        padding_priority.append("forearms")
    
    for day in plan["workout_days"]:
        day_exercises = day.get("exercises", [])
        current_sets = day.get("total_sets", 0)
        fatigue_cap = day.get("fatigue_cap", 999)
        current_fatigue = day.get("total_fatigue", 0)
        
        while (len(day_exercises) < 4 or current_sets < 12) and current_fatigue < fatigue_cap:
            day_ex_names = [ex["name"] for ex in day_exercises]
            padded = False
            
            for muscle in padding_priority:
                if padded: break
                
                if muscle in ("abs", "calves", "forearms", "traps", "lower_back"):
                    mapped_group = muscle
                else:
                    mapped_group = MUSCLE_GROUP.get(muscle, muscle)
                
                current_group_sets = running_weekly.get(mapped_group, 0)
                if current_group_sets >= mrv_cap:
                    continue
                
                # الحصول على العضلات الفرعية إذا كانت العضلة الأساسية Macro-group مثل chest
                subs = [k for k, v in MUSCLE_GROUP.items() if v == mapped_group] if muscle not in MUSCLE_GROUP else [muscle]
                
                pool = []
                for sub in subs:
                    # STRICT FILTER: Force isolation exercises only for padding
                    sub_pool = [ex for ex in filter_for_muscle(
                        sub, level, blocked, [], used_globally.get(mapped_group, []), workspace,
                        session_equip_used=None, goal=goal,
                        session_fatigue_so_far=current_fatigue,
                        session_names=day_ex_names
                    ) if not ex.get("compound", False)] # MUST BE ISOLATION
                    pool.extend(sub_pool)
                
                for ex in pool:
                    if ex["name"] in day_ex_names: continue
                    
                    ex_sets = 3
                    fc = compute_fatigue_cost(ex)
                    
                    if current_fatigue + fc * ex_sets > fatigue_cap:
                        continue
                    
                    # MRV cap check before adding - abs/calves have independent MRV
                    if current_group_sets + ex_sets > mrv_cap:
                        max_allowed = mrv_cap - current_group_sets
                        if max_allowed < 2:
                            continue  # Can't add without exceeding MRV
                        ex_sets = max_allowed
                    
                    day_exercises.append(enrich_exercise({
                        "name": ex["name"],
                        "primary": ex["primary"],
                        "secondary": ex["secondary"],
                        "equipment": ex["equipment"],
                        "compound": ex["compound"],
                        "sets": ex_sets,
                        "reps": get_reps(ex, goal),
                        "failure": SETS_PROTOCOL[level]["failure"],
                        "tags": ex["tags"],
                        "rest": get_rest_time(ex, goal),
                        "fatigue_cost": fc,
                    }, ex, goal))
                    
                    day_ex_names.append(ex["name"])
                    current_sets += ex_sets
                    current_fatigue += fc * ex_sets
                    used_globally[mapped_group] = used_globally.get(mapped_group, []) + [ex["name"]]
                    running_weekly[mapped_group] = running_weekly.get(mapped_group, 0) + ex_sets
                    padded = True
                    break
            
            if not padded:
                break
        
        day["exercises"] = day_exercises
        day["total_sets"] = current_sets
        day["total_fatigue"] = current_fatigue
    
    return plan

# Mapping of major muscle groups to their connected accessory groups
CONNECTED_ACCESSORIES = {
    "legs": {
        "connected": ["lower_back", "adductors", "abductors"],
        "swap_candidates": {
            "hamstrings": ["Romanian Deadlift (RDL)", "Single Leg RDL"],
            "glutes": ["Hip Thrust (Barbell)", "Cable Pull-Through"],
            "calves": ["Seated Calf Raise", "Standing Calf Raise"],
        }
    },
    "back": {
        "connected": ["lower_back"],
        "swap_candidates": {
            "mid_back": ["Barbell Row (Pendlay)", "Chest-Supported Row (Machine)"],
            "lats": ["Lat Pulldown (Wide Grip)", "Pull-Up / Weighted Pull-Up"],
        }
    },
}

# ─────────────────────────────────────────────
#  THIRD PASS - Volume Optimization
# ─────────────────────────────────────────────
def third_pass_optimize_volume(plan, volume_report, blocked, level):
    """
    v4.0 NEW: Third Pass Optimization
    
    Logic:
      - Iterate through the volume_report
      - If a major group like "legs" has status == "high" AND a connected 
        accessory group is entirely missing or "low":
      - Find an isolation exercise in that day's plan
      - REMOVE it to drop the high volume
      - REPLACE it with a hybrid/compound exercise from the missing group
    
    Example:
      - legs is "high" but lower_back is missing → find Lying Leg Curl → replace with RDL
    """
    for day_idx, day in enumerate(plan["workout_days"]):
        day_exercises = day.get("exercises", [])
        if not day_exercises:
            continue
        
        # Get muscles worked in this day
        day_muscles = set()
        for ex in day_exercises:
            for m in ex.get("primary", {}):
                group = MUSCLE_GROUP.get(m, m)
                day_muscles.add(group)
        
        # Check each major group
        for major, data in CONNECTED_ACCESSORIES.items():
            if major not in day_muscles:
                continue
            
            # Check if major is HIGH
            major_status = volume_report.get(major, {}).get("status", "ok")
            if major_status != "high":
                continue
            
            # Check connected accessories
            connected = data["connected"]
            missing_accessories = []
            
            for acc in connected:
                acc_status = volume_report.get(acc, {}).get("status", "ok")
                if acc_status in ("low", "missing", None) or acc not in day_muscles:
                    missing_accessories.append(acc)
            
            if not missing_accessories:
                continue
            
            # Find isolation exercise to replace
            candidate_to_remove = None
            for ex in day_exercises:
                # Look for pure isolation exercises in the major group
                if not ex.get("compound", False):
                    # Check if it's a candidate for removal
                    if any(m in [major, "hamstrings", "calves", "abs"] for m in ex.get("primary", {})):
                        candidate_to_remove = ex
                        break
            
            if not candidate_to_remove:
                continue
            
            # Find replacement - look for hybrid exercise from missing accessory
            for acc in missing_accessories:
                swap_candidates = data["swap_candidates"]
                for source_muscle, possible_names in swap_candidates.items():
                    for name in possible_names:
                        # Check if this exercise exists and is not already in day
                        for db_ex in EXERCISE_DB:
                            if db_ex["name"] == name:
                                day_ex_names = [e["name"] for e in day_exercises]
                                if name not in day_ex_names:
                                    # DYNAMIC HARD CONSTRAINT CHECK & INJURY CHECK
                                    if any(b.lower() in name.lower() for b in blocked):
                                        continue
                                    if name in get_hard_blocked(day_ex_names, level):
                                        continue
                                    # Replace!
                                    new_ex = {
                                        "name": db_ex["name"],
                                        "primary": db_ex["primary"],
                                        "secondary": db_ex["secondary"],
                                        "equipment": db_ex["equipment"],
                                        "compound": db_ex["compound"],
                                        "sets": candidate_to_remove.get("sets", 3),
                                        "reps": candidate_to_remove.get("reps", "8-12"),
                                        "failure": candidate_to_remove.get("failure", "RIR 2"),
                                        "tags": db_ex["tags"],
                                        "rest": get_rest_time(db_ex, "maintain"),
                                        "fatigue_cost": compute_fatigue_cost(db_ex),
                                    }
                                    # Find index to replace at
                                    ex_idx = day_exercises.index(candidate_to_remove)
                                    day_exercises[ex_idx] = new_ex
                                    break
                        break
                    break
    
    return plan

# ─────────────────────────────────────────────
#  PLAN BUILDER
# ─────────────────────────────────────────────
def build_workout_plan(profile):
    level       = profile["experience"]
    days        = profile["training_days"]
    goal        = profile["goal"]
    activity    = profile.get("activity_level", "office")
    injuries    = profile.get("injuries", [])
    weak        = profile.get("weak_muscles", [])
    leg_pref    = profile.get("leg_days_preference", 2)
    workspace   = profile.get("workspace", "full_gym")
    volume_pref = profile.get("volume", "medium")
    protocol    = SETS_PROTOCOL[level]
    sets_per_ex = get_sets_per_ex(level, goal)   # goal-aware: strength→2-3, gain→3-4
    # 🟢 ضفنا التمارين المكروهة عشان يتعملها Block زي الإصابات بالظبط 🟢
    disliked_ex = profile.get("disliked_exercises", [])
    blocked     = get_blocked(injuries) + disliked_ex
    gender      = profile.get("gender", "male")

    # FIX 10: Sex/Gender Modifier - adjust glute/quad ratio for females (use local copy)
    legs_ratio = dict(LEGS_INTERNAL_RATIO)  # Don't mutate global!
    if gender == "female":
        legs_ratio["glutes"] = 0.28
        legs_ratio["quads"] = 0.24
    
    # FIX 7: Home Workspace + Advanced Users warning
    workspace_warning = ""
    if workspace == "home" and level == "advanced" and days >= 4:
        workspace_warning = "⚠️ Home workouts limit exercise variety for advanced users. Consider 'dumbbells' workspace for better options."
    
    # FIX 8: Session Max / All Weak Muscles warning
    weak_warning = ""
    if len(weak) >= 4 and days <= 2:
        weak_warning = "⚠️ You've listed 4+ weak muscle groups but only 2 training days. Consider increasing to 3-4 days to deliver the required volume for all weak groups."
    
    # FIX B9: Home + Strength incompatibility check
    strength_warning = ""
    if workspace == "home" and goal == "strength":
        if level == "beginner":
            strength_warning = "⚠️ Strength goal requires barbell access. Switched to maintenance programming for skill development."
            goal = "maintain"
        else:
            strength_warning = "⚠️ Strength goal requires barbell access. Switched to 'gain' goal for home-friendly programming."
            goal = "gain"  # Auto-downgrade to maintain workout viability

    split_key, split_reason = select_split(days, level, weak, leg_pref, goal, injuries, gender)
    split_data = SPLITS[split_key]
    
    import copy
    schedule = copy.deepcopy(split_data["schedule"])
    
    # Strip legs entirely if leg_pref == 0
    if leg_pref == 0:
        new_schedule = []
        for day in schedule:
            new_day = [m for m in day if m != "legs"]
            if not new_day:
                new_day = ["abs", "forearms"] # Fallback if the day is completely empty
            new_schedule.append(new_day)
        schedule = new_schedule
        split_reason += " (Legs removed as per preference)"
    
    BRO_SPLIT_KEYS = {"bro_split_4", "bro_split_5", "bro_modified_4"}

    all_groups = ["chest","back","shoulders","biceps","triceps","legs"]
    # DYNAMIC MUSCLE GROUPS: include forearms if weak
    if "arms" in weak or "forearms" in weak:
        if level in ("intermediate", "advanced"):
            all_groups.append("forearms")
    single_leg = (sum(1 for day in SPLITS[split_key]["schedule"] if "legs" in day) == 1)

    # FIX B3: Use actual schedule length, not profile days (handles beginner 6->5 cap)
    actual_days = len(schedule)
    weekly_target = {
        g: get_volume_target(g, level, goal, activity,
                             is_weak=(g in weak),
                             single_leg_day=(single_leg and g == "legs"),
                             training_days=actual_days,
                             volume_pref=volume_pref,
                             workspace=workspace,
                             gender=profile.get("gender", "male"))
        for g in all_groups
    }
    
    # MRV CEILING TRACKING - strict real-time enforcement
    mrv_cap = 24 if level == "advanced" else 20
    if profile.get("gender", "male") == "female":
        mrv_cap += 2

    running_weekly_sets = {g: 0 for g in all_groups}
    
    group_day_count = {}
    for day_groups in schedule:
        seen = set()
        for g in day_groups:
            if g not in seen:
                seen.add(g)
                group_day_count[g] = group_day_count.get(g, 0) + 1
        # FOREARM ALLOCATION: add forearms to days with back or biceps (pulling days)
        if "forearms" in all_groups and ("back" in day_groups or "biceps" in day_groups):
            group_day_count["forearms"] = group_day_count.get("forearms", 0) + 1

    day_budget = {}
    for g in all_groups:
        weekly = weekly_target[g]
        days_per_week = group_day_count.get(g, 1)
        # FIX B6: BRO SPLIT VOLUME BOOST: only apply 1.4x boost for actual bro splits
        if days_per_week == 1 and split_key in BRO_SPLIT_KEYS:
            weekly = math.ceil(weekly * 1.4)
        day_budget[g] = math.ceil(weekly / days_per_week)

    weekly_done   = {g: 0 for g in all_groups}
    used_globally = {g: [] for g in all_groups}
    chest_day_idx    = 0
    shoulder_day_idx = 0
    back_day_idx     = 0
    workout_days     = []

    MAX_EXERCISES_PER_DAY = 8

    GROUP_PRIORITY_WEIGHT = {
        "chest":     3,
        "back":      3,
        "shoulders": 3,
        "legs":      3,
        "biceps":    1,
        "triceps":   1,
        "forearms":  1,
    }

    def get_session_max(day_groups):
        hard_cap = SESSION_SETS_CAP[level][goal]
        modifier = VOLUME_MODIFIER.get(volume_pref, 1.0)
        calculated_cap = round(hard_cap * modifier)
        return max(SESSION_FLOOR, calculated_cap)

    def get_fatigue_cap(day_groups_today):
        """Return daily fatigue budget based on level + goal."""
        base = SESSION_FATIGUE_CAP[level][goal]
        modifier = VOLUME_MODIFIER.get(volume_pref, 1.0)
        if profile.get("gender", "male") == "female":
            modifier *= 1.10
        if weak and any(m in weak for m in day_groups_today):
            modifier *= 1.15
        return round(base * modifier)

    for day_groups in schedule:
        legs_attempted = False  # CONTRADICTION B FIX: Initialize for each day
        day_exercises  = []
        day_names_used = []
        session_sets        = 0
        session_fatigue     = 0                    # NEW: cumulative fatigue score
        session_fatigue_cap = get_fatigue_cap(day_groups)    # NEW: daily fatigue budget
        session_max         = get_session_max(day_groups)
        session_equip_used  = {}                   # NEW: {muscle_group: [equip, ...]}

        MAX_EXERCISES_TODAY = max(8, len(set(day_groups)) * 2)

        is_legs_only = (day_groups == ["legs"])

        def session_full():
            return (session_sets >= session_max
                    or session_fatigue >= session_fatigue_cap
                    or len(day_exercises) >= MAX_EXERCISES_TODAY)

        # FIX 4: Legs Unconditional +6 Sets - Adaptive padding based on volume preference
        # MRV cap enforcement for legs-only days
        if is_legs_only:
            target_legs = day_budget.get("legs", 10)
            current_legs_weekly = running_weekly_sets.get("legs", 0)
            remaining_mrv = mrv_cap - current_legs_weekly
            
            padding = 4 if volume_pref == "high" else 2
            target_with_padding = target_legs + padding
            legs_today = min(session_max, max(SESSION_FLOOR, target_with_padding))
            
            # CRITICAL: Must not exceed remaining MRV, and don't force SESSION_FLOOR if MRV is hit
            if remaining_mrv <= 0:
                legs_today = 0  # Already at or above cap
            elif legs_today > remaining_mrv:
                legs_today = remaining_mrv
                # If this results in too few sets, skip legs entirely
                if legs_today < 4:
                    legs_today = 0
                    
            if legs_today > 0:
                sub_order      = ["quads","hamstrings","glutes","calves","abs"]
                sub_budgets    = {}
                compound_subs  = ["quads","hamstrings","glutes"]
                isolation_subs = ["calves","abs"]

                iso_guarantee = len(isolation_subs) * 2
                comp_max_pool = max(0, legs_today - iso_guarantee)
                compound_min  = min(2, max(1, legs_today // len(sub_order)))
                for sub in compound_subs:
                    sub_budgets[sub] = max(round(legs_ratio[sub] * legs_today), compound_min)
                total_comp = sum(sub_budgets[s] for s in compound_subs)
                if total_comp > comp_max_pool and comp_max_pool > 0:
                    for sub in compound_subs:
                        sub_budgets[sub] = max(compound_min, round(sub_budgets[sub] * (comp_max_pool / total_comp)))
                allocated = sum(sub_budgets[s] for s in compound_subs)
                remaining_for_iso = legs_today - allocated
                
                for i, sub in enumerate(isolation_subs):
                    if i < len(isolation_subs) - 1:
                        sub_budgets[sub] = max(round(legs_ratio[sub] * remaining_for_iso), 2)
                    else:
                        sub_budgets[sub] = max(remaining_for_iso - sum(
                            sub_budgets[s] for s in isolation_subs[:i]), 2)

                total_legs_assigned = 0
                for sub in sub_order:
                    if session_full(): break
                    budget_left = sub_budgets.get(sub, 1)
                    pool = [e for e in filter_for_muscle(
                                sub, level, blocked, weak, used_globally["legs"], workspace,
                                session_equip_used=session_equip_used,
                                goal=goal,
                                session_fatigue_so_far=session_fatigue,
                                session_names=day_names_used)
                            if e["name"] not in day_names_used]
                    pool = sorted(pool, key=lambda x: (0 if x["compound"] else 1))
                    for ex in pool:
                        if budget_left <= 0 or session_full(): break
                        
                        # Pre-emptive MRV check - don't even try if already at cap
                        if running_weekly_sets.get("legs", 0) >= mrv_cap:
                            break  # Already at MRV cap for legs
                        
                        # DYNAMIC HARD CONSTRAINT CHECK
                        if ex["name"] in get_hard_blocked(day_names_used, level):
                            continue
                        fc = compute_fatigue_cost(ex)
                        ex_sets = get_valid_ex_sets(budget_left, sets_per_ex, session_max - session_sets, volume_pref)
                        if ex_sets == 0: break
                        # MRV CEILING CHECK: clamp sets to stay under cap
                        current_legs_sets = running_weekly_sets.get("legs", 0)
                        if current_legs_sets + ex_sets > mrv_cap:
                            max_allowed = mrv_cap - current_legs_sets
                            if max_allowed < 2:
                                break  # Cannot add more without exceeding MRV
                            ex_sets = max_allowed
                        # Fatigue cap: try fewer sets if needed
                        while ex_sets > 0 and session_fatigue + fc * ex_sets > session_fatigue_cap:
                            ex_sets -= 1
                        if ex_sets < 2: break
                        # STRICT MRV CEILING: clamp before appending to prevent breach
                        current_legs = running_weekly_sets.get("legs", 0)
                        max_allowed = mrv_cap - current_legs
                        if max_allowed <= 0:
                            break  # Cannot add more without exceeding MRV
                        actual_sets = min(ex_sets, max_allowed)
                        if actual_sets < 2:
                            break
                        running_weekly_sets["legs"] = current_legs + actual_sets
                        day_exercises.append(enrich_exercise({"name":ex["name"],"primary":ex["primary"],
                            "secondary":ex["secondary"],"equipment":ex["equipment"],
                            "sets":actual_sets,"reps":get_reps(ex,goal),
                            "failure":protocol["failure"],"tags":ex["tags"],
                            "compound":ex["compound"],"rest":get_rest_time(ex, goal),
                            "fatigue_cost": fc}, ex, goal))
                        day_names_used.append(ex["name"])
                        used_globally["legs"].append(ex["name"])
                        session_equip_used.setdefault("legs", []).append(ex["equipment"])
                        budget_left -= actual_sets; total_legs_assigned += actual_sets
                        session_sets += actual_sets; session_fatigue += fc * actual_sets

                weekly_done["legs"] += total_legs_assigned
            else:
                # Skip legs entirely - will be handled in non-legs-only path below
                is_legs_only = False
                weekly_done["legs"] = weekly_done.get("legs", 0)

            legs_attempted = is_legs_only  # Track if legs-only path was attempted

            muscles_in_day = []
            for ex in day_exercises:
                for m in ex["primary"]:
                    disp = MUSCLE_DISPLAY.get(m, m)
                    if disp not in muscles_in_day: muscles_in_day.append(disp)
            day_label = " + ".join(muscles_in_day) if muscles_in_day else "Legs"

        else:
            groups_today  = list(day_groups)
            group_budgets = {}
            for group in groups_today:
                want = min(day_budget[group], weekly_target[group] - weekly_done.get(group, 0))
                # Ensure every scheduled group gets at least 2 target sets
                group_budgets[group] = max(2, want)

            active_groups = [g for g in groups_today if group_budgets.get(g, 0) > 0]

            # CONTRADICTION B FIX: Allow legs to get at least SESSION_FLOOR when legs-only path hit MRV cap
            if legs_attempted and "legs" in groups_today:
                legs_budget = max(SESSION_FLOOR, group_budgets.get("legs", 0))
                max_allowed = min(legs_budget, session_max)
                if max_allowed >= 2:
                    group_budgets["legs"] = max_allowed

            compound_order = ["chest","back","shoulders","legs","biceps","triceps","forearms"]
            
            # Distribute based on muscle need first, session_max is emergency brake only
            # Start with group_budgets (muscle need), then cap if exceeds session_max
            total_needed = sum(group_budgets.values())
            
            if total_needed <= session_max:
                # PHASE 1: GUARANTEED FLOOR for isolation muscles (biceps, triceps)
                isolation_muscles = ["biceps", "triceps", "forearms"]
                isolation_min = 3  # Minimum sets guaranteed to isolation muscles
                final_budgets = {}
                for g in active_groups:
                    # MRV cap enforcement in budget calculation
                    current_sets = running_weekly_sets.get(g, 0)
                    remaining_mrv = mrv_cap - current_sets
                    if remaining_mrv <= 0:
                        final_budgets[g] = 0  # Already at MRV cap
                        continue
                    
                    original_budget = group_budgets[g]
                    if g in isolation_muscles:
                        budget = max(isolation_min, original_budget)
                    else:
                        budget = original_budget
                    
                    # Also cap by remaining MRV
                    if budget > remaining_mrv:
                        budget = remaining_mrv
                    if budget >= 2:
                        final_budgets[g] = budget
                used_so_far = sum(final_budgets.values())
                
                # PHASE 2: Proportional distribution of remaining capacity
                if used_so_far > session_max:
                    # Scale back proportionally
                    remaining = session_max - sum(min(isolation_min, final_budgets.get(g, 0)) for g in isolation_muscles if g in final_budgets)
                    compound_budget = {g: final_budgets[g] for g in final_budgets if g not in isolation_muscles}
                    compound_sum = sum(compound_budget.values())
                    if compound_sum > 0 and remaining > 0:
                        for g in compound_budget:
                            if g in active_groups:
                                final_budgets[g] = max(2, int(compound_budget[g] * (remaining / compound_sum)))
            else:
                # PROPORTIONAL SCALING: scale all groups down proportionally instead of dropping isolations
                scale_factor = session_max / total_needed
                final_budgets = {}
                for g in active_groups:
                    original = group_budgets[g]
                    scaled = max(2, int(original * scale_factor))
                    final_budgets[g] = scaled
            
            group_budgets = {g: final_budgets[g] for g in active_groups if final_budgets[g] > 0}

            if "shoulders" in groups_today:
                shoulder_day_idx += 1
            if "back" in groups_today:
                back_day_idx += 1

            sub_cycle = {"chest": chest_day_idx, "shoulders": 0, "back": 0, "legs": 0}
            sub_priorities = {
                "chest":     [["chest_upper","chest_mid"],["chest_mid","chest_upper"]],
                "shoulders": ["front_delt","lateral_delt","rear_delt"],
                "back":      ["lats","mid_back"],
                "legs":      ["quads","hamstrings","glutes","calves","abs"],
            }
            if "chest" in groups_today:
                chest_day_idx += 1

            def pop_exercise(group):
                if group in sub_priorities:
                    if group == "chest":
                        cycle_list = sub_priorities["chest"][sub_cycle["chest"] % 2]
                        sub = cycle_list[0]; cycle_list.append(cycle_list.pop(0))
                        pool = filter_for_muscle(
                            sub, level, blocked, weak, used_globally.get(group,[]), workspace,
                            session_equip_used=session_equip_used, goal=goal,
                            session_fatigue_so_far=session_fatigue, session_names=day_names_used)
                        for ex in pool:
                            if ex["name"] not in day_names_used: return ex
                    else:
                        for _ in range(len(sub_priorities[group])):
                            sub = sub_priorities[group][sub_cycle[group] % len(sub_priorities[group])]
                            sub_cycle[group] += 1
                            pool = filter_for_muscle(
                                sub, level, blocked, weak, used_globally.get(group,[]), workspace,
                                session_equip_used=session_equip_used, goal=goal,
                                session_fatigue_so_far=session_fatigue, session_names=day_names_used)
                            if group == "legs":
                                pool = sorted(pool, key=lambda x: (0 if x["compound"] else 1))
                            for ex in pool:
                                if ex["name"] not in day_names_used: return ex
                else:
                    sub_muscles = [m for m, g in MUSCLE_GROUP.items() if g == group]
                    candidates  = []
                    for sub in sub_muscles:
                        for ex in filter_for_muscle(
                                sub, level, blocked, weak, used_globally.get(group,[]), workspace,
                                session_equip_used=session_equip_used, goal=goal,
                                session_fatigue_so_far=session_fatigue, session_names=day_names_used):
                            if ex["name"] not in [c["name"] for c in candidates]:
                                candidates.append(ex)
                    candidates = sorted(candidates, key=lambda x: (
                        0 if x["compound"] else 1,
                        0 if x["name"] not in used_globally.get(group,[]) else 1))
                    for ex in candidates:
                        if ex["name"] not in day_names_used: return ex
                return None

            active_groups = sorted(list(group_budgets.keys()),
                                   key=lambda g: compound_order.index(g) if g in compound_order else 99)

            while active_groups:
                for group in list(active_groups):
                    if group_budgets.get(group, 0) <= 0:
                        if group in active_groups: active_groups.remove(group)
                        continue

                    # ── SHOULDERS ────────────────────────────────────────────
                    if group == "shoulders":
                        sh_exs = build_shoulders_exercises(
                            total_sets       = group_budgets["shoulders"],
                            level=level, goal=goal, blocked=blocked, weak=weak,
                            used=used_globally.get("shoulders", []),
                            sets_per_ex=sets_per_ex,
                            session_remaining=session_max - session_sets,
                            sh_day_idx=shoulder_day_idx,
                            workspace=workspace,
                            volume_pref=volume_pref,
                            session_equip_used=session_equip_used,
                            session_fatigue=session_fatigue,
                            session_names=day_names_used,
                            fatigue_cap_remaining=session_fatigue_cap - session_fatigue,
                        )
                        for ex in sh_exs:
                            # STRICT MRV CEILING: clamp before appending
                            current_sh = running_weekly_sets.get("shoulders", 0)
                            max_allowed = mrv_cap - current_sh
                            if max_allowed <= 0:
                                break
                            actual_sets = min(ex["sets"], max_allowed)
                            if actual_sets < 2:
                                continue
                            ex["sets"] = actual_sets
                            running_weekly_sets["shoulders"] = current_sh + actual_sets
                            day_exercises.append(ex)
                            day_names_used.append(ex["name"])
                            used_globally["shoulders"].append(ex["name"])
                            session_sets    += ex["sets"]
                            session_fatigue += ex.get("fatigue_cost", compute_fatigue_cost(ex)) * ex["sets"]
                            weekly_done["shoulders"] = weekly_done.get("shoulders", 0) + ex["sets"]
                            running_weekly_sets["shoulders"] = running_weekly_sets.get("shoulders", 0) + ex["sets"]
                        group_budgets["shoulders"] = 0
                        active_groups.remove("shoulders")
                        continue

                    # ── BACK ─────────────────────────────────────────────────
                    if group == "back":
                        back_exs = build_back_exercises(
                            back_sets_today = group_budgets["back"],
                            level=level, goal=goal, blocked=blocked, weak=weak,
                            used=used_globally.get("back", []),
                            sets_per_ex=sets_per_ex,
                            session_remaining=session_max - session_sets,
                            workspace=workspace,
                            back_session_count=back_day_idx,
                            volume_pref=volume_pref,
                            session_equip_used=session_equip_used,
                            session_fatigue=session_fatigue,
                            session_names=day_names_used,
                            fatigue_cap_remaining=session_fatigue_cap - session_fatigue,
                        )
                        for ex in back_exs:
                            # STRICT MRV CEILING: clamp before appending
                            current_bk = running_weekly_sets.get("back", 0)
                            max_allowed = mrv_cap - current_bk
                            if max_allowed <= 0:
                                break
                            actual_sets = min(ex["sets"], max_allowed)
                            if actual_sets < 2:
                                continue
                            ex["sets"] = actual_sets
                            running_weekly_sets["back"] = current_bk + actual_sets
                            day_exercises.append(ex)
                            day_names_used.append(ex["name"])
                            used_globally["back"].append(ex["name"])
                            session_sets    += ex["sets"]
                            session_fatigue += ex.get("fatigue_cost", compute_fatigue_cost(ex)) * ex["sets"]
                            weekly_done["back"] = weekly_done.get("back", 0) + ex["sets"]
                            running_weekly_sets["back"] = running_weekly_sets.get("back", 0) + ex["sets"]
                        group_budgets["back"] = 0
                        active_groups.remove("back")
                        continue

                    # ── CHEST (via build_chest_exercises) ────────────────────
                    if group == "chest":
                        chest_exs, sets_used = build_chest_exercises(
                            sets_today=group_budgets["chest"],
                            level=level, goal=goal, blocked=blocked, weak=weak,
                            used=used_globally.get("chest", []),
                            sets_per_ex=sets_per_ex,
                            chest_day_idx=chest_day_idx - 1,   # already incremented above
                            workspace=workspace,
                            volume_pref=volume_pref,
                            session_equip_used=session_equip_used,
                            session_fatigue=session_fatigue,
                            session_names=day_names_used,
                            fatigue_cap_remaining=session_fatigue_cap - session_fatigue,
                        )
                        for ex in chest_exs:
                            # STRICT MRV CEILING: clamp before appending
                            current_ch = running_weekly_sets.get("chest", 0)
                            max_allowed = mrv_cap - current_ch
                            if max_allowed <= 0:
                                break
                            actual_sets = min(ex["sets"], max_allowed)
                            if actual_sets < 2:
                                continue
                            ex["sets"] = actual_sets
                            running_weekly_sets["chest"] = current_ch + actual_sets
                            day_exercises.append(ex)
                            day_names_used.append(ex["name"])
                            used_globally["chest"].append(ex["name"])
                            session_sets    += ex["sets"]
                            session_fatigue += ex.get("fatigue_cost", compute_fatigue_cost(ex)) * ex["sets"]
                            weekly_done["chest"] = weekly_done.get("chest", 0) + ex["sets"]
                            running_weekly_sets["chest"] = running_weekly_sets.get("chest", 0) + ex["sets"]
                        group_budgets["chest"] = 0
                        active_groups.remove("chest")
                        continue

                    # ── GENERIC (biceps / triceps / remaining) ────────────────
                    fc_per_set = None   # computed below after exercise selected
                    ex_sets = get_valid_ex_sets(group_budgets[group], sets_per_ex, session_max - session_sets, volume_pref)
                    if ex_sets == 0:
                        if group in active_groups: active_groups.remove(group)
                        continue
                    
                    # Pre-emptive MRV check - skip group if already at cap
                    if running_weekly_sets.get(group, 0) >= mrv_cap:
                        if group in active_groups: active_groups.remove(group)
                        continue

                    # MRV CEILING CHECK: clamp sets to stay under cap
                    current_group_sets = running_weekly_sets.get(group, 0)
                    if current_group_sets + ex_sets > mrv_cap:
                        max_allowed = mrv_cap - current_group_sets
                        if max_allowed < 2:
                            if group in active_groups: active_groups.remove(group)
                            continue
                        ex_sets = max_allowed

                    selected_ex = pop_exercise(group)

                    if selected_ex:
                        fc_per_set = compute_fatigue_cost(selected_ex)
                        # Respect fatigue cap: trim sets if needed
                        while ex_sets > 0 and session_fatigue + fc_per_set * ex_sets > session_fatigue_cap:
                            ex_sets -= 1
                        if ex_sets < 2:
                            if group in active_groups: active_groups.remove(group)
                            continue
                        day_exercises.append(enrich_exercise({"name":selected_ex["name"],
                            "primary":selected_ex["primary"],
                            "secondary":selected_ex["secondary"],
                            "equipment":selected_ex["equipment"],
                            "sets":ex_sets,"reps":get_reps(selected_ex,goal),
                            "failure":protocol["failure"],"tags":selected_ex["tags"],
                            "compound":selected_ex["compound"],"rest":get_rest_time(selected_ex, goal),
                            "fatigue_cost": fc_per_set}, selected_ex, goal))
                        day_names_used.append(selected_ex["name"])
                        used_globally[group] = used_globally.get(group,[]) + [selected_ex["name"]]
                        session_equip_used.setdefault(group, []).append(selected_ex["equipment"])
                        session_sets    += ex_sets
                        session_fatigue += fc_per_set * ex_sets
                        group_budgets[group] -= ex_sets
                        weekly_done[group] = weekly_done.get(group, 0) + ex_sets
                        running_weekly_sets[group] = running_weekly_sets.get(group, 0) + ex_sets
                    else:
                        if group in active_groups: active_groups.remove(group)

                active_groups = [g for g in active_groups if group_budgets.get(g,0) > 0]

            label_parts = [MUSCLE_DISPLAY.get(g, g.capitalize()) for g in groups_today]
            day_label   = " + ".join(label_parts) if label_parts else "Full Body"

        workout_days.append({
            "day": day_label, "exercises": day_exercises,
            "total_sets": session_sets, "session_max": session_max,
            "total_fatigue": session_fatigue, "fatigue_cap": session_fatigue_cap,
        })

    plan = {"split": split_data["name"], "split_reason": split_reason, "days_per_week": days,
            "level": level, "goal": goal,
            "rest_protocol": REST_PROTOCOL,
            "workout_days": workout_days,
            "workspace_warning": workspace_warning,
            "weak_warning": weak_warning,
            "strength_warning": strength_warning,
            "gender": gender}
    
    # FIX 3: Add Deload Recommendation
    deload_interval = {"beginner": 8, "intermediate": 5, "advanced": 4}.get(level, 5)
    plan["deload_recommendation"] = f"At week {deload_interval}, reduce all sets by 40%, keep same exercises and intensity."
    
    # FIX 11: Advanced Bro Split Volume Note
    if level == "advanced" and "bro_split" in split_key:
        plan["bro_split_note"] = "Advanced bro split: each muscle gets 1 dedicated session/week. Volume is set 40% higher per session to compensate. This is evidence-consistent."
    
    # Feature 4: Second Pass - Fill Low Muscles
    plan = second_pass_fill_low_muscles(plan, profile, weekly_target, weekly_done, used_globally, blocked, sets_per_ex, volume_pref)
    
    # Feature 5: Session Padding - Guarantee minimum workout length
    plan = pad_short_sessions(plan, profile, blocked, used_globally)
    
    # v4.0: Third Pass - Volume Optimization
    # Get volume report for third pass
    primary_vol, secondary_vol = count_weekly_volume(plan)
    volume_report = check_volume_vs_targets(primary_vol, secondary_vol, profile)
    plan = third_pass_optimize_volume(plan, volume_report, blocked, profile["experience"])
    
    if profile.get("gender", "male") == "female":
        for d in plan.get("workout_days", []):
            for ex in d.get("exercises", []):
                if ex["rest"] == "2–3 min" or ex["rest"] == "2-3 min": ex["rest"] = "90–120 sec"
                elif ex["rest"] == "90–120 sec" or ex["rest"] == "90-120 sec": ex["rest"] = "60–90 sec"
                elif ex["rest"] == "60–90 sec" or ex["rest"] == "60-90 sec": ex["rest"] = "45–60 sec"
                elif ex["rest"] == "3–5 min" or ex["rest"] == "3-5 min": ex["rest"] = "2–3 min"

    # Enforce priority sorting intra-group: Freeweight -> Machine -> Isolation
    priority = {"bodyweight": 0, "barbell": 1, "dumbbell": 2, "machine": 3, "cable": 4, "other": 5}
    for d in plan.get("workout_days", []):
        d["exercises"] = sorted(d["exercises"], key=lambda ex: (
            0 if ex.get("compound") and ex["equipment"] in ("barbell", "dumbbell", "bodyweight") else
            1 if ex.get("compound") else 2,
            priority.get(ex["equipment"], 5)
        ))
        
    # 🟢 v4.0: DELOAD WEEK MODIFIER (تعديل الـ Deload) 🟢
    if profile.get("is_deload_week", False):
        for d in plan.get("workout_days", []):
            new_total_sets = 0
            for ex in d.get("exercises", []):
                # بنقلل مجموعة من كل تمرين، بس مش هينزل عن مجموعة واحدة
                ex["sets"] = max(1, ex["sets"] - 1)
                # بنجبره يشيل أوزان خفيفة للتعافي
                ex["load_guidance"] = "50–60% 1RM (Light weight for CNS & joint recovery)"
                # بنجبره ميقربش للـ Failure
                ex["failure"] = "RIR 3-4 (Active Recovery — DO NOT go to failure)"
                new_total_sets += ex["sets"]
            d["total_sets"] = new_total_sets
        
        plan["split_reason"] = "⚠️ DELOAD APPLIED: " + plan.get("split_reason", "")
        plan["deload_recommendation"] = "⚠️ DELOAD WEEK ACTIVE: We noticed high fatigue or pain in your logs. Volume and intensity are reduced this week to let your CNS recover."
        
    plan["volume_report"] = volume_report
    
    return plan

# ─────────────────────────────────────────────
#  VOLUME COUNTER + CHECKER
# ─────────────────────────────────────────────
def count_weekly_volume(plan):
    primary_vol, secondary_vol = {}, {}
    for day in plan["workout_days"]:
        for ex in day["exercises"]:
            for muscle, credit in ex["primary"].items():
                group = MUSCLE_GROUP.get(muscle, muscle)
                primary_vol[group] = round(primary_vol.get(group, 0) + credit * ex["sets"], 1)
            for muscle, credit in ex["secondary"].items():
                group = MUSCLE_GROUP.get(muscle, muscle)
                secondary_vol[group] = round(secondary_vol.get(group, 0) + credit * ex["sets"], 1)
    return primary_vol, secondary_vol

def check_volume_vs_targets(primary_vol, secondary_vol_bonus, profile):
    level    = profile["experience"]
    goal     = profile["goal"]
    activity = profile.get("activity_level", "office")
    weak     = profile.get("weak_muscles", [])
    injuries = profile.get("injuries", {})
    single_leg = (profile.get("leg_days_preference", 2) == 1)
    report   = {}
    isolation = {"biceps","triceps"}
    has_weak_upper = any(m in weak for m in ["chest","back","shoulders"])
    secondary_credit = {"triceps","biceps"}
    
    # FIX 2: Dynamic active_groups - calculate based on muscles actually planned
    # Only include forearms if arms/forearms is weak AND level is intermediate/advanced
    base_groups = ["chest","back","shoulders","biceps","triceps","legs"]
    active_groups = base_groups.copy()
    if level in ["intermediate","advanced"] and any(m in weak for m in ["arms","forearms"]):
        active_groups.append("forearms")
    
    for group in active_groups:
        actual = primary_vol.get(group, 0)
        if group in secondary_credit:
            actual = round(actual + secondary_vol_bonus.get(group, 0) * 0.5, 1)
        target_min = get_volume_target(group, level, goal, activity,
                                       is_weak=(group in weak),
                                       single_leg_day=(single_leg and group=="legs"),
                                       training_days=profile["training_days"],
                                       volume_pref=profile.get("volume", "medium"),
                                       workspace=profile.get("workspace", "full_gym"),
                                       gender=profile.get("gender", "male"))
        target_max = round(target_min * 1.35)
        
        # FIX 3: Biceps/Triceps Ceiling - raise target_max if compound-driven volume is high
        if group in ("biceps", "triceps"):
            freq = profile["training_days"]
            sess_cap = SESSION_SETS_CAP[level][goal]
            compound_floor = min(sess_cap * freq, 20)
            target_max = max(target_max, compound_floor)
        
        if group == "legs":
            sess_max = SESSION_SETS_CAP[level][goal]
            legs_target_max = sess_max * profile.get("leg_days_preference", 2)
            target_max = max(target_max, legs_target_max)
            
        if group in isolation and has_weak_upper and goal == "cut":
            pass # target_min = round(target_min * 0.80) removed for cut penalty
        if group == "triceps" and level == "beginner":
            target_min = round(target_min * 0.75)
        
        status = "ok" if target_min <= actual <= target_max else ("low" if actual < target_min else "high")
        
        # MRV Hard Cap Check
        mrv_hard_cap = 20 if level != "advanced" else 24
        if actual >= mrv_hard_cap and group in weak:
            status = "technique_review_needed"
            
        # FIX 5: Injury Volume Warning - check if LOW status is due to injury restrictions
        if status == "low" and injuries:
            blocked_muscles = set()
            # Handle injuries as a list (not dict)
            injury_list = injuries if isinstance(injuries, list) else list(injuries.values()) if isinstance(injuries, dict) else []
            for injury_parts in injury_list:
                if isinstance(injury_parts, list):
                    for part in injury_parts:
                        part_lower = part.lower()
                        for muscle_key in INJURY_RESTRICTIONS:
                            if muscle_key in part_lower or part_lower in muscle_key:
                                blocked_muscles.add(muscle_key)
                else:
                    part_lower = str(injury_parts).lower()
                    for muscle_key in INJURY_RESTRICTIONS:
                        if muscle_key in part_lower or part_lower in muscle_key:
                            blocked_muscles.add(muscle_key)
            
            group_lower = group.lower()
            if any(blocked_muscles.intersection(INJURY_RESTRICTIONS.keys())):
                restricted_muscles = [m for m in blocked_muscles if m in INJURY_RESTRICTIONS]
                restricted_exercises = set()
                for rm in restricted_muscles:
                    restricted_exercises.update(INJURY_RESTRICTIONS.get(rm, []))
                
                if restricted_exercises:
                    report[group] = {"actual": actual, "target_min": target_min,
                                     "target_max": target_max, "status": status,
                                     "injury_limited": True,
                                     "warning": f"Volume LOW due to injury restrictions: blocked exercises {len(restricted_exercises)} unavailable"}
                else:
                    report[group] = {"actual": actual, "target_min": target_min,
                                     "target_max": target_max, "status": status}
            else:
                report[group] = {"actual": actual, "target_min": target_min,
                                 "target_max": target_max, "status": status}
        else:
            report[group] = {"actual": actual, "target_min": target_min,
                             "target_max": target_max, "status": status}
    return report

# ─────────────────────────────────────────────
#  MACROS
# ─────────────────────────────────────────────
def calc_bmr(weight_kg, height_cm, age, gender):
    if gender == "male": return 10*weight_kg + 6.25*height_cm - 5*age + 5
    return 10*weight_kg + 6.25*height_cm - 5*age - 161

ACTIVITY_TDEE_BASE = {"office": 1.2, "light": 1.375, "heavy": 1.55}
TRAINING_DAYS_BONUS = {1: 0.0, 2: 0.05, 3: 0.10, 4: 0.15, 5: 0.20, 6: 0.25}

def calc_tdee(bmr, training_days, activity_level="office"):
    base = ACTIVITY_TDEE_BASE.get(activity_level, 1.2)
    bonus = TRAINING_DAYS_BONUS.get(min(training_days, 6), 0.15)
    return round(bmr * (base + bonus))

def calc_macros(tdee, goal, weight_kg, height_cm=None):
    """
    Balanced macro calculation — now with ideal weight protection.

    Problem: someone who is 130kg / 175cm doesn't need protein based on 130kg.
    Fat mass doesn't need protein like muscle does. Using actual weight inflates
    protein massively and leaves almost no room for carbs.

    Solution: calculate protein on the LOWER of actual weight vs ideal weight * 1.2
    Ideal weight formula: height_cm - 100  (rough but widely used)
    The *1.2 buffer allows for some healthy weight above ideal without penalising.

    Protein: 1.7–2.0 g/kg of calc_weight
    Fat:     0.8–0.9 g/kg of calc_weight
    Carbs:   remaining calories (primary fuel — never starve carbs)
    """
    # Use ideal weight as protein base if user is significantly above ideal
    if height_cm:
        ideal_weight = max(50, height_cm - 100)
        calc_weight  = min(weight_kg, ideal_weight * 1.2)
    else:
        calc_weight  = weight_kg   # fallback if height not provided

    if goal == "gain":
        target    = round(tdee + 300)
        protein_g = round(calc_weight * 1.8)
        fat_g     = round(calc_weight * 0.9)
    elif goal == "cut":
        target    = round(tdee - 400)
        protein_g = round(calc_weight * 2.4)   # Updated to 2.4 g/kg for cut per latest literature
        fat_g     = round(calc_weight * 0.8)
    elif goal == "strength":
        # القوة بتحتاج سعرات قريبة من الثبات أو فائض بسيط جداً
        target    = round(tdee + 150)
        protein_g = round(calc_weight * 1.8)
        fat_g     = round(calc_weight * 0.9)
    else:  # maintain
        target    = round(tdee)
        protein_g = round(calc_weight * 1.7)
        fat_g     = round(calc_weight * 0.9)

    carb_g = round(max(50, (target - protein_g * 4 - fat_g * 9) / 4))
    return {"tdee": round(tdee), "target_calories": target,
            "protein_g": protein_g, "carbs_g": carb_g, "fat_g": fat_g}

# ─────────────────────────────────────────────
#  GAP ANALYSIS
# ─────────────────────────────────────────────
def analyze_gaps(current_exercises, full_plan):
    current_groups = set()
    for ex_name in current_exercises:
        for db_ex in EXERCISE_DB:
            if ex_name.lower() in db_ex["name"].lower() or db_ex["name"].lower() in ex_name.lower():
                for m in db_ex["primary"]:
                    current_groups.add(MUSCLE_GROUP.get(m, m))
    covered = set()
    for day in full_plan["workout_days"]:
        for ex in day["exercises"]:
            for m in ex["primary"]:
                covered.add(MUSCLE_GROUP.get(m, m))
    missing = covered - current_groups
    suggestions = []
    for day in full_plan["workout_days"]:
        for ex in day["exercises"]:
            ex_groups = {MUSCLE_GROUP.get(m,m) for m in ex["primary"]}
            if ex_groups & missing:
                already = any(ex["name"].lower() in c.lower() or c.lower() in ex["name"].lower()
                              for c in current_exercises)
                if not already and ex not in suggestions:
                    suggestions.append(ex)
    return {"muscles_covered_now": sorted(current_groups),
            "muscles_missing":     sorted(missing),
            "suggested_additions": suggestions[:8]}

# ─────────────────────────────────────────────
#  INPUT HELPERS
# ─────────────────────────────────────────────
def ask_int(prompt, min_val, max_val):
    while True:
        try:
            val = int(input(prompt).strip())
            if min_val <= val <= max_val: return val
            print(f"  Enter a value between {min_val} and {max_val}.")
        except ValueError: print("  Please enter a valid number.")

def ask_float(prompt, min_val, max_val):
    while True:
        try:
            val = float(input(prompt).strip())
            if min_val <= val <= max_val: return val
            print(f"  Enter a value between {min_val} and {max_val}.")
        except ValueError: print("  Please enter a valid number.")

def ask_choice(prompt, valid):
    while True:
        ans = input(prompt).strip().lower()
        if ans in valid: return ans
        print(f"  Choose from: {', '.join(valid)}")

def collect_profile():
    print("\n"+"="*55)
    print("  💪 AI GYM TRAINER — WORKOUT RECOMMENDER v4.0")
    print("="*55)
    name   = input("  Your name: ").strip() or "Athlete"
    age    = ask_int("  Age: ", 10, 80)
    gender = ask_choice("  Gender (male/female): ", ["male","female"])
    weight = ask_float("  Weight (kg): ", 30, 300)
    height = ask_float("  Height (cm): ", 100, 250)
    print("\n  Goal:"); print("    gain / cut / maintain / strength")
    goal   = ask_choice("  Your goal: ", ["gain","cut","maintain","strength"])
    
    # سألنا على الأيام والمستوى الأول هنا
    days   = ask_int("  Training days/week (2-6): ", 2, 6)
    print("\n  Experience: beginner / intermediate / advanced")
    level  = ask_choice("  Level: ", ["beginner","intermediate","advanced"])
    
    print("\n  Activity: office / light / heavy")
    activity = ask_choice("  Activity: ", ["office","light","heavy"])
    raw    = input("\n  Injuries? (comma separated or Enter): ").strip()
    injuries = [i.strip() for i in raw.split(",") if i.strip()] if raw else []
    raw  = input("  Weak muscles? (comma separated or Enter): ").strip()
    weak = [m.strip() for m in raw.split(",") if m.strip()] if raw else []
    
    # المنطق بتاع إخفاء سؤال الرجل
    leg_pref = 2
    if level != "beginner" and days >= 4 and "legs" not in weak:
        leg_pref = ask_int("  Leg days (1 or 2): ", 1, 2)
    elif "legs" in weak:
        print("  [Auto-Set] Leg days set to 2 because legs are a weak point.")
        leg_pref = 2
    else:
        print("  [Auto-Set] Leg preference handled automatically for your level/days.")

    print("\n  Workspace: full_gym / dumbbells / home")
    workspace = ask_choice("  Workspace: ", ["full_gym","dumbbells","home"])
    print("\n  Volume: low / medium / high")
    volume = ask_choice("  Volume: ", ["low","medium","high"])
    raw     = input("  Current exercises? (comma separated or Enter): ").strip()
    current = [e.strip() for e in raw.split(",") if e.strip()] if raw else []
    return {"name":name,"age":age,"gender":gender,"weight_kg":weight,"height_cm":height,
            "goal":goal,"training_days":days,"experience":level,"activity_level":activity,
            "injuries":injuries,"weak_muscles":weak,"current_exercises":current,
            "leg_days_preference":leg_pref,"workspace":workspace,"volume":volume}

# ─────────────────────────────────────────────
#  DISPLAY
# ─────────────────────────────────────────────
def print_macros(macros, profile):
    labels = {"gain":"Muscle Gain 💪","cut":"Fat Loss 🔥","maintain":"Maintain ⚖️"}
    print("\n"+"="*55)
    print(f"  📊 NUTRITION — {labels.get(profile['goal'])}")
    print("="*55)
    print(f"  TDEE:          {macros['tdee']} kcal/day")
    print(f"  Target:        {macros['target_calories']} kcal/day")
    print(f"  Protein : {macros['protein_g']}g  Carbs: {macros['carbs_g']}g  Fat: {macros['fat_g']}g")

def print_workout_plan(plan, volume_report, secondary_vol):
    print("\n"+"="*55)
    print(f"  🏋️  WORKOUT PLAN — {plan['split']}")
    print("="*55)
    split_reason = plan.get("split_reason", "")
    if split_reason:
        print(f"  📋 {split_reason}")
    if plan["split"] in ["bro_split_4", "bro_split_5", "bro_modified_4"]:
        print(f"  ⚠️  Note: Bro Split trains each muscle 1x/week — consider upper/lower or full body for better frequency")
    
    # FIX 7: Workspace warning
    ws_warning = plan.get("workspace_warning", "")
    if ws_warning:
        print(f"  {ws_warning}")
    
    # FIX 8: Weak muscles warning
    weak_warning = plan.get("weak_warning", "")
    if weak_warning:
        print(f"  {weak_warning}")
    
    # FIX 11: Advanced Bro Split note
    bro_split_note = plan.get("bro_split_note", "")
    if bro_split_note:
        print(f"  ℹ️  {bro_split_note}")
    
    # FIX 3: Deload recommendation
    deload = plan.get("deload_recommendation", "")
    if deload:
        print(f"  🔄 Deload: {deload}")
    
    # FIX 2: Progressive overload instructions
    level = plan.get("level", "intermediate")
    goal = plan.get("goal", "maintain")
    progression_rule = "Progression rule: When all sets are completed within the rep range at target RIR for 2 consecutive sessions, add 2.5 kg (compound) or 1.25 kg (isolation) next session."
    print(f"  📈 {progression_rule}")
    
    protocol = SETS_PROTOCOL[plan["level"]]
    print(f"\n  Protocol: {protocol['sets']}x{protocol['reps']}  |  {protocol['failure']}")
    print(f"  Note: {protocol['note']}")
    for i, day in enumerate(plan["workout_days"], 1):
        fatigue     = day.get("total_fatigue", "?")
        fatigue_cap = day.get("fatigue_cap",   "?")
        print(f"\n  📅 Day {i}: {day['day'].upper()}")
        print(f"  Sets: {day.get('total_sets','?')} / limit: {day.get('session_max','?')}"
              f"  |  CNS Load: {fatigue}/{fatigue_cap}")
        # FIX 6: Day with reduced volume due to injuries
        if len(day.get("exercises", [])) < 3:
            print(f"  ⚠️  Day {i} has reduced volume due to injury restrictions.")
        print(f"  {'─'*48}")
        for j, ex in enumerate(day["exercises"], 1):
            pri  = " + ".join(ex["primary"].keys())
            sec  = " + ".join(ex["secondary"].keys()) if ex["secondary"] else "—"
            rest = ex.get("rest", "2–3 min")
            fc   = ex.get("fatigue_cost", compute_fatigue_cost(ex))
            sci_tags = [t for t in ex.get("tags", [])
                        if t in ("stretch_focused","unilateral","high_stability","strength","classic")]
            tag_str  = f"  [{', '.join(sci_tags)}]" if sci_tags else ""
            print(f"    {j}. {ex['name']}{tag_str}")
            print(f"       🎯 {pri}  ➕ {sec}")
            print(f"       {ex['sets']}x{ex['reps']}  |  {ex['equipment']}  |  ⏱ {rest}  |  CNS/set: {fc}")
            print(f"       🏋️  Load: {ex.get('load_guidance', '—')}")
            rom = ex.get("rom_note")
            if rom:
                print(f"       ⚠️  ROM: {rom}")
    print(f"\n  📈 WEEKLY VOLUME")
    print(f"  {'─'*48}")
    for group, data in volume_report.items():
        bonus = secondary_vol.get(group, 0)
        icon  = "✅" if data["status"]=="ok" else ("⚠️  LOW" if data["status"]=="low" else "🔴 HIGH")
        bstr  = f" (+{bonus})" if bonus > 0 else ""
        print(f"  {group:<12} {data['actual']:>5.1f}{bstr:<10}  target {data['target_min']}-{data['target_max']}  {icon}")

def save_recommendation(profile, plan, macros, gaps, volume_report, secondary_vol):
    Path("data").mkdir(exist_ok=True)
    output = {"profile":profile,"workout_plan":plan,"nutrition":macros,
              "gap_analysis":gaps,"volume_report":volume_report,
              "secondary_volume_bonus":secondary_vol}
    path = Path("data") / f"recommendation_{profile['name'].lower().replace(' ','_')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 Saved to: {path}")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def run():
    profile       = collect_profile()
    bmr           = calc_bmr(profile["weight_kg"],profile["height_cm"],profile["age"],profile["gender"])
    tdee          = calc_tdee(bmr, profile["training_days"], profile.get("activity_level", "office"))
    macros        = calc_macros(tdee, profile["goal"], profile["weight_kg"], profile.get("height_cm"))
    plan          = build_workout_plan(profile)
    primary_vol, secondary_vol = count_weekly_volume(plan)
    volume_report = check_volume_vs_targets(primary_vol, secondary_vol, profile)
    gaps          = analyze_gaps(profile.get("current_exercises",[]), plan)
    print_macros(macros, profile)
    print_workout_plan(plan, volume_report, secondary_vol)
    save_recommendation(profile, plan, macros, gaps, volume_report, secondary_vol)
    print(f"\n  ✅ Plan ready, {profile['name']}!  Split: {plan['split']}")
    return {"profile":profile,"plan":plan,"macros":macros,"gaps":gaps,"volume_report":volume_report}

if __name__ == "__main__":
    run()