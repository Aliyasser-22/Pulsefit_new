import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    LANDMINE_OBLIQUE_TWIST_SETUP,
    LANDMINE_OBLIQUE_TWIST_TWIST,
    LANDMINE_OBLIQUE_TWIST_SQUEEZE,
    LANDMINE_OBLIQUE_TWIST_CONTROL,
    GOOD_REP,
)

class LandmineObliqueTwistTrainerAI:
    def __init__(self, language="ar"):
        self.counter            = 0
        self.stage              = "center"
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
        if confs[5] > 0.4 and confs[6] > 0.4 and confs[11] > 0.4 and confs[12] > 0.4:
            l_s_idx, r_s_idx, l_h_idx, r_h_idx = 5, 6, 11, 12
        else:
            self.feedback = "SHOW FRONT VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(LANDMINE_OBLIQUE_TWIST_SETUP, urgent=True)
            return frame

        self.coach.reset_error(LANDMINE_OBLIQUE_TWIST_SETUP)

        left_shoulder = keypoints[l_s_idx]
        right_shoulder = keypoints[r_s_idx]
        mid_hip = (keypoints[l_h_idx] + keypoints[r_h_idx]) / 2

        raw_angle = calculate_angle(left_shoulder, mid_hip, right_shoulder)
        twist_angle = self._get_smoothed_angle(raw_angle)
        
        current_color = (0, 255, 0)
        voice_message = None

        if self.stage == "left" and twist_angle > 100:
            self.stage = "right"
        elif self.stage == "right" and twist_angle < 80:
            self.stage = "left"
            self.counter += 1
            self.feedback = "GOOD REP!"
            current_color = (0, 255, 0)
            self.coach.on_good_rep()
            self.coach.speak_if_ready(GOOD_REP)
        elif twist_angle < 80:
            self.stage = "left"
            self.feedback = "TWIST LEFT!"
            current_color = (0, 165, 255)
            voice_message = LANDMINE_OBLIQUE_TWIST_TWIST
        elif twist_angle > 100:
            self.stage = "right"
            self.feedback = "TWIST RIGHT!"
            current_color = (0, 165, 255)
            voice_message = LANDMINE_OBLIQUE_TWIST_CONTROL
        else:
            self.feedback = "TWISTING..."
            current_color = (0, 255, 0)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, str(int(twist_angle)), tuple(mid_hip.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(left_shoulder.astype(int)), tuple(mid_hip.astype(int)), current_color, 2)
        cv2.line(frame, tuple(right_shoulder.astype(int)), tuple(mid_hip.astype(int)), current_color, 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)