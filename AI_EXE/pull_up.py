import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    PULLUP_SETUP,
    PULLUP_PULL,
    PULLUP_HANG,
    PULLUP_CHIN,
    GOOD_REP
)

class PullUpTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "down"  # "down" = full hang, "up" = chin over bar
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
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4:
            s_idx, e_idx, w_idx = 6, 8, 10
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4:
            s_idx, e_idx, w_idx = 5, 7, 9
        else:
            self.feedback = "SHOW SIDE OR FRONT VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(PULLUP_SETUP, urgent=True)
            return frame

        self.coach.reset_error(PULLUP_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]

        raw_angle = calculate_angle(shoulder, elbow, wrist)
        angle = self._get_smoothed_angle(raw_angle)
        
        if self.stage == "down":
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)
        elif self.stage == "up":
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # 1) Chin over bar (top)
        if angle < 70:
            if self.stage != "up":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD SQUEEZE!"
                current_color = (0, 255, 0)
                
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(PULLUP_PULL)
                self.coach.reset_error(PULLUP_HANG)
                self.coach.reset_error(PULLUP_CHIN)
                
                self._reset_rep_tracking()

        # 2) Full hang (start position)
        elif angle > 155:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "FULL HANG!"
                current_color = (0, 255, 0)
                self.coach.reset_error(PULLUP_HANG)
                self._reset_rep_tracking()
            else:
                self.feedback = "FULL HANG!"
                current_color = (0, 255, 0)

        # 3) Warning: Not pulling high enough
        elif self.stage == "down" and 70 <= angle <= 155:
            if angle - self.min_angle_this_rep > 15:
                self.feedback = "PULL CHIN OVER BAR!"
                current_color = (0, 165, 255)
                voice_message = PULLUP_PULL
            else:
                self.feedback = "PULLING..."
                current_color = (255, 255, 255)

        # 4) Warning: Partial hang while descending
        elif self.stage == "up" and 70 <= angle <= 155:
            if self.max_angle_this_rep - angle > 15:
                self.feedback = "LOWER TO FULL HANG!"
                current_color = (0, 165, 255)
                voice_message = PULLUP_HANG
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.putText(frame, f"{int(angle)} DEG", tuple(elbow.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)