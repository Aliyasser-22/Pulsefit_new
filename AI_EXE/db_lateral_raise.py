import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    LATERAL_DB_SETUP,
    LATERAL_DB_RAISE,
    LATERAL_DB_LOWER,
    LATERAL_DB_TOO_HIGH,
    LATERAL_DB_BENT,  # 🟢 الرسالة الجديدة بتاعة الكوع
    GOOD_REP,
)

class DbLateralRaiseTrainerAI:
    def __init__(self, language="ar"):
        self.counter            = 0
        self.stage              = "down"
        self.feedback           = "Setup"
        self.coach              = AICoach(language=language)
        
        # 🟢 التنعيم 1 للاستجابة اللحظية (الويب)
        self.angle_history      = deque(maxlen=1)
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _get_smoothed_angle(self, angle):
        self.angle_history.append(angle)
        return float(np.mean(self.angle_history))

    def process(self, frame, keypoints, confs):
        # ── VISIBILITY CHECK (Front View) ──
        # 🟢 ضفنا المعصم (10 و 9) عشان نحسب زاوية الكوع
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW FRONT VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(LATERAL_DB_SETUP, urgent=True)
            return frame

        self.coach.reset_error(LATERAL_DB_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx]

        # 🟢 الزاوية الأساسية (بين الوسط والكتف والكوع) لمعرفة الرفعة
        raw_angle = calculate_angle(hip, shoulder, elbow)
        current_angle = self._get_smoothed_angle(raw_angle)
        
        # 🟢 زاوية الكوع (لمنع الغش وتنية الدراع)
        elbow_angle = calculate_angle(shoulder, elbow, wrist)
        
        current_color = (0, 255, 0)
        voice_message = None

        # ── TRACKING EXTREMES ──
        if self.stage == "down":
            self.max_angle_this_rep = max(self.max_angle_this_rep, current_angle)
        else:
            self.min_angle_this_rep = min(self.min_angle_this_rep, current_angle)

        # ── FORM CHECK 1: Too High (الترابيس) ──
        if current_angle > 110:
            self.feedback = "TOO HIGH!"
            current_color = (0, 0, 255)
            self.coach.on_error(LATERAL_DB_TOO_HIGH)
            
        # ── FORM CHECK 2: Too Bent (تنية الكوع للغش) ──
        # لو الزاوية قلت عن 130، يبقى تانى إيده 90 درجة تقريباً وده غلط
        elif elbow_angle < 130:
            self.feedback = "ARMS TOO BENT!"
            current_color = (0, 0, 255)
            self.coach.on_error(LATERAL_DB_BENT)
            
        else:
            # لو بيلعب صح، نشيل التحذيرات
            self.coach.reset_error(LATERAL_DB_TOO_HIGH)
            self.coach.reset_error(LATERAL_DB_BENT)

            # ── 1) Top (Arms parallel to ground) ──
            if current_angle > 85:
                if self.stage == "down":
                    self.stage = "up"
                    self.counter += 1
                    self.feedback = "GOOD REP!"
                    current_color = (0, 255, 0)
                    
                    self.coach.on_good_rep()
                    self.coach.speak_if_ready(GOOD_REP)
                    
                    self.coach.reset_error(LATERAL_DB_RAISE)
                    self.coach.reset_error(LATERAL_DB_LOWER)
                    
                    self._reset_rep_tracking()
                    self.max_angle_this_rep = current_angle 

            # ── 2) Bottom (Arms down) ──
            elif current_angle < 30:
                if self.stage != "down":
                    self.stage = "down"
                    self.feedback = "LIFT DB UP!"
                    current_color = (255, 255, 255)
                    
                    self.coach.reset_error(LATERAL_DB_RAISE)
                    self.coach.reset_error(LATERAL_DB_LOWER)
                    
                    self._reset_rep_tracking()
                    self.min_angle_this_rep = current_angle 

            # ── 3) Hysteresis: Ascending (stage=="down") ──
            elif self.stage == "down" and 30 <= current_angle <= 85:
                if self.max_angle_this_rep - current_angle > 15:
                    self.feedback = "RAISE TO SHOULDER LEVEL!"
                    current_color = (0, 165, 255)
                    voice_message = LATERAL_DB_RAISE
                else:
                    self.feedback = "RAISING..."
                    current_color = (255, 255, 255)

            # ── 4) Hysteresis: Descending (stage=="up") ──
            elif self.stage == "up" and 30 <= current_angle <= 85:
                if current_angle - self.min_angle_this_rep > 15:
                    self.feedback = "LOWER FULLY!"
                    current_color = (0, 165, 255)
                    voice_message = LATERAL_DB_LOWER
                else:
                    self.feedback = "LOWERING..."
                    current_color = (255, 255, 255)

        if voice_message:
            self.coach.on_error(voice_message)

        # ── رسم الهيكل العظمي ──
        cv2.putText(frame, f"Sh: {int(current_angle)}", tuple(shoulder.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Elb: {int(elbow_angle)}", tuple(elbow.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        cv2.line(frame, tuple(hip.astype(int)), tuple(shoulder.astype(int)), current_color, 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(elbow.astype(int)), current_color, 2)
        cv2.line(frame, tuple(elbow.astype(int)), tuple(wrist.astype(int)), current_color, 2)
        
        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)