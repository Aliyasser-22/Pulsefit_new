import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    FLOOR_PRESS_SETUP,
    FLOOR_PRESS_LOWER,
    FLOOR_PRESS_LOCK,
    FLOOR_PRESS_DROP,
    GOOD_REP # 🟢 مهمة عشان التشجيع
)

class DumbbellFloorPressTrainerAI:
    def __init__(self, language="ar"):
        self.counter        = 0
        self.stage          = "up"  # "up" = مفرود لفوق, "down" = الكوع لامس الأرض
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
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(FLOOR_PRESS_SETUP, urgent=True)
            return frame
        
        self.coach.reset_error(FLOOR_PRESS_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]

        # ── Calculate and smooth angle ───────────────────────────────
        raw_angle = calculate_angle(shoulder, elbow, wrist)
        angle = self._get_smoothed_angle(raw_angle)

        # ── Track extremes for direction detection ────────────────────
        if self.stage == "up":
            # وهو نازل بالدمبل (الزاوية بتقل) نراقب المينيمم
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)
        elif self.stage == "down":
            # وهو بيضغط لفوق (الزاوية بتزيد) نراقب الماكسيمم
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
                
                # 🟢 AI Coach Completion Logic
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(FLOOR_PRESS_LOCK)
                self.coach.reset_error(FLOOR_PRESS_LOWER)
                
                self._reset_rep_tracking()

        # 2) Bottom (elbow touches floor)
        # الـ Floor press ميزته إن الأرض بتوقفك، فالزاوية غالباً بتكون حول 95-90
        elif angle < 95:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "PRESS UP!"
                current_color = (255, 255, 255)
                self.coach.reset_error(FLOOR_PRESS_LOWER)
                self._reset_rep_tracking()
            else:
                self.feedback = "PRESS UP!"
                current_color = (255, 255, 255)

        # 3) Warning: Not lowering enough (Short rep while descending)
        elif self.stage == "up" and angle > 95:
            # 🟢 لو هو نازل وقرر يعكس اتجاهه ويطلع بـ 15 درجة قبل ما كوعه يلمس الأرض
            if angle - self.min_angle_this_rep > 15:
                self.feedback = "LOWER UNTIL ELBOW TOUCHES!"
                current_color = (0, 165, 255)
                voice_message = FLOOR_PRESS_LOWER
            else:
                self.feedback = "LOWERING..."
                current_color = (255, 255, 255)

        # 4) Warning: Partial lock-out while ascending
        elif self.stage == "down" and angle < 155:
            # 🟢 لو هو طالع وقرر يريح وينزل تاني بـ 15 درجة قبل ما يفرد دراعه
            if self.max_angle_this_rep - angle > 15:
                self.feedback = "LOCK IT OUT!"
                current_color = (0, 165, 255)
                voice_message = FLOOR_PRESS_LOCK
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