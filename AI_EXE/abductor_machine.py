import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    ABDUCTOR_MACHINE_SETUP,
    ABDUCTOR_MACHINE_OPEN,
    ABDUCTOR_MACHINE_SQUEEZE,
    ABDUCTOR_MACHINE_CLOSE,
    GOOD_REP,
)

class AbductorMachineTrainerAI:
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
        # ── VISIBILITY CHECK (Front View) ──
        if confs[23] > 0.4 and confs[24] > 0.4 and confs[25] > 0.4 and confs[26] > 0.4:
            l_hip_idx, r_hip_idx, l_knee_idx, r_knee_idx = 23, 24, 25, 26
        else:
            self.feedback = "SHOW FRONT VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(ABDUCTOR_MACHINE_SETUP, urgent=True)
            return frame

        self.coach.reset_error(ABDUCTOR_MACHINE_SETUP)

        left_knee  = keypoints[l_knee_idx]
        right_knee = keypoints[r_knee_idx]
        mid_hip    = (keypoints[l_hip_idx] + keypoints[r_hip_idx]) / 2

        raw_angle = calculate_angle(left_knee, mid_hip, right_knee)
        current_angle = self._get_smoothed_angle(raw_angle)
        
        current_color = (0, 255, 0)
        voice_message = None

        # ── TRACKING EXTREMES ──
        if self.stage == "down":  # opening, angle increasing
            self.max_angle_this_rep = max(self.max_angle_this_rep, current_angle)
        else:  # closing, angle decreasing
            self.min_angle_this_rep = min(self.min_angle_this_rep, current_angle)

        # ── 1) Top (Spread) ──
        if current_angle > 120:
            if self.stage == "down":
                self.stage = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)
                
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                
                self.coach.reset_error(ABDUCTOR_MACHINE_OPEN)
                self.coach.reset_error(ABDUCTOR_MACHINE_CLOSE)
                
                self._reset_rep_tracking()
                self.max_angle_this_rep = current_angle # Seed for closing

        # ── 2) Bottom (Closed) ──
        elif current_angle < 60:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "CLOSE LEGS!"
                current_color = (255, 255, 255)
                
                self.coach.reset_error(ABDUCTOR_MACHINE_OPEN)
                self.coach.reset_error(ABDUCTOR_MACHINE_CLOSE)
                
                self._reset_rep_tracking()
                self.min_angle_this_rep = current_angle # Seed for opening

        # ── 3) Hysteresis: Ascending (Opening, stage=="down") ──
        elif self.stage == "down" and 60 <= current_angle <= 120:
            if self.max_angle_this_rep - current_angle > 15:
                self.feedback = "PUSH LEGS OUT!"
                current_color = (0, 165, 255)
                voice_message = ABDUCTOR_MACHINE_OPEN
            else:
                self.feedback = "OPENING..."
                current_color = (255, 255, 255)

        # ── 4) Hysteresis: Descending (Closing, stage=="up") ──
        elif self.stage == "up" and 60 <= current_angle <= 120:
            if current_angle - self.min_angle_this_rep > 15:
                self.feedback = "CLOSE WITH CONTROL!"
                current_color = (0, 165, 255)
                voice_message = ABDUCTOR_MACHINE_CLOSE
            else:
                self.feedback = "CLOSING..."
                current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, str(int(current_angle)), tuple(mid_hip.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(left_knee.astype(int)), tuple(mid_hip.astype(int)), current_color, 2)
        cv2.line(frame, tuple(right_knee.astype(int)), tuple(mid_hip.astype(int)), current_color, 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)