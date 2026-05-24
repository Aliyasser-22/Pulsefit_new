import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    SEATED_CALF_RAISE_SETUP,
    SEATED_CALF_RAISE_RAISE,
    SEATED_CALF_RAISE_SQUEEZE,
    SEATED_CALF_RAISE_LOWER,
    GOOD_REP,
)


class SeatedCalfRaiseTrainerAI:
    """
    Ankle angle: calculate_angle(knee, ankle, foot_index)
    - Plantar flexion (heel up):  angle INCREASES (> 130)
    - Dorsiflexion   (heel down): angle DECREASES (< 90)
    """

    def __init__(self, language="ar"):
        self.counter  = 0
        self.stage    = "down"
        self.feedback = "Setup"
        self.coach = AICoach(language=language)

        self.angle_history      = deque(maxlen=1)
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _smooth(self, angle):
        self.angle_history.append(angle)
        return float(np.mean(self.angle_history))

    def process(self, frame, keypoints, confs):
        # Left side: knee=13, ankle=15, foot_index=31
        if confs[13] > 0.4 and confs[15] > 0.4 and confs[31] > 0.4:
            k_idx, a_idx, f_idx = 13, 15, 31
        # Right side: knee=14, ankle=16, foot_index=32
        elif confs[14] > 0.4 and confs[16] > 0.4 and confs[32] > 0.4:
            k_idx, a_idx, f_idx = 14, 16, 32
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(SEATED_CALF_RAISE_SETUP, urgent=True)
            return frame

        self.coach.reset_error(SEATED_CALF_RAISE_SETUP)

        knee       = keypoints[k_idx]
        ankle      = keypoints[a_idx]
        foot_index = keypoints[f_idx]

        ankle_angle = self._smooth(calculate_angle(knee, ankle, foot_index))
        current_color = (0, 255, 0)

        # Track extremes
        if self.stage == "up":
            self.min_angle_this_rep = min(self.min_angle_this_rep, ankle_angle)
        else:
            self.max_angle_this_rep = max(self.max_angle_this_rep, ankle_angle)

        # 1) Top (heel fully raised)
        if ankle_angle > 130:
            if self.stage == "down":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(SEATED_CALF_RAISE_RAISE)
                self._reset_rep_tracking()
                self.max_angle_this_rep = ankle_angle
            else:
                self.feedback = "SQUEEZE CALVES!"
                current_color = (0, 255, 0)

        # 2) Bottom (heel fully lowered / full stretch)
        elif ankle_angle < 90:
            if self.stage != "down":
                self.stage    = "down"
                self.feedback = "RAISE YOUR HEELS!"
                current_color = (255, 255, 255)
                self.coach.reset_error(SEATED_CALF_RAISE_LOWER)
                self._reset_rep_tracking()
                self.min_angle_this_rep = ankle_angle

        # 3) Hysteresis: descending (stage=="up")
        elif self.stage == "up" and 90 <= ankle_angle <= 130:
            if ankle_angle - self.min_angle_this_rep > 15:
                self.feedback = "LOWER FULLY FOR STRETCH!"
                current_color = (0, 165, 255)
                self.coach.on_error(SEATED_CALF_RAISE_LOWER)
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)
                self.coach.reset_error(SEATED_CALF_RAISE_LOWER)

        # 4) Hysteresis: ascending (stage=="down")
        elif self.stage == "down" and 90 <= ankle_angle <= 130:
            if self.max_angle_this_rep - ankle_angle > 15:
                self.feedback = "RAISE HEELS HIGHER!"
                current_color = (0, 165, 255)
                self.coach.on_error(SEATED_CALF_RAISE_RAISE)
            else:
                self.feedback = "RAISING..."
                current_color = (255, 255, 255)
                self.coach.reset_error(SEATED_CALF_RAISE_RAISE)

        cv2.putText(frame, f"Ankle:{int(ankle_angle)}", tuple(ankle.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.line(frame, tuple(knee.astype(int)),       tuple(ankle.astype(int)),      current_color, 2)
        cv2.line(frame, tuple(ankle.astype(int)),      tuple(foot_index.astype(int)), current_color, 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)