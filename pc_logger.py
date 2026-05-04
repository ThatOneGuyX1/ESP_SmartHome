import serial
import json
import csv
import sys
import time
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="ESP-NOW Serial Logger")
    parser.add_argument("port", help="COM port of the ESP32 (e.g., COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--out", type=str, default="esp_now_log.csv", help="Output CSV file")
    
    args = parser.parse_args()

    print(f"Connecting to {args.port} at {args.baud} baud...")
    
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        print("Make sure the port is correct and not used by another program (like a serial monitor/PuTTY).")
        sys.exit(1)

    print(f"Connected! Appending data to {args.out}")
    print("Waiting for JSON_OUT lines from ESP32...")
    print("(Press Ctrl+C to stop logging)")
    
    csv_file_exists = os.path.exists(args.out)
    jsonl_out = args.out.replace('.csv', '.jsonl')
    
    with open(args.out, 'a', newline='') as f_csv, open(jsonl_out, 'a') as f_jsonl:
        writer = csv.writer(f_csv)
        
        # Write CSV headers if file is new
        if not csv_file_exists:
            writer.writerow([
                "local_timestamp", "type", "temp", "humidity", "light", "occ", 
                "ts_ms", "bat_mv", "bat_soc", "chip_temp", "rssi", "heap", "uptime"
            ])
        
        try:
            while True:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                
                # If it's a JSON line, process it
                if line.startswith("JSON_OUT:"):
                    json_str = line[len("JSON_OUT:"):]
                    try:
                        data = json.loads(json_str)
                        
                        data['local_timestamp'] = time.time()
                        
                        # Write raw JSON Lines for backup parsing
                        f_jsonl.write(json.dumps(data) + '\n')
                        f_jsonl.flush()
                        
                        # Flatten into CSV
                        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['local_timestamp']))
                        row = [
                            time_str,
                            data.get('type', ''),
                            data.get('temp', ''),
                            data.get('humidity', ''),
                            data.get('light', ''),
                            data.get('occ', ''),
                            data.get('ts', ''),
                            data.get('bat_mv', ''),
                            data.get('bat_soc', ''),
                            data.get('chip_temp', ''),
                            data.get('rssi', ''),
                            data.get('heap', ''),
                            data.get('uptime', '')
                        ]
                        writer.writerow(row)
                        f_csv.flush()
                        
                        print(f"[{time_str}] LOGGED {data.get('type', 'Unknown').upper()} packet")
                    except json.JSONDecodeError:
                        print(f"Failed to parse JSON: {json_str}")
                else:
                    # Optional: uncomment to print all other normal logs the ESP32 sends
                    # print(f"ESP32: {line}")
                    pass
        
        except KeyboardInterrupt:
            print("\nLogging complete. Port closed.")
            ser.close()

if __name__ == '__main__':
    main()
