import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    HAMMER_CURL_SETUP,
    HAMMER_CURL_CURL,
    HAMMER_CURL_STRETCH,
    HAMMER_SWINGING,
    PIN_ELBOW,  # 🟢 ضفنا رسالة تثبيت الكوع هنا
    GOOD_REP 
)

class HammerCurlTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "down"  # "down" = مفرود, "up" = متني
        self.feedback   = "Setup"
        self.coach      = AICoach(language=language)
        
        # 🟢 التنعيم 1 للاستجابة اللحظية (الـ Sweet Spot بتاعتك)
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
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW SIDE VIEW & ARM"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(HAMMER_CURL_SETUP, urgent=True)
            return frame

        self.coach.reset_error(HAMMER_CURL_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        raw_angle = calculate_angle(shoulder, elbow, wrist)
        angle = self._get_smoothed_angle(raw_angle)
        
        if self.stage == "down":
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)
        elif self.stage == "up":
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # 🟢 التحكم الصارم: منع الكوع إنه يبعد عن الجسم بأكتر من 30 درجة
        upper_arm_angle = calculate_angle(hip, shoulder, elbow)
        if upper_arm_angle > 30:
            self.feedback = "KEEP ELBOW PINNED!"
            current_color = (0, 0, 255)
            self.coach.on_error(PIN_ELBOW)  # 👈 هيزعقله ويقوله ثبت كوعك
        else:
            # لو كوعه ثابت، نلغي التحذير ونكمل حساب العدة عادي
            self.coach.reset_error(PIN_ELBOW)
            self.coach.reset_error(HAMMER_SWINGING)

            # 🟢 زاوية القفل السريعة (75)
            if angle < 75:
                if self.stage != "up":
                    self.stage    = "up"
                    self.counter += 1
                    self.feedback = "GOOD SQUEEZE!"
                    current_color = (0, 255, 0)
                    
                    phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                    self.coach.speak_motivation(phase)
                    self.coach.on_good_rep()
                    self.coach.speak_if_ready(GOOD_REP)
                    
                    self.coach.reset_error(HAMMER_CURL_CURL)
                    self.coach.reset_error(HAMMER_CURL_STRETCH)
                    self._reset_rep_tracking()

            # 🟢 زاوية الفرد السريعة (145)
            elif angle > 145:
                if self.stage != "down":
                    self.stage = "down"
                    self.feedback = "GOOD STRETCH!"
                    current_color = (0, 255, 0)
                    self.coach.reset_error(HAMMER_CURL_STRETCH)
                    self._reset_rep_tracking()
                else:
                    self.feedback = "GOOD STRETCH!"
                    current_color = (0, 255, 0)

            # 🟢 السماحية اللي إنت ظبطتها على 15 (زي ما هي)
            elif self.stage == "down" and 75 <= angle <= 145:
                if angle - self.min_angle_this_rep > 15:
                    self.feedback = "CURL UP HIGH!"
                    current_color = (0, 165, 255)
                    voice_message = HAMMER_CURL_CURL
                else:
                    self.feedback = "CURLING..."
                    current_color = (255, 255, 255)

            elif self.stage == "up" and 75 <= angle <= 145:
                if self.max_angle_this_rep - angle > 15:
                    self.feedback = "LOWER FOR FULL STRETCH!"
                    current_color = (0, 165, 255)
                    voice_message = HAMMER_CURL_STRETCH
                else:
                    self.feedback = "LOWERING..."
                    current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)
        cv2.putText(frame, f"{int(angle)} DEG", tuple(elbow.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)