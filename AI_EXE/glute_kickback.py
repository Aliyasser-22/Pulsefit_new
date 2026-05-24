import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    GLUTE_KICKBACK_SETUP,
    GLUTE_KICKBACK_KICK,
    GLUTE_KICKBACK_SQUEEZE,
    GLUTE_KICKBACK_LOWER,
    GOOD_REP,
)


class GluteKickbackTrainerAI:
    """
    Glute kickback: tracked via HIP ANGLE (shoulder-hip-knee).
    - Leg kicked back/up: hip angle INCREASES (> 160).
    - Leg forward/down:   hip angle DECREASES (< 110).
    """

    def __init__(self, language="ar"):
        self.counter  = 0
        self.stage    = "down"        # "down" = leg forward, "up" = leg kicked back
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
        if confs[5] > 0.4 and confs[11] > 0.4 and confs[13] > 0.4 and confs[15] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 5, 11, 13, 15
        elif confs[6] > 0.4 and confs[12] > 0.4 and confs[14] > 0.4 and confs[16] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 6, 12, 14, 16
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(GLUTE_KICKBACK_SETUP, urgent=True)
            return frame

        self.coach.reset_error(GLUTE_KICKBACK_SETUP)

        shoulder = keypoints[s_idx]
        hip      = keypoints[h_idx]
        knee     = keypoints[k_idx]
        ankle    = keypoints[a_idx]

        hip_angle = self._smooth(calculate_angle(shoulder, hip, knee))
        current_color = (0, 255, 0)

        # Track extremes
        if self.stage == "up":
            # Descending (returning leg forward): angle DECREASES → track min
            self.min_angle_this_rep = min(self.min_angle_this_rep, hip_angle)
        else:
            # Ascending (kicking back): angle INCREASES → track max
            self.max_angle_this_rep = max(self.max_angle_this_rep, hip_angle)

        # 1) Top (leg fully kicked back — hip angle high)
        if hip_angle > 160:
            if self.stage == "down":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(GLUTE_KICKBACK_KICK)
                self._reset_rep_tracking()
                self.max_angle_this_rep = hip_angle
            else:
                self.feedback = "SQUEEZE GLUTE!"
                current_color = (0, 255, 0)

        # 2) Bottom (leg forward / hip angle low)
        elif hip_angle < 110:
            if self.stage != "down":
                self.stage    = "down"
                self.feedback = "KICK BACK!"
                current_color = (255, 255, 255)
                self.coach.reset_error(GLUTE_KICKBACK_SQUEEZE)
                self._reset_rep_tracking()
                self.min_angle_this_rep = hip_angle

        # 3) Hysteresis: descending (returning, stage=="up")
        elif self.stage == "up" and 110 <= hip_angle <= 160:
            if hip_angle - self.min_angle_this_rep > 15:
                self.feedback = "LOWER FULLY FIRST!"
                current_color = (0, 165, 255)
                self.coach.on_error(GLUTE_KICKBACK_LOWER)
            else:
                self.feedback = "RETURNING..."
                current_color = (255, 255, 255)
                self.coach.reset_error(GLUTE_KICKBACK_LOWER)

        # 4) Hysteresis: ascending (kicking, stage=="down")
        elif self.stage == "down" and 110 <= hip_angle <= 160:
            if self.max_angle_this_rep - hip_angle > 15:
                self.feedback = "KICK HIGHER!"
                current_color = (0, 165, 255)
                self.coach.on_error(GLUTE_KICKBACK_KICK)
            else:
                self.feedback = "KICKING..."
                current_color = (255, 255, 255)
                self.coach.reset_error(GLUTE_KICKBACK_KICK)

        cv2.putText(frame, f"Hip:{int(hip_angle)}", tuple(hip.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), (255, 100, 0), 2)
        cv2.line(frame, tuple(hip.astype(int)),      tuple(knee.astype(int)), current_color, 2)
        cv2.line(frame, tuple(knee.astype(int)),     tuple(ankle.astype(int)), current_color, 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)