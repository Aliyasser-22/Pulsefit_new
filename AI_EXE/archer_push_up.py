import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    ARCHER_PUSHUP_SETUP,
    ARCHER_PUSHUP_LOWER,
    ARCHER_PUSHUP_LOCK,
    ARCHER_PUSHUP_STRAIGHT,
    GOOD_REP
)

class ArcherPushUpTrainerAI:
    def __init__(self, language="ar"):
        self.counter        = 0
        self.stage          = "up"  # "up" = دراعه مفرود, "down" = نازل عالأرض
        self.feedback       = "Setup"
        self.coach          = AICoach(language=language)

        # ── Full Result Smoothing ────────────────────────────────────
        self._angle_buffer = deque(maxlen=1)

        # ── Robust Direction Tracking ────────────────────────────────
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
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4:
            s_idx, e_idx, w_idx = 6, 8, 10
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4:
            s_idx, e_idx, w_idx = 5, 7, 9
        else:
            self.feedback = "SHOW SIDE VIEW (BENDING ARM)"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(ARCHER_PUSHUP_SETUP, urgent=True)
            return frame
        
        self.coach.reset_error(ARCHER_PUSHUP_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]

        # ── Calculate and smooth angle ───────────────────────────────
        raw_angle = calculate_angle(shoulder, elbow, wrist)
        angle = self._get_smoothed_angle(raw_angle)

        # ── Track extremes for direction detection ────────────────────
        if self.stage == "up":
            # وهو نازل (المفروض الزاوية بتقل)، نراقب أقل زاوية وصلها
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)
        elif self.stage == "down":
            # وهو طالع (المفروض الزاوية بتزيد)، نراقب أعلى زاوية وصلها
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # 1) Peak / lock-out (arms extended)
        if angle > 155:
            if self.stage != "up":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)
                
                # AI Coach Completion Logic
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(ARCHER_PUSHUP_LOCK)
                self.coach.reset_error(ARCHER_PUSHUP_LOWER)
                
                self._reset_rep_tracking()

        # 2) Bottom (deep bend)
        elif angle < 95:
            if self.stage != "down":
                self.stage    = "down"
                self.feedback = "PUSH BACK UP!"
                current_color = (255, 255, 255)
                self.coach.reset_error(ARCHER_PUSHUP_LOWER)
                self._reset_rep_tracking()
            else:
                self.feedback = "PUSH BACK UP!"
                current_color = (255, 255, 255)

        # 3) Warning: Not going deep enough (Short rep while descending)
        elif self.stage == "up" and angle > 85:
            # لو الزاوية زادت فجأة بـ 15 درجة (يعني بدأ يرفع نفسه) قبل ما يوصل للعمق المطلوب (85)
            if angle - self.min_angle_this_rep > 15:
                self.feedback = "GO LOWER!"
                current_color = (0, 165, 255)
                voice_message = ARCHER_PUSHUP_LOWER
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)

        # 4) Warning: Partial extension (Didn't lock out while ascending)
        elif self.stage == "down" and angle < 155:
            # لو الزاوية قلت فجأة بـ 15 درجة (يعني بدأ ينزل تاني) قبل ما يوصل للـ Lockout (155)
            if self.max_angle_this_rep - angle > 15:
                self.feedback = "LOCK IT OUT!"
                current_color = (0, 165, 255)
                voice_message = ARCHER_PUSHUP_LOCK
            else:
                self.feedback = "PUSHING..."
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