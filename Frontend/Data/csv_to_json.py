import csv
import json
import os

# Danh sách các file cần chuyển đổi (Tên file CSV đầu vào và JSON đầu ra)
files_to_convert = [
    {"csv": "stops_raw.csv", "json": "stops_raw.json"},
    {"csv": "lines_clean.csv", "json": "lines_clean.json"},
    {"csv": "station_line_clean.csv", "json": "station_line_clean.json"}
]

def convert_csv_to_json(csv_filepath, json_filepath):
    try:
        # Mở file CSV để đọc
        with open(csv_filepath, mode='r', encoding='utf-8-sig') as csv_file:
            # csv.DictReader tự động lấy hàng đầu tiên làm Key (Tiêu đề cột)
            csv_reader = csv.DictReader(csv_file)
            data = list(csv_reader) # Biến toàn bộ các hàng thành một danh sách (Array)

        # Mở file JSON để ghi
        with open(json_filepath, mode='w', encoding='utf-8') as json_file:
            # json.dump sẽ xuất file đẹp, dễ nhìn với indent=4
            json.dump(data, json_file, ensure_ascii=False, indent=4)
            
        print(f"✅ Đã chuyển đổi thành công: {csv_filepath} -> {json_filepath}")
        
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file: {csv_filepath}. Vui lòng kiểm tra lại tên file.")
    except Exception as e:
        print(f"❌ Lỗi khi chuyển đổi {csv_filepath}: {e}")

# Chạy vòng lặp để xử lý cả 3 file
print("🔄 Bắt đầu nạp nguyên liệu...")
for item in files_to_convert:
    # Lấy đường dẫn hiện tại của thư mục Data
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, item["csv"])
    json_path = os.path.join(current_dir, item["json"])
    
    convert_csv_to_json(csv_path, json_path)

print("🎉 XONG! Dữ liệu đã sẵn sàng cho Frontend.")