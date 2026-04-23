from picamera2 import Picamera2
import cv2
import os

# 1. Define your shape categories
categories = ["face", "recycle", "hand", "fingerprint","3quarter_circle","segment"]
base_folder = "dataset"

# Automatically create a folder for each shape if it doesn't exist
for category in categories:
    folder_path = os.path.join(base_folder, category)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        print(f"Created folder: {folder_path}/")

# Keep track of how many photos you've taken for each shape
counters = {"face": 1, "recycle": 1, "hand": 1, "fingerprint": 1,"3quarter_circle": 1,"segment": 1}

# 2. Set up the camera
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (640, 480)}))
picam2.start()

print("\n--- DATA COLLECTION MODE ---")
print("Press 'c' to snap a CROSS")
print("Press 'd' to snap a DIAMOND")
print("Press 's' to snap a STAR")
print("Press 'r' to snap a RECYCLE")
print("Press 'q' to QUIT\n")

try:
    while True:
        # 3. Show live feed and fix the colors
        frame = picam2.capture_array()
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        # Draw a quick cheat sheet on the camera window
        
        cv2.imshow("Dataset Collector", frame_bgr)

        # 4. Listen for keyboard presses
        key = cv2.waitKey(1) & 0xFF
        category_to_save = None

        # Figure out which key was pressed
        if key == ord('l'):
            category_to_save = "line"
        elif key == ord('r'):
            category_to_save = "recycle"
        elif key == ord('h'):
            category_to_save = "hand"
        elif key == ord('s'):
            category_to_save = "segment"
        elif key == ord('f'):
            category_to_save = "face"
        elif key == ord('c'):
            category_to_save = "3quarter_circle"
        
        elif key == ord('q'):
            print("\nFinished collecting samples! Camera shutting down.")
            break

        # 5. Save the image to the matching folder
        if category_to_save:
            count = counters[category_to_save]
            img_name = f"{base_folder}/{category_to_save}/{category_to_save}_{count}.jpg"
            cv2.imwrite(img_name, frame_bgr)
            print(f" [SNAP] Saved: {img_name}")
            counters[category_to_save] += 1 # Increase the counter for next time

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    # 6. Clean up
    picam2.stop()
    picam2.close()
    cv2.destroyAllWindows()