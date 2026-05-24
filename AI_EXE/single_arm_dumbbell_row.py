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
    GOOD_REP
)

class StraightArmPulldownTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "up"  # "up" = الدراع مفرود لفوق (Stretch)، "down" = مسحوب لتحت عند الفخذ
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
        # ── Visibility check ────────────────────────────────────────
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW SIDE VIEW & HIPS"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(STRAIGHT_ARM_SETUP, urgent=True)
            return frame

        self.coach.reset_error(STRAIGHT_ARM_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        # ── Tracking Shoulder Angle (The main movement) ─────────────
        raw_shoulder_angle = calculate_angle(hip, shoulder, elbow)
        shoulder_angle = self._get_smoothed_angle(raw_shoulder_angle)

        # ── Checking Elbow Angle (Form Check) ───────────────────────
        elbow_angle = calculate_angle(shoulder, elbow, wrist)

        # ── Track extremes for direction detection ────────────────────
        if self.stage == "up":
            # بيسحب لتحت (زاوية الكتف بتقل) -> نسجل أقل زاوية
            self.min_angle_this_rep = min(self.min_angle_this_rep, shoulder_angle)
        elif self.stage == "down":
            # بيرجع لفوق (زاوية الكتف بتزيد) -> نسجل أكبر زاوية
            self.max_angle_this_rep = max(self.max_angle_this_rep, shoulder_angle)

        current_color = (0, 255, 0)
        voice_message = None

        # ── FORM CHECK: KEEP ARMS STRAIGHT ───────────────────────────
        # لو كوعه اتنى بزيادة (الزاوية قلت عن 140)، الكوتش هيزعق
        if elbow_angle < 140:
            self.feedback = "KEEP ARMS STRAIGHT!"
            current_color = (0, 0, 255)
            self.coach.on_error(STRAIGHT_ARM_BENT)
        else:
            self.coach.reset_error(STRAIGHT_ARM_BENT)

            # 1) Pulled down (Arms at thighs)
            if shoulder_angle < 40:
                if self.stage != "down":
                    self.stage    = "down"
                    self.counter += 1
                    self.feedback = "GOOD SQUEEZE!"
                    current_color = (0, 255, 0)
                    
                    phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                    self.coach.speak_motivation(phase)
                    self.coach.on_good_rep()
                    self.coach.speak_if_ready(GOOD_REP)
                    self.coach.reset_error(STRAIGHT_ARM_PULL)
                    self.coach.reset_error(STRAIGHT_ARM_STRETCH)
                    
                    self._reset_rep_tracking()

            # 2) Full stretch (Arms up)
            elif shoulder_angle > 140:
                if self.stage != "up":
                    self.stage = "up"
                    self.feedback = "FULL STRETCH!"
                    current_color = (0, 255, 0)
                    self.coach.reset_error(STRAIGHT_ARM_STRETCH)
                    self._reset_rep_tracking()
                else:
                    self.feedback = "FULL STRETCH!"
                    current_color = (0, 255, 0)

            # 3) Warning: Not pulling all the way down
            elif self.stage == "up" and 40 <= shoulder_angle <= 140:
                # لو عكس اتجاهه لفوق 15 درجة قبل ما يوصل للفخذ
                if shoulder_angle - self.min_angle_this_rep > 15:
                    self.feedback = "PULL TO THIGHS!"
                    current_color = (0, 165, 255)
                    voice_message = STRAIGHT_ARM_PULL
                else:
                    self.feedback = "PULLING..."
                    current_color = (255, 255, 255)

            # 4) Warning: Partial stretch while returning
            elif self.stage == "down" and 40 <= shoulder_angle <= 140:
                # لو سحب تاني لتحت 15 درجة قبل ما يرفع إيده للآخر
                if self.max_angle_this_rep - shoulder_angle > 15:
                    self.feedback = "STRETCH FULLY UP!"
                    current_color = (0, 165, 255)
                    voice_message = STRAIGHT_ARM_STRETCH
                else:
                    self.feedback = "STRETCHING..."
                    current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        # ── Draw ─────────────────────────────────────────────────────
        cv2.putText(frame, f"Sh:{int(shoulder_angle)}", tuple(shoulder.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        # تلوين الساعد بالأحمر لو الكوع اتنى
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), (0, 0, 255) if elbow_angle < 140 else current_color, 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), (255, 0, 0), 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)