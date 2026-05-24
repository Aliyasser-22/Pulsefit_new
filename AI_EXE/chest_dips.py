import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    DIPS_SETUP,
    DIPS_LOWER,
    DIPS_LOCK,
    DIPS_LEAN,
    GOOD_REP # 🟢 ضفنا دي عشان التقفيل الصح للعدة
)

class ChestDipsTrainerAI:
    def __init__(self, language="ar"):
        self.counter        = 0
        self.stage          = "up"  # "up" = فوق مفرود, "down" = نازل تحت
        self.feedback       = "Setup"
        self.coach          = AICoach(language=language)

        # ── Full Result Smoothing ────────────────────────────────────
        self._press_angle_buffer  = deque(maxlen=1)
        self._shoulder_ext_buffer = deque(maxlen=1)

        # ── Robust Direction Tracking ────────────────────────────────
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _smooth(self, buffer: deque, val: float) -> float:
        buffer.append(val)
        return float(np.mean(buffer))

    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def process(self, frame, keypoints, confs):
        # ── Visibility check ────────────────────────────────────────
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW SIDE VIEW & HIPS"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(DIPS_SETUP, urgent=True)
            return frame
        
        self.coach.reset_error(DIPS_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        # ── Calculate metrics ────────────────────────────────────────
        raw_press_angle  = calculate_angle(shoulder, elbow, wrist)
        raw_shoulder_ext = calculate_angle(hip, shoulder, elbow)

        press_angle  = self._smooth(self._press_angle_buffer,  raw_press_angle)
        shoulder_ext = self._smooth(self._shoulder_ext_buffer, raw_shoulder_ext)

        # ── Track extremes for direction detection ────────────────────
        if self.stage == "up":
            # وهو نازل (الزاوية بتقل)، نراقب أقل زاوية وصلها
            self.min_angle_this_rep = min(self.min_angle_this_rep, press_angle)
        elif self.stage == "down":
            # وهو طالع (الزاوية بتزيد)، نراقب أعلى زاوية وصلها
            self.max_angle_this_rep = max(self.max_angle_this_rep, press_angle)

        current_color = (0, 255, 0)
        voice_message = None

        # 1) Peak / top position (Lockout)
        if press_angle > 155:
            if self.stage != "up":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)
                
                # 🟢 AI Coach Completion Logic
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(DIPS_LOCK)
                self.coach.reset_error(DIPS_LOWER)
                
                self._reset_rep_tracking()

        # 2) Bottom (deep dip) — requires adequate shoulder extension
        elif press_angle < 90 and shoulder_ext > 45:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "PUSH UP!"
                current_color = (255, 255, 255)
                self.coach.reset_error(DIPS_LOWER)
                self._reset_rep_tracking()
            else:
                self.feedback = "PUSH UP!"
                current_color = (255, 255, 255)

        # 3) Warning: Not dipping low enough while descending
        elif self.stage == "up" and press_angle > 90:
            # 🟢 لو عكس اتجاهه لفوق بـ 15 درجة قبل ما يوصل للعمق المطلوب
            if press_angle - self.min_angle_this_rep > 15:
                self.feedback = "DIP LOWER!"
                current_color = (0, 165, 255)
                voice_message = DIPS_LOWER
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)

        # 4) Warning: Partial lock-out while ascending
        elif self.stage == "down" and press_angle < 155:
            # 🟢 لو عكس اتجاهه لتحت بـ 15 درجة قبل ما يفرد دراعه للآخر
            if self.max_angle_this_rep - press_angle > 15:
                self.feedback = "LOCK ARMS OUT!"
                current_color = (0, 165, 255)
                voice_message = DIPS_LOCK
            else:
                self.feedback = "PUSHING..."
                current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, f"Ext: {int(shoulder_ext)}", tuple((shoulder + np.array([-30, -20])).astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)
        cv2.line(frame, tuple(hip.astype(int)), tuple(shoulder.astype(int)), (255, 0, 0), 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)