import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    BULGARIAN_SPLIT_SQUAT_SETUP,
    BULGARIAN_SPLIT_SQUAT_LOWER,
    BULGARIAN_SPLIT_SQUAT_UP,
    BULGARIAN_SPLIT_SQUAT_DEPTH,
    GOOD_REP
)

class BulgarianSplitSquatTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "up"
        self.feedback   = "Setup"
        self.coach = AICoach(language=language)
        
        self.angle_history = deque(maxlen=1)
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _get_smoothed_angle(self, angle):
        self.angle_history.append(angle)
        return float(np.mean(self.angle_history))

    def process(self, frame, keypoints, confs):
        # 🟢 ضفنا الكتف (s_idx) هنا عشان نعرف نحسب زاوية الضهر
        if confs[11] > 0.4 and confs[13] > 0.4 and confs[15] > 0.4 and confs[5] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 5, 11, 13, 15
        elif confs[10] > 0.4 and confs[12] > 0.4 and confs[14] > 0.4 and confs[6] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 6, 10, 12, 14
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(BULGARIAN_SPLIT_SQUAT_SETUP, urgent=True)
            return frame

        self.coach.reset_error(BULGARIAN_SPLIT_SQUAT_SETUP)

        shoulder = keypoints[s_idx]
        hip    = keypoints[h_idx]
        knee   = keypoints[k_idx]
        ankle  = keypoints[a_idx]

        raw_knee_angle = calculate_angle(hip, knee, ankle)
        knee_angle = self._get_smoothed_angle(raw_knee_angle)

        current_color = (0, 255, 0)
        voice_message = None

        # ── TRACKING EXTREMES ──
        if self.stage == "up":
            self.min_angle_this_rep = min(self.min_angle_this_rep, knee_angle)
        else:
            self.max_angle_this_rep = max(self.max_angle_this_rep, knee_angle)

        # ── FORM CHECK: BACK POSTURE ──
        # 🟢 صلحنا الزاوية هنا عشان تحسب ميل الضهر الفعلي
        hip_angle = calculate_angle(shoulder, hip, knee)
        if hip_angle < 45:
            self.feedback = "KEEP CHEST UP!"
            current_color = (0, 0, 255)

        # ── 1) Bottom (Deep Squat) ──
        if knee_angle < 95:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "PUSH UP!"
                current_color = (255, 255, 255)
                self.coach.reset_error(BULGARIAN_SPLIT_SQUAT_DEPTH)
                self._reset_rep_tracking()
                self.min_angle_this_rep = knee_angle  # Seed for ascending

        # ── 2) Top (Stand up) ──
        elif knee_angle > 160:
            if self.stage == "down":
                self.stage = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)

                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)

                self.coach.reset_error(BULGARIAN_SPLIT_SQUAT_UP)
                self.coach.reset_error(BULGARIAN_SPLIT_SQUAT_DEPTH)

                self._reset_rep_tracking()
                self.max_angle_this_rep = knee_angle  # Seed for descending

        # ── 3) Hysteresis: Short Rep while descending ──
        elif self.stage == "up" and 95 <= knee_angle <= 160:
            if knee_angle - self.min_angle_this_rep > 15:
                self.feedback = "FRONT THIGH PARALLEL!"
                current_color = (0, 165, 255)
                voice_message = BULGARIAN_SPLIT_SQUAT_DEPTH
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)

        # ── 4) Hysteresis: Short Rep while ascending ──
        elif self.stage == "down" and 95 <= knee_angle <= 160:
            if self.max_angle_this_rep - knee_angle > 15:
                self.feedback = "PUSH ALL THE WAY UP!"
                current_color = (0, 165, 255)
                voice_message = BULGARIAN_SPLIT_SQUAT_UP
            else:
                self.feedback = "PUSHING..."
                current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, str(int(knee_angle)), tuple(knee.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(hip.astype(int)), tuple(knee.astype(int)), current_color, 2)
        cv2.line(frame, tuple(knee.astype(int)), tuple(ankle.astype(int)), current_color, 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), (255, 0, 0), 2) # 🟢 رسمنا الضهر
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)