import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle, get_pull_ratio
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    FLY_L2H_SETUP,
    FLY_L2H_STRETCH,
    FLY_L2H_SQUEEZE,
    FLY_L2H_BENT,
    GOOD_REP,
)

class CableFlyLowToHighTrainerAI:
    def __init__(self, language="ar"):
        self.counter        = 0
        self.stage          = "back"
        self.feedback       = "Setup"
        self.coach          = AICoach(language=language)

        # ── Full Result Smoothing ────────────────────────────────────
        self._ratio_buffer = deque(maxlen=1)
        self._angle_buffer = deque(maxlen=1) # 🟢 ضفنا التنعيم للزاوية

        # ── Robust Direction Tracking ────────────────────────────────
        self.min_ratio_this_rep = 1.0
        self.max_ratio_this_rep = 0.0

    def _get_smoothed_ratio(self, ratio: float) -> float:
        self._ratio_buffer.append(ratio)
        return float(np.mean(self._ratio_buffer))

    def _get_smoothed_angle(self, angle: float) -> float:
        self._angle_buffer.append(angle)
        return float(np.mean(self._angle_buffer))

    def _reset_rep_tracking(self):
        self.min_ratio_this_rep = 1.0
        self.max_ratio_this_rep = 0.0

    def process(self, frame, keypoints, confs):
        # ── Visibility check ────────────────────────────────────────
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW SIDE VIEW WITH HIPS"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(FLY_L2H_SETUP, urgent=True)
            return frame
        
        self.coach.reset_error(FLY_L2H_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        # ── Calculate metrics ────────────────────────────────────────
        raw_angle   = calculate_angle(shoulder, elbow, wrist)
        raw_ratio   = get_pull_ratio(wrist, elbow, shoulder, hip)
        
        press_angle = self._get_smoothed_angle(raw_angle) # 🟢 تنعيم الزاوية
        ratio       = self._get_smoothed_ratio(raw_ratio)

        # ── Track extremes for direction detection ────────────────────
        # 🟢 وهو بيعصر لقدام النسبة بتزيد -> نسجل Max
        if self.stage == "back":
            self.max_ratio_this_rep = max(self.max_ratio_this_rep, ratio)
        # 🟢 وهو بيرجع لورا النسبة بتقل -> نسجل Min
        elif self.stage == "forward":
            self.min_ratio_this_rep = min(self.min_ratio_this_rep, ratio)

        current_color = (0, 255, 0)
        voice_message = None

        # ── 1. Ratio / Stage Logic (حساب العدة والاتجاه) ──────────────
        # 1) Back position (arms fully stretched back)
        if ratio < 0.35:
            if self.stage != "back":
                self.stage    = "back"
                self.feedback = "NOW SQUEEZE UP!"
                current_color = (255, 255, 255)
                self._reset_rep_tracking()
                self.coach.reset_error(FLY_L2H_STRETCH)
            else:
                self.feedback = "NOW SQUEEZE UP!"
                current_color = (255, 255, 255)

        # 2) Forward squeeze — rep complete (خليناها 0.70 بدل 0.75 عشان متبقاش رخمة)
        elif ratio > 0.70:
            if self.stage == "back":
                self.stage    = "forward"
                self.counter += 1
                self.feedback = "GOOD SQUEEZE!"
                current_color = (0, 255, 0)
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(FLY_L2H_SQUEEZE)
                self._reset_rep_tracking()

        # 3) Warning: Letting arms go back too early (Short Stretch)
        elif self.stage == "forward" and ratio < 0.60:
            # لو وهو بيرجع لورا قرر يعكس اتجاهه لقدام بـ 0.15 قبل ما يوصل للآخر
            if ratio - self.min_ratio_this_rep > 0.15:
                self.feedback = "LET ARMS GO BACK!"
                current_color = (0, 165, 255)
                voice_message = FLY_L2H_STRETCH

        # 4) Warning: Not squeezing fully (Short Squeeze)
        elif self.stage == "back" and 0.45 < ratio < 0.70:
            # لو وهو بيعصر لقدام قرر يعكس اتجاهه لورا بـ 0.15 قبل ما يوصل للآخر
            if self.max_ratio_this_rep - ratio > 0.15:
                self.feedback = "SQUEEZE HANDS TOGETHER!"
                current_color = (0, 165, 255)
                voice_message = FLY_L2H_SQUEEZE

        # 5) Normal squeezing
        elif self.stage == "back" and ratio >= 0.35:
            if not voice_message: 
                self.feedback = "SQUEEZING..."
                current_color = (255, 255, 255)

        # ── 2. Independent Angle Check (حساب الكوع مفصول تماماً) ───────
        if press_angle < 110:
            self.feedback = "DON'T BEND ELBOWS!"
            current_color = (0, 165, 255)
            voice_message = FLY_L2H_BENT
        elif press_angle > 115:
            self.coach.reset_error(FLY_L2H_BENT)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, f"Ratio: {ratio:.2f}", tuple(wrist.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), (255, 0, 0), 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)