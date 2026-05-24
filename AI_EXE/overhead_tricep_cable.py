import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    OVERHEAD_TRICEP_CABLE_SETUP,
    OVERHEAD_TRICEP_CABLE_PUSH,
    OVERHEAD_TRICEP_CABLE_STRETCH,
    OVERHEAD_TRICEP_CABLE_DROP,
    OVERHEAD_KEEP_ELBOWS_HIGH,  
    GOOD_REP 
)

class OverheadTricepCableTrainerAI:
    def __init__(self, language="ar"):
        self.counter    = 0
        self.stage      = "up"  
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
        if confs[6] > 0.4 and confs[8] > 0.4 and confs[10] > 0.4 and confs[12] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 6, 8, 10, 12
        elif confs[5] > 0.4 and confs[7] > 0.4 and confs[9] > 0.4 and confs[11] > 0.4:
            s_idx, e_idx, w_idx, h_idx = 5, 7, 9, 11
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(OVERHEAD_TRICEP_CABLE_SETUP, urgent=True)
            return frame

        self.coach.reset_error(OVERHEAD_TRICEP_CABLE_SETUP)

        shoulder = keypoints[s_idx]
        elbow    = keypoints[e_idx]
        wrist    = keypoints[w_idx]
        hip      = keypoints[h_idx] 

        raw_angle = calculate_angle(shoulder, elbow, wrist)
        angle = self._get_smoothed_angle(raw_angle)
        
        if self.stage == "up":
            self.max_angle_this_rep = max(self.max_angle_this_rep, angle)
        elif self.stage == "down":
            self.min_angle_this_rep = min(self.min_angle_this_rep, angle)

        current_color = (0, 255, 0)
        voice_message = None

        # 🟢 التحكم المنطقي في الكوع: ميزعقش غير لو الكوع نزل لتحت مستوى الكتف
        upper_arm_angle = calculate_angle(hip, shoulder, elbow)
        if upper_arm_angle < 85: 
            self.feedback = "KEEP ELBOWS HIGH!"
            current_color = (0, 0, 255)
            self.coach.on_error(OVERHEAD_KEEP_ELBOWS_HIGH)
        else:
            self.coach.reset_error(OVERHEAD_KEEP_ELBOWS_HIGH)

            # 🟢 زاوية الفرد خليناها 140 عشان تناسب مرونة الكتف
            if angle > 140:
                if self.stage != "down":
                    self.stage    = "down"
                    self.counter += 1
                    self.feedback = "GOOD SQUEEZE!"
                    current_color = (0, 255, 0)
                    
                    phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                    self.coach.speak_motivation(phase)
                    self.coach.on_good_rep()
                    self.coach.speak_if_ready(GOOD_REP)
                    
                    self.coach.reset_error(OVERHEAD_TRICEP_CABLE_PUSH)
                    self.coach.reset_error(OVERHEAD_TRICEP_CABLE_STRETCH)
                    self._reset_rep_tracking()

            # 🟢 زاوية التمدد (وراء الرأس) خليناها 90
            elif angle < 90:
                if self.stage != "up":
                    self.stage = "up"
                    self.feedback = "GOOD STRETCH!"
                    current_color = (0, 255, 0)
                    self.coach.reset_error(OVERHEAD_TRICEP_CABLE_STRETCH)
                    self._reset_rep_tracking()
                else:
                    self.feedback = "GOOD STRETCH!"
                    current_color = (0, 255, 0)

            # 3) Warning: Not extending fully
            elif self.stage == "up" and 90 <= angle <= 140:
                if self.max_angle_this_rep - angle > 15 and self.max_angle_this_rep > 100:
                    self.feedback = "EXTEND FULLY!"
                    current_color = (0, 165, 255)
                    voice_message = OVERHEAD_TRICEP_CABLE_PUSH
                else:
                    self.feedback = "PUSHING..."
                    current_color = (255, 255, 255)

            # 4) Warning: Partial stretch
            elif self.stage == "down" and 90 <= angle <= 140:
                if angle - self.min_angle_this_rep > 15 and self.min_angle_this_rep < 120:
                    self.feedback = "LOWER BAR BEHIND HEAD!"
                    current_color = (0, 165, 255)
                    voice_message = OVERHEAD_TRICEP_CABLE_STRETCH
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