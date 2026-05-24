"""
AI Coach v4.3 - Fully Local & Context-Aware Voice Assistance
================================================
Changes from v4.2:
- _generate_and_queue: removed `and urgent` condition → Arabic TTS always used for ar language
- speak_motivation: now routes through _speak_text_direct (non-blocking thread)
- _speak_text_direct: new method, queues TTS audio without blocking caller
"""

import os
import pygame
import threading
import queue
import time
import logging
import hashlib
import atexit
from collections import deque
from gtts import gTTS
import random
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

from AI_EXE.messages import (
    # Setup
    KEEP_BACK_STRAIGHT, STEP_BACK, CANT_SEE_BODY, SIT_DOWN,LATERAL_DB_BENT,OVERHEAD_KEEP_ELBOWS_HIGH,GOBLET_SQUAT_CHEST,
    # Bicep
    RELAX_SHOULDER, PIN_ELBOW, DONT_REST_BODY,
    LIFT_OFF_LEG, FULL_EXTENSION, SQUEEZE_UP,
    # Tricep
    TUCK_ELBOWS, DONT_QUIT, LOCK_ARMS,
    # Flat dumbbell press
    FLAT_PRESS_SETUP, FLAT_PRESS_LOWER, FLAT_PRESS_LOCK, FLAT_PRESS_DROP,
    # Shoulder press
    GOOD_REP, GO_DOWN, PUSH_UP_FULLY, KEEP_BOTH_ARMS_EQUAL, STABILIZE_YOUR_HIPS,
    # Tbar row
    TBAR_SETUP, TBAR_EXTENSION, TBAR_PULL_MORE,
    # Chest Batch 1
    INCLINE_DB_SETUP, INCLINE_DB_LOWER, INCLINE_DB_LOCK, INCLINE_DB_DROP,
    INCLINE_BB_SETUP, INCLINE_BB_LOWER, INCLINE_BB_LOCK, INCLINE_BB_TOUCH,
    FLY_L2H_SETUP, FLY_L2H_STRETCH, FLY_L2H_SQUEEZE, FLY_L2H_BENT,
    # Chest Batch 2
    LANDMINE_PRESS_SETUP, LANDMINE_PRESS_LOWER, LANDMINE_PRESS_LOCK, LANDMINE_PRESS_DROP,
    FLAT_BB_SETUP, FLAT_BB_LOWER, FLAT_BB_LOCK, FLAT_BB_TOUCH,
    FLY_H2L_SETUP, FLY_H2L_STRETCH, FLY_H2L_SQUEEZE, FLY_H2L_BENT,
    MACHINE_PRESS_SETUP, MACHINE_PRESS_LOWER, MACHINE_PRESS_LOCK, MACHINE_PRESS_DROP,
    FLOOR_PRESS_SETUP, FLOOR_PRESS_LOWER, FLOOR_PRESS_LOCK, FLOOR_PRESS_DROP,
    DIPS_SETUP, DIPS_LOWER, DIPS_LOCK, DIPS_LEAN,
    DECLINE_PUSHUP_SETUP, DECLINE_PUSHUP_LOWER, DECLINE_PUSHUP_LOCK, DECLINE_PUSHUP_DROP,
    ARCHER_PUSHUP_SETUP, ARCHER_PUSHUP_LOWER, ARCHER_PUSHUP_LOCK, ARCHER_PUSHUP_STRAIGHT,
    # Back Batch 1
    LAT_WIDE_SETUP, LAT_WIDE_PULL, LAT_WIDE_STRETCH, LAT_WIDE_SQUEEZE,
    PULLUP_SETUP, PULLUP_PULL, PULLUP_HANG, PULLUP_CHIN,
    LAT_UNDER_SETUP, LAT_UNDER_PULL, LAT_UNDER_STRETCH, LAT_UNDER_SQUEEZE,
    STRAIGHT_ARM_SETUP, STRAIGHT_ARM_PULL, STRAIGHT_ARM_STRETCH, STRAIGHT_ARM_BENT,
    # Back Batch 2
    AST_PULLUP_SETUP, AST_PULLUP_PULL, AST_PULLUP_HANG, AST_PULLUP_CHIN,
    CABLE_ROW_SETUP, CABLE_ROW_PULL, CABLE_ROW_STRETCH, CABLE_ROW_SQUEEZE,
    DB_ROW_SETUP, DB_ROW_PULL, DB_ROW_STRETCH, DB_ROW_SQUEEZE,
    CHEST_ROW_SETUP, CHEST_ROW_PULL, CHEST_ROW_STRETCH, CHEST_ROW_SQUEEZE,
    PENDLAY_ROW_SETUP, PENDLAY_ROW_PULL, PENDLAY_ROW_STRETCH, PENDLAY_ROW_SQUEEZE,
    MEADOWS_ROW_SETUP, MEADOWS_ROW_PULL, MEADOWS_ROW_STRETCH, MEADOWS_ROW_SQUEEZE,
    TRAP_DEADLIFT_SETUP, TRAP_DEADLIFT_PULL, TRAP_DEADLIFT_LOCK, TRAP_DEADLIFT_DROP,
    CONV_DEADLIFT_SETUP, CONV_DEADLIFT_PULL, CONV_DEADLIFT_LOCK, CONV_DEADLIFT_DROP,
    # Shoulders Batch 1
    SEATED_DB_PRESS_SETUP, SEATED_DB_PRESS_LOWER, SEATED_DB_PRESS_LOCK, SEATED_DB_PRESS_DROP,
    MACHINE_PRESS_SHOULDER_SETUP, MACHINE_PRESS_SHOULDER_LOWER, MACHINE_PRESS_SHOULDER_LOCK, MACHINE_PRESS_SHOULDER_DROP,
    OHP_BARBELL_SETUP, OHP_BARBELL_LOWER, OHP_BARBELL_LOCK, OHP_BARBELL_DROP,
    ARNOLD_PRESS_SETUP, ARNOLD_PRESS_LOWER, ARNOLD_PRESS_LOCK, ARNOLD_PRESS_DROP,
    # Shoulders Batch 2
    LATERAL_MACHINE_SETUP, LATERAL_MACHINE_RAISE, LATERAL_MACHINE_LOWER, LATERAL_MACHINE_TOO_HIGH,
    LATERAL_CABLE_SETUP, LATERAL_CABLE_RAISE, LATERAL_CABLE_LOWER, LATERAL_CABLE_TOO_HIGH,
    LATERAL_DB_SETUP, LATERAL_DB_RAISE, LATERAL_DB_LOWER, LATERAL_DB_TOO_HIGH,
    LATERAL_LANDMINE_SETUP, LATERAL_LANDMINE_RAISE, LATERAL_LANDMINE_LOWER, LATERAL_LANDMINE_TOO_HIGH,
    FACE_PULL_SETUP, FACE_PULL_PULL, FACE_PULL_STRETCH, FACE_PULL_SQUEEZE,
    REAR_CABLE_FLY_SETUP, REAR_CABLE_FLY_PULL, REAR_CABLE_FLY_STRETCH, REAR_CABLE_FLY_SQUEEZE,
    REV_PEC_DECK_SETUP, REV_PEC_DECK_PULL, REV_PEC_DECK_STRETCH, REV_PEC_DECK_SQUEEZE,
    # Bicep Curls
    PREACHER_CURL_SETUP, PREACHER_CURL_CURL, PREACHER_CURL_STRETCH, PREACHER_CURL_PIN,
    HAMMER_CURL_SETUP, HAMMER_CURL_CURL, HAMMER_CURL_STRETCH, HAMMER_SWINGING,
    HIGH_CABLE_CURL_SETUP, HIGH_CABLE_CURL_CURL, HIGH_CABLE_CURL_STRETCH, HIGH_CABLE_DROP,
    INCLINE_DB_CURL_SETUP, INCLINE_DB_CURL_CURL, INCLINE_DB_CURL_STRETCH, INCLINE_DB_CURL_DROP,
    BARBELL_CURL_SETUP, BARBELL_CURL_CURL, BARBELL_CURL_STRETCH, BARBELL_CURL_SWING,
    SPIDER_CURL_SETUP, SPIDER_CURL_CURL, SPIDER_CURL_STRETCH, SPIDER_CURL_SQUEEZE,
    # Chin-Up & Inverted Row
    CHINUP_SETUP, CHINUP_PULL, CHINUP_STRETCH, CHINUP_SQUEEZE,
    INVERTED_ROW_SETUP, INVERTED_ROW_PULL, INVERTED_ROW_STRETCH, INVERTED_ROW_SQUEEZE,
    # Tricep Exercises
    TRICEP_PUSHDOWN_SETUP, TRICEP_PUSHDOWN_PUSH, TRICEP_PUSHDOWN_STRETCH, TRICEP_PUSHDOWN_DROP,
    TRICEP_PUSHDOWN_ROPE_SETUP, TRICEP_PUSHDOWN_ROPE_PUSH, TRICEP_PUSHDOWN_ROPE_STRETCH, TRICEP_PUSHDOWN_ROPE_DROP,
    OVERHEAD_TRICEP_CABLE_SETUP, OVERHEAD_TRICEP_CABLE_PUSH, OVERHEAD_TRICEP_CABLE_STRETCH, OVERHEAD_TRICEP_CABLE_DROP,
    OVERHEAD_TRICEP_DB_SETUP, OVERHEAD_TRICEP_DB_PUSH, OVERHEAD_TRICEP_DB_STRETCH, OVERHEAD_TRICEP_DB_DROP,
    DIAMOND_PUSHUP_SETUP, DIAMOND_PUSHUP_LOWER, DIAMOND_PUSHUP_PUSH, DIAMOND_PUSHUP_WIDE,
    SKULL_CRUSHER_SETUP, SKULL_CRUSHER_LOWER, SKULL_CRUSHER_PUSH, SKULL_CRUSHER_ELBOWS,
    CLOSE_GRIP_BENCH_SETUP, CLOSE_GRIP_BENCH_LOWER, CLOSE_GRIP_BENCH_PUSH, CLOSE_GRIP_BENCH_FLARE,
    TRICEP_DIPS_UPRIGHT_SETUP, TRICEP_DIPS_UPRIGHT_LOWER, TRICEP_DIPS_UPRIGHT_PUSH, TRICEP_DIPS_UPRIGHT_LEAN,
    # Forearm Exercises
    WRIST_CURL_SETUP, WRIST_CURL_CURL, WRIST_CURL_STRETCH, WRIST_CURL_DROP,
    REVERSE_WRIST_CURL_SETUP, REVERSE_WRIST_CURL_CURL, REVERSE_WRIST_CURL_STRETCH, REVERSE_WRIST_CURL_DROP,
    # Quad Exercises
    LEG_PRESS_SETUP, LEG_PRESS_LOWER, LEG_PRESS_PUSH, LEG_PRESS_DEPTH,
    GOBLET_SQUAT_SETUP, GOBLET_SQUAT_LOWER, GOBLET_SQUAT_UP, GOBLET_SQUAT_DEPTH,
    LEG_EXTENSION_SETUP, LEG_EXTENSION_EXTEND, LEG_EXTENSION_LOWER, LEG_EXTENSION_SQUEEZE,
    WALKING_LUNGE_SETUP, WALKING_LUNGE_STEP, WALKING_LUNGE_LOWER, WALKING_LUNGE_PUSH,
    BARBELL_BACK_SQUAT_SETUP, BARBELL_BACK_SQUAT_LOWER, BARBELL_BACK_SQUAT_UP, BARBELL_BACK_SQUAT_DEPTH, BARBELL_BACK_SQUAT_KNEE,
    HACK_SQUAT_SETUP, HACK_SQUAT_LOWER, HACK_SQUAT_PUSH, HACK_SQUAT_DEPTH,
    BULGARIAN_SPLIT_SQUAT_SETUP, BULGARIAN_SPLIT_SQUAT_LOWER, BULGARIAN_SPLIT_SQUAT_UP, BULGARIAN_SPLIT_SQUAT_DEPTH,
    # Hamstring Exercises
    LYING_LEG_CURL_SETUP, LYING_LEG_CURL_CURL, LYING_LEG_CURL_LOWER, LYING_LEG_CURL_KNEE,
    ROMANIAN_DEADLIFT_SETUP, ROMANIAN_DEADLIFT_HINGE, ROMANIAN_DEADLIFT_LOWER, ROMANIAN_DEADLIFT_UP, ROMANIAN_DEADLIFT_BACK,
    SINGLE_LEG_RDL_SETUP, SINGLE_LEG_RDL_HINGE, SINGLE_LEG_RDL_UP, SINGLE_LEG_RDL_BALANCE,
    NORDIC_CURL_SETUP, NORDIC_CURL_LOWER, NORDIC_CURL_CATCH, NORDIC_CURL_RETURN,
    # Glute Exercises
    HIP_THRUST_SETUP, HIP_THRUST_THRUST, HIP_THRUST_TOP, HIP_THRUST_LOWER,
    CABLE_PULL_THROUGH_SETUP, CABLE_PULL_THROUGH_PULL, CABLE_PULL_THROUGH_SQUEEZE, CABLE_PULL_THROUGH_HIP,
    SUMO_DEADLIFT_SETUP, SUMO_DEADLIFT_PULL, SUMO_DEADLIFT_LOCK, SUMO_DEADLIFT_BACK,
    DB_GLUTE_BRIDGE_SETUP, DB_GLUTE_BRIDGE_UP, DB_GLUTE_BRIDGE_TOP, DB_GLUTE_BRIDGE_LOWER,
    GLUTE_KICKBACK_SETUP, GLUTE_KICKBACK_KICK, GLUTE_KICKBACK_SQUEEZE, GLUTE_KICKBACK_LOWER,
    SINGLE_LEG_GLUTE_BRIDGE_SETUP, SINGLE_LEG_GLUTE_BRIDGE_UP, SINGLE_LEG_GLUTE_BRIDGE_SQUEEZE, SINGLE_LEG_GLUTE_BRIDGE_HIP,
    # Calf Exercises
    SEATED_CALF_RAISE_SETUP, SEATED_CALF_RAISE_RAISE, SEATED_CALF_RAISE_SQUEEZE, SEATED_CALF_RAISE_LOWER,
    STANDING_CALF_RAISE_SETUP, STANDING_CALF_RAISE_RAISE, STANDING_CALF_RAISE_SQUEEZE, STANDING_CALF_RAISE_LOWER,
    DONKEY_CALF_RAISE_SETUP, DONKEY_CALF_RAISE_RAISE, DONKEY_CALF_RAISE_SQUEEZE, DONKEY_CALF_RAISE_LOWER,
    # Abs / Core Exercises
    CABLE_CRUNCH_SETUP, CABLE_CRUNCH_CRUNCH, CABLE_CRUNCH_SQUEEZE, CABLE_CRUNCH_FULL,
    PLANK_SETUP, PLANK_HOLD, PLANK_HIPS_SAGGING, PLANK_HIPS_HIGH,
    HANGING_LEG_RAISE_SETUP, HANGING_LEG_RAISE_RAISE, HANGING_LEG_RAISE_SQUEEZE, HANGING_LEG_RAISE_LOWER,
    AB_WHEEL_ROLLOUT_SETUP, AB_WHEEL_ROLLOUT_ROLL, AB_WHEEL_ROLLOUT_RETURN, AB_WHEEL_ROLLOUT_CONTROL,
    LANDMINE_OBLIQUE_TWIST_SETUP, LANDMINE_OBLIQUE_TWIST_TWIST, LANDMINE_OBLIQUE_TWIST_SQUEEZE, LANDMINE_OBLIQUE_TWIST_CONTROL,
    # Lower Back Exercises
    BACK_EXTENSION_SETUP, BACK_EXTENSION_UP, BACK_EXTENSION_SQUEEZE, BACK_EXTENSION_LOWER,
    SUPERMAN_HOLD_SETUP, SUPERMAN_HOLD_HOLD, SUPERMAN_HOLD_SQUEEZE, SUPERMAN_HOLD_UP,
    # Trap Exercises
    BARBELL_SHRUG_SETUP, BARBELL_SHRUG_SHRUG, BARBELL_SHRUG_SQUEEZE, BARBELL_SHRUG_DROP,
    DB_SHRUG_SETUP, DB_SHRUG_SHRUG, DB_SHRUG_SQUEEZE, DB_SHRUG_DROP,
    # Adductor / Abductor Exercises
    ADDUCTOR_MACHINE_SETUP, ADDUCTOR_MACHINE_SQUEEZE, ADDUCTOR_MACHINE_OPEN, ADDUCTOR_MACHINE_FULL,
    ABDUCTOR_MACHINE_SETUP, ABDUCTOR_MACHINE_OPEN, ABDUCTOR_MACHINE_SQUEEZE, ABDUCTOR_MACHINE_CLOSE

)

# ── SEVERITY & MOTIVATION CONFIG ────────────────────────────────
SEVERITY: dict[str, float] = {
    "critical":   3.0,
    "warning":    9.0,
    "hint":       12.0,
    "completion": 20.0,
    "motivation": 6.0,
}

MSG_SEVERITY: dict[str, str] = {
    # Setup / visibility
    STEP_BACK:            "critical",
    CANT_SEE_BODY:        "critical",
    SIT_DOWN:             "critical",

    # Generic hints / completion
    GOOD_REP:             "completion",
    SQUEEZE_UP:           "hint",
    DONT_QUIT:            "hint",

    # Bicep
    RELAX_SHOULDER:       "warning",
    PIN_ELBOW:            "warning",
    DONT_REST_BODY:       "warning",
    LIFT_OFF_LEG:         "warning",
    FULL_EXTENSION:       "warning",

    # Tricep
    TUCK_ELBOWS:          "warning",
    LOCK_ARMS:            "warning",

    # Chest
    FLAT_PRESS_SETUP:     "warning",
    FLAT_PRESS_LOWER:     "warning",
    FLAT_PRESS_LOCK:      "warning",
    FLAT_PRESS_DROP:      "warning",
    INCLINE_DB_SETUP:     "warning",
    INCLINE_DB_LOWER:     "warning",
    INCLINE_DB_LOCK:      "warning",
    INCLINE_DB_DROP:      "warning",
    INCLINE_BB_SETUP:     "warning",
    INCLINE_BB_LOWER:     "warning",
    INCLINE_BB_LOCK:      "warning",
    INCLINE_BB_TOUCH:     "warning",
    FLY_L2H_SETUP:        "warning",
    FLY_L2H_STRETCH:      "hint",
    FLY_L2H_SQUEEZE:      "hint",
    FLY_L2H_BENT:         "warning",
    LANDMINE_PRESS_SETUP: "warning",
    LANDMINE_PRESS_LOWER: "warning",
    LANDMINE_PRESS_LOCK:  "warning",
    LANDMINE_PRESS_DROP:  "warning",
    FLAT_BB_SETUP:        "warning",
    FLAT_BB_LOWER:        "warning",
    FLAT_BB_LOCK:         "warning",
    FLAT_BB_TOUCH:        "warning",
    FLY_H2L_SETUP:        "warning",
    FLY_H2L_STRETCH:      "hint",
    FLY_H2L_SQUEEZE:      "hint",
    FLY_H2L_BENT:         "warning",
    MACHINE_PRESS_SETUP:  "warning",
    MACHINE_PRESS_LOWER:  "warning",
    MACHINE_PRESS_LOCK:   "warning",
    MACHINE_PRESS_DROP:   "warning",
    FLOOR_PRESS_SETUP:    "warning",
    FLOOR_PRESS_LOWER:    "warning",
    FLOOR_PRESS_LOCK:     "warning",
    FLOOR_PRESS_DROP:     "warning",
    DIPS_SETUP:           "warning",
    DIPS_LOWER:           "warning",
    DIPS_LOCK:            "warning",
    DIPS_LEAN:            "warning",
    DECLINE_PUSHUP_SETUP: "warning",
    DECLINE_PUSHUP_LOWER: "warning",
    DECLINE_PUSHUP_LOCK:  "warning",
    DECLINE_PUSHUP_DROP:  "warning",
    ARCHER_PUSHUP_SETUP:  "warning",
    ARCHER_PUSHUP_LOWER:  "warning",
    ARCHER_PUSHUP_LOCK:   "warning",
    ARCHER_PUSHUP_STRAIGHT: "warning",

    # Shoulders
    KEEP_BACK_STRAIGHT:   "warning",
    GO_DOWN:              "warning",
    PUSH_UP_FULLY:        "warning",
    KEEP_BOTH_ARMS_EQUAL: "warning",
    STABILIZE_YOUR_HIPS:  "warning",
    SEATED_DB_PRESS_SETUP: "warning",
    SEATED_DB_PRESS_LOWER: "warning",
    SEATED_DB_PRESS_LOCK:  "warning",
    SEATED_DB_PRESS_DROP:  "warning",
    MACHINE_PRESS_SHOULDER_SETUP: "warning",
    MACHINE_PRESS_SHOULDER_LOWER: "warning",
    MACHINE_PRESS_SHOULDER_LOCK:  "warning",
    MACHINE_PRESS_SHOULDER_DROP:  "warning",
    OHP_BARBELL_SETUP:    "warning",
    OHP_BARBELL_LOWER:    "warning",
    OHP_BARBELL_LOCK:     "warning",
    OHP_BARBELL_DROP:     "warning",
    ARNOLD_PRESS_SETUP:   "warning",
    ARNOLD_PRESS_LOWER:   "warning",
    ARNOLD_PRESS_LOCK:    "warning",
    ARNOLD_PRESS_DROP:    "warning",
    LATERAL_MACHINE_SETUP: "warning",
    LATERAL_MACHINE_RAISE: "warning",
    LATERAL_MACHINE_LOWER: "warning",
    LATERAL_MACHINE_TOO_HIGH: "warning",
    LATERAL_CABLE_SETUP:  "warning",
    LATERAL_CABLE_RAISE:  "warning",
    LATERAL_CABLE_LOWER:  "warning",
    LATERAL_CABLE_TOO_HIGH: "warning",
    LATERAL_DB_SETUP:     "warning",
    LATERAL_DB_RAISE:     "warning",
    LATERAL_DB_LOWER:     "warning",
    LATERAL_DB_TOO_HIGH:  "warning",
    LATERAL_LANDMINE_SETUP: "warning",
    LATERAL_LANDMINE_RAISE: "warning",
    LATERAL_LANDMINE_LOWER: "warning",
    LATERAL_LANDMINE_TOO_HIGH: "warning",
    FACE_PULL_SETUP:      "warning",
    FACE_PULL_PULL:       "warning",
    FACE_PULL_STRETCH:    "hint",
    FACE_PULL_SQUEEZE:    "hint",
    REAR_CABLE_FLY_SETUP: "warning",
    REAR_CABLE_FLY_PULL:  "warning",
    REAR_CABLE_FLY_STRETCH: "hint",
    REAR_CABLE_FLY_SQUEEZE: "hint",
    REV_PEC_DECK_SETUP:   "warning",
    REV_PEC_DECK_PULL:    "warning",
    REV_PEC_DECK_STRETCH: "hint",
    REV_PEC_DECK_SQUEEZE: "hint",

    # Back
    TBAR_SETUP:           "warning",
    TBAR_EXTENSION:       "warning",
    TBAR_PULL_MORE:       "warning",
    LAT_WIDE_SETUP:       "warning",
    LAT_WIDE_PULL:        "warning",
    LAT_WIDE_STRETCH:     "hint",
    LAT_WIDE_SQUEEZE:     "hint",
    PULLUP_SETUP:         "warning",
    PULLUP_PULL:          "warning",
    PULLUP_HANG:          "warning",
    PULLUP_CHIN:          "warning",
    LAT_UNDER_SETUP:      "warning",
    LAT_UNDER_PULL:       "warning",
    LAT_UNDER_STRETCH:    "hint",
    LAT_UNDER_SQUEEZE:    "hint",
    STRAIGHT_ARM_SETUP:   "warning",
    STRAIGHT_ARM_PULL:    "warning",
    STRAIGHT_ARM_STRETCH: "hint",
    STRAIGHT_ARM_BENT:    "warning",
    AST_PULLUP_SETUP:     "warning",
    AST_PULLUP_PULL:      "warning",
    AST_PULLUP_HANG:      "warning",
    AST_PULLUP_CHIN:      "warning",
    CABLE_ROW_SETUP:      "warning",
    CABLE_ROW_PULL:       "warning",
    CABLE_ROW_STRETCH:    "hint",
    CABLE_ROW_SQUEEZE:    "hint",
    DB_ROW_SETUP:         "warning",
    DB_ROW_PULL:          "warning",
    DB_ROW_STRETCH:       "hint",
    DB_ROW_SQUEEZE:       "hint",
    CHEST_ROW_SETUP:      "warning",
    CHEST_ROW_PULL:       "warning",
    CHEST_ROW_STRETCH:    "hint",
    CHEST_ROW_SQUEEZE:    "hint",
    PENDLAY_ROW_SETUP:    "warning",
    PENDLAY_ROW_PULL:     "warning",
    PENDLAY_ROW_STRETCH:  "hint",
    PENDLAY_ROW_SQUEEZE:  "hint",
    MEADOWS_ROW_SETUP:    "warning",
    MEADOWS_ROW_PULL:     "warning",
    MEADOWS_ROW_STRETCH:  "hint",
    MEADOWS_ROW_SQUEEZE:  "hint",
    TRAP_DEADLIFT_SETUP:  "warning",
    TRAP_DEADLIFT_PULL:   "warning",
    TRAP_DEADLIFT_LOCK:   "warning",
    TRAP_DEADLIFT_DROP:   "warning",
    CONV_DEADLIFT_SETUP:  "warning",
    CONV_DEADLIFT_PULL:   "warning",
    CONV_DEADLIFT_LOCK:   "warning",
    CONV_DEADLIFT_DROP:   "warning",

    # Arms
    PREACHER_CURL_SETUP:  "warning",
    PREACHER_CURL_CURL:   "warning",
    PREACHER_CURL_STRETCH:"hint",
    PREACHER_CURL_PIN:    "warning",
    HAMMER_CURL_SETUP:    "warning",
    HAMMER_CURL_CURL:     "warning",
    HAMMER_CURL_STRETCH:  "hint",
    HAMMER_SWINGING:      "warning",
    HIGH_CABLE_CURL_SETUP:"warning",
    HIGH_CABLE_CURL_CURL: "warning",
    HIGH_CABLE_CURL_STRETCH: "hint",
    HIGH_CABLE_DROP:      "warning",
    INCLINE_DB_CURL_SETUP:"warning",
    INCLINE_DB_CURL_CURL: "warning",
    INCLINE_DB_CURL_STRETCH: "hint",
    INCLINE_DB_CURL_DROP: "warning",
    BARBELL_CURL_SETUP:   "warning",
    BARBELL_CURL_CURL:    "warning",
    BARBELL_CURL_STRETCH: "hint",
    BARBELL_CURL_SWING:   "warning",
    SPIDER_CURL_SETUP:    "warning",
    SPIDER_CURL_CURL:     "warning",
    SPIDER_CURL_STRETCH:  "hint",
    SPIDER_CURL_SQUEEZE:  "hint",
    CHINUP_SETUP:         "warning",
    CHINUP_PULL:          "warning",
    CHINUP_STRETCH:       "hint",
    CHINUP_SQUEEZE:       "hint",
    INVERTED_ROW_SETUP:   "warning",
    INVERTED_ROW_PULL:    "warning",
    INVERTED_ROW_STRETCH: "hint",
    INVERTED_ROW_SQUEEZE: "hint",
    TRICEP_PUSHDOWN_SETUP:"warning",
    TRICEP_PUSHDOWN_PUSH: "warning",
    TRICEP_PUSHDOWN_STRETCH: "hint",
    TRICEP_PUSHDOWN_DROP: "warning",
    TRICEP_PUSHDOWN_ROPE_SETUP: "warning",
    TRICEP_PUSHDOWN_ROPE_PUSH:  "warning",
    TRICEP_PUSHDOWN_ROPE_STRETCH: "hint",
    TRICEP_PUSHDOWN_ROPE_DROP:  "warning",
    OVERHEAD_TRICEP_CABLE_SETUP: "warning",
    OVERHEAD_TRICEP_CABLE_PUSH:  "warning",
    OVERHEAD_TRICEP_CABLE_STRETCH: "hint",
    OVERHEAD_TRICEP_CABLE_DROP:  "warning",
    OVERHEAD_TRICEP_DB_SETUP:    "warning",
    OVERHEAD_TRICEP_DB_PUSH:     "warning",
    OVERHEAD_TRICEP_DB_STRETCH:  "hint",
    OVERHEAD_TRICEP_DB_DROP:     "warning",
    DIAMOND_PUSHUP_SETUP: "warning",
    DIAMOND_PUSHUP_LOWER: "warning",
    DIAMOND_PUSHUP_PUSH:  "warning",
    DIAMOND_PUSHUP_WIDE:  "warning",
    SKULL_CRUSHER_SETUP:  "warning",
    SKULL_CRUSHER_LOWER:  "warning",
    SKULL_CRUSHER_PUSH:   "warning",
    SKULL_CRUSHER_ELBOWS: "warning",
    CLOSE_GRIP_BENCH_SETUP: "warning",
    CLOSE_GRIP_BENCH_LOWER: "warning",
    CLOSE_GRIP_BENCH_PUSH:  "warning",
    CLOSE_GRIP_BENCH_FLARE: "warning",
    TRICEP_DIPS_UPRIGHT_SETUP: "warning",
    TRICEP_DIPS_UPRIGHT_LOWER: "warning",
    TRICEP_DIPS_UPRIGHT_PUSH:  "warning",
    TRICEP_DIPS_UPRIGHT_LEAN:  "warning",

    # Forearms
    WRIST_CURL_SETUP:           "warning",
    WRIST_CURL_CURL:            "warning",
    WRIST_CURL_STRETCH:         "hint",
    WRIST_CURL_DROP:            "warning",
    REVERSE_WRIST_CURL_SETUP:   "warning",
    REVERSE_WRIST_CURL_CURL:    "warning",
    REVERSE_WRIST_CURL_STRETCH: "hint",
    REVERSE_WRIST_CURL_DROP:    "warning",

    # Legs & Lower Body
    LEG_PRESS_SETUP:      "warning",
    LEG_PRESS_LOWER:      "warning",
    LEG_PRESS_PUSH:       "warning",
    LEG_PRESS_DEPTH:      "warning",
    GOBLET_SQUAT_SETUP:   "warning",
    GOBLET_SQUAT_LOWER:   "warning",
    GOBLET_SQUAT_UP:      "warning",
    GOBLET_SQUAT_DEPTH:   "warning",
    LEG_EXTENSION_SETUP:  "warning",
    LEG_EXTENSION_EXTEND: "warning",
    LEG_EXTENSION_LOWER:  "warning",
    LEG_EXTENSION_SQUEEZE:"hint",
    WALKING_LUNGE_SETUP:  "warning",
    WALKING_LUNGE_STEP:   "warning",
    WALKING_LUNGE_LOWER:  "warning",
    WALKING_LUNGE_PUSH:   "warning",
    BARBELL_BACK_SQUAT_SETUP: "warning",
    BARBELL_BACK_SQUAT_LOWER: "warning",
    BARBELL_BACK_SQUAT_UP:    "warning",
    BARBELL_BACK_SQUAT_DEPTH: "warning",
    BARBELL_BACK_SQUAT_KNEE:  "warning",
    HACK_SQUAT_SETUP:     "warning",
    HACK_SQUAT_LOWER:     "warning",
    HACK_SQUAT_PUSH:      "warning",
    HACK_SQUAT_DEPTH:     "warning",
    BULGARIAN_SPLIT_SQUAT_SETUP: "warning",
    BULGARIAN_SPLIT_SQUAT_LOWER: "warning",
    BULGARIAN_SPLIT_SQUAT_UP:    "warning",
    BULGARIAN_SPLIT_SQUAT_DEPTH: "warning",
    LYING_LEG_CURL_SETUP: "warning",
    LYING_LEG_CURL_CURL:  "warning",
    LYING_LEG_CURL_LOWER: "warning",
    LYING_LEG_CURL_KNEE:  "warning",
    ROMANIAN_DEADLIFT_SETUP: "warning",
    ROMANIAN_DEADLIFT_HINGE: "warning",
    ROMANIAN_DEADLIFT_LOWER: "warning",
    ROMANIAN_DEADLIFT_UP:    "warning",
    ROMANIAN_DEADLIFT_BACK:  "warning",
    SINGLE_LEG_RDL_SETUP:    "warning",
    SINGLE_LEG_RDL_HINGE:    "warning",
    SINGLE_LEG_RDL_UP:       "warning",
    SINGLE_LEG_RDL_BALANCE:  "warning",
    NORDIC_CURL_SETUP:    "warning",
    NORDIC_CURL_LOWER:    "warning",
    NORDIC_CURL_CATCH:    "warning",
    NORDIC_CURL_RETURN:   "warning",
    HIP_THRUST_SETUP:     "warning",
    HIP_THRUST_THRUST:    "warning",
    HIP_THRUST_TOP:       "hint",
    HIP_THRUST_LOWER:     "warning",
    CABLE_PULL_THROUGH_SETUP: "warning",
    CABLE_PULL_THROUGH_PULL:  "warning",
    CABLE_PULL_THROUGH_SQUEEZE: "hint",
    CABLE_PULL_THROUGH_HIP:   "warning",
    SUMO_DEADLIFT_SETUP:  "warning",
    SUMO_DEADLIFT_PULL:   "warning",
    SUMO_DEADLIFT_LOCK:   "warning",
    SUMO_DEADLIFT_BACK:   "warning",
    DB_GLUTE_BRIDGE_SETUP:"warning",
    DB_GLUTE_BRIDGE_UP:   "warning",
    DB_GLUTE_BRIDGE_TOP:  "hint",
    DB_GLUTE_BRIDGE_LOWER:"warning",
    GLUTE_KICKBACK_SETUP: "warning",
    GLUTE_KICKBACK_KICK:  "warning",
    GLUTE_KICKBACK_SQUEEZE: "hint",
    GLUTE_KICKBACK_LOWER: "warning",
    SINGLE_LEG_GLUTE_BRIDGE_SETUP: "warning",
    SINGLE_LEG_GLUTE_BRIDGE_UP:    "warning",
    SINGLE_LEG_GLUTE_BRIDGE_SQUEEZE: "hint",
    SINGLE_LEG_GLUTE_BRIDGE_HIP:   "warning",
    SEATED_CALF_RAISE_SETUP:   "warning",
    SEATED_CALF_RAISE_RAISE:   "warning",
    SEATED_CALF_RAISE_SQUEEZE: "hint",
    SEATED_CALF_RAISE_LOWER:   "warning",
    STANDING_CALF_RAISE_SETUP: "warning",
    STANDING_CALF_RAISE_RAISE: "warning",
    STANDING_CALF_RAISE_SQUEEZE: "hint",
    STANDING_CALF_RAISE_LOWER: "warning",
    DONKEY_CALF_RAISE_SETUP:   "warning",
    DONKEY_CALF_RAISE_RAISE:   "warning",
    DONKEY_CALF_RAISE_SQUEEZE: "hint",
    DONKEY_CALF_RAISE_LOWER:   "warning",

    # Core & Accessories
    CABLE_CRUNCH_SETUP:   "warning",
    CABLE_CRUNCH_CRUNCH:  "warning",
    CABLE_CRUNCH_SQUEEZE: "hint",
    CABLE_CRUNCH_FULL:    "warning",
    PLANK_SETUP:          "warning",
    PLANK_HOLD:           "hint",
    PLANK_HIPS_SAGGING:   "warning",
    PLANK_HIPS_HIGH:      "warning",
    HANGING_LEG_RAISE_SETUP:   "warning",
    HANGING_LEG_RAISE_RAISE:   "warning",
    HANGING_LEG_RAISE_SQUEEZE: "hint",
    HANGING_LEG_RAISE_LOWER:   "warning",
    AB_WHEEL_ROLLOUT_SETUP:    "warning",
    AB_WHEEL_ROLLOUT_ROLL:     "warning",
    AB_WHEEL_ROLLOUT_RETURN:   "warning",
    AB_WHEEL_ROLLOUT_CONTROL:  "warning",
    LANDMINE_OBLIQUE_TWIST_SETUP:   "warning",
    LANDMINE_OBLIQUE_TWIST_TWIST:   "warning",
    LANDMINE_OBLIQUE_TWIST_SQUEEZE: "hint",
    LANDMINE_OBLIQUE_TWIST_CONTROL: "warning",
    BACK_EXTENSION_SETUP:   "warning",
    BACK_EXTENSION_UP:      "warning",
    BACK_EXTENSION_SQUEEZE: "hint",
    BACK_EXTENSION_LOWER:   "warning",
    SUPERMAN_HOLD_SETUP:    "warning",
    SUPERMAN_HOLD_HOLD:     "warning",
    SUPERMAN_HOLD_SQUEEZE:  "hint",
    SUPERMAN_HOLD_UP:       "warning",
    BARBELL_SHRUG_SETUP:    "warning",
    BARBELL_SHRUG_SHRUG:    "warning",
    BARBELL_SHRUG_SQUEEZE:  "hint",
    BARBELL_SHRUG_DROP:     "warning",
    DB_SHRUG_SETUP:         "warning",
    DB_SHRUG_SHRUG:         "warning",
    DB_SHRUG_SQUEEZE:       "hint",
    DB_SHRUG_DROP:          "warning",
    ADDUCTOR_MACHINE_SETUP:   "warning",
    ADDUCTOR_MACHINE_SQUEEZE: "hint",
    ADDUCTOR_MACHINE_OPEN:    "warning",
    ADDUCTOR_MACHINE_FULL:    "warning",
    ABDUCTOR_MACHINE_SETUP:   "warning",
    ABDUCTOR_MACHINE_OPEN:    "warning",
    ABDUCTOR_MACHINE_SQUEEZE: "hint",
    ABDUCTOR_MACHINE_CLOSE:   "warning",
}

MOTIVATION_BANK: dict[str, dict[str, list[str]]] = {
    "ar": {
        "starting":    ["ركز من الأول", "يلا ابدأ صح", "خليها نظيفة", "كمّل بتركيز"],
        "middle":      ["كمّل يا بطل", "معاك فيها", "نص الطريق عديت", "ماتوقفش"],
        "final":       ["آخر تلاتة خليهم أحسن", "دفع دلوقتي", "متوقفش هنا", "الآخر ده هو اللي بيفرق"],
        "after_error": ["تصحيح كويس كمّل", "أحسن افضل كده", "شايفك اتحسنت", "كده صح"],
        "clean_set":   ["set نظيف عاش", "ده هو الكلام", "شكل تمامه كده", "احترافي"],
    },
    "en": {
        "starting":    ["Focus from the start", "Let's go clean", "Lock in", "Start strong"],
        "middle":      ["Keep pushing", "Halfway there", "Stay with it", "Don't stop now"],
        "final":       ["Last three, make them count", "Push now", "Don't stop here", "This is where it counts"],
        "after_error": ["Good fix, keep going", "Better, stay like that", "I see the improvement", "That's it"],
        "clean_set":   ["Clean set, let's go", "That's the way", "Perfect form", "Dialed in"],
    },
}


ARABIC_MESSAGES = {
 
    # ── SETUP / VISIBILITY ────────────────────────────────────
    STEP_BACK:        "ارجع لورا عشان أشوف ركبتيك",
    CANT_SEE_BODY:    "مش شايف جسمك من فوق",
    SIT_DOWN:         "اقعد على الكرسي لو سمحت",
 
    # ── BICEP CURL ────────────────────────────────────────────
    RELAX_SHOULDER:   "فك كتفك وارتاح",
    PIN_ELBOW:        "خلي كوعك لازق في جسمك",
    DONT_REST_BODY:   "ماترتكيش على جسمك",
    LIFT_OFF_LEG:     "ارفع كوعك عن ضهرك",
    FULL_EXTENSION:   "افرد دراعك للاخر، ماتغشش",
    SQUEEZE_UP:       "اعصر فوق، ماتنزلش لسه",
 
    # ── TRICEP PUSHDOWN ───────────────────────────────────────
    TUCK_ELBOWS:      "ضم كوعك وماتحركوش لقدام",
    DONT_QUIT:        "ماتوقفش، اعصر لتحت للاخر",
    LOCK_ARMS:        "افرد دراعيك للاخر لتحت",
 
    # ── FLAT DUMBBELL PRESS ───────────────────────────────────
    FLAT_PRESS_SETUP:  "اتحرك ناحية الجنب عشان أشوف دراعك",
    FLAT_PRESS_LOWER:  "نزل الوزن للاخر لصدرك",
    FLAT_PRESS_LOCK:   "افرد دراعيك للاخر فوق",
    FLAT_PRESS_DROP:   "نزل كوعك لتحت أكتر عشان تحس بالإطالة",
 
    # ── SHOULDER PRESS ────────────────────────────────────────
    KEEP_BACK_STRAIGHT:   "خلي ضهرك مستقيم",
    GOOD_REP:             "عاش، عدة ممتازة",
    GO_DOWN:              "انزل للاخر",
    PUSH_UP_FULLY:        "ادفع لفوق للاخر",
    KEEP_BOTH_ARMS_EQUAL: "خلي دراعيك متساويين",
    STABILIZE_YOUR_HIPS:  "ثبت وردكيك وماتتحركش",
 
    # ── TBAR ROW ──────────────────────────────────────────────
    TBAR_SETUP:      "اعرض جانبك للكاميرا",
    TBAR_PULL_MORE:  "اسحب للاخر لصدرك",
    TBAR_EXTENSION:  "افرد دراعيك للاخر لتحت",
 
    # ── INCLINE DUMBBELL PRESS ────────────────────────────────
    INCLINE_DB_SETUP:  "اتحرك ناحية الجنب عشان أشوف دراعك",
    INCLINE_DB_LOWER:  "نزل الدمبلز على صدرك العلوي",
    INCLINE_DB_LOCK:   "افرد دراعيك للاخر فوق",
    INCLINE_DB_DROP:   "نزل كوعك أكتر عشان تحس بالإطالة",
 
    # ── INCLINE BARBELL PRESS ─────────────────────────────────
    INCLINE_BB_SETUP:  "اتحرك ناحية الجنب عشان أشوف دراعك",
    INCLINE_BB_LOWER:  "نزل البار على صدرك العلوي",
    INCLINE_BB_LOCK:   "افرد دراعيك للاخر فوق",
    INCLINE_BB_TOUCH:  "لمس صدرك بالبار",
 
    # ── CABLE FLY LOW TO HIGH ─────────────────────────────────
    FLY_L2H_SETUP:   "اعرض جانبك عشان أشوف جسمك كله",
    FLY_L2H_STRETCH: "ارجع بإيديك لورا عشان تحس بالإطالة",
    FLY_L2H_SQUEEZE: "جيب إيديك لبعض واعصر صدرك السفلي",
    FLY_L2H_BENT:    "خلي كوعك مني شوية بس ماتتحركش",
 
    # ── LANDMINE PRESS ────────────────────────────────────────
    LANDMINE_PRESS_SETUP:  "اتحرك ناحية الجنب عشان أشوف دراعك",
    LANDMINE_PRESS_LOWER:  "نزل البار للاخر على صدرك",
    LANDMINE_PRESS_LOCK:   "افرد دراعك للاخر فوق",
    LANDMINE_PRESS_DROP:   "نزل كوعك للاخر",
 
    # ── FLAT BARBELL BENCH PRESS ──────────────────────────────
    FLAT_BB_SETUP:  "اتحرك ناحية الجنب عشان أشوف دراعك",
    FLAT_BB_LOWER:  "نزل البار على صدرك",
    FLAT_BB_LOCK:   "افرد دراعيك للاخر فوق",
    FLAT_BB_TOUCH:  "لمس صدرك بالبار",
 
    # ── CABLE FLY HIGH TO LOW ─────────────────────────────────
    FLY_H2L_SETUP:   "اعرض جانبك عشان أشوف جسمك كله",
    FLY_H2L_STRETCH: "ارجع بإيديك لورا عشان تحس بالإطالة",
    FLY_H2L_SQUEEZE: "جيب إيديك لبعض واعصر لتحت",
    FLY_H2L_BENT:    "خلي كوعك مني شوية بس ماتتحركش",
 
    # ── MACHINE CHEST PRESS ───────────────────────────────────
    MACHINE_PRESS_SETUP:  "اتحرك ناحية الجنب عشان أشوف دراعك",
    MACHINE_PRESS_LOWER:  "رجع الهاندلز للاخر لورا",
    MACHINE_PRESS_LOCK:   "افرد دراعيك للاخر",
    MACHINE_PRESS_DROP:   "نزل أكتر من كده",
 
    # ── DUMBBELL FLOOR PRESS ──────────────────────────────────
    FLOOR_PRESS_SETUP:  "اتحرك ناحية الجنب عشان أشوف دراعك",
    FLOOR_PRESS_LOWER:  "نزل لحد ما ترايسبسك يلمس الأرض",
    FLOOR_PRESS_LOCK:   "افرد دراعيك للاخر فوق",
    FLOOR_PRESS_DROP:   "لمس الأرض بهدوء",
 
    # ── CHEST DIPS ────────────────────────────────────────────
    DIPS_SETUP:  "اعرض جانبك للكاميرا",
    DIPS_LOWER:  "انزل أعمق عشان تحس بالإطالة في الصدر",
    DIPS_LOCK:   "ادفع لفوق للاخر وافرد دراعيك",
    DIPS_LEAN:   "مايل لقدام شوية عشان تشتغل صدرك",
 
    # ── DECLINE PUSH-UP ───────────────────────────────────────
    DECLINE_PUSHUP_SETUP:  "اعرض جانبك للكاميرا",
    DECLINE_PUSHUP_LOWER:  "انزل أكتر، صدرك يوصل للأرض",
    DECLINE_PUSHUP_LOCK:   "افرد دراعيك للاخر فوق",
    DECLINE_PUSHUP_DROP:   "انزل لتحت",
 
    # ── ARCHER PUSH-UP ────────────────────────────────────────
    ARCHER_PUSHUP_SETUP:    "اعرض الدراع اللي بتتني بيها للكاميرا",
    ARCHER_PUSHUP_LOWER:    "نزل الدراع اللي بتتني بيها أكتر",
    ARCHER_PUSHUP_LOCK:     "ادفع لفوق وافرد دراعك",
    ARCHER_PUSHUP_STRAIGHT: "خلي الدراع التانية مستقيمة تماماً",
 
    # ── LAT PULLDOWN WIDE ─────────────────────────────────────
    LAT_WIDE_SETUP:   "اتحرك ناحية الجنب عشان أشوف وردكيك",
    LAT_WIDE_PULL:    "ادفع كوعك لتحت لجنبك",
    LAT_WIDE_STRETCH: "افرد دراعيك للاخر لفوق",
    LAT_WIDE_SQUEEZE: "اعصر اللات",
 
    # ── PULL UP ───────────────────────────────────────────────
    PULLUP_SETUP:  "اعرض جانبك للكاميرا",
    PULLUP_PULL:   "اطلع لفوق لحد ما دقنك يعدي البار",
    PULLUP_HANG:   "انزل للاخر وافرد دراعيك",
    PULLUP_CHIN:   "ارفع صدرك لفوق",
 
    # ── LAT PULLDOWN UNDERHAND ────────────────────────────────
    LAT_UNDER_SETUP:   "اعرض جانبك عشان أشوف وردكيك ودراعيك",
    LAT_UNDER_PULL:    "اسحب البار لصدرك",
    LAT_UNDER_STRETCH: "افرد دراعيك للاخر لفوق",
    LAT_UNDER_SQUEEZE: "اعصر ضهرك",
 
    # ── STRAIGHT ARM PULLDOWN ─────────────────────────────────
    STRAIGHT_ARM_SETUP:    "اقف بالجنب عشان أشوف جسمك كله",
    STRAIGHT_ARM_PULL:     "اسحب البار للاخر لأوراكك",
    STRAIGHT_ARM_STRETCH:  "ارفع دراعيك فوق للإطالة",
    STRAIGHT_ARM_BENT:     "خلي دراعيك مستقيمين تماماً",
 
    # ── MACHINE ASSISTED PULL-UP ──────────────────────────────
    AST_PULLUP_SETUP:  "اوقف على الباد واعرض جانبك",
    AST_PULLUP_PULL:   "اطلع لفوق للاخر",
    AST_PULLUP_HANG:   "انزل للاخر وحس بالإطالة",
    AST_PULLUP_CHIN:   "ارفع صدرك لفوق",
 
    # ── SEATED CABLE ROW ──────────────────────────────────────
    CABLE_ROW_SETUP:   "اقعد منتصب واعرض جانبك",
    CABLE_ROW_PULL:    "اسحب الهاندل لبطنك",
    CABLE_ROW_STRETCH: "افرد دراعيك للاخر لقدام",
    CABLE_ROW_SQUEEZE: "اعصر لوح كتفك مع بعض",
 
    # ── SINGLE ARM DUMBBELL ROW ───────────────────────────────
    DB_ROW_SETUP:    "اتكي وعرض الدراع الشغالة للكاميرا",
    DB_ROW_PULL:     "اسحب الدمبل لوركك",
    DB_ROW_STRETCH:  "نزل الدمبل للاخر لتحت",
    DB_ROW_SQUEEZE:  "اعصر ضهرك فوق",
    LATERAL_DB_BENT: "ماتتنيش كوعك أوي، خلي في انحناء بسيط بس",
 
    # ── CHEST-SUPPORTED ROW ───────────────────────────────────
    CHEST_ROW_SETUP:   "استلقي على الباد واعرض جانبك",
    CHEST_ROW_PULL:    "اسحب الهاندلز ورا جسمك",
    CHEST_ROW_STRETCH: "سيب الوزن يسحبك لقدام",
    CHEST_ROW_SQUEEZE: "اعصر قوي فوق",
 
    # ── BARBELL ROW (PENDLAY) ─────────────────────────────────
    PENDLAY_ROW_SETUP:   "اتخذ وضعية الحنية واعرض جانبك",
    PENDLAY_ROW_PULL:    "اسحب البار بقوة لصدرك",
    PENDLAY_ROW_STRETCH: "حط البار على الأرض بين كل عدة",
    PENDLAY_ROW_SQUEEZE: "اعصر وسط ضهرك",
 
    # ── MEADOWS ROW ───────────────────────────────────────────
    MEADOWS_ROW_SETUP:   "وسع بين قدميك واعرض الدراع الشغالة",
    MEADOWS_ROW_PULL:    "اسحب البار لفوق وللجنب",
    MEADOWS_ROW_STRETCH: "انزل للاخر للإطالة",
    MEADOWS_ROW_SQUEEZE: "اعصر فوق",
 
    # ── TRAP BAR DEADLIFT ─────────────────────────────────────
    TRAP_DEADLIFT_SETUP:  "اوقف جوا البار واعرض جانبك",
    TRAP_DEADLIFT_PULL:   "ادفع الأرض بقدميك",
    TRAP_DEADLIFT_LOCK:   "افرد وردكيك للاخر فوق",
    TRAP_DEADLIFT_DROP:   "نزل الوزن بتحكم",
 
    # ── CONVENTIONAL DEADLIFT ─────────────────────────────────
    CONV_DEADLIFT_SETUP:  "اقترب من البار واعرض جانبك",
    CONV_DEADLIFT_PULL:   "ادفع الأرض وجيب وردكيك لقدام",
    CONV_DEADLIFT_LOCK:   "افرد وردكيك للاخر فوق",
    CONV_DEADLIFT_DROP:   "إرجع لورا ونزل بتحكم",
 
    # ── SEATED DB SHOULDER PRESS ──────────────────────────────
    SEATED_DB_PRESS_SETUP:  "اقعد منتصب واعرض جانبك",
    SEATED_DB_PRESS_LOWER:  "نزل الدمبلز لحد ما يلمسوا كتفك",
    SEATED_DB_PRESS_LOCK:   "افرد دراعيك للاخر فوق",
    SEATED_DB_PRESS_DROP:   "نزل كوعك",
 
    # ── MACHINE SHOULDER PRESS ────────────────────────────────
    MACHINE_PRESS_SHOULDER_SETUP:  "اقعد منتصب واعرض جانبك",
    MACHINE_PRESS_SHOULDER_LOWER:  "نزل الهاندلز للاخر",
    MACHINE_PRESS_SHOULDER_LOCK:   "افرد دراعيك للاخر فوق",
    MACHINE_PRESS_SHOULDER_DROP:   "نزل لتحت",
 
    # ── OVERHEAD PRESS (BARBELL) ──────────────────────────────
    OHP_BARBELL_SETUP:  "اوقف منتصب واعرض جانبك",
    OHP_BARBELL_LOWER:  "نزل البار على ترقوتك",
    OHP_BARBELL_LOCK:   "دفع راسك للأمام وافرد دراعيك",
    OHP_BARBELL_DROP:   "نزل البار للاخر لتحت",
 
    # ── ARNOLD PRESS ──────────────────────────────────────────
    ARNOLD_PRESS_SETUP:  "اعرض جانبك للكاميرا",
    ARNOLD_PRESS_LOWER:  "لف الدمبلز لجوا لتحت",
    ARNOLD_PRESS_LOCK:   "لف لبرا وادفع لفوق",
    ARNOLD_PRESS_DROP:   "نزلهم قدام وشك",
 
    # ── LATERAL RAISES ────────────────────────────────────────
    LATERAL_MACHINE_SETUP:    "اوقف بوشك للكاميرا للرفعات الجانبية",
    LATERAL_MACHINE_RAISE:    "ارفع دراعيك لمستوى كتفك",
    LATERAL_MACHINE_LOWER:    "نزل الوزن بتحكم",
    LATERAL_MACHINE_TOO_HIGH: "ماترفعش فوق مستوى كتفك",
 
    LATERAL_CABLE_SETUP:    "اقف بالجنب للكابل واعرض وشك",
    LATERAL_CABLE_RAISE:    "ارفع الكابل لبرا ولفوق",
    LATERAL_CABLE_LOWER:    "مقاوم الكابل وهو بيسحبك لتحت",
    LATERAL_CABLE_TOO_HIGH: "وقف لما دراعك يبقى موازي للأرض",
 
    LATERAL_DB_SETUP:    "اقف بوشك للكاميرا",
    LATERAL_DB_RAISE:    "ارفع كوعك وارفع دراعك",
    LATERAL_DB_LOWER:    "نزل الدمبلز ببطء",
    LATERAL_DB_TOO_HIGH: "ماترفعش إيدك أعلى من كتفك",
 
    LATERAL_LANDMINE_SETUP:    "اقف بوشك للكاميرا وامسك البار",
    LATERAL_LANDMINE_RAISE:    "ادفع البار لفوق وللجنب",
    LATERAL_LANDMINE_LOWER:    "نزل البار بتحكم",
    LATERAL_LANDMINE_TOO_HIGH: "ماترفعش لفوق أوي",
 
    # ── REAR DELT ─────────────────────────────────────────────
    FACE_PULL_SETUP:    "اعرض جانبك عشان أشوف السحبة",
    FACE_PULL_PULL:     "اسحب الروب لوشك وافرده",
    FACE_PULL_STRETCH:  "سيب الروب يسحب دراعيك لقدام",
    FACE_PULL_SQUEEZE:  "اعصر الدلتا الخلفية",
 
    REAR_CABLE_FLY_SETUP:    "اعرض جانبك للكاميرا",
    REAR_CABLE_FLY_PULL:     "اسحب الكابلز للجنبين لورا",
    REAR_CABLE_FLY_STRETCH:  "سيب دراعيك يتقاطعوا قدامك",
    REAR_CABLE_FLY_SQUEEZE:  "اعصر الدلتا الخلفية",
 
    REV_PEC_DECK_SETUP:    "اقعد على الماكينة واعرض جانبك",
    REV_PEC_DECK_PULL:     "ادفع الهاندلز للاخر لورا",
    REV_PEC_DECK_STRETCH:  "سيب الهاندلز يتقابلوا قدامك",
    REV_PEC_DECK_SQUEEZE:  "اعصر ضهرك العلوي",
 
    # ── BICEP CURLS ───────────────────────────────────────────
    PREACHER_CURL_SETUP:    "اقعد على بنش البريتشر واعرض جانبك",
    PREACHER_CURL_CURL:     "ارفع الوزن لفوق لدقنك",
    PREACHER_CURL_STRETCH:  "انزل للاخر عشان تحس بالإطالة",
    PREACHER_CURL_PIN:      "خلي كوعك على الباد ماترفعوش",
 
    HAMMER_CURL_SETUP:   "اقف بالجنب عشان أشوف دراعك",
    HAMMER_CURL_CURL:    "ارفع الوزن لفوق للاخر",
    HAMMER_CURL_STRETCH: "افرد دراعك للاخر لتحت",
    HAMMER_SWINGING:     "ماتمرجحش جسمك، اِثْبَت",
 
    HIGH_CABLE_CURL_SETUP:   "اقف قبال الكابل العالي واعرض جانبك",
    HIGH_CABLE_CURL_CURL:    "ارفع الهاندل لراسك",
    HIGH_CABLE_CURL_STRETCH: "افرد دراعيك للاخر لتحت",
    HIGH_CABLE_DROP:         "نزل كوعك لمستوى كتفك",
 
    INCLINE_DB_CURL_SETUP:    "اقعد على البنش المائل واعرض جانبك",
    INCLINE_DB_CURL_CURL:     "ارفع الدمبلز لفوق للاخر",
    INCLINE_DB_CURL_STRETCH:  "انزل للاخر عشان الإطالة",
    INCLINE_DB_CURL_DROP:     "نزل كوعك أكتر للإطالة الأعمق",
 
    BARBELL_CURL_SETUP:    "اقف مع البار واعرض جانبك",
    BARBELL_CURL_CURL:     "ارفع البار لصدرك",
    BARBELL_CURL_STRETCH:  "انزل للاخر وافرد دراعيك",
    BARBELL_CURL_SWING:    "ماتمرجحش البار، تحكم في الحركة",
 
    SPIDER_CURL_SETUP:    "استلقي على البطن على البنش المائل واعرض جانبك",
    SPIDER_CURL_CURL:     "ارفع الدمبلز لجبهتك",
    SPIDER_CURL_STRETCH:  "انزل للاخر وحس بالإطالة",
    SPIDER_CURL_SQUEEZE:  "اعصر قوي فوق",
 
    # ── CHIN-UP & INVERTED ROW ────────────────────────────────
    CHINUP_SETUP:    "اتعلق في البار بقبضة تحتية واعرض جانبك",
    CHINUP_PULL:     "اطلع لحد ما دقنك يعدي البار",
    CHINUP_STRETCH:  "انزل للاخر وافرد دراعيك",
    CHINUP_SQUEEZE:  "اعصر الباي سبس فوق",
 
    INVERTED_ROW_SETUP:    "اتعلق تحت البار بقبضة تحتية واعرض جانبك",
    INVERTED_ROW_PULL:     "اسحب صدرك للبار",
    INVERTED_ROW_STRETCH:  "انزل وافرد دراعيك للاخر",
    INVERTED_ROW_SQUEEZE:  "اعصر ضهرك والباي سبس فوق",
 
    # ── TRICEP EXERCISES ──────────────────────────────────────
    TRICEP_PUSHDOWN_SETUP:    "اقف قبال الماكينة واعرض جانبك",
    TRICEP_PUSHDOWN_PUSH:     "ادفع البار لتحت وافرد دراعيك",
    TRICEP_PUSHDOWN_STRETCH:  "افرد دراعيك للاخر لفوق",
    TRICEP_PUSHDOWN_DROP:     "نزل كوعك أكتر عشان تشغل الترايسبس",
 
    TRICEP_PUSHDOWN_ROPE_SETUP:    "امسك الروب واعرض جانبك",
    TRICEP_PUSHDOWN_ROPE_PUSH:     "ادفع الروب لتحت واعزله",
    TRICEP_PUSHDOWN_ROPE_STRETCH:  "افرد دراعيك للاخر لفوق",
    TRICEP_PUSHDOWN_ROPE_DROP:     "نزل كوعك لورا",
 
    OVERHEAD_TRICEP_CABLE_SETUP:   "اقف بوشك للكابل السفلي والروب ورا راسك",
    OVERHEAD_TRICEP_CABLE_PUSH:    "ادفع الروب لتحت وافرد دراعيك",
    OVERHEAD_TRICEP_CABLE_STRETCH: "خلي كوعك عالي للإطالة الكاملة",
    OVERHEAD_TRICEP_CABLE_DROP:    "نزل الوزن ببطء",
 
    OVERHEAD_TRICEP_DB_SETUP:    "امسك الدمبل فوق راسك واعرض جانبك",
    OVERHEAD_TRICEP_DB_PUSH:     "ادفع الدمبل لتحت وافرد دراعك",
    OVERHEAD_TRICEP_DB_STRETCH:  "خلي كوعك عالي للإطالة الأعمق",
    OVERHEAD_TRICEP_DB_DROP:     "نزل الوزن ورا راسك",
    OVERHEAD_KEEP_ELBOWS_HIGH:   "ارفع كوعك لفوق وثبته",
 
    DIAMOND_PUSHUP_SETUP:   "اتخذ وضعية الضغط وقرب إيديك من بعض",
    DIAMOND_PUSHUP_LOWER:   "انزل صدرك لإيديك",
    DIAMOND_PUSHUP_PUSH:    "ادفع لفوق وافرد دراعيك",
    DIAMOND_PUSHUP_WIDE:    "قرب إيديك أكتر عشان تشغل الترايسبس أكتر",
 
    SKULL_CRUSHER_SETUP:    "استلقي على البنش وامسك البار فوق راسك",
    SKULL_CRUSHER_LOWER:    "نزل البار لجبهتك",
    SKULL_CRUSHER_PUSH:     "ارفع البار للاخر وافرد دراعيك",
    SKULL_CRUSHER_ELBOWS:   "خلي كوعك ثابت لفوق",
 
    CLOSE_GRIP_BENCH_SETUP:   "استلقي على البنش وامسك البار بقبضة ضيقة",
    CLOSE_GRIP_BENCH_LOWER:   "نزل البار لصدرك",
    CLOSE_GRIP_BENCH_PUSH:    "ادفع لفوق وافرد دراعيك",
    CLOSE_GRIP_BENCH_FLARE:   "ماتفتحش كوعك، خليه لازق",
 
    TRICEP_DIPS_UPRIGHT_SETUP:   "اقف بين بارين الديبس واعرض جانبك",
    TRICEP_DIPS_UPRIGHT_LOWER:   "انزل وانني كوعك",
    TRICEP_DIPS_UPRIGHT_PUSH:    "ادفع لفوق وافرد دراعيك",
    TRICEP_DIPS_UPRIGHT_LEAN:    "مايل لقدام شوية عشان الترايسبس",
 
    # ── FOREARM EXERCISES ─────────────────────────────────────
    WRIST_CURL_SETUP:    "اقعد وامسك البار بقبضة تحتية",
    WRIST_CURL_CURL:     "ارفع رسغيك لفوق",
    WRIST_CURL_STRETCH:  "انزل ومد ساعدك",
    WRIST_CURL_DROP:     "ماتستخدمش الباي سبس، حرك رسغك بس",
 
    REVERSE_WRIST_CURL_SETUP:    "اقعد وامسك البار بقبضة فوقية",
    REVERSE_WRIST_CURL_CURL:     "ارفع رسغيك لفوق",
    REVERSE_WRIST_CURL_STRETCH:  "انزل ومد ساعدك",
    REVERSE_WRIST_CURL_DROP:     "خلي دراعيك مستقيمين",
 
    # ── QUAD EXERCISES ────────────────────────────────────────
    LEG_PRESS_SETUP:   "اقعد في ماكينة الليج بريس واعرض جانبك",
    LEG_PRESS_LOWER:   "نزل الوزن لحد ما ركبتك تتني تسعين درجة",
    LEG_PRESS_PUSH:    "ادفع الوزن لفوق وافرد رجليك",
    LEG_PRESS_DEPTH:   "انزل أعمق، كسر الموازاة للرانج الكامل",
 
    GOBLET_SQUAT_SETUP:   "امسك الدمبل لصدرك واعرض جانبك",
    GOBLET_SQUAT_LOWER:   "انزل لحد ما فخدك يبقى موازي للأرض",
    GOBLET_SQUAT_UP:      "اطلع لفوق من كعبيك",
    GOBLET_SQUAT_DEPTH:   "انزل أعمق، كسر الموازاة",
 
    LEG_EXTENSION_SETUP:    "اقعد في ماكينة الليج إكستنشن واعرض جانبك",
    LEG_EXTENSION_EXTEND:   "افرد رجليك للاخر فوق",
    LEG_EXTENSION_LOWER:    "نزل الوزن بتحكم",
    LEG_EXTENSION_SQUEEZE:  "اعصر الكواد فوق",
 
    WALKING_LUNGE_SETUP:   "اقف واعرض جانبك للانجز",
    WALKING_LUNGE_STEP:    "خطوة لقدام",
    WALKING_LUNGE_LOWER:   "انزل لحد ما ركبتيك تتنوا تسعين درجة",
    WALKING_LUNGE_PUSH:    "ادفع لفوق من كعب رجلك الأمامية",
 
    BARBELL_BACK_SQUAT_SETUP:   "حط البار على ضهرك العلوي واعرض جانبك",
    BARBELL_BACK_SQUAT_LOWER:   "انزل لحد ما فخدك يكسر الموازاة",
    BARBELL_BACK_SQUAT_UP:      "اطلع من كعبيك واعصر الجلوت",
    BARBELL_BACK_SQUAT_DEPTH:   "انزل أعمق، كسر الموازاة",
    BARBELL_BACK_SQUAT_KNEE:    "ماتخليش ركبتيك تميل لجوا، دفعهم لبرا",
 
    HACK_SQUAT_SETUP:   "اتخذ وضعيتك في ماكينة الهاك سكوات واعرض جانبك",
    HACK_SQUAT_LOWER:   "انزل لحد ما فخدك يبقى موازي للمنصة",
    HACK_SQUAT_PUSH:    "ادفع لفوق وافرد رجليك",
    HACK_SQUAT_DEPTH:   "انزل أعمق لتشغيل الكواد أكتر",
 
    BULGARIAN_SPLIT_SQUAT_SETUP:   "حط رجل على البنش واعرض جانبك",
    BULGARIAN_SPLIT_SQUAT_LOWER:   "انزل لحد ما فخدك الأمامي يبقى موازي للأرض",
    BULGARIAN_SPLIT_SQUAT_UP:      "ادفع لفوق من كعب رجلك الأمامية",
    BULGARIAN_SPLIT_SQUAT_DEPTH:   "انزل أعمق، فخدك الأمامي موازي للأرض",
 
    # ── HAMSTRING EXERCISES ───────────────────────────────────
    LYING_LEG_CURL_SETUP:   "استلقي على بطنك في ماكينة الليج كيرل واعرض جانبك",
    LYING_LEG_CURL_CURL:    "ارفع رجليك لفوق واعصر",
    LYING_LEG_CURL_LOWER:   "انزل بتحكم للإطالة الكاملة",
    LYING_LEG_CURL_KNEE:    "ماترفعش وردكيك، افضل مستلقي على الباد",
 
    ROMANIAN_DEADLIFT_SETUP:   "امسك البار واعرض جانبك",
    ROMANIAN_DEADLIFT_HINGE:   "اتني من الوسط وادفع وردكيك لورا",
    ROMANIAN_DEADLIFT_LOWER:   "نزل البار على طول رجليك",
    ROMANIAN_DEADLIFT_UP:      "ادفع وردكيك لقدام واعصر",
    ROMANIAN_DEADLIFT_BACK:    "خلي ضهرك مستقيم، ماترجعوش",
 
    SINGLE_LEG_RDL_SETUP:     "اقف على رجل وإيدك جانبك واعرض جانبك",
    SINGLE_LEG_RDL_HINGE:     "اتني من الوسط ونزل الوزن",
    SINGLE_LEG_RDL_UP:        "ادفع وردكيك لقدام",
    SINGLE_LEG_RDL_BALANCE:   "اتزن، وكور محكوم",
 
    NORDIC_CURL_SETUP:    "ركع على الباد واعرض جانبك",
    NORDIC_CURL_LOWER:    "نزل جسمك لقدام ببطء",
    NORDIC_CURL_CATCH:    "اتمسك بإيديك",
    NORDIC_CURL_RETURN:   "ارجع لوضعية البداية",
 
    # ── GLUTE EXERCISES ───────────────────────────────────────
    HIP_THRUST_SETUP:    "اقعد وضهرك العلوي على البنش والبار على وردكيك",
    HIP_THRUST_THRUST:   "ادفع وردكيك لفوق واعصر الجلوت",
    HIP_THRUST_TOP:      "اعصر قوي فوق، مد وردكيك كامل",
    HIP_THRUST_LOWER:    "نزل بتحكم",
 
    CABLE_PULL_THROUGH_SETUP:    "قف بضهرك للكابل وامسك الروب من بين رجليك",
    CABLE_PULL_THROUGH_PULL:     "اسحب الروب من بين رجليك وادفع وردكيك لقدام",
    CABLE_PULL_THROUGH_SQUEEZE:  "اعصر الجلوت فوق",
    CABLE_PULL_THROUGH_HIP:      "ادفع وردكيك لقدام، ماتسحبش بدراعيك",
 
    SUMO_DEADLIFT_SETUP:   "اوقف بقدمين واسعين واعرض جانبك",
    SUMO_DEADLIFT_PULL:    "ادفع من كعبيك واسحب لفوق",
    SUMO_DEADLIFT_LOCK:    "افرد وردكيك للاخر فوق",
    SUMO_DEADLIFT_BACK:    "خلي ضهرك مستقيم",
 
    DB_GLUTE_BRIDGE_SETUP:    "استلقي على ضهرك والدمبل على وردكيك",
    DB_GLUTE_BRIDGE_UP:       "ارفع وردكيك واعصر الجلوت",
    DB_GLUTE_BRIDGE_TOP:      "اعصر قوي فوق",
    DB_GLUTE_BRIDGE_LOWER:    "انزل بتحكم",
 
    GLUTE_KICKBACK_SETUP:    "اقف على إيديك وركبيك واعرض جانبك",
    GLUTE_KICKBACK_KICK:     "ارفع رجلك لورا ولفوق",
    GLUTE_KICKBACK_SQUEEZE:  "اعصر الجلوت فوق",
    GLUTE_KICKBACK_LOWER:    "نزل بتحكم",
 
    SINGLE_LEG_GLUTE_BRIDGE_SETUP:    "استلقي على ضهرك ومد رجل",
    SINGLE_LEG_GLUTE_BRIDGE_UP:       "ارفع وردكيك لفوق",
    SINGLE_LEG_GLUTE_BRIDGE_SQUEEZE:  "اعصر الجلوت قوي فوق",
    SINGLE_LEG_GLUTE_BRIDGE_HIP:      "خلي وردكيك متساوية، ماتميلش",
 
    # ── CALF EXERCISES ────────────────────────────────────────
    SEATED_CALF_RAISE_SETUP:    "اقعد على ماكينة الكالف ريز والركبة تحت الباد",
    SEATED_CALF_RAISE_RAISE:    "ارفع كعبيك للاخر",
    SEATED_CALF_RAISE_SQUEEZE:  "اعصر الكالف فوق",
    SEATED_CALF_RAISE_LOWER:    "انزل للاخر للإطالة الكاملة",
 
    STANDING_CALF_RAISE_SETUP:    "اوقف على منصة الكالف واعرض جانبك",
    STANDING_CALF_RAISE_RAISE:    "ارفع كعبيك للاخر",
    STANDING_CALF_RAISE_SQUEEZE:  "اعصر الكالف فوق",
    STANDING_CALF_RAISE_LOWER:    "انزل للاخر ومد الكالف",
 
    DONKEY_CALF_RAISE_SETUP:    "اتني على ماكينة الدونكي كالف واعرض جانبك",
    DONKEY_CALF_RAISE_RAISE:    "ارفع كعبيك لفوق",
    DONKEY_CALF_RAISE_SQUEEZE:  "اعصر قوي فوق",
    DONKEY_CALF_RAISE_LOWER:    "انزل للاخر للإطالة الأعمق",
 
    # ── ABS / CORE EXERCISES ──────────────────────────────────
    CABLE_CRUNCH_SETUP:    "اركع قبال الماكينة وامسك الروب",
    CABLE_CRUNCH_CRUNCH:   "اتني لتحت واعصر بطنك",
    CABLE_CRUNCH_SQUEEZE:  "اعصر قوي لتحت",
    CABLE_CRUNCH_FULL:     "استخدم الرانج الكامل",
 
    PLANK_SETUP:        "اتخذ وضعية الضغط على ساعديك",
    PLANK_HOLD:         "اتمسك، كور محكوم",
    PLANK_HIPS_SAGGING: "ماتهبطش وردكيك، ارفعهم",
    PLANK_HIPS_HIGH:    "نزل وردكيك، ماتعملش بايك أب",
 
    HANGING_LEG_RAISE_SETUP:    "اتعلق في بار البولاب واعرض جانبك",
    HANGING_LEG_RAISE_RAISE:    "ارفع رجليك لفوق",
    HANGING_LEG_RAISE_SQUEEZE:  "اعصر بطنك فوق",
    HANGING_LEG_RAISE_LOWER:    "انزل بتحكم",
 
    AB_WHEEL_ROLLOUT_SETUP:    "اركع على الأرض وامسك العجلة",
    AB_WHEEL_ROLLOUT_ROLL:     "اتمدد لقدام",
    AB_WHEEL_ROLLOUT_RETURN:   "ارجع لوضعية البداية",
    AB_WHEEL_ROLLOUT_CONTROL:  "تحكم في الحركة، ماتهبطش",
 
    LANDMINE_OBLIQUE_TWIST_SETUP:    "اقف مع اللاندماين واعرض جانبك",
    LANDMINE_OBLIQUE_TWIST_TWIST:    "تلوي واسحب بعضلة الأوبليك",
    LANDMINE_OBLIQUE_TWIST_SQUEEZE:  "اعصر الأوبليك",
    LANDMINE_OBLIQUE_TWIST_CONTROL:  "تحكم في اللف",
 
    # ── LOWER BACK ────────────────────────────────────────────
    BACK_EXTENSION_SETUP:    "استلقي على بطنك على بنش الهايبر إكستنشن",
    BACK_EXTENSION_UP:       "ارفع جسمك العلوي لفوق",
    BACK_EXTENSION_SQUEEZE:  "اعصر ضهرك السفلي فوق",
    BACK_EXTENSION_LOWER:    "انزل بتحكم",
 
    SUPERMAN_HOLD_SETUP:    "استلقي على بطنك على الأرض ومد دراعيك",
    SUPERMAN_HOLD_HOLD:     "ارفع دراعيك ورجليك واتمسك",
    SUPERMAN_HOLD_SQUEEZE:  "اعصر ضهرك السفلي",
    SUPERMAN_HOLD_UP:       "ارفع أكتر",
 
    # ── TRAP EXERCISES ────────────────────────────────────────
    BARBELL_SHRUG_SETUP:    "امسك البار بإيتين وعرض وشك",
    BARBELL_SHRUG_SHRUG:    "ارفع كتفيك لفوق",
    BARBELL_SHRUG_SQUEEZE:  "اعصر التراب فوق",
    BARBELL_SHRUG_DROP:     "انزل ببطء ماتهبطش",
 
    DB_SHRUG_SETUP:    "امسك الدمبلز جنبك واعرض وشك",
    DB_SHRUG_SHRUG:    "ارفع كتفيك لفوق",
    DB_SHRUG_SQUEEZE:  "اعصر التراب فوق",
    DB_SHRUG_DROP:     "انزل ببطء",
 
    # ── ADDUCTOR / ABDUCTOR ───────────────────────────────────
    ADDUCTOR_MACHINE_SETUP:    "اقعد في ماكينة الأداكتور ورجليك متفرقين",
    ADDUCTOR_MACHINE_SQUEEZE:  "ضم رجليك مع بعض",
    ADDUCTOR_MACHINE_OPEN:     "افتح بتحكم للإطالة",
    ADDUCTOR_MACHINE_FULL:     "رانج كامل",
 
    ABDUCTOR_MACHINE_SETUP:    "اقعد في ماكينة الأباكتور ورجليك مع بعض",
    ABDUCTOR_MACHINE_OPEN:     "افتح رجليك للجنبين",
    ABDUCTOR_MACHINE_SQUEEZE:  "اعصر فوق",
    ABDUCTOR_MACHINE_CLOSE:    "اقفل بتحكم",
 
    # ── GOBLET SQUAT CHEST ────────────────────────────────────
    GOBLET_SQUAT_CHEST: "ارفع صدرك لفوق وماتميلش بضهرك لقدام",
}


class AICoach:
    """
    AI Coach v4.4 — fully local, severity-based cooldowns, Smart Silence,
    time-based debouncing for transient pose noise.
    Changes vs v4.3:
      • ERROR_GRACE_PERIOD = 0.8 s : errors must persist before speaking
      • _error_start_time   : tracks first-seen timestamp per error
      • on_error            : debounced — speaks only after grace period,
                              or immediately if urgent=True
      • reset_error         : clears timer completely for that error
    """

    def __init__(self, language="ar"):
        # ── AUDIO SETUP ─────────────────────────────────────────
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=4096)

        # ── THREAD SAFETY ───────────────────────────────────────
        self._cache_lock = threading.Lock()

        # ── AUDIO QUEUE ─────────────────────────────────────────
        self.audio_queue = queue.Queue()
        self.is_speaking_urgent = False
        self.language = language

        # ── VOICE CACHING ───────────────────────────────────────
        self._voice_cache: dict[str, str] = {}
        self._cache_dir = "voice_cache"
        os.makedirs(self._cache_dir, exist_ok=True)

        # ── CONTEXT AWARENESS ───────────────────────────────────
        self.current_exercise = None
        self.rep_count   = 0
        self.error_count = 0

        # ── SMART COACHING STATE ────────────────────────────────
        self._last_spoken:     dict[str, float] = {}
        self._error_streak:    dict[str, int]   = {}
        self._last_motivation: dict[str, str]   = {}
        self._clean_reps   = 0
        self._silence_mode = False
        self._error_start_time: dict[str, float] = {}
        self.ERROR_GRACE_PERIOD = 0.8

        # ── LOGGING ─────────────────────────────────────────────
        self.logger = logging.getLogger("AICoach")
        self.logger.setLevel(logging.INFO)

        fh = logging.FileHandler("ai_coach.log", encoding="utf-8")
        fh.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

        # ── VOICE MAP ───────────────────────────────────────────
        self.voice_map = {
            # Setup
            STEP_BACK:       "my_voice/step_back.mp3",
            CANT_SEE_BODY:   "my_voice/cant_see_body.mp3",
            SIT_DOWN:        "my_voice/sit_down.mp3",
            # Bicep curl
            RELAX_SHOULDER:  "my_voice/relax_shoulders.mp3",
            PIN_ELBOW:       "my_voice/pin_elbow.mp3",
            DONT_REST_BODY:  "my_voice/dont_rest.mp3",
            LIFT_OFF_LEG:    "my_voice/lift_elbow.mp3",
            FULL_EXTENSION:  "my_voice/dont_cheat_down.mp3",
            SQUEEZE_UP:      "my_voice/squeeze_up.mp3",
            # Tricep pushdown
            TUCK_ELBOWS:     "my_voice/tuck_elbows.mp3",
            DONT_QUIT:       "my_voice/dont_quit.mp3",
            LOCK_ARMS:       "my_voice/lock_arms.mp3",
            # Flat dumbbell press
            FLAT_PRESS_SETUP: "my_voice/flat_press_setup.mp3",
            FLAT_PRESS_LOWER: "my_voice/flat_press_lower.mp3",
            FLAT_PRESS_LOCK:  "my_voice/flat_press_lock.mp3",
            FLAT_PRESS_DROP:  "my_voice/flat_press_drop.mp3",
            # Shoulder press
            KEEP_BACK_STRAIGHT:   "my_voice/keep_back_straight.mp3",
            GOOD_REP:             "my_voice/good_rep.mp3",
            GO_DOWN:              "my_voice/go_down.mp3",
            PUSH_UP_FULLY:        "my_voice/push_up_fully.mp3",
            KEEP_BOTH_ARMS_EQUAL: "my_voice/keep_both_arms_equal.mp3",
            STABILIZE_YOUR_HIPS:  "my_voice/stabilize_hips.mp3",
            # Tbar row
            TBAR_SETUP:      "my_voice/TBAR_SETUP.mp3",
            TBAR_EXTENSION:  "my_voice/TBAR_EXTENSION.mp3",
            TBAR_PULL_MORE:  "my_voice/TBAR_PULL_MORE.mp3",
            # Incline Dumbbell
            INCLINE_DB_SETUP: "my_voice/incline_db_setup.mp3",
            INCLINE_DB_LOWER: "my_voice/incline_db_lower.mp3",
            INCLINE_DB_LOCK:  "my_voice/incline_db_lock.mp3",
            INCLINE_DB_DROP:  "my_voice/incline_db_drop.mp3",
            # Incline Barbell
            INCLINE_BB_SETUP:  "my_voice/incline_bb_setup.mp3",
            INCLINE_BB_LOWER:  "my_voice/incline_bb_lower.mp3",
            INCLINE_BB_LOCK:   "my_voice/incline_bb_lock.mp3",
            INCLINE_BB_TOUCH:  "my_voice/incline_bb_touch.mp3",
            # Cable Fly L2H
            FLY_L2H_SETUP:    "my_voice/fly_l2h_setup.mp3",
            FLY_L2H_STRETCH:  "my_voice/fly_l2h_stretch.mp3",
            FLY_L2H_SQUEEZE:  "my_voice/fly_l2h_squeeze.mp3",
            FLY_L2H_BENT:     "my_voice/fly_l2h_bent.mp3",
            # Chest Batch 2
            LANDMINE_PRESS_SETUP: "my_voice/landmine_setup.mp3",
            LANDMINE_PRESS_LOWER: "my_voice/landmine_lower.mp3",
            LANDMINE_PRESS_LOCK:  "my_voice/landmine_lock.mp3",
            LANDMINE_PRESS_DROP:  "my_voice/landmine_drop.mp3",
            FLAT_BB_SETUP:  "my_voice/flat_bb_setup.mp3",
            FLAT_BB_LOWER:  "my_voice/flat_bb_lower.mp3",
            FLAT_BB_LOCK:   "my_voice/flat_bb_lock.mp3",
            FLAT_BB_TOUCH:  "my_voice/flat_bb_touch.mp3",
            FLY_H2L_SETUP:    "my_voice/fly_h2l_setup.mp3",
            FLY_H2L_STRETCH:  "my_voice/fly_h2l_stretch.mp3",
            FLY_H2L_SQUEEZE:  "my_voice/fly_h2l_squeeze.mp3",
            FLY_H2L_BENT:     "my_voice/fly_h2l_bent.mp3",
            MACHINE_PRESS_SETUP:  "my_voice/machine_press_setup.mp3",
            MACHINE_PRESS_LOWER:  "my_voice/machine_press_lower.mp3",
            MACHINE_PRESS_LOCK:   "my_voice/machine_press_lock.mp3",
            MACHINE_PRESS_DROP:   "my_voice/machine_press_drop.mp3",
            FLOOR_PRESS_SETUP:    "my_voice/floor_press_setup.mp3",
            FLOOR_PRESS_LOWER:    "my_voice/floor_press_lower.mp3",
            FLOOR_PRESS_LOCK:     "my_voice/floor_press_lock.mp3",
            FLOOR_PRESS_DROP:     "my_voice/floor_press_drop.mp3",
            DIPS_SETUP:  "my_voice/dips_setup.mp3",
            DIPS_LOWER:  "my_voice/dips_lower.mp3",
            DIPS_LOCK:   "my_voice/dips_lock.mp3",
            DIPS_LEAN:   "my_voice/dips_lean.mp3",
            DECLINE_PUSHUP_SETUP:  "my_voice/decline_pushup_setup.mp3",
            DECLINE_PUSHUP_LOWER:  "my_voice/decline_pushup_lower.mp3",
            DECLINE_PUSHUP_LOCK:   "my_voice/decline_pushup_lock.mp3",
            DECLINE_PUSHUP_DROP:   "my_voice/decline_pushup_drop.mp3",
            ARCHER_PUSHUP_SETUP:     "my_voice/archer_pushup_setup.mp3",
            ARCHER_PUSHUP_LOWER:     "my_voice/archer_pushup_lower.mp3",
            ARCHER_PUSHUP_LOCK:      "my_voice/archer_pushup_lock.mp3",
            ARCHER_PUSHUP_STRAIGHT:  "my_voice/archer_pushup_straight.mp3",
            # Back Batch 1
            LAT_WIDE_SETUP:    "my_voice/lat_wide_setup.mp3",
            LAT_WIDE_PULL:     "my_voice/lat_wide_pull.mp3",
            LAT_WIDE_STRETCH:  "my_voice/lat_wide_stretch.mp3",
            LAT_WIDE_SQUEEZE:  "my_voice/lat_wide_squeeze.mp3",
            PULLUP_SETUP:  "my_voice/pullup_setup.mp3",
            PULLUP_PULL:   "my_voice/pullup_pull.mp3",
            PULLUP_HANG:   "my_voice/pullup_hang.mp3",
            PULLUP_CHIN:   "my_voice/pullup_chin.mp3",
            LAT_UNDER_SETUP:   "my_voice/lat_under_setup.mp3",
            LAT_UNDER_PULL:    "my_voice/lat_under_pull.mp3",
            LAT_UNDER_STRETCH: "my_voice/lat_under_stretch.mp3",
            LAT_UNDER_SQUEEZE: "my_voice/lat_under_squeeze.mp3",
            STRAIGHT_ARM_SETUP:    "my_voice/straight_arm_setup.mp3",
            STRAIGHT_ARM_PULL:     "my_voice/straight_arm_pull.mp3",
            STRAIGHT_ARM_STRETCH:  "my_voice/straight_arm_stretch.mp3",
            STRAIGHT_ARM_BENT:     "my_voice/straight_arm_bent.mp3",
            # Back Batch 2
            AST_PULLUP_SETUP:  "my_voice/ast_pullup_setup.mp3",
            AST_PULLUP_PULL:   "my_voice/ast_pullup_pull.mp3",
            AST_PULLUP_HANG:   "my_voice/ast_pullup_hang.mp3",
            AST_PULLUP_CHIN:   "my_voice/ast_pullup_chin.mp3",
            CABLE_ROW_SETUP:   "my_voice/cable_row_setup.mp3",
            CABLE_ROW_PULL:    "my_voice/cable_row_pull.mp3",
            CABLE_ROW_STRETCH: "my_voice/cable_row_stretch.mp3",
            CABLE_ROW_SQUEEZE: "my_voice/cable_row_squeeze.mp3",
            DB_ROW_SETUP:    "my_voice/db_row_setup.mp3",
            DB_ROW_PULL:     "my_voice/db_row_pull.mp3",
            DB_ROW_STRETCH:  "my_voice/db_row_stretch.mp3",
            DB_ROW_SQUEEZE:  "my_voice/db_row_squeeze.mp3",
            CHEST_ROW_SETUP:   "my_voice/chest_row_setup.mp3",
            CHEST_ROW_PULL:    "my_voice/chest_row_pull.mp3",
            CHEST_ROW_STRETCH: "my_voice/chest_row_stretch.mp3",
            CHEST_ROW_SQUEEZE: "my_voice/chest_row_squeeze.mp3",
            PENDLAY_ROW_SETUP:   "my_voice/pendlay_row_setup.mp3",
            PENDLAY_ROW_PULL:    "my_voice/pendlay_row_pull.mp3",
            PENDLAY_ROW_STRETCH: "my_voice/pendlay_row_stretch.mp3",
            PENDLAY_ROW_SQUEEZE: "my_voice/pendlay_row_squeeze.mp3",
            MEADOWS_ROW_SETUP:   "my_voice/meadows_row_setup.mp3",
            MEADOWS_ROW_PULL:    "my_voice/meadows_row_pull.mp3",
            MEADOWS_ROW_STRETCH: "my_voice/meadows_row_stretch.mp3",
            MEADOWS_ROW_SQUEEZE: "my_voice/meadows_row_squeeze.mp3",
            TRAP_DEADLIFT_SETUP:  "my_voice/trap_deadlift_setup.mp3",
            TRAP_DEADLIFT_PULL:   "my_voice/trap_deadlift_pull.mp3",
            TRAP_DEADLIFT_LOCK:   "my_voice/trap_deadlift_lock.mp3",
            TRAP_DEADLIFT_DROP:   "my_voice/trap_deadlift_drop.mp3",
            CONV_DEADLIFT_SETUP:  "my_voice/conv_deadlift_setup.mp3",
            CONV_DEADLIFT_PULL:   "my_voice/conv_deadlift_pull.mp3",
            CONV_DEADLIFT_LOCK:   "my_voice/conv_deadlift_lock.mp3",
            CONV_DEADLIFT_DROP:   "my_voice/conv_deadlift_drop.mp3",
            # Shoulders Batch 1
            SEATED_DB_PRESS_SETUP:  "my_voice/seated_db_press_setup.mp3",
            SEATED_DB_PRESS_LOWER:  "my_voice/seated_db_press_lower.mp3",
            SEATED_DB_PRESS_LOCK:   "my_voice/seated_db_press_lock.mp3",
            SEATED_DB_PRESS_DROP:   "my_voice/seated_db_press_drop.mp3",
            MACHINE_PRESS_SHOULDER_SETUP: "my_voice/machine_press_shoulder_setup.mp3",
            MACHINE_PRESS_SHOULDER_LOWER: "my_voice/machine_press_shoulder_lower.mp3",
            MACHINE_PRESS_SHOULDER_LOCK:  "my_voice/machine_press_shoulder_lock.mp3",
            MACHINE_PRESS_SHOULDER_DROP:  "my_voice/machine_press_shoulder_drop.mp3",
            OHP_BARBELL_SETUP:  "my_voice/ohp_barbell_setup.mp3",
            OHP_BARBELL_LOWER:  "my_voice/ohp_barbell_lower.mp3",
            OHP_BARBELL_LOCK:   "my_voice/ohp_barbell_lock.mp3",
            OHP_BARBELL_DROP:   "my_voice/ohp_barbell_drop.mp3",
            ARNOLD_PRESS_SETUP: "my_voice/arnold_press_setup.mp3",
            ARNOLD_PRESS_LOWER: "my_voice/arnold_press_lower.mp3",
            ARNOLD_PRESS_LOCK:  "my_voice/arnold_press_lock.mp3",
            ARNOLD_PRESS_DROP:  "my_voice/arnold_press_drop.mp3",
            # Shoulders Batch 2
            LATERAL_MACHINE_SETUP:    "my_voice/lateral_machine_setup.mp3",
            LATERAL_MACHINE_RAISE:    "my_voice/lateral_machine_raise.mp3",
            LATERAL_MACHINE_LOWER:    "my_voice/lateral_machine_lower.mp3",
            LATERAL_MACHINE_TOO_HIGH: "my_voice/lateral_machine_too_high.mp3",
            LATERAL_CABLE_SETUP:    "my_voice/lateral_cable_setup.mp3",
            LATERAL_CABLE_RAISE:    "my_voice/lateral_cable_raise.mp3",
            LATERAL_CABLE_LOWER:    "my_voice/lateral_cable_lower.mp3",
            LATERAL_CABLE_TOO_HIGH: "my_voice/lateral_cable_too_high.mp3",
            LATERAL_DB_SETUP:    "my_voice/lateral_db_setup.mp3",
            LATERAL_DB_RAISE:    "my_voice/lateral_db_raise.mp3",
            LATERAL_DB_LOWER:    "my_voice/lateral_db_lower.mp3",
            LATERAL_DB_TOO_HIGH: "my_voice/lateral_db_too_high.mp3",
            LATERAL_LANDMINE_SETUP:    "my_voice/lateral_landmine_setup.mp3",
            LATERAL_LANDMINE_RAISE:    "my_voice/lateral_landmine_raise.mp3",
            LATERAL_LANDMINE_LOWER:    "my_voice/lateral_landmine_lower.mp3",
            LATERAL_LANDMINE_TOO_HIGH: "my_voice/lateral_landmine_too_high.mp3",
            FACE_PULL_SETUP:    "my_voice/face_pull_setup.mp3",
            FACE_PULL_PULL:     "my_voice/face_pull_pull.mp3",
            FACE_PULL_STRETCH:  "my_voice/face_pull_stretch.mp3",
            FACE_PULL_SQUEEZE:  "my_voice/face_pull_squeeze.mp3",
            REAR_CABLE_FLY_SETUP:   "my_voice/rear_cable_fly_setup.mp3",
            REAR_CABLE_FLY_PULL:    "my_voice/rear_cable_fly_pull.mp3",
            REAR_CABLE_FLY_STRETCH: "my_voice/rear_cable_fly_stretch.mp3",
            REAR_CABLE_FLY_SQUEEZE: "my_voice/rear_cable_fly_squeeze.mp3",
            REV_PEC_DECK_SETUP:   "my_voice/rev_pec_deck_setup.mp3",
            REV_PEC_DECK_PULL:    "my_voice/rev_pec_deck_pull.mp3",
            REV_PEC_DECK_STRETCH: "my_voice/rev_pec_deck_stretch.mp3",
            REV_PEC_DECK_SQUEEZE: "my_voice/rev_pec_deck_squeeze.mp3",
            # Bicep Curls
            PREACHER_CURL_SETUP:   "my_voice/preacher_curl_setup.mp3",
            PREACHER_CURL_CURL:    "my_voice/preacher_curl_curl.mp3",
            PREACHER_CURL_STRETCH: "my_voice/preacher_curl_stretch.mp3",
            PREACHER_CURL_PIN:     "my_voice/preacher_curl_pin.mp3",
            HAMMER_CURL_SETUP:   "my_voice/hammer_curl_setup.mp3",
            HAMMER_CURL_CURL:    "my_voice/hammer_curl_curl.mp3",
            HAMMER_CURL_STRETCH: "my_voice/hammer_curl_stretch.mp3",
            HAMMER_SWINGING:     "my_voice/hammer_curl_swing.mp3",
            HIGH_CABLE_CURL_SETUP:   "my_voice/high_cable_curl_setup.mp3",
            HIGH_CABLE_CURL_CURL:    "my_voice/high_cable_curl_curl.mp3",
            HIGH_CABLE_CURL_STRETCH: "my_voice/high_cable_curl_stretch.mp3",
            HIGH_CABLE_DROP:         "my_voice/high_cable_curl_drop.mp3",
            INCLINE_DB_CURL_SETUP:   "my_voice/incline_db_curl_setup.mp3",
            INCLINE_DB_CURL_CURL:    "my_voice/incline_db_curl_curl.mp3",
            INCLINE_DB_CURL_STRETCH: "my_voice/incline_db_curl_stretch.mp3",
            INCLINE_DB_CURL_DROP:    "my_voice/incline_db_curl_drop.mp3",
            BARBELL_CURL_SETUP:   "my_voice/barbell_curl_setup.mp3",
            BARBELL_CURL_CURL:    "my_voice/barbell_curl_curl.mp3",
            BARBELL_CURL_STRETCH: "my_voice/barbell_curl_stretch.mp3",
            BARBELL_CURL_SWING:   "my_voice/barbell_curl_swing.mp3",
            SPIDER_CURL_SETUP:   "my_voice/spider_curl_setup.mp3",
            SPIDER_CURL_CURL:    "my_voice/spider_curl_curl.mp3",
            SPIDER_CURL_STRETCH: "my_voice/spider_curl_stretch.mp3",
            SPIDER_CURL_SQUEEZE: "my_voice/spider_curl_squeeze.mp3",
            # Chin-Up & Inverted Row
            CHINUP_SETUP:   "my_voice/chinup_setup.mp3",
            CHINUP_PULL:    "my_voice/chinup_pull.mp3",
            CHINUP_STRETCH: "my_voice/chinup_stretch.mp3",
            CHINUP_SQUEEZE: "my_voice/chinup_squeeze.mp3",
            INVERTED_ROW_SETUP:   "my_voice/inverted_row_setup.mp3",
            INVERTED_ROW_PULL:    "my_voice/inverted_row_pull.mp3",
            INVERTED_ROW_STRETCH: "my_voice/inverted_row_stretch.mp3",
            INVERTED_ROW_SQUEEZE: "my_voice/inverted_row_squeeze.mp3",
            # Tricep Exercises
            TRICEP_PUSHDOWN_SETUP:   "my_voice/tricep_pushdown_setup.mp3",
            TRICEP_PUSHDOWN_PUSH:    "my_voice/tricep_pushdown_push.mp3",
            TRICEP_PUSHDOWN_STRETCH: "my_voice/tricep_pushdown_stretch.mp3",
            TRICEP_PUSHDOWN_DROP:    "my_voice/tricep_pushdown_drop.mp3",
            TRICEP_PUSHDOWN_ROPE_SETUP:   "my_voice/tricep_pushdown_rope_setup.mp3",
            TRICEP_PUSHDOWN_ROPE_PUSH:    "my_voice/tricep_pushdown_rope_push.mp3",
            TRICEP_PUSHDOWN_ROPE_STRETCH: "my_voice/tricep_pushdown_rope_stretch.mp3",
            TRICEP_PUSHDOWN_ROPE_DROP:    "my_voice/tricep_pushdown_rope_drop.mp3",
            OVERHEAD_TRICEP_CABLE_SETUP:   "my_voice/overhead_tricep_cable_setup.mp3",
            OVERHEAD_TRICEP_CABLE_PUSH:    "my_voice/overhead_tricep_cable_push.mp3",
            OVERHEAD_TRICEP_CABLE_STRETCH: "my_voice/overhead_tricep_cable_stretch.mp3",
            OVERHEAD_TRICEP_CABLE_DROP:    "my_voice/overhead_tricep_cable_drop.mp3",
            OVERHEAD_TRICEP_DB_SETUP:   "my_voice/overhead_tricep_db_setup.mp3",
            OVERHEAD_TRICEP_DB_PUSH:    "my_voice/overhead_tricep_db_push.mp3",
            OVERHEAD_TRICEP_DB_STRETCH: "my_voice/overhead_tricep_db_stretch.mp3",
            OVERHEAD_TRICEP_DB_DROP:    "my_voice/overhead_tricep_db_drop.mp3",
            DIAMOND_PUSHUP_SETUP:  "my_voice/diamond_pushup_setup.mp3",
            DIAMOND_PUSHUP_LOWER:  "my_voice/diamond_pushup_lower.mp3",
            DIAMOND_PUSHUP_PUSH:   "my_voice/diamond_pushup_push.mp3",
            DIAMOND_PUSHUP_WIDE:   "my_voice/diamond_pushup_wide.mp3",
            SKULL_CRUSHER_SETUP:   "my_voice/skull_crusher_setup.mp3",
            SKULL_CRUSHER_LOWER:   "my_voice/skull_crusher_lower.mp3",
            SKULL_CRUSHER_PUSH:    "my_voice/skull_crusher_push.mp3",
            SKULL_CRUSHER_ELBOWS:  "my_voice/skull_crusher_elbows.mp3",
            CLOSE_GRIP_BENCH_SETUP:  "my_voice/close_grip_bench_setup.mp3",
            CLOSE_GRIP_BENCH_LOWER:  "my_voice/close_grip_bench_lower.mp3",
            CLOSE_GRIP_BENCH_PUSH:   "my_voice/close_grip_bench_push.mp3",
            CLOSE_GRIP_BENCH_FLARE:  "my_voice/close_grip_bench_flare.mp3",
            TRICEP_DIPS_UPRIGHT_SETUP:  "my_voice/tricep_dips_upright_setup.mp3",
            TRICEP_DIPS_UPRIGHT_LOWER:  "my_voice/tricep_dips_upright_lower.mp3",
            TRICEP_DIPS_UPRIGHT_PUSH:   "my_voice/tricep_dips_upright_push.mp3",
            TRICEP_DIPS_UPRIGHT_LEAN:   "my_voice/tricep_dips_upright_lean.mp3",
            # Forearm Exercises
            WRIST_CURL_SETUP:   "my_voice/wrist_curl_setup.mp3",
            WRIST_CURL_CURL:    "my_voice/wrist_curl_curl.mp3",
            WRIST_CURL_STRETCH: "my_voice/wrist_curl_stretch.mp3",
            WRIST_CURL_DROP:    "my_voice/wrist_curl_drop.mp3",
            REVERSE_WRIST_CURL_SETUP:   "my_voice/reverse_wrist_curl_setup.mp3",
            REVERSE_WRIST_CURL_CURL:    "my_voice/reverse_wrist_curl_curl.mp3",
            REVERSE_WRIST_CURL_STRETCH: "my_voice/reverse_wrist_curl_stretch.mp3",
            REVERSE_WRIST_CURL_DROP:    "my_voice/reverse_wrist_curl_drop.mp3",
            # Quad Exercises
            LEG_PRESS_SETUP:  "my_voice/leg_press_setup.mp3",
            LEG_PRESS_LOWER:  "my_voice/leg_press_lower.mp3",
            LEG_PRESS_PUSH:   "my_voice/leg_press_push.mp3",
            LEG_PRESS_DEPTH:  "my_voice/leg_press_depth.mp3",
            GOBLET_SQUAT_SETUP:  "my_voice/goblet_squat_setup.mp3",
            GOBLET_SQUAT_LOWER:  "my_voice/goblet_squat_lower.mp3",
            GOBLET_SQUAT_UP:     "my_voice/goblet_squat_up.mp3",
            GOBLET_SQUAT_DEPTH:  "my_voice/goblet_squat_depth.mp3",
            LEG_EXTENSION_SETUP:   "my_voice/leg_extension_setup.mp3",
            LEG_EXTENSION_EXTEND:  "my_voice/leg_extension_extend.mp3",
            LEG_EXTENSION_LOWER:   "my_voice/leg_extension_lower.mp3",
            LEG_EXTENSION_SQUEEZE: "my_voice/leg_extension_squeeze.mp3",
            WALKING_LUNGE_SETUP:  "my_voice/walking_lunge_setup.mp3",
            WALKING_LUNGE_STEP:   "my_voice/walking_lunge_step.mp3",
            WALKING_LUNGE_LOWER:  "my_voice/walking_lunge_lower.mp3",
            WALKING_LUNGE_PUSH:   "my_voice/walking_lunge_push.mp3",
            BARBELL_BACK_SQUAT_SETUP:  "my_voice/barbell_back_squat_setup.mp3",
            BARBELL_BACK_SQUAT_LOWER:  "my_voice/barbell_back_squat_lower.mp3",
            BARBELL_BACK_SQUAT_UP:     "my_voice/barbell_back_squat_up.mp3",
            BARBELL_BACK_SQUAT_DEPTH:  "my_voice/barbell_back_squat_depth.mp3",
            BARBELL_BACK_SQUAT_KNEE:   "my_voice/barbell_back_squat_knee.mp3",
            HACK_SQUAT_SETUP:  "my_voice/hack_squat_setup.mp3",
            HACK_SQUAT_LOWER:  "my_voice/hack_squat_lower.mp3",
            HACK_SQUAT_PUSH:   "my_voice/hack_squat_push.mp3",
            HACK_SQUAT_DEPTH:  "my_voice/hack_squat_depth.mp3",
            BULGARIAN_SPLIT_SQUAT_SETUP:  "my_voice/bulgarian_split_squat_setup.mp3",
            BULGARIAN_SPLIT_SQUAT_LOWER:  "my_voice/bulgarian_split_squat_lower.mp3",
            BULGARIAN_SPLIT_SQUAT_UP:     "my_voice/bulgarian_split_squat_up.mp3",
            BULGARIAN_SPLIT_SQUAT_DEPTH:  "my_voice/bulgarian_split_squat_depth.mp3",
            # Hamstring Exercises
            LYING_LEG_CURL_SETUP:  "my_voice/lying_leg_curl_setup.mp3",
            LYING_LEG_CURL_CURL:   "my_voice/lying_leg_curl_curl.mp3",
            LYING_LEG_CURL_LOWER:  "my_voice/lying_leg_curl_lower.mp3",
            LYING_LEG_CURL_KNEE:   "my_voice/lying_leg_curl_knee.mp3",
            ROMANIAN_DEADLIFT_SETUP:  "my_voice/romanian_deadlift_setup.mp3",
            ROMANIAN_DEADLIFT_HINGE:  "my_voice/romanian_deadlift_hinge.mp3",
            ROMANIAN_DEADLIFT_LOWER:  "my_voice/romanian_deadlift_lower.mp3",
            ROMANIAN_DEADLIFT_UP:     "my_voice/romanian_deadlift_up.mp3",
            ROMANIAN_DEADLIFT_BACK:   "my_voice/romanian_deadlift_back.mp3",
            SINGLE_LEG_RDL_SETUP:    "my_voice/single_leg_rdl_setup.mp3",
            SINGLE_LEG_RDL_HINGE:    "my_voice/single_leg_rdl_hinge.mp3",
            SINGLE_LEG_RDL_UP:       "my_voice/single_leg_rdl_up.mp3",
            SINGLE_LEG_RDL_BALANCE:  "my_voice/single_leg_rdl_balance.mp3",
            NORDIC_CURL_SETUP:   "my_voice/nordic_curl_setup.mp3",
            NORDIC_CURL_LOWER:   "my_voice/nordic_curl_lower.mp3",
            NORDIC_CURL_CATCH:   "my_voice/nordic_curl_catch.mp3",
            NORDIC_CURL_RETURN:  "my_voice/nordic_curl_return.mp3",
            # Glute Exercises
            HIP_THRUST_SETUP:   "my_voice/hip_thrust_setup.mp3",
            HIP_THRUST_THRUST:  "my_voice/hip_thrust_thrust.mp3",
            HIP_THRUST_TOP:     "my_voice/hip_thrust_top.mp3",
            HIP_THRUST_LOWER:   "my_voice/hip_thrust_lower.mp3",
            CABLE_PULL_THROUGH_SETUP:   "my_voice/cable_pull_through_setup.mp3",
            CABLE_PULL_THROUGH_PULL:    "my_voice/cable_pull_through_pull.mp3",
            CABLE_PULL_THROUGH_SQUEEZE: "my_voice/cable_pull_through_squeeze.mp3",
            CABLE_PULL_THROUGH_HIP:     "my_voice/cable_pull_through_hip.mp3",
            SUMO_DEADLIFT_SETUP:  "my_voice/sumo_deadlift_setup.mp3",
            SUMO_DEADLIFT_PULL:   "my_voice/sumo_deadlift_pull.mp3",
            SUMO_DEADLIFT_LOCK:   "my_voice/sumo_deadlift_lock.mp3",
            SUMO_DEADLIFT_BACK:   "my_voice/sumo_deadlift_back.mp3",
            DB_GLUTE_BRIDGE_SETUP:  "my_voice/db_glute_bridge_setup.mp3",
            DB_GLUTE_BRIDGE_UP:     "my_voice/db_glute_bridge_up.mp3",
            DB_GLUTE_BRIDGE_TOP:    "my_voice/db_glute_bridge_top.mp3",
            DB_GLUTE_BRIDGE_LOWER:  "my_voice/db_glute_bridge_lower.mp3",
            GLUTE_KICKBACK_SETUP:   "my_voice/glute_kickback_setup.mp3",
            GLUTE_KICKBACK_KICK:    "my_voice/glute_kickback_kick.mp3",
            GLUTE_KICKBACK_SQUEEZE: "my_voice/glute_kickback_squeeze.mp3",
            GLUTE_KICKBACK_LOWER:   "my_voice/glute_kickback_lower.mp3",
            SINGLE_LEG_GLUTE_BRIDGE_SETUP:   "my_voice/single_leg_glute_bridge_setup.mp3",
            SINGLE_LEG_GLUTE_BRIDGE_UP:      "my_voice/single_leg_glute_bridge_up.mp3",
            SINGLE_LEG_GLUTE_BRIDGE_SQUEEZE: "my_voice/single_leg_glute_bridge_squeeze.mp3",
            SINGLE_LEG_GLUTE_BRIDGE_HIP:     "my_voice/single_leg_glute_bridge_hip.mp3",
            # Calf Exercises
            SEATED_CALF_RAISE_SETUP:   "my_voice/seated_calf_raise_setup.mp3",
            SEATED_CALF_RAISE_RAISE:   "my_voice/seated_calf_raise_raise.mp3",
            SEATED_CALF_RAISE_SQUEEZE: "my_voice/seated_calf_raise_squeeze.mp3",
            SEATED_CALF_RAISE_LOWER:   "my_voice/seated_calf_raise_lower.mp3",
            STANDING_CALF_RAISE_SETUP:   "my_voice/standing_calf_raise_setup.mp3",
            STANDING_CALF_RAISE_RAISE:   "my_voice/standing_calf_raise_raise.mp3",
            STANDING_CALF_RAISE_SQUEEZE: "my_voice/standing_calf_raise_squeeze.mp3",
            STANDING_CALF_RAISE_LOWER:   "my_voice/standing_calf_raise_lower.mp3",
            DONKEY_CALF_RAISE_SETUP:   "my_voice/donkey_calf_raise_setup.mp3",
            DONKEY_CALF_RAISE_RAISE:   "my_voice/donkey_calf_raise_raise.mp3",
            DONKEY_CALF_RAISE_SQUEEZE: "my_voice/donkey_calf_raise_squeeze.mp3",
            DONKEY_CALF_RAISE_LOWER:   "my_voice/donkey_calf_raise_lower.mp3",
            # Abs / Core Exercises
            CABLE_CRUNCH_SETUP:   "my_voice/cable_crunch_setup.mp3",
            CABLE_CRUNCH_CRUNCH:  "my_voice/cable_crunch_crunch.mp3",
            CABLE_CRUNCH_SQUEEZE: "my_voice/cable_crunch_squeeze.mp3",
            CABLE_CRUNCH_FULL:    "my_voice/cable_crunch_full.mp3",
            PLANK_SETUP:       "my_voice/plank_setup.mp3",
            PLANK_HOLD:        "my_voice/plank_hold.mp3",
            PLANK_HIPS_SAGGING:"my_voice/plank_hips_sagging.mp3",
            PLANK_HIPS_HIGH:   "my_voice/plank_hips_high.mp3",
            HANGING_LEG_RAISE_SETUP:   "my_voice/hanging_leg_raise_setup.mp3",
            HANGING_LEG_RAISE_RAISE:   "my_voice/hanging_leg_raise_raise.mp3",
            HANGING_LEG_RAISE_SQUEEZE: "my_voice/hanging_leg_raise_squeeze.mp3",
            HANGING_LEG_RAISE_LOWER:   "my_voice/hanging_leg_raise_lower.mp3",
            AB_WHEEL_ROLLOUT_SETUP:   "my_voice/ab_wheel_rollout_setup.mp3",
            AB_WHEEL_ROLLOUT_ROLL:    "my_voice/ab_wheel_rollout_roll.mp3",
            AB_WHEEL_ROLLOUT_RETURN:  "my_voice/ab_wheel_rollout_return.mp3",
            AB_WHEEL_ROLLOUT_CONTROL: "my_voice/ab_wheel_rollout_control.mp3",
            LANDMINE_OBLIQUE_TWIST_SETUP:   "my_voice/landmine_oblique_twist_setup.mp3",
            LANDMINE_OBLIQUE_TWIST_TWIST:   "my_voice/landmine_oblique_twist_twist.mp3",
            LANDMINE_OBLIQUE_TWIST_SQUEEZE: "my_voice/landmine_oblique_twist_squeeze.mp3",
            LANDMINE_OBLIQUE_TWIST_CONTROL: "my_voice/landmine_oblique_twist_control.mp3",
            # Lower Back Exercises
            BACK_EXTENSION_SETUP:   "my_voice/back_extension_setup.mp3",
            BACK_EXTENSION_UP:      "my_voice/back_extension_up.mp3",
            BACK_EXTENSION_SQUEEZE: "my_voice/back_extension_squeeze.mp3",
            BACK_EXTENSION_LOWER:   "my_voice/back_extension_lower.mp3",
            SUPERMAN_HOLD_SETUP:    "my_voice/superman_hold_setup.mp3",
            SUPERMAN_HOLD_HOLD:     "my_voice/superman_hold_hold.mp3",
            SUPERMAN_HOLD_SQUEEZE:  "my_voice/superman_hold_squeeze.mp3",
            SUPERMAN_HOLD_UP:       "my_voice/superman_hold_up.mp3",
            # Trap Exercises
            BARBELL_SHRUG_SETUP:   "my_voice/barbell_shrug_setup.mp3",
            BARBELL_SHRUG_SHRUG:   "my_voice/barbell_shrug_shrug.mp3",
            BARBELL_SHRUG_SQUEEZE: "my_voice/barbell_shrug_squeeze.mp3",
            BARBELL_SHRUG_DROP:    "my_voice/barbell_shrug_drop.mp3",
            DB_SHRUG_SETUP:   "my_voice/db_shrug_setup.mp3",
            DB_SHRUG_SHRUG:   "my_voice/db_shrug_shrug.mp3",
            DB_SHRUG_SQUEEZE: "my_voice/db_shrug_squeeze.mp3",
            DB_SHRUG_DROP:    "my_voice/db_shrug_drop.mp3",
            # Adductor / Abductor Exercises
            ADDUCTOR_MACHINE_SETUP:   "my_voice/adductor_machine_setup.mp3",
            ADDUCTOR_MACHINE_SQUEEZE: "my_voice/adductor_machine_squeeze.mp3",
            ADDUCTOR_MACHINE_OPEN:    "my_voice/adductor_machine_open.mp3",
            ADDUCTOR_MACHINE_FULL:    "my_voice/adductor_machine_full.mp3",
            ABDUCTOR_MACHINE_SETUP:   "my_voice/abductor_machine_setup.mp3",
            ABDUCTOR_MACHINE_OPEN:    "my_voice/abductor_machine_open.mp3",
            ABDUCTOR_MACHINE_SQUEEZE: "my_voice/abductor_machine_squeeze.mp3",
            ABDUCTOR_MACHINE_CLOSE:   "my_voice/abductor_machine_close.mp3",
        }

        # Start background audio thread
        self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._audio_thread.start()

        # Register cleanup on exit
        atexit.register(self._cleanup)

        # ── GROQ API (optional — for AI motivation) ─────────────
        self._groq_client = None
        if GROQ_AVAILABLE:
            try:
                api_key = os.environ.get("GROQ_API_KEY", "")
                if api_key:
                    self._groq_client = Groq(api_key=api_key)
            except Exception:
                pass

    # ── INTERNAL HELPERS ────────────────────────────────────────
# ── INTERNAL HELPERS ────────────────────────────────────────

    def _get_cached_voice(self, text: str, lang: str) -> str | None:
        """Return path to a cached TTS file, generating it if needed."""
        key = hashlib.md5(f"{lang}:{text}".encode()).hexdigest()
        with self._cache_lock:
            if key in self._voice_cache:
                cached = self._voice_cache[key]
                if os.path.exists(cached):
                    return cached

        try:
            filepath = os.path.join(self._cache_dir, f"{key}.mp3")
            tts = gTTS(text=text, lang=lang)
            tts.save(filepath)
            with self._cache_lock:
                self._voice_cache[key] = filepath
            return filepath
        except Exception as e:
            self.logger.error(f"TTS generation failed for '{text}': {e}")
            return None

    def _generate_and_queue(self, text: str, urgent: bool = False):
        """Generate TTS audio and put it in the playback queue."""
        if self._silence_mode:
            return

        if self.language == "en":
            pre_recorded = self.voice_map.get(text)
            if pre_recorded and os.path.exists(pre_recorded):
                self.audio_queue.put((pre_recorded, urgent, True))
                return

        tts_lang = "ar" if self.language == "ar" else "en"
        
        # 🟢 السر هنا: لو اللغة عربي، بنترجم النص من القاموس الأول
        spoken_text = text
        if self.language == "ar":
            spoken_text = ARABIC_MESSAGES.get(text, text)

        filename = self._get_cached_voice(spoken_text, tts_lang)
        if filename and not self._silence_mode and self.audio_queue.qsize() < 5:
            self.audio_queue.put((filename, urgent, False))

    def _speak_text_direct(self, text: str):
        """Generate TTS for `text` and queue it for playback (Non-blocking)."""
        if self._silence_mode:
            return
            
        tts_lang = "ar" if self.language == "ar" else "en"
        
        # 🟢 السر هنا برضه عشان رسايل التشجيع
        spoken_text = text
        if self.language == "ar":
            spoken_text = ARABIC_MESSAGES.get(text, text)
            
        filename = self._get_cached_voice(spoken_text, tts_lang)
        if filename and not self._silence_mode and self.audio_queue.qsize() < 5:
            self.audio_queue.put((filename, False, False))
    def _audio_loop(self):
        """Background thread for audio playback."""
        while True:
            filename, is_urgent, is_pre_recorded = self.audio_queue.get()

            # If stopped, skip all queued audio immediately
            if self._silence_mode:
                self.is_speaking_urgent = False
                self.audio_queue.task_done()
                continue

            try:
                self.is_speaking_urgent = is_urgent
                pygame.mixer.music.load(filename)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    if self._silence_mode:
                        pygame.mixer.music.stop()
                        break
                    pygame.time.Clock().tick(10)

                pygame.mixer.music.unload()
                self.is_speaking_urgent = False
                time.sleep(0.05)

                if not is_pre_recorded and "voice_cache" not in filename:
                    try:
                        os.remove(filename)
                    except Exception:
                        pass
            except Exception as e:
                self.logger.error(f"Play Error: {e}", exc_info=True)
                self.is_speaking_urgent = False

            self.audio_queue.task_done()

    def _cleanup(self):
        """Clean up resources on exit."""
        self.logger.info("Cleaning up AI Coach resources...")
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:
            pass
        try:
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
        except Exception:
            pass
        self.logger.info("AI Coach cleanup completed")

    # ── PUBLIC API ──────────────────────────────────────────────

    def get_motivation(self, phase: str = "middle") -> str:
        """Return a motivation phrase for the given phase, avoiding recent repeats."""
        bank = MOTIVATION_BANK.get(self.language, MOTIVATION_BANK["en"])
        phrases = bank.get(phase, bank["middle"])
        last = self._last_motivation.get(phase)
        choices = [p for p in phrases if p != last] or phrases
        chosen = random.choice(choices)
        self._last_motivation[phase] = chosen
        return chosen

    def speak_motivation(self, phase: str = "middle"):
        if time.time() - self._last_spoken.get("__motivation__", 0) < SEVERITY["motivation"]:
            return
        text = self.get_motivation(phase)
        self._last_spoken["__motivation__"] = time.time()
        threading.Thread(
            target=self._speak_text_direct,
            args=(text,),
            daemon=True,
        ).start()

    def _speak(self, message: str, urgent: bool = False, is_error: bool = False):
        """
        Internal core — Centralized Logic for Cooldowns and Nag Capping.
        """
        if self._silence_mode:
            return

        severity = MSG_SEVERITY.get(message, "warning")
        cooldown = SEVERITY[severity]
        now = time.time()

        # 🔴 نظام הـ Nag Capping يطبق هنا عشان يشتغل على كل الأخطاء
        if is_error:
            streak = self._error_streak.get(message, 0)
            if streak >= 4 and severity != "critical":
                return
            if streak == 3:
                cooldown /= 2

        if now - self._last_spoken.get(message, 0) < cooldown:
            return

        if is_error:
            self._error_streak[message] = self._error_streak.get(message, 0) + 1
            self._clean_reps = 0

        _urgent = urgent or (severity == "critical")
        if _urgent:
            try:
                while not self.audio_queue.empty():
                    self.audio_queue.get_nowait()
                    self.audio_queue.task_done()
            except Exception:
                pass

        self._last_spoken[message] = now
        self.logger.info(f"Speaking [{severity}]: {message}")
        threading.Thread(
            target=self._generate_and_queue,
            args=(message, _urgent),
            daemon=True,
        ).start()

    def on_error(self, message: str, urgent: bool = False):
        """Report a form or setup error."""
        # Time-based debouncing: ignore transient errors unless they persist
        if urgent:
            self._speak(message, urgent=True, is_error=True)
            return

        now = time.time()
        streak = self._error_streak.get(message, 0)

        if streak == 0:
            # First occurrence — start the grace timer
            if message not in self._error_start_time:
                self._error_start_time[message] = now
                return
            elapsed = now - self._error_start_time[message]
            if elapsed >= self.ERROR_GRACE_PERIOD:
                # Error persisted long enough — speak and keep timer for cooldown
                self._speak(message, urgent=False, is_error=True)
            # else: still within grace period, ignore
        else:
            # Already spoken at least once — rely on severity cooldown in _speak
            self._speak(message, urgent=False, is_error=True)

    def speak_if_ready(self, message: str, urgent: bool = False):
        """Speak a completion / positive-feedback message (e.g. GOOD_REP)."""
        self._speak(message, urgent=urgent, is_error=False)

    def reset_error(self, message: str):
        """Call when a previously reported error is corrected."""
        self._error_streak.pop(message, None)
        self._error_start_time.pop(message, None)
        self.logger.info(f"Error corrected: {message}")

    def on_good_rep(self):
        """Call after each clean rep is counted."""
        self.rep_count   += 1
        self._clean_reps += 1
        self.logger.info(f"Good rep #{self.rep_count} (clean streak: {self._clean_reps})")

    def on_set_complete(self):
        """Call at the end of a set."""
        phase = "clean_set" if self.error_count == 0 else "middle"
        self.speak_motivation(phase)
        self.logger.info(f"Set complete — reps: {self.rep_count}, errors: {self.error_count}")
        self.rep_count   = 0
        self.error_count = 0
        self._clean_reps = 0
        self._error_streak.clear()

    def set_exercise(self, exercise: str):
        """Switch to a new exercise and reset per-set counters."""
        self.current_exercise = exercise
        self.rep_count   = 0
        self.error_count = 0
        self._clean_reps = 0
        self.logger.info(f"Exercise set to: {exercise}")

    def set_silence(self, silent: bool):
        """Enable or disable silence mode."""
        self._silence_mode = silent
        self.logger.info(f"Silence mode: {silent}")


    def speak(self, text: str, urgent: bool = False,
              use_groq: bool = False, is_motivation: bool = False):
        """
        Compatibility wrapper — called by all exercise trainers.
        Routes motivation through Groq (if available), otherwise MOTIVATION_BANK.
        """
        if is_motivation:
            if use_groq and self._groq_client:
                try:
                    resp = self._groq_client.chat.completions.create(
                        model="llama3-8b-8192",
                        messages=[{"role":"user","content":
                            f"Give ONE short hype phrase in {'Arabic' if self.language=='ar' else 'English'} "
                            f"for a gym athlete. Max 8 words. No quotes."}],
                        max_tokens=30,
                    )
                    phrase = resp.choices[0].message.content.strip()
                    threading.Thread(target=self._speak_text_direct, args=(phrase,), daemon=True).start()
                    return
                except Exception:
                    pass
            self.speak_motivation("middle")
        else:
            self._speak(text, urgent=urgent, is_error=urgent)

    def stop(self):
        """Stop audio immediately — call when workout ends."""
        # Set silence FIRST to prevent any new audio from being queued
        self._silence_mode = True
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:
            pass
        # Drain any remaining items from the queue
        try:
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
        except Exception:
            pass

    def resume(self):
        """Resume after stop()."""
        self._silence_mode = False

    def get_cache_stats(self) -> dict:
        """Return voice cache statistics."""
        with self._cache_lock:
            total_size = 0
            for filepath in self._voice_cache.values():
                try:
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
                except Exception:
                    pass
            return {
                "cached_files":  len(self._voice_cache),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "cache_dir":     self._cache_dir,
            }

    def clear_cache(self):
        """Clear all cached TTS files from disk and memory."""
        with self._cache_lock:
            self.logger.info("Clearing voice cache...")
            for filepath in list(self._voice_cache.values()):
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    self.logger.warning(f"Could not delete {filepath}: {e}")
            self._voice_cache.clear()
            self.logger.info("Voice cache cleared")