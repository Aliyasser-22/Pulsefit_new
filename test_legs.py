"""
Quick test: 4 training days, 2 leg-day preference
Check that BOTH leg days contain compound leg exercises (Quads/Hamstrings/Glutes)
"""
import sys, os, importlib

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

# Import the engine (file has a space in name)
spec = importlib.util.spec_from_file_location(
    "workout4", os.path.join(os.path.dirname(__file__), "workout4 (1).py"))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

profile = {
    "experience":   "intermediate",
    "training_days": 4,
    "goal":          "gain",
    "activity_level": "office",
    "injuries":      [],
    "weak_muscles":  [],
    "leg_days_preference": 2,
    "workspace":     "full_gym",
    "volume":        "medium",
    "gender":        "male",
}

plan = engine.build_workout_plan(profile)

print("=" * 70)
print(f"Split chosen : {plan.get('split_name','?')}")
print(f"Split reason : {plan.get('split_reason','?')}")
print("=" * 70)

COMPOUND_LEG_SUBS = {"quads", "hamstrings", "glutes"}

for i, day in enumerate(plan["workout_days"], 1):
    muscles_in_day = set()
    for ex in day["exercises"]:
        for m in ex["primary"]:
            muscles_in_day.add(m)

    # Classify
    has_compound_legs = bool(muscles_in_day & COMPOUND_LEG_SUBS)
    has_calves = "calves" in muscles_in_day
    has_abs    = "abs" in muscles_in_day

    label = day.get("day_label", f"Day {i}")
    print(f"\n--- {label} ({day.get('total_sets',0)} sets) ---")
    for ex in day["exercises"]:
        primary_list = ", ".join(ex["primary"].keys())
        print(f"  {ex['name']:45s}  {ex['sets']}x{ex['reps']:10s}  [{primary_list}]")

    # Summary flags
    flags = []
    if has_compound_legs: flags.append("✅ COMPOUND LEGS")
    if has_calves:        flags.append("🦵 Calves")
    if has_abs:           flags.append("🏋️ Abs")
    if not has_compound_legs and (has_calves or has_abs):
        flags.append("⚠️  NO COMPOUND LEGS!")
    print(f"  >> {' | '.join(flags)}")

print("\n" + "=" * 70)
print("TEST RESULT:")
# Count leg days with compounds
leg_days_with_compounds = 0
for day in plan["workout_days"]:
    muscles = set()
    for ex in day["exercises"]:
        for m in ex["primary"]:
            muscles.add(m)
    if muscles & COMPOUND_LEG_SUBS:
        leg_days_with_compounds += 1

if leg_days_with_compounds >= 2:
    print(f"✅ PASS — {leg_days_with_compounds} leg days have compound exercises")
else:
    print(f"❌ FAIL — Only {leg_days_with_compounds} leg day(s) have compound exercises (expected 2)")
print("=" * 70)
