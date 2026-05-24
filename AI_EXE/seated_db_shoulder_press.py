import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    SEATED_DB_PRESS_SETUP,
    SEATED_DB_PRESS_LOWER,
    SEATED_DB_PRESS_LOCK,
    SEATED_DB_PRESS_DROP,
    GOOD_REP,
)

class SeatedDbShoulderPressTrainerAI:
    def __init__(self, language="ar"):
        self.counter            = 0
        self.stage              = "down"
        self.feedback           = "Setup"
        self.coach              = AICoach(language=language)
        
        self.angle_history      = deque(maxlen=1)
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _get_smoothed_angle(self, angle):
        self.angle_history.append(angle)
        return float(np.mean(self.angle_history))

    def process(self, frame, keypoints, confs):
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4:
            s_idx, e_idx, w_idx = 6, 8, 10
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4:
            s_idx, e_idx, w_idx = 5, 7, 9
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(SEATED_DB_PRESS_SETUP, urgent=True)
            return frame

        self.coach.reset_error(SEATED_DB_PRESS_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]

        raw_angle = calculate_angle(shoulder, elbow, wrist)
        current_angle = self._get_smoothed_angle(raw_angle)

        current_color = (0, 255, 0)
        voice_message = None

        # ── TRACKING EXTREMES ──
        if self.stage == "down":
            self.max_angle_this_rep = max(self.max_angle_this_rep, current_angle)
        else:
            self.min_angle_this_rep = min(self.min_angle_this_rep, current_angle)

        # ── 1) Top (Lockout) ──
        if current_angle > 160:
            if self.stage == "down":
                self.stage = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)
                
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                
                self.coach.reset_error(SEATED_DB_PRESS_LOCK)
                self.coach.reset_error(SEATED_DB_PRESS_LOWER)
                self.coach.reset_error(SEATED_DB_PRESS_DROP)
                
                self._reset_rep_tracking()
                self.max_angle_this_rep = current_angle # Seed for descending

        # ── 2) Bottom (Starting position) ──
        elif current_angle < 90:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "PRESS UP!"
                current_color = (255, 255, 255)
                
                self.coach.reset_error(SEATED_DB_PRESS_LOWER)
                self.coach.reset_error(SEATED_DB_PRESS_DROP)
                
                self._reset_rep_tracking()
                self.min_angle_this_rep = current_angle # Seed for ascending

        # ── 3) Hysteresis: Ascending (stage=="down") ──
        elif self.stage == "down" and 90 <= current_angle <= 160:
            if self.max_angle_this_rep - current_angle > 15:
                self.feedback = "PUSH ALL THE WAY UP!"
                current_color = (0, 165, 255)
                voice_message = SEATED_DB_PRESS_LOCK
            else:
                self.feedback = "PRESSING..."
                current_color = (255, 255, 255)

        # ── 4) Hysteresis: Descending (stage=="up") ──
        elif self.stage == "up" and 90 <= current_angle <= 160:
            if current_angle - self.min_angle_this_rep > 15:
                self.feedback = "LOWER FULLY!"
                current_color = (0, 165, 255)
                voice_message = SEATED_DB_PRESS_LOWER
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, str(int(current_angle)), tuple(elbow.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)