import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    SPIDER_CURL_SETUP,
    SPIDER_CURL_CURL,
    SPIDER_CURL_STRETCH,
    SPIDER_CURL_SQUEEZE,
    GOOD_REP # 🟢 عشان التشجيع
)

class SpiderCurlTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "down"  # "down" = دراع مفرود للأرض، "up" = دراع متني عند الراس
        self.feedback   = "Setup"
        self.coach      = AICoach(language=language)
        
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
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(SPIDER_CURL_SETUP, urgent=True)
            return frame

        self.coach.reset_error(SPIDER_CURL_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        # ── Calculate and smooth angle ───────────────────────────────
        raw_angle = calculate_angle(shoulder, elbow, wrist)
        angle = self._get_smoothed_angle(raw_angle)
        
        # ── Track extremes for direction detection ────────────────────
        if self.stage == "down":
            # طالع لفوق (الزاوية بتقل) -> نسجل أقل زاوية
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)
        elif self.stage == "up":
            # نازل لتحت (الزاوية بتزيد) -> نسجل أكبر زاوية
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # ── UPPER ARM FORM CHECK (Spider Logic) ──────────────────────
        upper_arm_angle = calculate_angle(hip, shoulder, elbow)
        # في السبايدر كيرل دراعك مائل للأمام، لو رجعته لورا (الزاوية صغرت عن 75) يبقى غلط
        if upper_arm_angle < 75:
            self.feedback = "KEEP ELBOWS POINTED TO FLOOR!"
            current_color = (0, 0, 255)
            self.coach.on_error(SPIDER_CURL_SETUP)
        else:
            self.coach.reset_error(SPIDER_CURL_SETUP)

            # 1) Top / squeeze (arm fully curled)
            if angle < 50:
                if self.stage != "up":
                    self.stage    = "up"
                    self.counter += 1
                    self.feedback = "GOOD SQUEEZE!"
                    current_color = (0, 255, 0)
                    
                    # 🟢 AI Coach Completion Logic
                    phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                    self.coach.speak_motivation(phase)
                    self.coach.on_good_rep()
                    self.coach.speak_if_ready(GOOD_REP)
                    self.coach.reset_error(SPIDER_CURL_STRETCH)
                    self.coach.reset_error(SPIDER_CURL_CURL)
                    
                    self._reset_rep_tracking()

            # 2) Bottom (arm fully extended)
            elif angle > 155:
                if self.stage != "down":
                    self.stage = "down"
                    self.feedback = "GOOD STRETCH!"
                    current_color = (0, 255, 0)
                    self.coach.reset_error(SPIDER_CURL_STRETCH)
                    self._reset_rep_tracking()
                else:
                    self.feedback = "GOOD STRETCH!"
                    current_color = (0, 255, 0)

            # 3) Warning: Not curling high enough (short rep while ascending)
            elif self.stage == "down" and 50 <= angle <= 155:
                # لو نزل الوزن تاني قبل ما يكمل الرفعة (الزاوية كبرت 15 درجة)
                if angle - self.min_angle_this_rep > 15:
                    self.feedback = "CURL UP TO CHIN!"
                    current_color = (0, 165, 255)
                    voice_message = SPIDER_CURL_CURL
                else:
                    self.feedback = "CURLING..."
                    current_color = (255, 255, 255)

            # 4) Warning: Partial extension while descending
            elif self.stage == "up" and 50 <= angle <= 155:
                # لو شد الوزن تاني قبل ما يفرد دراعه للاخر (الزاوية صغرت 15 درجة)
                if self.max_angle_this_rep - angle > 15:
                    self.feedback = "LOWER FOR FULL STRETCH!"
                    current_color = (0, 165, 255)
                    voice_message = SPIDER_CURL_STRETCH
                else:
                    self.feedback = "LOWERING..."
                    current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        # ── Draw skeleton & angle ─────────────────────────────────────
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)
        cv2.putText(frame, f"{int(angle)} DEG", tuple(elbow.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)