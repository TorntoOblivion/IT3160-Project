
ALTER TABLE STATIONS 
MODIFY LATITUDE DECIMAL(12, 8),
MODIFY LONGITUDE DECIMAL(12, 8);

-- Bước 2: Làm sạch bảng STATIONS
TRUNCATE TABLE STATIONS;

-- Bước 3: Bơm dữ liệu từ stops_raw sang STATIONS
INSERT INTO STATIONS (STATION_ID, STATION_NAME, LATITUDE, LONGITUDE, COORDINATES)
SELECT 
stop_id, 
-- Cắt bỏ tiếng Thái (phần trước dấu ;), chỉ lấy tên tiếng Anh
TRIM(SUBSTRING_INDEX(stop_name, ';', -1)) AS STATION_NAME,
stop_lat, 
stop_lon, 
-- Ép kiểu tọa độ sang POINT chuẩn SRID 4326
ST_GeomFromText(CONCAT('POINT(', stop_lat, ' ', stop_lon, ')'), 4326)
FROM stops_raw;

DROP TABLE stops_raw;


CREATE TEMPORARY TABLE lines_raw (
    line_id VARCHAR(30),
    line_name VARCHAR(255),
    color VARCHAR(20),
    typee VARCHAR(30)
);

-- 2. Nạp dữ liệu vào bảng tạm
LOAD DATA LOCAL INFILE 'C:/Users/Son/Desktop/Intro AI/lines_clean.csv'
INTO TABLE lines_raw
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

-- 3. Bơm dữ liệu từ bảng tạm sang bảng LINE chính thức, đồng thời xóa tiếng Thái
TRUNCATE TABLE LINE;

INSERT INTO LINE (LINE_ID, LINE_NAME, COLOR, TYPEE)
SELECT 
line_id, 
-- Cắt phần tiếng Thái (trước dấu ;), chỉ lấy tên tiếng Anh
TRIM(SUBSTRING_INDEX(line_name, ';', -1)) AS LINE_NAME,
color, 
typee
FROM lines_raw;

DROP TEMPORARY TABLE lines_raw;


-- 3 nap du lieu vao bang station_line
TRUNCATE TABLE STATION_LINE;

LOAD DATA LOCAL INFILE 'C:/Users/Son/Desktop/DATA_AI/station_line_clean.csv'
INTO TABLE STATION_LINE
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;