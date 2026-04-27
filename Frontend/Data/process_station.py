import pandas as pd

print("1. Đang đọc danh sách các tuyến Metro...")
# Đọc file lines_clean của bạn để lấy LINE_ID
lines = pd.read_csv('lines_clean.csv')
valid_line_ids = lines['LINE_ID'].astype(str).tolist()

print("2. Đang phân tích file trips.txt...")
# Đọc trips.txt
trips = pd.read_csv('trips.txt', dtype=str)

# Chỉ lấy các chuyến đi thuộc các tuyến Metro của chúng ta
metro_trips = trips[trips['route_id'].isin(valid_line_ids)]

# Một tuyến có chiều đi (0) và chiều về (1). Ta chỉ cần lấy 1 chiều đi đại diện để bóc thứ tự trạm
representative_trips = metro_trips[metro_trips['direction_id'] == '0'].drop_duplicates(subset=['route_id'])

# Tạo một "từ điển" để map từ trip_id sang LINE_ID
trip_to_line = dict(zip(representative_trips['trip_id'], representative_trips['route_id']))
valid_trip_ids = list(trip_to_line.keys())

print("3. Đang quét file khổng lồ stop_times.txt (có thể mất vài giây)...")
# Chỉ đọc 3 cột cần thiết để tiết kiệm RAM cho máy tính
stop_times = pd.read_csv('stop_times.txt', dtype=str, usecols=['trip_id', 'stop_id', 'stop_sequence'])

# Lọc: Chỉ lấy các trạm thuộc những chuyến đi đại diện ở trên
station_line = stop_times[stop_times['trip_id'].isin(valid_trip_ids)].copy()

# Ghép LINE_ID vào dựa trên trip_id
station_line['LINE_ID'] = station_line['trip_id'].map(trip_to_line)

# Đổi tên cột cho chuẩn với MySQL của bạn
station_line.rename(columns={'stop_id': 'STATION_ID', 'stop_sequence': 'STOP_SEQUENCE'}, inplace=True)

# Sắp xếp lại cho đẹp mắt (Theo Tuyến, rồi theo Thứ tự trạm)
final_df = station_line[['STATION_ID', 'LINE_ID', 'STOP_SEQUENCE']]
final_df['STOP_SEQUENCE'] = final_df['STOP_SEQUENCE'].astype(int)
final_df = final_df.sort_values(by=['LINE_ID', 'STOP_SEQUENCE'])

# Lưu thành file CSV mới
final_df.to_csv('station_line_clean.csv', index=False)
print("-> THÀNH CÔNG! Đã xuất ra file station_line_clean.csv")