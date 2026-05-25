"""app.py — PulseFit + SQLite Auth + PWA"""
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
import threading, time, os, sys, importlib, importlib.util, pathlib
from datetime import datetime
import sqlite3, hashlib, secrets
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_APP_ROOT = pathlib.Path(__file__).resolve().parent


def _parse_env_bytes(raw: bytes) -> dict:
    """Parse .env bytes (UTF-8 / UTF-16 / BOM)."""
    if not raw:
        return {}
    if raw.startswith(b"\xff\xfe"):
        text = raw.decode("utf-16-le")
    elif raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16-be")
    else:
        text = None
        for enc in ("utf-8-sig", "utf-8", "utf-16-le", "utf-16"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeError, UnicodeDecodeError):
                continue
        if text is None:
            text = raw.decode("latin-1", errors="replace")

    out = {}
    for line in text.splitlines():
        line = line.strip().strip("\ufeff")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().strip("\ufeff")
        out[key] = val.strip().strip('"').strip("'")
    return out


def _load_project_env():
    """Load .env from project folder (supports UTF-8 and Windows UTF-16 saves).
    On Railway, env vars are injected directly — .env file may not exist, and that's fine.
    Never overwrite an already-set env var (Railway-injected vars take priority)."""
    # If GROQ_API_KEY is already set (e.g. by Railway dashboard), nothing to do
    if os.getenv("GROQ_API_KEY", "").strip():
        print("[env] GROQ_API_KEY already set via environment (Railway/system)")
        return

    env_file = _APP_ROOT / ".env"
    if not env_file.exists():
        print(f"[env] .env not found at {env_file} — set GROQ_API_KEY in Railway dashboard")
        return

    size = env_file.stat().st_size
    if size == 0:
        print("[env] .env is EMPTY on disk — open .env in Cursor and press Ctrl+S to save")
        return

    raw = env_file.read_bytes()
    for key, val in _parse_env_bytes(raw).items():
        if not os.environ.get(key):   # don't overwrite Railway-injected vars
            os.environ[key] = val

    if os.getenv("GROQ_API_KEY", "").strip():
        print(f"[env] GROQ_API_KEY OK ({size} byte .env)")
    else:
        print("[env] .env has data but GROQ_API_KEY line missing — use: GROQ_API_KEY=gsk_...")


_load_project_env()
from food3 import find_food_strict, FOOD_DB, calc_nutrients, COOKING_METHODS, groq_lookup, display_name_for_query

from datetime import timedelta

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "pulsefit-secret-2026"
app.config["SESSION_PERMANENT"]        = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # stay logged in 30 days
# ══════════════════════════════════════════════════════════════
# WORKOUT / CAMERA
# ══════════════════════════════════════════════════════════════
def _load_pose_model():
    """Load YOLO only when workout/camera is used (saves ~2GB if you only need Nutrition)."""
    global pose_model
    if pose_model is None:
        model_path = str(_APP_ROOT / "yolo11n-pose.pt")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"yolo11n-pose.pt model not found at {model_path}")
        from ultralytics import YOLO
        pose_model = YOLO(model_path)

# ══════════════════════════════════════════════════════════════
# DATABASE SETUP (SQLite)
# ══════════════════════════════════════════════════════════════
# Check if we are running on Railway with a volume mounted at /data
if os.path.exists("/data"):
    DB_PATH = pathlib.Path("/data/pulsefit.db")
else:
    DB_PATH = pathlib.Path(__file__).parent / "pulsefit.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            email    TEXT    UNIQUE NOT NULL,
            password TEXT    NOT NULL,
            created  TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_plans (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL REFERENCES users(id),
            user_data TEXT,
            plan_data TEXT,
            updated   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workout_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            exercise    TEXT,
            reps        INTEGER,
            sets        INTEGER,
            duration    TEXT,
            date        TEXT,
            weight_kg   REAL,
            rpe         INTEGER,
            completed   INTEGER DEFAULT 1,
            skip_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS nutrition_log (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL REFERENCES users(id),
            meal     TEXT,
            name     TEXT,
            calories REAL,
            protein  REAL,
            carbs    REAL,
            fat      REAL,
            grams    REAL,
            date     TEXT
        );
CREATE TABLE IF NOT EXISTS ml_fatigue_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT,
            avg_rpe REAL,
            skip_rate_percent REAL,
            critical_skips INTEGER,
            rule_based_deload INTEGER, 
            user_accepted_deload INTEGER DEFAULT -1,
            deload_effective INTEGER DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS ml_overload_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT,
            exercise TEXT,
            goal TEXT,
            recommended_weight_kg REAL,
            recommended_reps INTEGER,
            actual_weight_kg REAL,
            actual_reps INTEGER,
            rpe INTEGER,
            overload_success INTEGER,
            user_accepted_recommendation INTEGER
        );
        CREATE TABLE IF NOT EXISTS ml_volume_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT,
            muscle_group TEXT,
            target_min REAL,
            target_max REAL,
            actual_sets REAL,
            status TEXT,
            user_muscle_feedback INTEGER DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS water_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            date TEXT,
            amount_ml INTEGER
        );
        CREATE TABLE IF NOT EXISTS weight_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            date TEXT,
            weight_kg REAL
        );
        """)
        
        # Add new columns gracefully if DB already exists
        try: conn.execute("ALTER TABLE workout_history ADD COLUMN weight_kg REAL;")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE workout_history ADD COLUMN rpe INTEGER;")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE workout_history ADD COLUMN completed INTEGER DEFAULT 1;")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE workout_history ADD COLUMN skip_reason TEXT;")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE ml_fatigue_logs ADD COLUMN deload_effective INTEGER DEFAULT NULL;")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE ml_overload_logs ADD COLUMN user_accepted_recommendation INTEGER;")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE ml_volume_logs ADD COLUMN user_muscle_feedback INTEGER DEFAULT NULL;")
        except sqlite3.OperationalError: pass

init_db()

# ── Auth helpers ───────────────────────────────────────────────
def hash_password(pw):
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + pw).encode()).hexdigest()
    return f"{salt}:{hashed}"

def check_password(pw, stored):
    try:
        parts = stored.split(":", 1)   # maxsplit=1 — safe even if hash had colons
        if len(parts) != 2:
            return False
        salt, hashed = parts
        return hashlib.sha256((salt + pw).encode()).hexdigest() == hashed
    except:
        return False

def current_user_id():
    return session.get("user_id")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user_id():
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

import json

# ══════════════════════════════════════════════════════════════
# EXERCISE MAP
# ══════════════════════════════════════════════════════════════
EXERCISE_MAP = {
 # ── SHOULDERS ──────────────────────────────────────────────
 "seated_db_shoulder_press": ("AI_EXE.seated_db_shoulder_press", "SeatedDbShoulderPressTrainerAI"),
 "machine_shoulder_press":   ("AI_EXE.machine_shoulder_press",   "MachineShoulderPressTrainerAI"),
 "overhead_press_barbell":   ("AI_EXE.overhead_press_barbell",   "OverheadPressBarbellTrainerAI"),
 "arnold_press":             ("AI_EXE.arnold_press",             "ArnoldPressTrainerAI"),
 "machine_lateral_raise":    ("AI_EXE.machine_lateral_raise",    "MachineLateralRaiseTrainerAI"),
 "cable_lateral_raise":      ("AI_EXE.cable_lateral_raise",      "CableLateralRaiseTrainerAI"),
 "db_lateral_raise":         ("AI_EXE.db_lateral_raise",         "DbLateralRaiseTrainerAI"),
 "landmine_lateral_raise":   ("AI_EXE.landmine_lateral_raise",   "LandmineLateralRaiseTrainerAI"),
 "face_pull":                ("AI_EXE.face_pull",                "FacePullTrainerAI"),
 "rear_delt_cable_fly":      ("AI_EXE.rear_delt_cable_fly",      "RearDeltCableFlyTrainerAI"),
 "reverse_pec_deck":         ("AI_EXE.reverse_pec_deck",         "ReversePecDeckTrainerAI"),
 # ── CHEST ──────────────────────────────────────────────────
 "incline_dumbbell_press":   ("AI_EXE.incline_dumbbell_press",   "InclineDumbbellPressTrainerAI"),
 "incline_barbell_press":    ("AI_EXE.incline_barbell_press",    "InclineBarbellPressTrainerAI"),
 "cable_fly_low_to_high":    ("AI_EXE.cable_fly_low_to_high",    "CableFlyLowToHighTrainerAI"),
 "flat_dumbbell_press":      ("AI_EXE.flat_dumbbell_press",      "FlatDumbbellPressTrainerAI"),
 "flat_barbell_bench_press": ("AI_EXE.flat_barbell_bench_press", "FlatBarbellBenchPressTrainerAI"),
 "cable_fly_high_to_low":    ("AI_EXE.cable_fly_high_to_low",    "CableFlyHighToLowTrainerAI"),
 "machine_chest_press":      ("AI_EXE.machine_chest_press",      "MachineChestPressTrainerAI"),
 "dumbbell_floor_press":     ("AI_EXE.dumbbell_floor_press",     "DumbbellFloorPressTrainerAI"),
 "chest_dips":               ("AI_EXE.chest_dips",               "ChestDipsTrainerAI"),
 # ── BACK ───────────────────────────────────────────────────
 "lat_pulldown_wide":        ("AI_EXE.lat_pulldown_wide",        "LatPulldownWideTrainerAI"),
 "pull_up":                  ("AI_EXE.pull_up",                  "PullUpTrainerAI"),
 "lat_pulldown_underhand":   ("AI_EXE.lat_pulldown_underhand",   "LatPulldownUnderhandTrainerAI"),
 "straight_arm_pulldown":    ("AI_EXE.straight_arm_pulldown",    "StraightArmPulldownTrainerAI"),
 "machine_assisted_pull_up": ("AI_EXE.machine_assisted_pull_up", "MachineAssistedPullUpTrainerAI"),
 "seated_cable_row":         ("AI_EXE.seated_cable_row",         "SeatedCableRowTrainerAI"),
 "single_arm_dumbbell_row":  ("AI_EXE.single_arm_dumbbell_row",  "SingleArmDumbbellRowTrainerAI"),
 "chest_supported_row":      ("AI_EXE.chest_supported_row",      "ChestSupportedRowTrainerAI"),
 "barbell_row_pendlay":      ("AI_EXE.barbell_row_pendlay",      "BarbellRowPendlayTrainerAI"),
 "meadows_row":              ("AI_EXE.meadows_row",              "MeadowsRowTrainerAI"),
 "conventional_deadlift":    ("AI_EXE.conventional_deadlift",    "ConventionalDeadliftTrainerAI"),
 # ── BICEPS ─────────────────────────────────────────────────
 "preacher_curl":            ("AI_EXE.preacher_curl",            "PreacherCurlTrainerAI"),
 "hammer_curl":              ("AI_EXE.hammer_curl",              "HammerCurlTrainerAI"),
 "cable_curl_high":          ("AI_EXE.cable_curl_high",          "CableCurlHighTrainerAI"),
 "incline_db_curl":          ("AI_EXE.incline_db_curl",          "InclineDbCurlTrainerAI"),
 "barbell_curl":             ("AI_EXE.barbell_curl",             "BarbellCurlTrainerAI"),
 "spider_curl":              ("AI_EXE.spider_curl",              "SpiderCurlTrainerAI"),
 "chin_up":                  ("AI_EXE.chin_up",                  "ChinUpTrainerAI"),
 "inverted_row":             ("AI_EXE.inverted_row",             "InvertedRowTrainerAI"),
 # ── TRICEPS ────────────────────────────────────────────────
 "tricep_pushdown":          ("AI_EXE.tricep_pushdown",       "TricepPushdownTrainerAI"),
 "overhead_tricep_cable":    ("AI_EXE.overhead_tricep_cable",    "OverheadTricepCableTrainerAI"),
 "tricep_pushdown_rope":     ("AI_EXE.tricep_pushdown_rope",     "TricepPushdownRopeTrainerAI"),
 "overhead_tricep_db":       ("AI_EXE.overhead_tricep_db",       "OverheadTricepDbTrainerAI"),
 "diamond_pushup":           ("AI_EXE.diamond_pushup",           "DiamondPushupTrainerAI"),
 "skull_crusher":            ("AI_EXE.skull_crusher",            "SkullCrusherTrainerAI"),
 "close_grip_bench":         ("AI_EXE.close_grip_bench",         "CloseGripBenchTrainerAI"),
 "tricep_dips_upright":      ("AI_EXE.tricep_dips_upright",      "TricepDipsUprightTrainerAI"),
 # ── CORE ───────────────────────────────────────────────────
 "plank":                    ("AI_EXE.plank",                    "PlankTrainerAI"),
 "hanging_leg_raise":        ("AI_EXE.hanging_leg_raise",        "HangingLegRaiseTrainerAI"),
 "cable_crunch":             ("AI_EXE.cable_crunch",             "CableCrunchTrainerAI"),
 "ab_wheel_rollout":         ("AI_EXE.ab_wheel_rollout",         "AbWheelRolloutTrainerAI"),
 # ── LEGS ───────────────────────────────────────────────────
 "barbell_back_squat":       ("AI_EXE.barbell_back_squat",       "BarbellBackSquatTrainerAI"),
 "bulgarian_split_squat":    ("AI_EXE.bulgarian_split_squat",    "BulgarianSplitSquatTrainerAI"),
 "goblet_squat":             ("AI_EXE.goblet_squat",             "GobletSquatTrainerAI"),
 "hack_squat":               ("AI_EXE.hack_squat",               "HackSquatTrainerAI"),
 "leg_press":                ("AI_EXE.leg_press",                "LegPressTrainerAI"),
 "leg_extension":            ("AI_EXE.leg_extension",            "LegExtensionTrainerAI"),
 "lying_leg_curl":           ("AI_EXE.lying_leg_curl",           "LyingLegCurlTrainerAI"),
 "romanian_deadlift":        ("AI_EXE.romanian_deadlift",        "RomanianDeadliftTrainerAI"),
 "sumo_deadlift":            ("AI_EXE.sumo_deadlift",            "SumoDeadliftTrainerAI"),
 "trap_bar_deadlift":        ("AI_EXE.trap_bar_deadlift",        "TrapBarDeadliftTrainerAI"),
 "nordic_curl":              ("AI_EXE.nordic_curl",              "NordicCurlTrainerAI"),
 "walking_lunge":            ("AI_EXE.walking_lunge",            "WalkingLungeTrainerAI"),
 "hip_thrust":               ("AI_EXE.hip_thrust",               "HipThrustTrainerAI"),
 "glute_kickback":           ("AI_EXE.glute_kickback",           "GluteKickbackTrainerAI"),
 "cable_pull_through":       ("AI_EXE.cable_pull_through",       "CablePullThroughTrainerAI"),
 "abductor_machine":         ("AI_EXE.abductor_machine",         "AbductorMachineTrainerAI"),
 "adductor_machine":         ("AI_EXE.adductor_machine",         "AdductorMachineTrainerAI"),
 "db_glute_bridge":          ("AI_EXE.db_glute_bridge",          "DbGluteBridgeTrainerAI"),
 "single_leg_glute_bridge":  ("AI_EXE.single_leg_glute_bridge",  "SingleLegGluteBridgeTrainerAI"),
 "single_leg_rdl":           ("AI_EXE.single_leg_rdl",           "SingleLegRdlTrainerAI"),
 "seated_calf_raise":        ("AI_EXE.seated_calf_raise",        "SeatedCalfRaiseTrainerAI"),
 "donkey_calf_raise":        ("AI_EXE.donkey_calf_raise",        "DonkeyCalfRaiseTrainerAI"),
 "standing_calf_raise":      ("AI_EXE.standing_calf_raise",      "StandingCalfRaiseTrainerAI"),
}

DB_NAME_TO_KEY = {
 "Incline Dumbbell Press":"incline_dumbbell_press","Incline Barbell Press":"incline_barbell_press",
 "Cable Fly Low to High":"cable_fly_low_to_high","Flat Dumbbell Press":"flat_dumbbell_press",
 "Flat Barbell Bench Press":"flat_barbell_bench_press","Cable Fly High to Low":"cable_fly_high_to_low",
 "Machine Chest Press":"machine_chest_press","Dumbbell Floor Press":"dumbbell_floor_press",
 "Chest Dips (Forward Lean)":"chest_dips","Lat Pulldown (Wide Grip)":"lat_pulldown_wide",
 "Pull-Up / Weighted Pull-Up":"pull_up","Lat Pulldown (Underhand Grip)":"lat_pulldown_underhand",
 "Straight Arm Pulldown":"straight_arm_pulldown","Machine Assisted Pull-Up":"machine_assisted_pull_up",
 "Seated Cable Row (Neutral Grip)":"seated_cable_row","Single Arm Dumbbell Row":"single_arm_dumbbell_row",
 "Chest-Supported Row (Machine)":"chest_supported_row","Barbell Row (Pendlay)":"barbell_row_pendlay",
 "Meadows Row":"meadows_row","Conventional Deadlift":"conventional_deadlift",
 "Face Pull":"face_pull","Rear Delt Cable Fly":"rear_delt_cable_fly","Reverse Pec Deck":"reverse_pec_deck",
 "Seated DB Shoulder Press":"seated_db_shoulder_press","Machine Shoulder Press":"machine_shoulder_press",
 "Overhead Press (Barbell)":"overhead_press_barbell","Arnold Press":"arnold_press",
 "Machine Lateral Raise":"machine_lateral_raise","Cable Lateral Raise":"cable_lateral_raise",
 "DB Lateral Raise":"db_lateral_raise","Landmine Lateral Raise":"landmine_lateral_raise",
 "Preacher Curl (Machine/EZ Bar)":"preacher_curl","Hammer Curl":"hammer_curl",
 "Cable Curl (High Cable)":"cable_curl_high","Incline Dumbbell Curl":"incline_db_curl",
 "Barbell Curl":"barbell_curl","Spider Curl":"spider_curl",
 "Chin-Up (Bicep Focus)":"chin_up","Inverted Row (Supinated Grip)":"inverted_row",
 "Tricep Pushdown (Cable)":"tricep_pushdown","Overhead Tricep Extension (Cable)":"overhead_tricep_cable",
 "Tricep Pushdown (Rope)":"tricep_pushdown_rope",
 "Overhead Tricep Extension (Dumbbell)":"overhead_tricep_db",
 "Diamond Push-Up":"diamond_pushup","Skull Crusher (EZ Bar)":"skull_crusher",
 "Close Grip Bench Press":"close_grip_bench","Dips (Upright / Tricep Focused)":"tricep_dips_upright",
 "Plank":"plank","Hanging Leg Raise":"hanging_leg_raise","Cable Crunch":"cable_crunch","Ab Wheel Rollout":"ab_wheel_rollout",
 "Barbell Back Squat":"barbell_back_squat","Bulgarian Split Squat":"bulgarian_split_squat",
 "Goblet Squat":"goblet_squat","Hack Squat (Machine)":"hack_squat",
 "Leg Press":"leg_press","Leg Extension":"leg_extension","Lying Leg Curl":"lying_leg_curl",
 "Romanian Deadlift (RDL)":"romanian_deadlift","Sumo Deadlift":"sumo_deadlift",
 "Trap Bar Deadlift":"trap_bar_deadlift","Nordic Curl":"nordic_curl",
 "Walking Lunge":"walking_lunge","Hip Thrust":"hip_thrust",
 "Glute Kickback":"glute_kickback","Cable Pull-Through":"cable_pull_through","Cable Pull Through":"cable_pull_through",
 "Abductor Machine":"abductor_machine","Adductor Machine":"adductor_machine",
 "DB Glute Bridge":"db_glute_bridge","Single Leg Glute Bridge":"single_leg_glute_bridge",
 "Single Leg RDL":"single_leg_rdl","Seated Calf Raise":"seated_calf_raise",
 "Donkey Calf Raise":"donkey_calf_raise","Standing Calf Raise":"standing_calf_raise",
}

# ══════════════════════════════════════════════════════════════
# TRAINER LOADER
# ══════════════════════════════════════════════════════════════
def _load_trainer(key, lang="ar"):
    if key not in EXERCISE_MAP: return None
    mod_path, cls_name = EXERCISE_MAP[key]
    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError as e:
        print(f"[Trainer] Module not found for {key}: {e}"); return None
    except Exception as e:
        print(f"[Trainer] Import error for {key}: {e}"); return None

    candidates = [cls_name, "".join(w.capitalize() for w in key.split("_")) + "TrainerAI"]
    import inspect
    module_classes = [
        name for name, obj in inspect.getmembers(mod, inspect.isclass)
        if name.endswith("TrainerAI") and obj.__module__ == mod.__name__
    ]
    candidates += module_classes
    for cname in candidates:
        if hasattr(mod, cname):
            try:
                print(f"[Trainer] Loaded {key} -> {mod_path}.{cname}")
                return getattr(mod, cname)(language=lang)
            except Exception as e:
                print(f"[Trainer] Init failed {cname}: {e}"); continue
    print(f"[Trainer] No valid class in {mod_path}. Available: {module_classes}")
    return None

# ══════════════════════════════════════════════════════════════
# WORKOUT STATE
# ══════════════════════════════════════════════════════════════
workout_state  = {"running": False, "exercise": None, "reps": 0, "feedback": "Ready", "_frame": None}
workout_lock   = threading.Lock()
current_trainer = None
pose_model      = None

# ══════════════════════════════════════════════════════════════
# STATIC / PWA ROUTES
# ══════════════════════════════════════════════════════════════
@app.route("/favicon.ico")
def favicon(): return app.send_static_file("favicon.ico")

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "PulseFit",
        "short_name": "PulseFit",
        "description": "AI-powered personal fitness trainer",
        "start_url": "/dashboard",
        "display": "standalone",
        "background_color": "#0b0f19",
        "theme_color": "#e8f04a",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ],
        "shortcuts": [
            {"name": "Workout",   "url": "/workout",   "description": "Start a workout session"},
            {"name": "Nutrition", "url": "/nutrition", "description": "Log your meals"},
            {"name": "History",   "url": "/history",   "description": "View workout history"}
        ]
    })

@app.route("/sw.js")
def service_worker():
    from flask import make_response
    sw = """
const CACHE = 'pulsefit-v1';
const OFFLINE_URLS = ['/', '/static/style.css', '/static/common.js', '/static/script.js'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(OFFLINE_URLS)));
    self.skipWaiting();
});
self.addEventListener('activate', e => {
    e.waitUntil(caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ));
    self.clients.claim();
});
self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        fetch(e.request).then(r => {
            const clone = r.clone();
            caches.open(CACHE).then(c => c.put(e.request, clone));
            return r;
        }).catch(() => caches.match(e.request))
    );
});
"""
    r = make_response(sw)
    r.headers["Content-Type"] = "application/javascript"
    r.headers["Service-Worker-Allowed"] = "/"
    return r

# ══════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    if current_user_id(): return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET": return render_template("register.html")
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email")    or "").strip().lower()
    password =  data.get("password") or ""
    if not username or not email or not password:
        return jsonify({"error": "All fields required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password, created) VALUES (?,?,?,?)",
                (username, email, hash_password(password), datetime.now().strftime("%d %b %Y"))
            )
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            session.permanent   = True
            session["user_id"]   = user["id"]
            session["username"]  = user["username"]
        return jsonify({"status": "ok", "redirect": "/questionnaire"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET": return render_template("login.html")
    data = request.get_json(force=True) or {}
    email    = (data.get("email")    or "").strip().lower()
    password =  data.get("password") or ""
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_password(password, user["password"]):
        return jsonify({"error": "Invalid email or password"}), 401
    session.permanent   = True
    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    # Load plan from DB into session
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_plans WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user["id"],)
        ).fetchone()
    if row:
        session["userData"] = json.loads(row["user_data"] or "{}")
        session["plan"]     = json.loads(row["plan_data"] or "{}")
    return jsonify({"status": "ok", "redirect": "/dashboard" if "plan" in session else "/questionnaire"})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/me")
def api_me():
    uid = current_user_id()
    if not uid: return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "username": session.get("username"), "user_id": uid})

# ══════════════════════════════════════════════════════════════
# PAGE ROUTES (protected)
# ══════════════════════════════════════════════════════════════
@app.route("/questionnaire")
@login_required
def questionnaire(): return render_template("questionnaire.html")

@app.route("/dashboard")
@login_required
def dashboard():
    uid = current_user_id()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM user_plans WHERE user_id=? LIMIT 1", (uid,)).fetchone()
    if not row: return redirect(url_for("questionnaire"))
    return render_template("dashboard.html")

@app.route("/nutrition")
@login_required
def nutrition(): return render_template("nutrition.html")

@app.route("/workout")
@login_required
def workout():
    uid = current_user_id()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM user_plans WHERE user_id=? LIMIT 1", (uid,)).fetchone()
    if not row: return redirect(url_for("questionnaire"))
    return render_template("workout.html")

@app.route("/profile")
@login_required
def profile():
    uid = current_user_id()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM user_plans WHERE user_id=? LIMIT 1", (uid,)).fetchone()
    if not row: return redirect(url_for("questionnaire"))
    return render_template("profile.html")

@app.route("/history")
@login_required
def history(): return render_template("history.html")

@app.errorhandler(404)
def not_found(e): return render_template("404.html"), 404
# ══════════════════════════════════════════════════════════════
# PLAN API (TESTING VERSION - Records ML Logs per Second)
# ══════════════════════════════════════════════════════════════
@app.route("/api/save-plan", methods=["POST"])
@login_required
def save_plan():
    data = request.get_json(force=True) or {}
    user = data.get("userData", {})
    uid = current_user_id()

    # 🟢 1. حساب الـ Deload أوتوماتيك من الهيستوري بتاع آخر 7 أيام 🟢
    is_deload_week = False
    with get_db() as conn:
        history = conn.execute("SELECT * FROM workout_history WHERE user_id=? ORDER BY id DESC LIMIT 100", (uid,)).fetchall()
        today = datetime.now().date()
        total_rpe, rpe_count, skipped_count, critical_skips, total_exercises = 0, 0, 0, 0, 0
        fatigue_keywords = ["tired", "pain", "fatigue", "injured", "sore", "exhausted", "تعب", "وجع", "الم", "اصابة", "مجهد"]

        for h in history:
            try:
                date_str = h["date"].split(",")[0].strip()
                row_date = datetime.strptime(date_str, "%d %b %Y").date()
                if (today - row_date).days > 7: continue
                total_exercises += 1
                if h["completed"] == 0:
                    skipped_count += 1
                    reason = str(h["skip_reason"]).lower() if h["skip_reason"] else ""
                    if any(w in reason for w in fatigue_keywords): critical_skips += 1
                if h["rpe"] is not None and h["rpe"] > 0:
                    total_rpe += h["rpe"]
                    rpe_count += 1
            except: continue
        
        avg_rpe = (total_rpe / rpe_count) if rpe_count > 0 else 0
        skip_rate = (skipped_count / total_exercises * 100) if total_exercises > 0 else 0
        if critical_skips > 0 or avg_rpe >= 8.5 or (avg_rpe >= 8.0 and skip_rate >= 20.0):
            is_deload_week = True

# 🔥 الكود الخاص بالـ ML (نسخة الـ Production - بيسجل مرة واحدة في اليوم) 🔥
        today_str = today.strftime("%Y-%m-%d")
        existing_log = conn.execute("SELECT id FROM ml_fatigue_logs WHERE user_id=? AND date=?", (uid, today_str)).fetchone()
        if not existing_log:
            conn.execute(
                """INSERT INTO ml_fatigue_logs 
                   (user_id, date, avg_rpe, skip_rate_percent, critical_skips, rule_based_deload) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (uid, today_str, avg_rpe, skip_rate, critical_skips, 1 if is_deload_week else 0)
            )

    # 🧠 ذكاء الـ ML: قراءة Volume Logs القديمة لتعديل الخطة الجديدة 🧠
    weak_muscles_from_ml = []
    with get_db() as conn:
        # نبحث عن العضلات التي كانت "low" في آخر 30 يوم
        under_volume_logs = conn.execute(
            """SELECT muscle_group FROM ml_volume_logs 
               WHERE user_id=? AND status='low' AND date >= date('now', '-30 day')
               GROUP BY muscle_group""", 
            (uid,)
        ).fetchall()
        for log in under_volume_logs:
            weak_muscles_from_ml.append(log["muscle_group"].lower())

    goal_map  = {"lose": "cut", "build": "gain", "maintain": "maintain"}
    equip_map = {"full_gym": "full_gym", "dumbbell_only": "dumbbells", "at_home": "home"}
    inj = user.get("injuries", ""); weak = user.get("weakMuscles", "")
    
    # دمج العضلات الضعيفة من المستخدم مع التي اكتشفها الـ ML
    final_weak_muscles = [weak] if weak and weak not in ("", "None") else []
    for m in weak_muscles_from_ml:
        if m not in final_weak_muscles:
            final_weak_muscles.append(m)
    
    profile = {
        "experience":          user.get("level", "beginner"),
        "training_days":       min(int(user.get("workoutDays", 3)), 6),
        "goal":                goal_map.get(user.get("goal", "maintain"), "maintain"),
        "activity_level":      "office",
        "injuries":            [inj]  if inj  and inj  not in ("", "None") else [],
        "weak_muscles":        final_weak_muscles,
        "leg_days_preference": min(int(user.get("legDays", 2)), 2),
        "workspace":           equip_map.get(user.get("equipment", "full_gym"), "full_gym"),
        "volume":              user.get("volume", "medium"),
        "gender":              user.get("gender", "male"),
        "weight_kg":           float(user.get("weight", 70)),
        "height_cm":           float(user.get("height", 175)),
        "age":                 int(user.get("age", 25)),
        "is_deload_week":      is_deload_week , 
        "disliked_exercises":  user.get("dislikedExercises", [])
    }
    
    try:
        import pathlib, importlib.util
        # 🔗 ربط مباشر بالملف النضيف workout4.py
        ep = pathlib.Path(__file__).parent / "workout4.py"
        spec = importlib.util.spec_from_file_location("workout_engine", ep)
        eng  = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)
        
        
        
        engine_result = eng.build_workout_plan(profile)
        ai_days = engine_result.get("workout_days", []) if isinstance(engine_result, dict) else engine_result
        
        for day in ai_days:
            if "day" in day and not day.get("focus"):
                day["focus"] = day["day"]
            for ex in day.get("exercises", []):
                k = DB_NAME_TO_KEY.get(ex.get("name", ""))
                ex["cam_key"] = k; ex["has_cam"] = k is not None and k in EXERCISE_MAP

        split_name = engine_result.get("split", "") if isinstance(engine_result, dict) else ""
        schedule = [f"Day {i+1}: {d.get('focus', d.get('day', ''))}" for i, d in enumerate(ai_days)]
        
        plan = {
            "title":        f"{profile['goal'].title()} Plan",
            "split":        split_name,
            "days_per_week": len(ai_days),
            "level":        profile.get("experience", ""),
            "goal":         profile.get("goal", ""),
            "schedule":     schedule,
            "ai_days":      ai_days,
            "deload_msg":   engine_result.get("deload_recommendation", "") if is_deload_week else ""
        }
    except Exception as e:
        print(f"[Engine] ERROR: {e}")
        plan = data.get("plan", {"title": "Your Plan", "schedule": [], "ai_days": []})

    # 🔥 3. تسجيل الـ Volume Compliance في الداتابيز 🔥
    vol_report = engine_result.get("volume_report", {})
    today_str = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        has_logged = conn.execute("SELECT id FROM ml_volume_logs WHERE user_id=? AND date=? LIMIT 1", (uid, today_str)).fetchone()
        if not has_logged and vol_report:
            for muscle, data_vol in vol_report.items():
                conn.execute(
                    """INSERT INTO ml_volume_logs 
                        (user_id, date, muscle_group, target_min, target_max, actual_sets, status) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (uid, today_str, muscle, float(data_vol.get("target_min",0)), float(data_vol.get("target_max",0)), float(data_vol.get("actual",0)), data_vol.get("status",""))
                    )

    session["userData"] = user
    session["plan"]     = plan

    # Save to DB
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM user_plans WHERE user_id=?", (uid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE user_plans SET user_data=?, plan_data=?, updated=? WHERE user_id=?",
                (json.dumps(user), json.dumps(plan), datetime.now().isoformat(), uid)
            )
        else:
            conn.execute(
                "INSERT INTO user_plans (user_id, user_data, plan_data, updated) VALUES (?,?,?,?)",
                (uid, json.dumps(user), json.dumps(plan), datetime.now().isoformat())
            )
    return jsonify({"status": "ok", "redirect": "/dashboard"})
@app.route("/api/debug-plan")
@login_required
def debug_plan():
    uid = current_user_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_plans WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)
        ).fetchone()
    if not row:
        return jsonify({"error": "No plan in DB"})
    plan = json.loads(row["plan_data"] or "{}")
    return jsonify({
        "plan_keys": list(plan.keys()),
        "has_ai_days": "ai_days" in plan,
        "ai_days_count": len(plan.get("ai_days", [])),
        "schedule_count": len(plan.get("schedule", [])),
    })

@app.route("/api/get-plan")
@login_required
def get_plan():
    uid = current_user_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_plans WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)
        ).fetchone()
    if row:
        plan = json.loads(row["plan_data"] or "{}")
        # 🔥 Patch old plans dynamically
        for day in plan.get("ai_days", []):
            for ex in day.get("exercises", []):
                k = DB_NAME_TO_KEY.get(ex.get("name", ""))
                ex["cam_key"] = k
                ex["has_cam"] = k is not None and k in EXERCISE_MAP
        return jsonify({
            "userData": json.loads(row["user_data"] or "{}"),
            "plan":     plan
        })
    return jsonify({"userData": session.get("userData", {}), "plan": session.get("plan", {})})

@app.route("/api/get-today-exercises")
@login_required
def get_today_exercises():
    plan = session.get("plan", {})
    # if session plan is empty, try fetch from db
    if not plan:
        uid = current_user_id()
        with get_db() as conn:
            row = conn.execute("SELECT plan_data FROM user_plans WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
            if row:
                plan = json.loads(row["plan_data"] or "{}")

    ai_days = plan.get("ai_days", [])
    try: idx = int(request.args.get("day", 0))
    except: idx = 0
    if not ai_days: return jsonify({"exercises": [], "focus": "No plan yet"})
    day = ai_days[idx % len(ai_days)]
    
    # 🔥 Patch on the fly
    user_goal = session.get("userData", {}).get("goal", "maintain")
    uid = current_user_id()

    with get_db() as conn:
        for ex in day.get("exercises", []):
            k = DB_NAME_TO_KEY.get(ex.get("name", ""))
            ex["cam_key"] = k
            ex["has_cam"] = k is not None and k in EXERCISE_MAP
            
            # 🔥 ذكاء الـ ML: توقع الوزن (Progressive Overload) 🔥
            last_perf = conn.execute(
                "SELECT weight_kg, reps, rpe FROM workout_history WHERE user_id=? AND exercise=? AND completed=1 ORDER BY id DESC LIMIT 1",
                (uid, ex.get("name", ""))
            ).fetchone()
            
            if last_perf and last_perf["weight_kg"] is not None:
                last_w = float(last_perf["weight_kg"])
                last_r = int(last_perf["reps"])
                last_rpe = int(last_perf["rpe"] or 8)
                
                increment = 2.5 if last_w >= 20 else 1.25  # smart increment
                if user_goal == "cut":
                    if last_rpe <= 7:
                        ex["recommended_weight"] = last_w + increment
                    else:
                        ex["recommended_weight"] = last_w
                    ex["recommended_reps"] = last_r
                else: 
                    if last_rpe <= 8:
                        ex["recommended_weight"] = last_w + increment
                        ex["recommended_reps"] = last_r
                    else:
                        ex["recommended_weight"] = last_w
                        ex["recommended_reps"] = last_r + 1
            else:
                ex["recommended_weight"] = 0 
                ex["recommended_reps"] = 0
        
    return jsonify({"focus": day.get("focus", day.get("muscle_group", "")), "exercises": day.get("exercises", [])})

# ══════════════════════════════════════════════════════════════
# FOOD API
# ══════════════════════════════════════════════════════════════
def _food_search_results(foods, grams, match_type, query=""):
    out = []
    for f in foods[:5]:
        n = calc_nutrients(f, grams, 0, 0, 0)
        label = display_name_for_query(f, query) if query else f["name"]
        out.append({
            "id": f["id"], "name": label, "canonical_name": f["name"],
            "grams": grams,
            "calories": n["calories"], "protein": n["protein"],
            "carbs": n["carbs"], "fat": n["fat"],
            "ask_cooking": f.get("ask_cooking", False),
        })
    return jsonify({"found": True, "match_type": match_type, "results": out})


def _groq_configured():
    """Check if GROQ_API_KEY is available (env var or .env file)."""
    _load_project_env()
    return bool(os.getenv("GROQ_API_KEY", "").strip())


@app.route("/api/food/search", methods=["POST"])
def food_search():
    b = request.get_json(force=True) or {}
    q = (b.get("query") or "").strip()
    g = float(b.get("grams") or 100)
    use_ai_only = bool(b.get("use_ai"))
    if not q:
        return jsonify({"error": "query required"}), 400

    def _groq_fail_payload():
        err = "لم نقدر نحدد الأكلة عبر Groq. جرّب اسم أوضح أو أضفها يدوياً."
        if not _groq_configured():
            # Check os.environ first (Railway injects vars directly, no .env file needed)
            if not os.getenv("GROQ_API_KEY", "").strip():
                err = "GROQ_API_KEY غير موجود. أضفه في Railway Dashboard → Variables."
            print("[food_search] GROQ_API_KEY missing — Groq skipped")
        return {"found": False, "query": q, "ai_attempted": True, "groq_error": err}

    # Optional: skip local DB and ask Groq directly
    if use_ai_only:
        food = groq_lookup(q) if _groq_configured() else None
        if not food:
            return jsonify(_groq_fail_payload())
        return _food_search_results([food], g, "groq", q)

    # Strict local match only (no fuzzy) — then Groq for unknown dishes
    results, mt = find_food_strict(q)
    if results and mt in ("db", "franco"):
        return _food_search_results(results, g, mt, q)

    print(f"[food_search] No strict match for '{q}' — trying Groq...")
    food = groq_lookup(q) if _groq_configured() else None
    if food:
        return _food_search_results([food], g, "groq", q)

    return jsonify(_groq_fail_payload())

@app.route("/api/food/cooking-methods")
def cooking_methods(): return jsonify(COOKING_METHODS)

@app.route("/api/food/with-cooking", methods=["POST"])
def food_with_cooking():
    b = request.get_json(force=True) or {}
    food = next((f for f in FOOD_DB if f["id"] == int(b.get("food_id", -1))), None)
    if not food: return jsonify({"error": "Not found"}), 404
    m = COOKING_METHODS.get(str(b.get("cooking_key", "1")), COOKING_METHODS["1"])
    g = float(b.get("grams") or 100); n = calc_nutrients(food, g, m.get("fat_add", 0), m.get("cal_add", 0), m.get("carb_add", 0))
    return jsonify({"name": food["name"], "cooking_label": m["label"], "grams": g, **n})

@app.route("/api/food/add-custom", methods=["POST"])
def add_custom_food():
    b = request.get_json(force=True) or {}
    meal = (b.get("meal") or "").strip().lower(); name = (b.get("name") or "").strip(); cal = b.get("calories")
    if not meal or not name: return jsonify({"error": "Meal and name required"}), 400
    try: cal = float(cal)
    except: return jsonify({"error": "Invalid calories"}), 400
    if cal <= 0: return jsonify({"error": "Calories must be >0"}), 400
    cf = session.get("custom_foods", [])
    cf.append({"id": len(cf)+1, "meal": meal, "name": name, "calories": round(cal, 1),
               "protein": round(float(b.get("protein") or 0), 1),
               "carbs":   round(float(b.get("carbs")   or 0), 1),
               "fat":     round(float(b.get("fat")     or 0), 1)})
    session["custom_foods"] = cf
    return jsonify({"status": "ok", "food": cf[-1]})

@app.route("/api/food/custom-list")
def custom_food_list(): return jsonify({"custom_foods": session.get("custom_foods", [])})

# ══════════════════════════════════════════════════════════════
# WATER & WEIGHT API
# ══════════════════════════════════════════════════════════════
@app.route("/api/water", methods=["GET", "POST"])
@login_required
def api_water():
    uid = current_user_id()
    today_str = datetime.now().strftime("%Y-%m-%d")
    if request.method == "POST":
        data = request.get_json(force=True)
        amount = int(data.get("amount_ml", 0))
        with get_db() as conn:
            row = conn.execute("SELECT id, amount_ml FROM water_log WHERE user_id=? AND date=?", (uid, today_str)).fetchone()
            if row:
                conn.execute("UPDATE water_log SET amount_ml = amount_ml + ? WHERE id=?", (amount, row["id"]))
            else:
                conn.execute("INSERT INTO water_log (user_id, date, amount_ml) VALUES (?, ?, ?)", (uid, today_str, amount))
        return jsonify({"status": "ok"})
    else:
        with get_db() as conn:
            row = conn.execute("SELECT amount_ml FROM water_log WHERE user_id=? AND date=?", (uid, today_str)).fetchone()
        return jsonify({"amount_ml": row["amount_ml"] if row else 0})

@app.route("/api/weight", methods=["GET", "POST"])
@login_required
def api_weight():
    uid = current_user_id()
    if request.method == "POST":
        data = request.get_json(force=True)
        weight = float(data.get("weight_kg", 0))
        today_str = datetime.now().strftime("%Y-%m-%d")
        with get_db() as conn:
            row = conn.execute("SELECT id FROM weight_log WHERE user_id=? AND date=?", (uid, today_str)).fetchone()
            if row:
                conn.execute("UPDATE weight_log SET weight_kg = ? WHERE id=?", (weight, row["id"]))
            else:
                conn.execute("INSERT INTO weight_log (user_id, date, weight_kg) VALUES (?, ?, ?)", (uid, today_str, weight))
        return jsonify({"status": "ok"})
    else:
        with get_db() as conn:
            rows = conn.execute("SELECT date, weight_kg FROM weight_log WHERE user_id=? ORDER BY date ASC LIMIT 30", (uid,)).fetchall()
        return jsonify({"history": [dict(r) for r in rows]})

# ══════════════════════════════════════════════════════════════
# HISTORY API  — updated to support weight, rpe, completed, skip_reason
# ══════════════════════════════════════════════════════════════
@app.route("/api/history/save", methods=["POST"])
@login_required
def save_history():
    data = request.get_json(force=True)
    uid = current_user_id()
    
    # 1. استخراج الداتا اللي جيالنا من واجهة التمرين
    ex_name = data.get("exercise")
    reps = data.get("reps", 0)
    sets = data.get("sets", 0)
    rpe = data.get("rpe")
    completed = data.get("completed", 1)
    skip_reason = data.get("skip_reason")
    duration = data.get("duration", "—")
    weight_kg = data.get("weight_kg")

    today_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    with get_db() as conn:
        # 2. حفظ التمرينة العادية في جدول الهيستوري
        conn.execute(
            """INSERT INTO workout_history 
               (user_id, date, exercise, sets, reps, duration, weight_kg, rpe, completed, skip_reason) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, today_str, ex_name, sets, reps, duration, weight_kg, rpe, completed, skip_reason)
        )
        
        # 3. 🔥 ذكاء الـ ML: تحديث قرار اليوزر (user_accepted_deload) 🔥
        # بنجيب آخر ريكورد لليوزر ده في جدول الـ ML
  # 3. 🔥 ذكاء الـ ML: تحديث قرار اليوزر (user_accepted_deload) 🔥
        last_ml_log = conn.execute(
            "SELECT id, rule_based_deload, user_accepted_deload FROM ml_fatigue_logs WHERE user_id=? ORDER BY id DESC LIMIT 1", 
            (uid,)
        ).fetchone()

        if last_ml_log:
            log_id = last_ml_log["id"]
            rule_deload = last_ml_log["rule_based_deload"]
            accepted = last_ml_log["user_accepted_deload"]

            if rule_deload == 1:
                # هل اليوزر عاند في التمرينة دي؟
                user_rejected_now = (sets > 3) or (rpe is not None and rpe >= 9)
                
                if user_rejected_now:
                    # لو عاند في التمرينة دي.. الأسبوع كله باظ، سجل 0 وماترجعش فيها!
                    conn.execute("UPDATE ml_fatigue_logs SET user_accepted_deload = 0 WHERE id=?", (log_id,))
                else:
                    # لو التمرينة دي خفيفة ومحترمة.. 
                    # سجل 1 (بشرط إن الأسبوع ميكونش باظ قبل كده وواخد 0 في تمرينة تانية)
                    if accepted == -1 or accepted is None:
                        conn.execute("UPDATE ml_fatigue_logs SET user_accepted_deload = 1 WHERE id=?", (log_id,))

        # 4. 🔥 تسجيل التطور في جدول ml_overload_logs 🔥
        user_goal = session.get("userData", {}).get("goal", "maintain")
        
        last_perf = conn.execute(
            "SELECT weight_kg, reps, rpe FROM workout_history WHERE user_id=? AND exercise=? AND completed=1 AND id != (SELECT MAX(id) FROM workout_history WHERE user_id=? AND exercise=?) ORDER BY id DESC LIMIT 1",
            (uid, ex_name, uid, ex_name)
        ).fetchone()

        if weight_kg is not None:
            if last_perf and last_perf["weight_kg"] is not None:
                last_w = float(last_perf["weight_kg"])
                last_r = int(last_perf["reps"])
                last_rpe = int(last_perf["rpe"] or 8)
                
                increment = 2.5 if last_w >= 20 else 1.25
                rec_w, rec_r = last_w, last_r
                
                if user_goal == "cut":
                    if last_rpe <= 7: rec_w += increment
                else:
                    if last_rpe <= 8: rec_w += increment
                    else: rec_r += 1
                
                w_kg = float(weight_kg)
                r = int(reps)
                current_rpe = int(rpe) if rpe is not None else 8

                user_accepted_rec = 1
                if w_kg > rec_w:
                    user_accepted_rec = 0  # كابر
                elif w_kg < rec_w:
                    user_accepted_rec = -1 # شال أخف
                    
                success = 0
                if user_accepted_rec == 1 and current_rpe <= 8:
                    if w_kg >= rec_w and r >= rec_r:
                        success = 1
                elif user_accepted_rec == 0:
                    if r >= rec_r and current_rpe <= 8.5:
                        success = 1
                    if current_rpe >= 9 or r < rec_r:
                        success = 0
                elif user_accepted_rec == -1:
                    if r >= rec_r + 2 and current_rpe <= 8:
                        success = 1
            else:
                rec_w = 0
                rec_r = 0
                success = None
                user_accepted_rec = None
                
            conn.execute(
                """INSERT INTO ml_overload_logs 
                   (user_id, date, exercise, goal, recommended_weight_kg, recommended_reps, actual_weight_kg, actual_reps, rpe, overload_success, user_accepted_recommendation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, today_str, ex_name, user_goal, rec_w, rec_r, float(weight_kg), int(reps), int(rpe) if rpe is not None else 8, success, user_accepted_rec)
            )

    return jsonify({"status": "ok"})
@app.route("/api/history/list")
@login_required
def history_list():
    uid = current_user_id()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM workout_history WHERE user_id=? ORDER BY id DESC LIMIT 100", (uid,)
        ).fetchall()
    return jsonify({"history": [dict(r) for r in rows]})

@app.route("/api/history/clear", methods=["POST"])
@login_required
def history_clear():
    uid = current_user_id()
    with get_db() as conn:
        conn.execute("DELETE FROM workout_history WHERE user_id=?", (uid,))
    return jsonify({"status": "ok"})

@app.route("/api/dashboard-summary")
@login_required
def dashboard_summary():
    uid = current_user_id()
    with get_db() as conn:
        history = conn.execute("SELECT * FROM workout_history WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
        row = conn.execute("SELECT plan_data FROM user_plans WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    
    plan = json.loads(row["plan_data"] or "{}") if row else {}
    schedule = plan.get("schedule", [])
    
    if not history:
        return jsonify({
            "streak": 0,
            "last_session": None,
            "next_workout": schedule[0] if schedule else "No plan yet"
        })
    
    daily_sessions = {}
    for h in history:
        try:
            d_str = h["date"].split(",")[0].strip()
            # If day lacks leading zero, strptime handles it fine with %d
            dt = datetime.strptime(d_str, "%d %b %Y").date()
            if dt not in daily_sessions:
                daily_sessions[dt] = []
            daily_sessions[dt].append(h)
        except Exception as e:
            continue
            
    sorted_days = sorted(daily_sessions.keys(), reverse=True)
    
    streak = 0
    today = datetime.now().date()
    check_date = today
    
    if sorted_days and sorted_days[0] == today:
        streak += 1
        check_date = today - timedelta(days=1)
    elif sorted_days and sorted_days[0] == today - timedelta(days=1):
        streak += 1
        check_date = today - timedelta(days=2)
        
    if streak > 0:
        for d in sorted_days[1:]:
            if d == check_date:
                streak += 1
                check_date -= timedelta(days=1)
            elif d < check_date:
                break
                
    last_session_dt = sorted_days[0] if sorted_days else None
    last_session_data = None
    if last_session_dt:
        ex_names = []
        for h in daily_sessions[last_session_dt]:
            if h["exercise"] and h["exercise"] not in ex_names:
                ex_names.append(h["exercise"])
        last_time_str = daily_sessions[last_session_dt][0]["date"]
        last_session_data = {
            "date": last_time_str,
            "exercises": ex_names
        }
        
    unique_days_count = len(sorted_days)
    next_workout = schedule[unique_days_count % len(schedule)] if schedule else "No plan yet"
    
    return jsonify({
        "streak": streak,
        "last_session": last_session_data,
        "next_workout": next_workout
    })
@app.route("/api/weekly-stats")
@login_required
def weekly_stats():
    uid = current_user_id()
    
    with get_db() as conn:
        history = conn.execute(
            "SELECT * FROM workout_history WHERE user_id=? ORDER BY id DESC LIMIT 200", 
            (uid,)
        ).fetchall()
        
    if not history:
        return jsonify({
            "sessions_completed": 0,
            "avg_rpe": 0,
            "skip_rate_percent": 0,
            "fatigue_level": "Low",
            "deload_suggested": False
        })

    today = datetime.now().date()
    last_7_days_data = []
    unique_dates = set()
    
    total_rpe = 0
    rpe_count = 0
    skipped_count = 0
    critical_skips = 0  
    total_exercises = 0

    # كلمات مفتاحية بتدل على الإرهاق أو الإصابة
    fatigue_keywords = ["tired", "pain", "fatigue", "injured", "sore", "exhausted", "تعب", "وجع", "الم", "اصابة", "مجهد", "مرهق", "مش قادر", "مرض", "sick", "ill"]

    for h in history:
        try:
            date_str = h["date"].split(",")[0].strip()
            row_date = datetime.strptime(date_str, "%d %b %Y").date()
            
            if (today - row_date).days > 7:
                continue
                
            last_7_days_data.append(h)
            total_exercises += 1
            
            # حساب الأيام اللي اتمرن فيها بجد
            if h["completed"] == 1:
                unique_dates.add(row_date)
            
            # تحليل سبب التخطي
            if h["completed"] == 0:
                skipped_count += 1
                reason = str(h["skip_reason"]).lower() if h["skip_reason"] else ""
                
                if any(word in reason for word in fatigue_keywords):
                    critical_skips += 1
                
            # حساب الـ RPE حتى لو التمرينة متكملتش
            if h["rpe"] is not None and h["rpe"] > 0:
                total_rpe += h["rpe"]
                rpe_count += 1
                
        except Exception as e:
            continue

    sessions_completed = len(unique_dates)
    avg_rpe = round(total_rpe / rpe_count, 1) if rpe_count > 0 else 0
    skip_rate = round((skipped_count / total_exercises) * 100, 1) if total_exercises > 0 else 0

    deload_suggested = False
    fatigue_level = "Low"

    # 🧠 ذكاء الـ ML: التقييم التراكمي للإرهاق (Cumulative Fatigue) 🧠
    with get_db() as conn:
        past_logs = conn.execute(
            "SELECT avg_rpe FROM ml_fatigue_logs WHERE user_id=? AND date >= date('now', '-14 day') ORDER BY id DESC LIMIT 2", (uid,)
        ).fetchall()
        
        cumulative_fatigue = False
        if len(past_logs) >= 2 and avg_rpe >= 7.8 and past_logs[1]["avg_rpe"] >= 7.8:
            cumulative_fatigue = True

    # اللوجيك بتاع الـ Deload
    if critical_skips > 0:
        fatigue_level = "High (Pain/Fatigue Explicitly Reported)"
        deload_suggested = True
    elif avg_rpe >= 8.5:
        fatigue_level = "High (Heavy CNS Load)"
        deload_suggested = True
    elif avg_rpe >= 8.0 and skip_rate >= 20.0:
        fatigue_level = "High (Burnout Symptoms)"
        deload_suggested = True
    elif cumulative_fatigue:
        fatigue_level = "High (Cumulative CNS Load > 2 weeks)"
        deload_suggested = True
    elif avg_rpe >= 7.0:
        fatigue_level = "Moderate"
    else:
        fatigue_level = "Optimal"

    # الحفظ في جدول الـ ML لتجميع الداتا للمستقبل
# 🧠 ذكاء الـ ML: التقييم المتأخر (Delayed Feedback) والحفظ 🧠
    with get_db() as conn:
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. تقييم الديلود القديم: كل الأسابيع المعلقة (بدون LIMIT 1)
        pending_evals = conn.execute(
            """SELECT id, date FROM ml_fatigue_logs 
               WHERE user_id=? AND rule_based_deload=1 AND deload_effective IS NULL 
               AND date <= date('now', '-7 day')
               ORDER BY id ASC""",
            (uid,)
        ).fetchall()

        for pending in pending_evals:
            # لو الأسبوع الحالي هو ديلود أيضاً، ننتظر الأسبوع القادم للحكم (تجنب Consecutive Deloads failure)
            if deload_suggested:
                continue
                
            # بنسأل جدول التطور: هل اليوزر نجح يزود أوزان بعد الديلود؟
            progress_check = conn.execute(
                """SELECT COUNT(*) as success_count FROM ml_overload_logs 
                   WHERE user_id=? AND overload_success=1 
                   AND date > ?""",
                (uid, pending["date"])
            ).fetchone()
            
            has_progress = progress_check["success_count"] > 0
            
            if avg_rpe < 8.0 and critical_skips == 0 and has_progress:
                is_effective = 1
            else:
                is_effective = 0
                
            conn.execute("UPDATE ml_fatigue_logs SET deload_effective = ? WHERE id = ?", (is_effective, pending["id"]))

        # 2. حفظ بيانات الأسبوع الحالي
        existing_log = conn.execute("SELECT id FROM ml_fatigue_logs WHERE user_id=? AND date=?", (uid, today_str)).fetchone()
        
        if not existing_log:
            conn.execute(
                """INSERT INTO ml_fatigue_logs 
                   (user_id, date, avg_rpe, skip_rate_percent, critical_skips, rule_based_deload) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (uid, today_str, avg_rpe, skip_rate, critical_skips, 1 if deload_suggested else 0)
            )

    return jsonify({
        "timeframe": "Last 7 Days",
        "total_exercises_planned": total_exercises,
        "sessions_completed": sessions_completed,
        "avg_rpe": avg_rpe,
        "skip_rate_percent": skip_rate,
        "critical_skips_count": critical_skips,
        "fatigue_level": fatigue_level,
        "deload_suggested": deload_suggested
    })
@app.route("/api/workout/start", methods=["POST"])
@login_required
def workout_start():
    global current_trainer, workout_state
    b   = request.get_json(force=True) or {}; key = b.get("exercise", "tricep_pushdown")
    lang = b.get("language", "ar")
    if key not in EXERCISE_MAP: return jsonify({"error": f"Unknown: {key}"}), 400
    with workout_lock:
        if workout_state["running"]: return jsonify({"error": "Already running"}), 409
    try:
        _load_pose_model()
    except (FileNotFoundError, ImportError, Exception) as e:
        print(f"[workout_start] model load error: {e}")
        return jsonify({"error": f"Model load failed: {e}"}), 503
    t = _load_trainer(key, lang)
    if t is None: return jsonify({"error": f"Load failed: {key}"}), 500
    current_trainer = t
    with workout_lock:
        workout_state.update({"running": True, "exercise": key, "reps": 0, "feedback": "Setup", "_frame": None})
    return jsonify({"status": "started", "exercise": key})


@app.route("/api/workout/frame", methods=["POST"])
@login_required
def workout_frame():
    if "frame" not in request.files: 
        return jsonify({"error": "No frame"}), 400
    
    try:
        import cv2
        import numpy as np
    except ImportError:
        return jsonify({
            "error": "Workout camera needs OpenCV. Run: py -m pip install opencv-python-headless numpy"
        }), 503

    frame = cv2.imdecode(np.frombuffer(request.files["frame"].read(), np.uint8), cv2.IMREAD_COLOR)
    if frame is None: 
        return jsonify({"error": "Decode failed"}), 400
        
    with workout_lock:
        if not workout_state["running"] or current_trainer is None:
            return jsonify({"running": False, "reps": 0, "feedback": "Session ended"}), 200
            
    try:
        _load_pose_model()
        
        r = pose_model.track(frame, persist=True, verbose=False)
        
        if not r or r[0].keypoints is None or len(r[0].keypoints.xy) == 0:
            return jsonify({"running": True, "reps": workout_state["reps"], "feedback": "Can't see you – step back"})
            
        kp = r[0].keypoints.xy[0].cpu().numpy()
        cf = r[0].keypoints.conf[0].cpu().numpy()
        
        if kp.shape[0] == 0:
            return jsonify({"running": True, "reps": workout_state["reps"], "feedback": "Can't see you – step back"})
            
        with workout_lock:
            if not workout_state["running"]:
                return jsonify({"running": False, "reps": workout_state["reps"], "feedback": "Session ended"}), 200
                
        current_trainer.process(frame, kp, cf)
        
        with workout_lock:
            workout_state["reps"]    = current_trainer.counter
            workout_state["feedback"] = current_trainer.feedback
            return jsonify({"running": True, "reps": workout_state["reps"], "feedback": workout_state["feedback"]})
            
    except Exception as e:
        print(f"[Frame] {e}")
        return jsonify({"error": "Processing error"}), 500

@app.route("/api/workout/stop", methods=["POST"])
@login_required
def workout_stop():
    global workout_state, current_trainer
    with workout_lock:
        if not workout_state["running"]: return jsonify({"error": "Not running"}), 400
        workout_state["running"] = False
        s = {"exercise": workout_state["exercise"], "reps": workout_state["reps"]}
    try:
        if current_trainer and hasattr(current_trainer, "coach"):
            current_trainer.coach.stop()
    except: pass
    return jsonify({"status": "stopped", "summary": s})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)