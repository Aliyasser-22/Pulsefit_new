import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    HIGH_CABLE_CURL_SETUP,
    HIGH_CABLE_CURL_CURL,
    HIGH_CABLE_CURL_STRETCH,
    HIGH_CABLE_DROP,
    GOOD_REP
)

class CableCurlHighTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "down"  # "down" = دراع مفرود, "up" = متني جنب الودن
        self.feedback   = "Setup"
        self.coach      = AICoach(language=language)

        self._angle_buffer      = deque(maxlen=1)
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _get_smoothed_angle(self, angle: float) -> float:
        self._angle_buffer.append(angle)
        return float(np.mean(self._angle_buffer))

    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def process(self, frame, keypoints, confs):
        # ── Visibility check ─────────────────────────────────────────
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW FRONT OR SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(HIGH_CABLE_CURL_SETUP, urgent=True)
            return frame

        self.coach.reset_error(HIGH_CABLE_CURL_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        # ── Calculate and smooth angle ────────────────────────────────
        raw_angle = calculate_angle(shoulder, elbow, wrist)
        angle     = self._get_smoothed_angle(raw_angle)

        # ── Track extremes for direction detection ────────────────────
        if self.stage == "down":
            # بيسحب الكابل لراسه (الزاوية بتقل)
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)
        elif self.stage == "up":
            # بيفرد دراعه (الزاوية بتزيد)
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # ── Upper arm form check (High Cable Logic) ───────────────────
        upper_arm_angle = calculate_angle(hip, shoulder, elbow)
        # كوعك لازم يكون مرفوع، لو نزل تحت 65 درجة يبقى بتغش
        if upper_arm_angle < 65:
            self.feedback = "KEEP ELBOWS HIGH!"
            current_color = (0, 0, 255)
            self.coach.on_error(HIGH_CABLE_DROP)
        else:
            self.coach.reset_error(HIGH_CABLE_DROP)

            # 1) Top — arm fully curled to head
            if angle < 50:
                if self.stage != "up":
                    self.stage    = "up"
                    self.counter += 1
                    self.feedback = "GOOD SQUEEZE!"
                    current_color = (0, 255, 0)

                    phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                    self.coach.speak_motivation(phase)
                    self.coach.on_good_rep()
                    self.coach.speak_if_ready(GOOD_REP)
                    self.coach.reset_error(HIGH_CABLE_CURL_CURL)
                    self.coach.reset_error(HIGH_CABLE_CURL_STRETCH)
                    self.coach.reset_error(HIGH_CABLE_DROP)
                    self._reset_rep_tracking()

            # 2) Bottom — arm fully extended
            elif angle > 150:
                if self.stage != "down":
                    self.stage = "down"
                    self.coach.reset_error(HIGH_CABLE_CURL_STRETCH)
                    self._reset_rep_tracking()
                self.feedback = "GOOD STRETCH!"
                current_color = (0, 255, 0)

            # 3) Not curling high enough (short rep while pulling)
            elif self.stage == "down" and 50 < angle < 120:
                # لو رجع فرد دراعه قبل ما يكمل السحبة
                if angle - self.min_angle_this_rep > 15:
                    self.feedback = "CURL TO HEAD!"
                    current_color = (0, 165, 255)
                    voice_message = HIGH_CABLE_CURL_CURL
                else:
                    self.feedback = "CURLING..."
                    current_color = (255, 255, 255)

            # 4) Partial extension while descending
            elif self.stage == "up" and 90 < angle < 150:
                # لو سحب تاني قبل ما يفرد دراعه للاخر
                if self.max_angle_this_rep - angle > 15:
                    self.feedback = "STRETCH FULLY!"
                    current_color = (0, 165, 255)
                    voice_message = HIGH_CABLE_CURL_STRETCH
                else:
                    self.feedback = "LOWERING..."
                    current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        # ── Draw skeleton & angle ─────────────────────────────────────
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)),   tuple(wrist.astype(int)),  current_color, 2)
        cv2.putText(frame, f"{int(angle)} DEG", tuple(elbow.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)