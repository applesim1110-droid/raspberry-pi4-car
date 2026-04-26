import cv2
import numpy as np
from tflite_runtime.interpreter import Interpreter
from picamera2 import Picamera2
def direction(best_cnt):
    M = cv2.moments(best_cnt)
    if M["m00"] != 0:
        cX, cY = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
        l = tuple(best_cnt[best_cnt[:,:,0].argmin()][0])
        r = tuple(best_cnt[best_cnt[:,:,0].argmax()][0])
        t = tuple(best_cnt[best_cnt[:,:,1].argmin()][0])
        b = tuple(best_cnt[best_cnt[:,:,1].argmax()][0])
        dists = {"LEFT": cX-l[0], "RIGHT": r[0]-cX, "UP": cY-t[1], "DOWN": b[1]-cY}
        direction = max(dists, key=dists.get)
        v_flip = {"LEFT": "RIGHT", "RIGHT": "LEFT", "UP": "DOWN", "DOWN": "UP"}
        direction=v_flip[direction]
        return direction
# ==========================================
# 1. LOAD AI MODEL & LABELS
# ==========================================
print("Loading AI Model...")
interpreter = Interpreter(model_path="model_unquant.tflite")
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

with open("labels.txt", "r") as f:
    labels = [line.strip() for line in f.readlines()]

# ==========================================
# 2. START CAMERA
# ==========================================
print("Starting camera... Press 'q' to quit.")
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (320, 240)}))
picam2.start()

try:
    display_text = "Scanning..."
    while True:
        frame = picam2.capture_array()
        if frame is None: continue

        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # ==========================================
        # 3. AI SENTRY (Look at everything first)
        # ==========================================
        ai_frame = np.ascontiguousarray(frame[:, :, :3])
        img = cv2.resize(ai_frame, (224, 224))
        img = np.float32(img)
        img = np.expand_dims(img, axis=0)
        img = (img / 127.5) - 1.0  

        interpreter.set_tensor(input_details[0]['index'], img)
        interpreter.invoke()
        output_data = interpreter.get_tensor(output_details[0]['index'])
        
        index = np.argmax(output_data[0])
        confidence = output_data[0][index]
        label_text = labels[index][2:] if labels[index][1].isspace() else labels[index]

       
        display_text ="Scanning:"
            # --- FIND THE SHAPE WITH OPENCV ---
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hsv = cv2.GaussianBlur(hsv, (7,7), 0)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
            
        # 1. Create your two masks just like you did

        _, mask_color = cv2.threshold(saturation, 70, 255, cv2.THRESH_BINARY)
        _, mask_brightness = cv2.threshold(value, 60, 255, cv2.THRESH_BINARY)
        # 2. Combine them

        color_mask = cv2.bitwise_and(mask_color, mask_brightness)
        cv2.imshow("Mask1", color_mask)

        # --- THE HEALING FIX ---            # B. MORPH_CLOSE: This "closes" the holes/creases by expanding then shrinking.
        # It acts like digital tape over the bends in your paper.
        
        kernel_big = np.ones((5, 5), np.uint8)
    # C. MORPH_OPEN: Now clean up the tiny random dots outside the shape.
        kernel_small = np.ones((5, 5), np.uint8)
        
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel_big)  
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel_small)
        cv2.imshow("Mask2", color_mask)

        contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = [cnt for cnt in contours if 500 < cv2.contourArea(cnt) < 20000]
        
        if valid_contours:
            all_points = np.vstack(valid_contours)
            best_cnt = all_points.reshape(-1, 1, 2)
            best_cnt = best_cnt.astype(np.int32)
            if len(best_cnt) <5:
                continue
            x, y, w, h = cv2.boundingRect(best_cnt)

            # add padding so box doesn't “jump”
            pad = 15

            x = max(0,x - pad)
            y = max(0,y - pad)
            w = w + 2 * pad
            h = h + 2 * pad
            
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0,255,0), 2)

            # --- 1. CALCULATE ALL MATH ONCE ---
            area = cv2.contourArea(best_cnt)
            hull = cv2.convexHull(best_cnt)
            hull_area = cv2.contourArea(hull)
            solidity = area / float(hull_area) if hull_area > 0 else 0
            
            peri = cv2.arcLength(best_cnt, True)
            approx = cv2.approxPolyDP(best_cnt, 0.04 * peri, True)
            corners = len(approx)
            defect_count = 0
            try:
            # --- CONVEXITY DEFECTS (FOR STAR) ---
                hull_indices = cv2.convexHull(best_cnt, returnPoints=False)
                if hull_indices is not None and len(hull_indices) >=4:
                    defects = cv2.convexityDefects(best_cnt, hull_indices)
                    if defects is not None:
                      for i in range(defects.shape[0]):
                        s, e, f, d = defects[i][0]
                        d=d/256.0 #normalize
                        if d > 5:
                            defect_count += 1
            except:
                defect_count = 0
            print("Solidity:"+str(solidity)+"corneres:"+str(corners)+"defect:"+str(defect_count))
            
            # --- AI RESULT ---
            ai_label=label_text.upper()
            ai_conf=confidence
            
            
            geo_label = None
            shape_name=geo_label
            # RULE C: Is it an Arrow? (Even if AI is unsure, the math knows)
            if "ARROW" in ai_label:
                dir=direction(best_cnt)
            
            if 0.55 <= solidity<0.7 and corners >= 8 and defect_count >= 5:
               geo_label = "STAR"
            elif 0.7 <=solidity<=0.84 and defect_count==1 :
               geo_label = "3/4 CIRCLE"
            elif 0.84 < solidity < 0.89 and 4<=corners<=7:
               geo_label = "CROSS"
            
            elif solidity >= 0.89:
                circ = (4 * np.pi * area) / (peri * peri) if peri > 0 else 0
               
                print(f"Circularity: {circ:.2f}, Corners: {corners}")

                if corners ==4:
                    pts=approx.reshape(4,2)
                    sides=[np.linalg.norm(pts[i]-pts[(i+1)%4]) for i in range(4)]
                    ratio=min(sides)/max(sides)
                    if ratio>0.85:
                        geo_label="DIAMOND"
                    else:geo_label = "TRAPEZIUM"
                    print("ratio:" +str(ratio))
                # --- THE DECISION ---
                elif circ > 0.82 and corners >= 7:
                    # High circularity + many corners = OCTAGON
                    geo_label = "OCTAGON"
                elif 0.7<=circ <= 0.82 and corners >= 5 :
                    # Lower circularity + flat side = SEGMENT
                    geo_label = "SEGMENT"
            
            
            # ==========================================
            # AI + GEOMETRY DECISION SYSTEM
            # ==========================================
            # If this is NOT an arrow, decide using confidence + geometry
            if geo_label is not None:
                if ai_label !=geo_label:
                    shape_name = geo_label
            else:
                shape_name = ai_label
            
                
            
            # ==========================================
            # DISPLAY TEXT
            # ==========================================
            # Only show confidence for AI-based symbols/arrows
            if geo_label is None:
                if "ARROW" in shape_name:
                    display_text = f"{shape_name} {dir} ({int(ai_conf * 100)}%)"
                else:
                    display_text = f"{shape_name} ({int(ai_conf * 100)}%)"
            else:
                display_text = shape_name

            # ==========================================
            # DRAW LABEL ABOVE BOX
            # ==========================================
            text_y = max(y - 10, 20)
            cv2.putText(frame,display_text,(x, text_y),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0, 255, 255),2)
            print(f"DEBUG: Sol:{solidity:.2f} Corn:{corners} Label:{label_text}")

            
        
        
        else:
            display_text = "Scanning..."
        cv2.imshow("Robot Vision System", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
        
        


finally:
    print("Shutting down...")
    picam2.stop()
    picam2.close()
    cv2.destroyAllWindows() 
