import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    CONV_DEADLIFT_SETUP,
    CONV_DEADLIFT_PULL,
    CONV_DEADLIFT_LOCK,
    CONV_DEADLIFT_DROP,
    GOOD_REP
)

class ConventionalDeadliftTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "down"  # "down" = bar on floor, "up" = locked out
        self.feedback   = "Setup"
        self.coach      = AICoach(language=language)
        
        self._angle_buffer = deque(maxlen=1)
        
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _get_smoothed_angle(self, angle: float) -> float:
        self._angle_buffer.append(angle)
        return float(np.mean(self._angle_buffer))

    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def process(self, frame, keypoints, confs):
        if confs[6] > 0.4 and confs[12] > 0.4 and confs[14] > 0.4 and confs[16] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 6, 12, 14, 16
        elif confs[5] > 0.4 and confs[11] > 0.4 and confs[13] > 0.4 and confs[15] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 5, 11, 13, 15
        else:
            self.feedback = "SHOW SIDE VIEW FULL BODY"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(CONV_DEADLIFT_SETUP, urgent=True)
            return frame

        self.coach.reset_error(CONV_DEADLIFT_SETUP)

        shoulder = keypoints[s_idx]
        hip      = keypoints[h_idx]
        knee     = keypoints[k_idx]
        ankle    = keypoints[a_idx]

        # Tracking Hip Angle for Deadlift
        raw_angle = calculate_angle(shoulder, hip, knee)
        angle = self._get_smoothed_angle(raw_angle)
        
        # When stage is 'down' (standing up), angle increases -> track max
        if self.stage == "down":
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)
        # When stage is 'up' (lowering bar), angle decreases -> track min
        elif self.stage == "up":
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # 1) Lockout (up) - Hip straight
        if angle > 165:
            if self.stage != "up":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD LOCKOUT!"
                current_color = (0, 255, 0)
                
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(CONV_DEADLIFT_PULL)
                self.coach.reset_error(CONV_DEADLIFT_LOCK)
                self.coach.reset_error(CONV_DEADLIFT_DROP)
                
                self._reset_rep_tracking()

        # 2) Bar on floor (down) - Hip bent
        elif angle < 100:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "BAR ON FLOOR!"
                current_color = (0, 255, 0)
                self.coach.reset_error(CONV_DEADLIFT_DROP)
                self._reset_rep_tracking()
            else:
                self.feedback = "BAR ON FLOOR!"
                current_color = (0, 255, 0)

        # 3) Warning: Not pulling all the way to lockout
        elif self.stage == "down" and 100 <= angle <= 165:
            # If the angle drops by 15 without hitting 165, they gave up the pull
            if self.max_angle_this_rep - angle > 15:
                self.feedback = "LOCK YOUR HIPS OUT!"
                current_color = (0, 165, 255)
                voice_message = CONV_DEADLIFT_LOCK
            else:
                self.feedback = "PULLING..."
                current_color = (255, 255, 255)

        # 4) Warning: Partial drop while returning down
        elif self.stage == "up" and 100 <= angle <= 165:
            # If the angle increases by 15 without hitting 100, they started pulling too early
            if angle - self.min_angle_this_rep > 15:
                self.feedback = "LOWER BAR TO FLOOR!"
                current_color = (0, 165, 255)
                voice_message = CONV_DEADLIFT_DROP
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, f"Hip:{int(angle)}", tuple(hip.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), current_color, 2)
        cv2.line(frame, tuple(hip.astype(int)), tuple(knee.astype(int)), current_color, 2)
        cv2.line(frame, tuple(knee.astype(int)), tuple(ankle.astype(int)), current_color, 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)