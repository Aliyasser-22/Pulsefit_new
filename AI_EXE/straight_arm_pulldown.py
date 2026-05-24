import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    STRAIGHT_ARM_SETUP,
    STRAIGHT_ARM_PULL,
    STRAIGHT_ARM_STRETCH,
    STRAIGHT_ARM_BENT,
)

class StraightArmPulldownTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "up"
        self.prev_angle = 0
        self.feedback   = "Setup"
        self.coach = AICoach(language=language)
        self._pos_buffer = deque(maxlen=1)
        self._baseline   = None
        self._sent_errors = set()

    def _smooth(self, val: float) -> float:
        self._pos_buffer.append(val)
        return float(np.mean(self._pos_buffer))

    def _calibrate(self, val: float):
        if self._baseline is None and len(self._pos_buffer) >= 6:
            self._baseline = float(np.mean(self._pos_buffer))

    def _raise_error(self, msg, urgent=False):
        if msg not in self._sent_errors:
            self._sent_errors.add(msg)
            self.coach.on_error(msg, urgent=urgent)

    def _clear_error(self, msg):
        if msg in self._sent_errors:
            self._sent_errors.discard(msg)
            self.coach.reset_error(msg)

    def process(self, frame, keypoints, confs):
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW SIDE VIEW & HIPS"
            self._draw_feedback(frame, (0, 0, 255))
            self._raise_error(STRAIGHT_ARM_SETUP, urgent=True)
            return frame

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        smooth_val = self._smooth(shoulder[1])
        self._calibrate(smooth_val)
        if self._baseline is None:
            self._draw_feedback(frame, (200, 200, 200))
            return frame
        movement = self._baseline - smooth_val

        shoulder_angle = calculate_angle(hip, shoulder, elbow)
        elbow_angle    = calculate_angle(shoulder, elbow, wrist)

        angle_change = shoulder_angle - self.prev_angle
        current_color = (0, 255, 0)

        if elbow_angle < 130:
            self.feedback = "KEEP ARMS STRAIGHT!"
            current_color = (0, 165, 255)
            self._raise_error(STRAIGHT_ARM_BENT)
        else:
            if shoulder_angle < 30:
                if self.stage != "down":
                    self.feedback = "LET ARMS UP!"
                    current_color = (255, 255, 255)
                self.stage = "down"
                self._clear_error(STRAIGHT_ARM_PULL)
                self._clear_error(STRAIGHT_ARM_STRETCH)
                
            elif self.stage == "up" and 30 < shoulder_angle < 80 and angle_change > 2.0:
                self.feedback = "PULL TO THIGHS!"
                current_color = (0, 165, 255)
                self._raise_error(STRAIGHT_ARM_PULL)
                
            elif shoulder_angle > 130 and self.stage == "down":
                self.stage = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)
                self._clear_error(STRAIGHT_ARM_PULL)
                self._clear_error(STRAIGHT_ARM_STRETCH)
                self._clear_error(STRAIGHT_ARM_BENT)
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(STRAIGHT_ARM_STRETCH)
                    
            elif self.stage == "down" and 80 < shoulder_angle < 130 and angle_change < -2.0:
                self.feedback = "STRETCH UP!"
                current_color = (0, 165, 255)
                self._raise_error(STRAIGHT_ARM_STRETCH)

        self.prev_angle = shoulder_angle

        cv2.putText(frame, str(int(shoulder_angle)), tuple(shoulder.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), (255, 255, 255) if elbow_angle < 130 else current_color, 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), (255, 0, 0), 2)
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)