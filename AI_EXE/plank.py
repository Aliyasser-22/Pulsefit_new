import cv2
import time
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    PLANK_SETUP,
    PLANK_HOLD,
    PLANK_HIPS_SAGGING,
    PLANK_HIPS_HIGH,
)

class PlankTrainerAI:
    def __init__(self, language="ar"):
        self.feedback   = "Setup"
        self.coach = AICoach(language=language)
        self.start_time = None
        self.hold_duration = 0.0
        self.angle_history = deque(maxlen=1)

    def _get_smoothed_angle(self, angle):
        self.angle_history.append(angle)
        return float(np.mean(self.angle_history))

    def process(self, frame, keypoints, confs):
        # ── VISIBILITY CHECK ──
        if confs[5] > 0.4 and confs[11] > 0.4 and confs[13] > 0.4:
            s_idx, h_idx, k_idx = 5, 11, 13
        elif confs[6] > 0.4 and confs[12] > 0.4 and confs[14] > 0.4:
            s_idx, h_idx, k_idx = 6, 12, 14
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(PLANK_SETUP, urgent=True)
            self.start_time = None # Reset timer if person disappears
            return frame

        self.coach.reset_error(PLANK_SETUP)
        shoulder, hip, knee = keypoints[s_idx], keypoints[h_idx], keypoints[k_idx]
        body_angle = self._get_smoothed_angle(calculate_angle(shoulder, hip, knee))
        
        current_color = (0, 255, 0)

        # ── TIMER LOGIC ──
        if 160 <= body_angle <= 180:
            if self.start_time is None:
                self.start_time = time.time()
            self.hold_duration = time.time() - self.start_time
            self.feedback = "HOLDING..."
            current_color = (0, 255, 0)
            
            # Reset postural errors when form is correct
            self.coach.reset_error(PLANK_HIPS_HIGH)
            self.coach.reset_error(PLANK_HIPS_SAGGING)
        else:
            self.start_time = None # Stop/Reset timer if form breaks
            self.feedback = "FIX YOUR HIPS!"
            current_color = (0, 0, 255)
            
            if body_angle < 160:
                self.coach.on_error(PLANK_HIPS_HIGH)
            elif body_angle > 180:
                self.coach.on_error(PLANK_HIPS_SAGGING)

        # ── DRAW ──
        cv2.putText(frame, str(int(body_angle)), tuple(hip.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), current_color, 2)
        cv2.line(frame, tuple(hip.astype(int)), tuple(knee.astype(int)), current_color, 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"HOLD TIME: {int(self.hold_duration)}s", (200, 45), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)