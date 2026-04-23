from picamera2 import Picamera2
import cv2
import time
import car_movement as car
from servomovement import servoturn
import numpy as np

picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(main={"size":(320,240)}))
picam2.start()

# --- PID SETTINGS (Tuned for Stability) ---
Kp = 0.25  # Turning power
Kd = 0.01 # Brakes (Higher value stops overshooting)
Ki = 0    # Usually keep at 0 for line following
base_speed = 40  # Steady speed
last_error = 0
last_time=time.time()
last_side=0 # -1 for Left, 1 for Right

time.sleep(2)
servoturn(0)


# --- Auto-Calibration ---
print("Calibrating lighting conditions...")
frame = picam2.capture_array()
gray_calibrate = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
# Otsu automatically finds the best threshold for your specific room lighting
ret, _ = cv2.threshold(gray_calibrate, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
linethreshold = ret
print(f"Calibration complete. Threshold set to: {linethreshold}")

try:
    while True:
        frame = picam2.capture_array()
        if frame is None: continue
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time
    
        roi = frame[100:160, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, mask = cv2.threshold(blurred, linethreshold, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) 
  
        if len(contours) > 0:
            # Find the largest contour (the line)
            c = max(contours, key=cv2.contourArea)
            M = cv2.moments(c)
            
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
            '''
            rect = cv2.minAreaRect(c)
            cx = int(rect[0][0])
            cy = int(rect[0][1])
            In short:
minAreaRect (Bounding Box): Only looks at the outermost pixels. If there’s a single speck of noise or a rough edge, the center "snaps" or jitters, causing the motors to twitch.
cv2.moments (Centroid): Calculates the average center (Center of Mass) of every single pixel in the line.
Why it's better for your report:
Smoother Steering: It filters out image noise automatically.
Better Curves: It stays on the "meat" of the line even when the line is bent or diagonal.
Stability: It prevents the PID error from jumping suddenly, which saves your motors from vibrating.
'''
            # --- 2. PID MATH ---
            
            print(f"LIVE X: {cx}")
            
            error = cx-160
            if error <- 30: last_side = -1   # Line is on the left
            elif error >30: last_side = 1 # Line is on the right
            
            P = Kp * error
            D = Kd * ((error - last_error) / dt) if dt > 0 else 0
            correction = int(P + D)
            last_error = error
            print("Correction:"+str(correction))

            l_speed = base_speed - correction
            r_speed = base_speed + correction

            # Clamp motor speeds between 0 and 80
            l_speed=max(-80,min(l_speed,80))
            r_speed=max(-80,min(r_speed,80))
            
            car.set_motors(l_speed, r_speed)

            # --- 3. DEBUG DRAWING ---
            # Draw on the ROI so we can see what the robot is thinking
            cv2.circle(roi, (cx, cy), 5, (0, 0, 255), -1)
            cv2.drawContours(roi, [c], -1, (0, 255, 0), 2)
            # Draw a center target line
            cv2.line(roi, (160, 0), (160, 60), (255, 0, 0), 1)


        else:
                
                if last_side == 1:
                # Swing Right: Left motor pushes hard, right motor is dead
                        print("Sharp Search Right")
                        car.set_motors(60,-60)
                elif last_side == -1:
                # Swing Left: Right motor pushes hard, left motor is dead
                        print("Sharp Search Left")
                        car.set_motors(-60, 60)
              
        # Show both the full camera and the mask for debugging

        cv2.imshow("Mask (Sensing Strip)", mask)
        cv2.imshow("Camera Feed", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
except Exception as e:
    print(f"An error occurred: {e}")
    
finally:
    print("Shutting down cleanly...")
    car.stop()
    servoturn(0)
    picam2.stop()
    picam2.close()
    cv2.destroyAllWindows()
    
      