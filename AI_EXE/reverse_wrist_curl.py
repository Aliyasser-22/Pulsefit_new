import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    REVERSE_WRIST_CURL_SETUP,
    REVERSE_WRIST_CURL_CURL,
    REVERSE_WRIST_CURL_STRETCH,
    REVERSE_WRIST_CURL_DROP,
    GOOD_REP # 🟢 عشان التشجيع
)

class ReverseWristCurlTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "down"  # "down" = إيد مفرودة لتحت، "up" = مرفوعة لفوق (Extension)
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
        # بنحتاج الكوع والرسغ والصوابع (نقطة 4 هي الإبهام أو ممكن نستخدم 16/15 لو Pose)
        # في YOLOv8-pose، النقط من 17 لـ 20 هي الصوابع، بس خلينا نعتمد على دقة الرسغ
        if confs[8] > 0.4 and confs[10] > 0.4:
            e_idx, w_idx = 8, 10 # Right side
        elif confs[7] > 0.4 and confs[9] > 0.4:
            e_idx, w_idx = 7, 9  # Left side
        else:
            self.feedback = "SHOW WRIST & ELBOW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(REVERSE_WRIST_CURL_SETUP, urgent=True)
            return frame

        self.coach.reset_error(REVERSE_WRIST_CURL_SETUP)

        elbow  = keypoints[e_idx]
        wrist  = keypoints[w_idx]
        # بنستخدم نقطة "اليد" (نقطة 10) والرسغ (نقطة 9) لتحديد الاتجاه
        # في حالة الـ Reverse Curl، إحنا بنقيس حركة ظهر الإيد
        finger = keypoints[w_idx] + (keypoints[w_idx] - keypoints[e_idx]) * 0.5 # نقطة تخيلية للامتداد

        # في تمارين الساعد، الزاوية بتتحسب بين الكوع والرسغ ونقطة اليد
        # بما إن الـ Pose العادي مبيجبش الصوابع بدقة، بنعتمد على الـ Movement Vector
        raw_angle = calculate_angle(elbow, wrist, keypoints[10]+5) # تعديل بسيط للدقة
        angle = self._get_smoothed_angle(raw_angle)
        
        # ── Track extremes for direction detection ────────────────────
        if self.stage == "down":
            # بيرفع إيده لفوق (الزاوية بتقل في الـ Extension)
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)
        elif self.stage == "up":
            # بينزل إيده لتحت (الزاوية بتزيد)
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # 1) Extension complete (Top - wrist pulled up)
        if angle < 140: # في الـ Pose estimation الـ 180 هي الاستقامة، الـ Extension بيقلل الزاوية
            if self.stage != "up":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD SQUEEZE!"
                current_color = (0, 255, 0)
                
                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)
                self.coach.reset_error(REVERSE_WRIST_CURL_CURL)
                self.coach.reset_error(REVERSE_WRIST_CURL_STRETCH)
                
                self._reset_rep_tracking()

        # 2) Full stretch (Bottom - wrist hanging)
        elif angle > 170:
            if self.stage != "down":
                self.stage = "down"
                self.feedback = "FULL STRETCH!"
                current_color = (0, 255, 0)
                self.coach.reset_error(REVERSE_WRIST_CURL_STRETCH)
                self._reset_rep_tracking()

        # 3) Warning: Short rep while ascending
        elif self.stage == "down" and angle < 170:
            # لو نزل إيده تاني (الزاوية كبرت) قبل ما يوصل للقمة
            if angle - self.min_angle_this_rep > 10:
                self.feedback = "CURL UP FULLY!"
                current_color = (0, 165, 255)
                voice_message = REVERSE_WRIST_CURL_CURL

        # 4) Warning: Short rep while descending
        elif self.stage == "up" and angle > 140:
            # لو رفع إيده تاني (الزاوية صغرت) قبل ما ينزل للاخر
            if self.max_angle_this_rep - angle > 10:
                self.feedback = "LOWER FULLY!"
                current_color = (0, 165, 255)
                voice_message = REVERSE_WRIST_CURL_STRETCH

        if voice_message:
            self.coach.on_error(voice_message)

        # ── Draw ─────────────────────────────────────────────────────
        cv2.putText(frame, f"{int(angle)} DEG", tuple(wrist.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)