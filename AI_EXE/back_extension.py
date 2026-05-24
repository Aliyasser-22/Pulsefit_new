import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    BACK_EXTENSION_SETUP,
    BACK_EXTENSION_UP,
    BACK_EXTENSION_SQUEEZE,
    BACK_EXTENSION_LOWER,
    GOOD_REP,
)

class BackExtensionTrainerAI:
    def __init__(self, language="ar"):
        self.counter            = 0
        self.stage              = "down" # down = bent forward, up = extended back
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
        # ── VISIBILITY CHECK (Shoulder, Hip, Knee) ──
        if confs[5] > 0.4 and confs[11] > 0.4 and confs[13] > 0.4:
            s_idx, h_idx, k_idx = 5, 11, 13
        elif confs[6] > 0.4 and confs[12] > 0.4 and confs[14] > 0.4:
            s_idx, h_idx, k_idx = 6, 12, 14
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(BACK_EXTENSION_SETUP, urgent=True)
            return frame

        self.coach.reset_error(BACK_EXTENSION_SETUP)
        shoulder, hip, knee = keypoints[s_idx], keypoints[h_idx], keypoints[k_idx]
        current_angle = self._get_smoothed_angle(calculate_angle(shoulder, hip, knee))
        current_color = (0, 255, 0)
        voice_message = None

        # ── TRACKING EXTREMES (Normal Logic) ──
        if self.stage == "down": # Extending up -> Angle INCREASES -> Track max
            self.max_angle_this_rep = max(self.max_angle_this_rep, current_angle)
        else: # Lowering down -> Angle DECREASES -> Track min
            self.min_angle_this_rep = min(self.min_angle_this_rep, current_angle)

        # ── 1) Top (Fully Extended) ──
        if current_angle > 165:
            if self.stage == "down":
                self.stage = "up"
                self.counter += 1
                self.feedback = "GOOD SQUEEZE!"
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(BACK_EXTENSION_UP)
                self._reset_rep_tracking()
                self.min_angle_this_rep = current_angle
        # ── 2) Bottom (Flexed Forward) ──
        elif current_angle < 110:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "LIFT YOUR TORSO!"
                self.coach.reset_error(BACK_EXTENSION_LOWER)
                self._reset_rep_tracking()
                self.max_angle_this_rep = current_angle

        # ── 3) Hysteresis Warnings ──
        elif self.stage == "down" and 110 <= current_angle <= 165:
            if self.max_angle_this_rep - current_angle > 15:
                voice_message = BACK_EXTENSION_UP
            else: self.feedback = "EXTENDING..."
        elif self.stage == "up" and 110 <= current_angle <= 165:
            if current_angle - self.min_angle_this_rep > 15:
                voice_message = BACK_EXTENSION_LOWER
            else: self.feedback = "LOWERING..."

        if voice_message: self.coach.on_error(voice_message)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), current_color, 2)
        cv2.line(frame, tuple(hip.astype(int)), tuple(knee.astype(int)), current_color, 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)