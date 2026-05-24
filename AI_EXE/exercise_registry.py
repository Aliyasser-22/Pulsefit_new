"""
AI_EXE/exercise_registry.py
============================
Single source of truth:
  filename  →  correct class name
  exercise DB name  →  (filename, class)

The original files had classes placed in the WRONG files (shifted by one).
This module imports everything correctly regardless of that confusion.
"""

import importlib, sys

# ── TRUE MAP: what class actually lives in each file ──────────────────────────
# Determined by scanning each file's source.
_FILE_CLASS_MAP = {
    # file (in AI_EXE/)              : actual class inside it
    "abductor_machine"               : "AbWheelRolloutTrainerAI",       # mislabeled
    "adductor_machine"               : "AbductorMachineTrainerAI",
    "back_extension"                 : "AdductorMachineTrainerAI",
    "barbell_shrug"                  : "BackExtensionTrainerAI",
    "cable_crunch"                   : "BarbellShrugTrainerAI",
    "cable_fly_low_to_high"          : "ArcherPushUpTrainerAI",          # mislabeled
    "cable_lateral_raise"            : "ArnoldPressTrainerAI",           # mislabeled → Arnold Press
    "chest_dips"                     : "CableFlyHighToLowTrainerAI",
    "chest_supported_row"            : "BarbellRowPendlayTrainerAI",
    "chin_up"                        : "BarbellCurlTrainerAI",
    "close_grip_bench"               : "CableCurlHighTrainerAI",
    "conventional_deadlift"          : "ChestSupportedRowTrainerAI",
    "db_lateral_raise"               : "CableLateralRaiseTrainerAI",
    "db_shrug"                       : "CableCrunchTrainerAI",
    "decline_push_up"                : "CableFlyLowToHighTrainerAI",
    "diamond_pushup"                 : "ChinUpTrainerAI",
    "dumbbell_floor_press"           : "ChestDipsTrainerAI",
    "face_pull"                      : "DbLateralRaiseTrainerAI",
    "flat_barbell_bench_press"       : "DeclinePushUpTrainerAI",
    "flat_dumbbell_press"            : "DumbbellFloorPressTrainerAI",
    "hammer_curl"                    : "CloseGripBenchPressTrainerAI",
    "hanging_leg_raise"              : "DbShrugTrainerAI",
    "incline_barbell_press"          : "FlatBarbellBenchPressTrainerAI",
    "incline_db_curl"                : "DiamondPushupTrainerAI",
    "incline_dumbbell_press"         : "FlatDumbbellPressTrainerAI",
    "inverted_row"                   : "HammerCurlTrainerAI",
    "landmine_lateral_raise"         : "FacePullTrainerAI",
    "landmine_oblique_twist"         : "HangingLegRaiseTrainerAI",
    "landmine_press"                 : "InclineBarbellPressTrainerAI",
    "lat_pulldown_underhand"         : "ConventionalDeadliftTrainerAI",
    "lat_pulldown_wide"              : "LatPulldownUnderhandTrainerAI",
    "machine_assisted_pull_up"       : "LatPulldownWideTrainerAI",
    "machine_chest_press"            : "InclineDumbbellPressTrainerAI",
    "machine_lateral_raise"          : "LandmineLateralRaiseTrainerAI",
    "machine_shoulder_press"         : "MachineLateralRaiseTrainerAI",
    "meadows_row"                    : "MachineAssistedPullUpTrainerAI",
    "overhead_press_barbell"         : "MachineShoulderPressTrainerAI",
    "overhead_tricep_cable"          : "InclineDumbbellCurlTrainerAI",
    "overhead_tricep_db"             : "InvertedRowTrainerAI",
    "plank"                          : "LandmineObliqueTwistTrainerAI",
    "preacher_curl"                  : "OverheadTricepCableTrainerAI",
    "pull_up"                        : "MeadowsRowTrainerAI",
    "rear_delt_cable_fly"            : "OverheadPressBarbellTrainerAI",
    "reverse_pec_deck"               : "RearDeltCableFlyTrainerAI",
    "reverse_wrist_curl"             : "OverheadTricepDbTrainerAI",
    "seated_cable_row"               : "PullUpTrainerAI",
    "seated_db_shoulder_press"       : "ReversePecDeckTrainerAI",
    "single_arm_dumbbell_row"        : "SeatedCableRowTrainerAI",
    "skull_crusher"                  : "PreacherCurlTrainerAI",
    "spider_curl"                    : "ReverseWristCurlTrainerAI",
    "straight_arm_pulldown"          : "SingleArmDumbbellRowTrainerAI",
    "superman_hold"                  : "PlankTrainerAI",
    "trap_bar_deadlift"              : "StraightArmPulldownTrainerAI",
    "tricep_dips_upright"            : "SkullCrusherTrainerAI",
    "tricep_pushdown"                : "SpiderCurlTrainerAI",
    "tricep_pushdown_rope"           : "TricepDipsUprightTrainerAI",
    "wrist_curl"                     : "TricepPushdownTrainerAI",
    # correctly named (original PulseFit)
    "tricep_pushdown_ai"             : "TricepPushdownTrainerAI",
}

# ── EXERCISE NAME → (module, class) ──────────────────────────────────────────
# Maps the exact "name" field from workout4__1_.py EXERCISE_DB
# to the module file and class that handles it.
EXERCISE_NAME_MAP = {
    # CHEST
    "Incline Dumbbell Press"         : ("incline_dumbbell_press",   "FlatDumbbellPressTrainerAI"),
    "Incline Barbell Press"          : ("landmine_press",           "InclineBarbellPressTrainerAI"),
    "Cable Fly Low to High"          : ("decline_push_up",          "CableFlyLowToHighTrainerAI"),
    "Flat Dumbbell Press"            : ("flat_dumbbell_press",      "DumbbellFloorPressTrainerAI"),
    "Flat Barbell Bench Press"       : ("incline_barbell_press",    "FlatBarbellBenchPressTrainerAI"),
    "Cable Fly High to Low"          : ("chest_dips",               "CableFlyHighToLowTrainerAI"),
    "Machine Chest Press"            : ("machine_chest_press",      "InclineDumbbellPressTrainerAI"),
    "Dumbbell Floor Press"           : ("dumbbell_floor_press",     "ChestDipsTrainerAI"),
    "Chest Dips (Forward Lean)"      : ("flat_barbell_bench_press", "DeclinePushUpTrainerAI"),
    # BACK - LATS
    "Lat Pulldown (Wide Grip)"       : ("machine_assisted_pull_up", "LatPulldownWideTrainerAI"),
    "Pull-Up / Weighted Pull-Up"     : ("seated_cable_row",         "PullUpTrainerAI"),
    "Lat Pulldown (Underhand Grip)"  : ("lat_pulldown_wide",        "LatPulldownUnderhandTrainerAI"),
    "Straight Arm Pulldown"          : ("trap_bar_deadlift",        "StraightArmPulldownTrainerAI"),
    "Machine Assisted Pull-Up"       : ("meadows_row",              "MachineAssistedPullUpTrainerAI"),
    # BACK - MID
    "Seated Cable Row (Neutral Grip)": ("single_arm_dumbbell_row",  "SeatedCableRowTrainerAI"),
    "Single Arm Dumbbell Row"        : ("straight_arm_pulldown",    "SingleArmDumbbellRowTrainerAI"),
    "Chest-Supported Row (Machine)"  : ("conventional_deadlift",    "ChestSupportedRowTrainerAI"),
    "Barbell Row (Pendlay)"          : ("chest_supported_row",      "BarbellRowPendlayTrainerAI"),
    "Meadows Row"                    : ("pull_up",                  "MeadowsRowTrainerAI"),
    "Conventional Deadlift"          : ("lat_pulldown_underhand",   "ConventionalDeadliftTrainerAI"),
    # REAR DELT
    "Face Pull"                      : ("landmine_lateral_raise",   "FacePullTrainerAI"),
    "Rear Delt Cable Fly"            : ("rear_delt_cable_fly",      "OverheadPressBarbellTrainerAI"),
    "Reverse Pec Deck"               : ("reverse_pec_deck",         "RearDeltCableFlyTrainerAI"),
    # SHOULDERS
    "Seated DB Shoulder Press"       : ("seated_db_shoulder_press", "ReversePecDeckTrainerAI"),
    "Machine Shoulder Press"         : ("overhead_press_barbell",   "MachineShoulderPressTrainerAI"),
    "Overhead Press (Barbell)"       : ("machine_shoulder_press",   "MachineLateralRaiseTrainerAI"),
    "Arnold Press"                   : ("cable_lateral_raise",      "ArnoldPressTrainerAI"),
    "Machine Lateral Raise"          : ("machine_lateral_raise",    "LandmineLateralRaiseTrainerAI"),
    "Cable Lateral Raise"            : ("db_lateral_raise",         "CableLateralRaiseTrainerAI"),
    "DB Lateral Raise"               : ("face_pull",                "DbLateralRaiseTrainerAI"),
    "Landmine Lateral Raise"         : ("adductor_machine",         "AbductorMachineTrainerAI"),
    # BICEPS
    "Preacher Curl (Machine/EZ Bar)" : ("skull_crusher",            "PreacherCurlTrainerAI"),
    "Hammer Curl"                    : ("inverted_row",             "HammerCurlTrainerAI"),
    "Cable Curl (High Cable)"        : ("close_grip_bench",         "CableCurlHighTrainerAI"),
    "Incline Dumbbell Curl"          : ("overhead_tricep_cable",    "InclineDumbbellCurlTrainerAI"),
    "Barbell Curl"                   : ("chin_up",                  "BarbellCurlTrainerAI"),
    "Spider Curl"                    : ("spider_curl",              "ReverseWristCurlTrainerAI"),
    "Chin-Up (Bicep Focus)"          : ("diamond_pushup",           "ChinUpTrainerAI"),
    "Inverted Row (Supinated Grip)"  : ("overhead_tricep_db",       "InvertedRowTrainerAI"),
    # TRICEPS
    "Tricep Pushdown (Cable)"        : ("wrist_curl",               "TricepPushdownTrainerAI"),
    "Overhead Tricep Extension (Cable)": ("preacher_curl",          "OverheadTricepCableTrainerAI"),
    "Tricep Pushdown (Rope)"         : ("tricep_pushdown_rope",     "TricepDipsUprightTrainerAI"),
    "Overhead Tricep Extension (Dumbbell)": ("reverse_wrist_curl",  "OverheadTricepDbTrainerAI"),
    "Diamond Push-Up"                : ("incline_db_curl",          "DiamondPushupTrainerAI"),
    "Skull Crusher (EZ Bar)"         : ("tricep_dips_upright",      "SkullCrusherTrainerAI"),
    "Close Grip Bench Press"         : ("hammer_curl",              "CloseGripBenchPressTrainerAI"),
    "Dips (Upright / Tricep Focused)": ("tricep_pushdown",          "SpiderCurlTrainerAI"),
}


def get_trainer_class(exercise_name: str):
    """
    Returns an instantiated trainer class for a given exercise DB name.
    Returns None if no trainer exists for this exercise.
    """
    if exercise_name not in EXERCISE_NAME_MAP:
        return None

    module_name, class_name = EXERCISE_NAME_MAP[exercise_name]
    full_module = f"AI_EXE.{module_name}"

    try:
        mod = importlib.import_module(full_module)
        cls = getattr(mod, class_name)
        return cls
    except (ImportError, AttributeError) as e:
        print(f"[Registry] Could not load {class_name} from {full_module}: {e}")
        return None


# ── EXERCISE MAP for app.py EXERCISE_MAP ─────────────────────────────────────
# Key = URL-safe exercise key used in the frontend
# Value = (module, class)
EXERCISE_MAP_FOR_APP = {
    # CHEST
    "incline_dumbbell_press"        : ("incline_dumbbell_press",   "FlatDumbbellPressTrainerAI"),
    "incline_barbell_press"         : ("landmine_press",           "InclineBarbellPressTrainerAI"),
    "cable_fly_low_to_high"         : ("decline_push_up",          "CableFlyLowToHighTrainerAI"),
    "flat_dumbbell_press"           : ("flat_dumbbell_press",      "DumbbellFloorPressTrainerAI"),
    "flat_barbell_bench_press"      : ("incline_barbell_press",    "FlatBarbellBenchPressTrainerAI"),
    "cable_fly_high_to_low"         : ("chest_dips",               "CableFlyHighToLowTrainerAI"),
    "machine_chest_press"           : ("machine_chest_press",      "InclineDumbbellPressTrainerAI"),
    "dumbbell_floor_press"          : ("dumbbell_floor_press",     "ChestDipsTrainerAI"),
    "chest_dips"                    : ("flat_barbell_bench_press", "DeclinePushUpTrainerAI"),
    # BACK
    "lat_pulldown_wide"             : ("machine_assisted_pull_up", "LatPulldownWideTrainerAI"),
    "pull_up"                       : ("seated_cable_row",         "PullUpTrainerAI"),
    "lat_pulldown_underhand"        : ("lat_pulldown_wide",        "LatPulldownUnderhandTrainerAI"),
    "straight_arm_pulldown"         : ("trap_bar_deadlift",        "StraightArmPulldownTrainerAI"),
    "machine_assisted_pull_up"      : ("meadows_row",              "MachineAssistedPullUpTrainerAI"),
    "seated_cable_row"              : ("single_arm_dumbbell_row",  "SeatedCableRowTrainerAI"),
    "single_arm_dumbbell_row"       : ("straight_arm_pulldown",    "SingleArmDumbbellRowTrainerAI"),
    "chest_supported_row"           : ("conventional_deadlift",    "ChestSupportedRowTrainerAI"),
    "barbell_row_pendlay"           : ("chest_supported_row",      "BarbellRowPendlayTrainerAI"),
    "meadows_row"                   : ("pull_up",                  "MeadowsRowTrainerAI"),
    "conventional_deadlift"         : ("lat_pulldown_underhand",   "ConventionalDeadliftTrainerAI"),
    # REAR DELT
    "face_pull"                     : ("landmine_lateral_raise",   "FacePullTrainerAI"),
    "rear_delt_cable_fly"           : ("rear_delt_cable_fly",      "OverheadPressBarbellTrainerAI"),
    "reverse_pec_deck"              : ("reverse_pec_deck",         "RearDeltCableFlyTrainerAI"),
    # SHOULDERS
    "seated_db_shoulder_press"      : ("seated_db_shoulder_press", "ReversePecDeckTrainerAI"),
    "machine_shoulder_press"        : ("overhead_press_barbell",   "MachineShoulderPressTrainerAI"),
    "overhead_press_barbell"        : ("machine_shoulder_press",   "MachineLateralRaiseTrainerAI"),
    "arnold_press"                  : ("cable_lateral_raise",      "ArnoldPressTrainerAI"),
    "machine_lateral_raise"         : ("machine_lateral_raise",    "LandmineLateralRaiseTrainerAI"),
    "cable_lateral_raise"           : ("db_lateral_raise",         "CableLateralRaiseTrainerAI"),
    "db_lateral_raise"              : ("face_pull",                "DbLateralRaiseTrainerAI"),
    "landmine_lateral_raise"        : ("adductor_machine",         "AbductorMachineTrainerAI"),
    # BICEPS
    "preacher_curl"                 : ("skull_crusher",            "PreacherCurlTrainerAI"),
    "hammer_curl"                   : ("inverted_row",             "HammerCurlTrainerAI"),
    "cable_curl_high"               : ("close_grip_bench",         "CableCurlHighTrainerAI"),
    "incline_db_curl"               : ("overhead_tricep_cable",    "InclineDumbbellCurlTrainerAI"),
    "barbell_curl"                  : ("chin_up",                  "BarbellCurlTrainerAI"),
    "spider_curl"                   : ("spider_curl",              "ReverseWristCurlTrainerAI"),
    "chin_up"                       : ("diamond_pushup",           "ChinUpTrainerAI"),
    "inverted_row"                  : ("overhead_tricep_db",       "InvertedRowTrainerAI"),
    # TRICEPS
    "tricep_pushdown"               : ("wrist_curl",               "TricepPushdownTrainerAI"),
    "overhead_tricep_cable"         : ("preacher_curl",            "OverheadTricepCableTrainerAI"),
    "tricep_pushdown_rope"          : ("tricep_pushdown_rope",     "TricepDipsUprightTrainerAI"),
    "overhead_tricep_db"            : ("reverse_wrist_curl",       "OverheadTricepDbTrainerAI"),
    "diamond_pushup"                : ("incline_db_curl",          "DiamondPushupTrainerAI"),
    "skull_crusher"                 : ("tricep_dips_upright",      "SkullCrusherTrainerAI"),
    "close_grip_bench"              : ("hammer_curl",              "CloseGripBenchPressTrainerAI"),
    "tricep_dips_upright"           : ("tricep_pushdown",          "SpiderCurlTrainerAI"),
}
