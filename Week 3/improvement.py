import cv2
import numpy as np
import time
import threading
from tflite_runtime.interpreter import Interpreter
from picamera2 import Picamera2
import car_movement as car
from servomovement import servoturn

# ==========================================
# CONFIGURATION & GLOBALS
# ==========================================
Kp, Kd = 0.25, 0.01
base_speed = 40
last_error = 0
last_side = 0
last_seen_color = "BLACK"
entry_turn_direction = None
ignore_color = False
last_detection_time = 0
has_snapped=False
turn=""
# AI Threading Variables
latest_label = "Line"  #shared state between main thread and AI daemon thread
label_lock = threading.Lock() #prevent race conditions，thread must acquire the lock before reading or writing to the label
latest_frame=None
display_status = "Line: BLACK"
display_action = "FOLLOW"

# ==========================================
# FUNCTIONS
# ==========================================
def wait(sec):
    global frame, display_status, display_action, latest_label
    
    start = time.time()
    while time.time() - start < sec:
        frame = picam2.capture_array()
        if frame is None:
            continue

        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        bbox = get_symbol_bbox(frame_bgr)
        if bbox is not None:
            x, y, w, h = bbox
            cv2.rectangle(frame_bgr, (x, y), (x+w, y+h), (0,255,255), 2)
        # redraw your UI (same as main loop)
        cv2.putText(frame_bgr, f"AI: {latest_label}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        cv2.putText(frame_bgr, display_status, (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,0), 2)
        cv2.putText(frame_bgr, f"Action: {display_action}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        cv2.imshow("RobotView", frame_bgr)
        cv2.waitKey(1)

def get_ai_label(frame):
    """Processes Floating-Point AI and returns the label with high confidence."""
    try:
        # Resize and convert image to decimals (float32) for unquantized models
        img = cv2.resize(frame, (224, 224))[:, :, :3] #takes first 3 channels rgb
        img = (np.float32(img) / 127.5) - 1.0 #normalise rgb to -1.0 to 1.0 range,small, balanced numbers that are easier to proces
        
        interpreter.set_tensor(input_details[0]['index'], np.expand_dims(img, axis=0)) #loads the image into the AI，batch dimension
        #input_details = [{'index': 0, 'shape': [1,224,224,3]}],[0] extract first element->dictionary
        #interpreter.set_tensor(0, np.expand_dims(img, axis=0)),first argument:Put data into input tensor number 0.(slot in model)
        #original:image=(224,224,3),h,w,channel, expand 1 batch dimension==[img] one image inside a list of images,batch size= how many img to model at one time,fix batch size
        #“Send this batch of images into the model’s first input slot.
        interpreter.invoke() #runs the inference
        '''
1.Convolution(look for patttern: edge,line,corners),use small filter
->slide across image and ask is there a (feature) here-> create image show where (feature) exist
2.Activation function(ReLU)->ignore useless stuff->outputs the input directly if it is positive, and zero otherwise->remove noise,keep important
3.Weight multiplication->how important is this feature->important,high weight, vice versa(feature x weight)
4.Softmax->convert raw output scores (logits) into a probability distribution where all values are between 0 and 1 and sum exactly to 1. 
        '''
        output_data = interpreter.get_tensor(output_details[0]['index']) #read data from the model
        
        idx = np.argmax(output_data[0]) #find index of highest value (probability)
        conf = output_data[0][idx]  # Floating point already outputs 0.0 to 1.0
        
        raw_label = labels[idx].strip()
        clean_label = raw_label.split(" ", 1)[-1] if raw_label[0].isdigit() else raw_label
        return clean_label if conf > 0.55 else "Line"
    except Exception as e:
        return "Line"
    
def ai_thread_func():
    global latest_label, latest_frame
    while True:
        if latest_frame is not None:
            # 1. Start timer for the MODEL WORK only
            frame_copy = latest_frame.copy()
            # Prevents "Data Tearing": stops Main Loop from overwriting pixels while AI is still reading.
            new_lbl = get_ai_label(frame_copy)
            
            with label_lock:
                latest_label = new_lbl

        # --- KEEP YOUR ORIGINAL SLEEP UNTOUCHED ---
        time.sleep(0.05)
def get_priority_mask(roi):
    """Detects Red, Yellow, or Black (with Sticky memory)."""
    global last_seen_color
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Red
    l_r1, u_r1 = np.array([0, 70, 50]), np.array([10, 255, 255])
    l_r2, u_r2 = np.array([170, 70, 50]), np.array([180, 255, 255])
    #wrap around seam of red 0-10,170-180
    mask_r = cv2.inRange(hsv, l_r1, u_r1)|cv2.inRange(hsv, l_r2, u_r2)
    mask_r=cv2.morphologyEx(mask_r,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    mask_r=cv2.morphologyEx(mask_r,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    #MORPH_OPEN:eraser to delete random floor dust. 
    #MORPH_CLOSE:digital glue, filling in cracks or glare on the red line.
    # Yellow
    l_y, u_y = np.array([15, 120, 120]), np.array([40, 255, 255])
    mask_y = cv2.inRange(hsv, l_y, u_y)
    '''
    # Noise Eraser
    kernel = np.ones((1,1), np.uint8)
    mask_r = cv2.morphologyEx(mask_r, cv2.MORPH_OPEN, kernel)
    mask_y = cv2.morphologyEx(mask_y, cv2.MORPH_OPEN, kernel)
    '''
    # "Sticky" Mask: Drops requirement if already on the color
    # if not on a red line, it requires a massive 150 pixels of red to trigger. 
    # But if already on a red line (last_seen_color == "RED"), it lowers the requirement to just 30 pixels. 
    # This stops the robot from dropping the line during fast, blurry turns.
    req_r = 30 if last_seen_color == "RED" else 150
    req_y = 30 if last_seen_color == "YELLOW" else 150
    
    if cv2.countNonZero(mask_r) > req_r:
       return mask_r, "RED"
    if cv2.countNonZero(mask_y) > req_y: return mask_y, "YELLOW"
    
        
    # Black
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    _, mask_b = cv2.threshold(blurred, linethreshold, 255, cv2.THRESH_BINARY_INV)
    if cv2.countNonZero(mask_b) > 150: return mask_b, "BLACK"
    blank_mask=np.zeros_like(mask_b)
    return blank_mask,"LOST"


def reset_pid_clock():
    global last_error
    last_error = 0
    
def get_cx(m):
    """Calculates the center X coordinate of the largest contour in a mask."""
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs: return 160
    cc = max(cs, key=cv2.contourArea)
    if cv2.contourArea(cc) < 30: 
        return 160
    mm = cv2.moments(cc)
    if mm["m00"] == 0: return 160
    return int(mm["m10"]/mm["m00"])

def execute_junction_turn(car, direction, turn):
    """Handles the motor commands for junction turns to remove duplicated code."""
    if turn == "soft":
        if direction == "RIGHT":
            car.set_motors(40, -40)
        elif direction == "LEFT":
            car.set_motors(-40, 40)
        wait(0.2) # not sure
    else: # hard
        if direction == "RIGHT":
            car.set_motors(60, -45)
        elif direction == "LEFT":
            car.set_motors(-45, 60)
        wait(0.8) # not sure
def follow_line(frame):
    global last_error, last_side, last_seen_color,turn, entry_turn_direction,last_detection_time ,has_snapped ,ignore_color
    error=0
    correction=0
    roi = frame[140:190, :]
    
        
    if time.time() < last_detection_time:
        ignore_color = True
    # ==========================================

    # ==========================================
    # GET MASK
    # ==========================================
    if ignore_color:
        car.set_motors(base_speed, base_speed)
        return 0
    
    mask, current_color = get_priority_mask(roi)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # ==========================================
    # JUNCTION DETECTION
    # ==========================================
    is_entering = current_color not in ["BLACK" ,"LOST"] and last_seen_color == "BLACK"
    is_exiting = current_color == "BLACK" and last_seen_color not in ["BLACK" ,"LOST"]
    if is_entering or is_exiting: 
        if is_entering and not has_snapped:
            has_snapped = True
            print(current_color)
            print("Color seen! Gliding to let AI catch up...")
            
            # 1. THE GLIDE (No stopping, smooth rolling)
            car.set_motors(base_speed, base_speed) 
            
            # 2. THE AI CATCH-UP WINDOW
            # We keep rolling forward for 0.2 seconds while constantly 
            # listening to see if the AI detects an arrow.
            timeout = time.time() + 0.2
            ai_veto = False
            
            while time.time() < timeout:
                with label_lock:
                    if "arrow" in latest_label.lower():
                        ai_veto = True
                        break # The AI found it! Stop waiting.
                wait(0.01) # Check the AI 100 times a second
            
            # 3. DID THE AI INTERVENE?
            if ai_veto:
                print("Rolling Veto: AI confirms Arrow!")
                return "AI_TAKEOVER" # Abort the junction entirely!
                
            # 4. IF NO VETO, PROCEED AS NORMAL JUNCTION
            print("AI says no arrow. Normal Junction confirmed.")
            
            # Compare black vs color center
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, black_mask = cv2.threshold(gray, linethreshold, 255, cv2.THRESH_BINARY_INV)

            black_cx = get_cx(black_mask)
            color_cx = get_cx(mask)
            diff = color_cx - black_cx

            # ==========================================
            # DECIDE TURN
            # ==========================================
            
            if abs(diff)>10:turn="hard"
            else:turn="soft"
            
            if diff > 0:entry_turn_direction = "RIGHT"
            else:entry_turn_direction = "LEFT"
            
            print("enter: "+entry_turn_direction)
            print("turn style saved as: " + turn)
            print("Executing ENTRY turn: " + turn)
            execute_junction_turn(car, entry_turn_direction, turn)
            last_seen_color = current_color
            reset_pid_clock()    
            return 0       
        
        elif is_exiting and has_snapped:
            has_snapped = False
            print(f"JUNCTION EXIT: Rigging search direction for {entry_turn_direction}")
            
            # 1. Trick the "last_side" memory so if PID fails, 
            # the robot automatically searches in the correct direction!
            if entry_turn_direction == "RIGHT":
                last_side = 1
            elif entry_turn_direction == "LEFT":
                last_side = -1
                
            # 2. We DO NOT command any blind motor turns here. 
            # We just let the next frame handle it via PID or Search.
            
            # 3. Clear the junction memory
            entry_turn_direction = None
            last_seen_color = current_color
            reset_pid_clock()
            
            return 0
            
                    
        if cnts:
            c = max(cnts, key=cv2.contourArea)

            if cv2.contourArea(c) > 50:
                M = cv2.moments(c)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    error = cx - 160

                    if error > 15: last_side = 1
                    elif error < -15: last_side = -1
            # ==========================================
            # NORMAL PID (ONLY FOR SMOOTH TRACKING)
            # ==========================================
            P = Kp * error
            D = Kd * (error - last_error)
            correction = int(P + D)
            last_error = error

            spd = 36 if current_color != "BLACK" else base_speed
            car.set_motors(spd - correction, spd + correction)

        # ==========================================
        # LOST LINE → SEARCH (KEEP YOUR STYLE)
        # ==========================================
        else:
            spd_s = 70
            if last_side == 1:
            # print("right search")
                car.set_motors(spd_s, -spd_s)
            else:
            # print("left search")
                car.set_motors(-spd_s, spd_s)

        last_seen_color = current_color
        cv2.imshow("linemask",mask)
        return error


def get_arrow_direction(frame_bgr):
    """Fast Arrow Detection via Center of Mass."""
    small_frame = cv2.resize(frame_bgr, (160, 120))
    hsv = cv2.cvtColor(small_frame, cv2.COLOR_BGR2HSV)
    
    # 1. THE "NOT BLACK" MASK
    # Saturation > 60: Ignores white, gray, and black (looks for actual color pigment)
    # Value > 60: Ignores dark shadows and black tape
    _, mask_s = cv2.threshold(hsv[:,:,1], 60, 255, cv2.THRESH_BINARY)
    _, mask_v = cv2.threshold(hsv[:,:,2], 60, 255, cv2.THRESH_BINARY)
    
    # Combine them: Must be colorful AND bright
    arrow_mask = cv2.bitwise_and(mask_s, mask_v)
    
    # 2. THE FUSION SHIELD (Crucial for multi-colored arrows)
    # This smudges the different colors together into one giant solid arrow shape
    # and bridges any cracks or white gaps between the colored ink.
  #  kernel = np.ones((7, 7), np.uint8) 
   # arrow_mask = cv2.morphologyEx(arrow_mask, cv2.MORPH_CLOSE, kernel)
    
    # Erase tiny specks of dust from the floor
    arrow_mask = cv2.morphologyEx(arrow_mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    cv2.imshow("",arrow_mask)
    cnts, _ = cv2.findContours(arrow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c= max(cnts, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        box_cX = x + (w / 2)
        box_cY = y + (h / 2)
        M = cv2.moments(c)
        if M["m00"] != 0:
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])

            # 5. Calculate the "Shift" 
            # How far does the heavy Center of Mass lean away from the Box Center?
            shift_x = cX - box_cX
            shift_y = cY - box_cY

            # 6. Find the True Direction (No dictionary flip needed!)
            # Whichever shift is larger tells us if it's horizontal or vertical
            if abs(shift_x) > abs(shift_y):
                # The mass leans horizontally!
                if shift_x > 0:return "RIGHT"  # Mass leans right
                else: return "LEFT"   # Mass leans left
            else:
                # The mass leans vertically!
                if shift_y > 0:return "DOWN"   # Mass leans down
                else:return "UP"     # Mass leans up

    return None

def get_symbol_bbox(frame):
    """Finds general object region for ANY symbol"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hsv = cv2.GaussianBlur(hsv, (7,7), 0)
    
    _, mask_color = cv2.threshold(hsv[:, :, 1], 70, 255, cv2.THRESH_BINARY)
    _, mask_brightness = cv2.threshold(hsv[:, :, 2], 90, 255, cv2.THRESH_BINARY)
    color_mask = cv2.bitwise_and(mask_color, mask_brightness)
    
    kernel_big = np.ones((7, 7), np.uint8)
    kernel_small = np.ones((5, 5), np.uint8)
    color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel_big)  
    color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel_small)

    cnts, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.imshow("box", color_mask)
    if cnts:
        valid = [c for c in cnts if cv2.contourArea(c) > 100]

        if valid:
            all_points = np.vstack(valid)
            x, y, w, h = cv2.boundingRect(all_points)
            return (x, y, w, h)

    return None

# ==========================================
# MAIN
# ==========================================
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (320, 240)}))
picam2.start()

frame = picam2.capture_array()
ret, _ = cv2.threshold(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 90, 255, cv2.THRESH_BINARY_INV)
linethreshold = ret
print(f"Calibration complete. Threshold: {linethreshold}")

# --- FLOATING POINT TFLITE MODEL LOADED HERE ---
#Creates a TensorFlow Lite interpreter object
interpreter = Interpreter(model_path="model_unquant.tflite", num_threads=4) #use float32,slow,accurate,parallelize 4 CPU threads when running inference in rasp4
interpreter.allocate_tensors() #prepare memory for model's input and output tensor,create buffer,prepare computation graph
input_details, output_details = interpreter.get_input_details(), interpreter.get_output_details()
#reture list of dictionaries
#input:asks the interpreter: “What input format do you need?”input_details = where to insert the paper,output_details = where to collect the result
with open("labels.txt", "r") as f:
    labels = [l.strip() for l in f.readlines()]

threading.Thread(target=ai_thread_func, daemon=True).start()
frame_count = 0
try:
    while True:
        frame_count += 1
        frame = picam2.capture_array()
        if frame is None: continue
        latest_frame=frame
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        # Only look for symbols every 3 frames to save CPU
        if frame_count % 3 == 0:
            bbox = get_symbol_bbox(frame_bgr)
        else:
            bbox = None # Reuse old bbox or skip
        
        with label_lock:
            label = latest_label
        lbl_lower = label.lower()
        
        ignore_color = False
        if lbl_lower == "line":
            display_status = f"Line: {last_seen_color}"
            display_action = "FOLLOW"
        
        display_frame = frame_bgr.copy()
        # Draw UI Text instantly
        cv2.putText(display_frame, f"AI: {label}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        # Draw current robot status/action
        cv2.putText(display_frame, display_status, (10, 60),cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,0), 2)
        cv2.putText(display_frame, f"Action: {display_action}", (10, 90),cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        if lbl_lower != "line":
           if bbox is not None:
               x, y, w, h = bbox
               cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 255), 2)
       
        if "arrow" in lbl_lower:
                ignore_color=True
                car.stop(); wait(0.1)
                direction = get_arrow_direction(frame_bgr)
                print(f"Arrow: {direction}")
                if direction:
                    display_status = f"Symbol: Arrow {direction}"
                    if direction == "LEFT":
                        display_action = "TURN LEFT"
                        car.set_motors(-60, 60)
                        wait(0.5); car.forward(50); wait(0.3)
                    elif direction == "RIGHT":
                        display_action = "TURN RIGHT"
                        car.set_motors(60, -60)
                        wait(0.5); car.forward(50); wait(0.3)
                    elif direction == "UP":
                        display_action = "FORWARD"
                        car.forward(50)
                        wait(0.4)
                    elif direction == "DOWN":
                        display_action = "REVERSE"
                        car.backward(50)
                        wait(0.4)
                    
                    reset_pid_clock()
                
                last_detection_time = time.time() + 0.5

                
                
                continue
        
        if "warning" in lbl_lower or "hand" in lbl_lower:
                ignore_color=True
                display_status = f"Symbol: {label}"
                display_action = "STOP"
                print("Action: STOP")
                car.stop(); wait(2)
                car.forward(50); wait(0.4)
                reset_pid_clock()
                last_detection_time = time.time() + 0.5
                continue
                
        # --- SYMBOL DETECTION ---
        # AI Backgrounds are ignored and passed safely to Search Mode!
        if lbl_lower != "line":
            print(f"SYMBOL SEEN: {label}")
            display_status = f"Symbol: {label}"
            display_action = "FOLLOW"
            if "recycle" in lbl_lower:
                
                display_action = "SPIN"
                print("Action: 360")
                target_time = time.time() + 2.1
                while time.time() <= target_time:
                    car.set_motors(70, -70)
                    picam2.capture_array(); cv2.waitKey(1)
                reset_pid_clock()
            else:
                follow_line(frame_bgr)
        else:
            # Normal driving
            current_error = follow_line(frame_bgr)
            if current_error == "AI_TAKEOVER":
                # The PID loop aborted the junction because the AI saw an arrow!
                # 'continue' instantly throws the code back to the very top of the 
                # while True loop, which instantly triggers your Arrow Arc Turn code!
                continue

        # Catch-all to update window if AI triggered
        cv2.imshow("RobotView", display_frame)
            
            
        if cv2.waitKey(1) & 0xFF == ord('q'): break
        
        
finally:
    car.stop()
    picam2.stop()
    cv2.destroyAllWindows()
