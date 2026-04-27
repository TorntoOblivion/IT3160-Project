document.addEventListener('DOMContentLoaded', () => {
    // Khởi tạo bản đồ
    window.map = L.map('map').setView([13.7563, 100.5018], 12);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(window.map);

    setTimeout(() => { window.map.invalidateSize(); }, 100);

    // --- CÁC BIẾN QUẢN LÝ ---
    window.startData = null; 
    window.endData = null;   
    let clickMarkers = []; // Mảng lưu các pin cắm xuống bản đồ
    window.globalStops = []; 

    // Load MRT stations từ backend (đã mapping đúng STATION_ID)
    fetch('http://127.0.0.1:5000/api/stations')
        .then(res => res.json())
        .then(mrtStations => {
            window.globalStops = mrtStations;
            initializeMap(mrtStations);
        })
        .catch(err => console.error("Error loading stations:", err));

    function initializeMap(mrtStations) {
        // Load lines & sequences từ local data
        Promise.all([
            fetch('../Data/lines_clean.json').then(res => res.json()),
            fetch('../Data/station_line_clean.json').then(res => res.json())
        ]).then(([linesData, sequenceData]) => {
            
            function getVal(obj, possibleNames) {
                if (!obj) return null;
                const keys = Object.keys(obj);
                for (let name of possibleNames) {
                    const foundKey = keys.find(k => k.toUpperCase().includes(name.toUpperCase()));
                    if (foundKey) return obj[foundKey];
                }
                return null;
            }

            const arrLines = Array.isArray(linesData) ? linesData : Object.values(linesData)[0];
            const arrSeq = Array.isArray(sequenceData) ? sequenceData : Object.values(sequenceData)[0];

            // Lọc dữ liệu để VẼ ĐƯỜNG RAY MRT
            const validLines = arrLines.filter(line => {
                const type = String(getVal(line, ["TYPEE", "TYPE"]) || "").trim().toUpperCase();
                return ["MRT"].includes(type);
            });
            const validLineIds = validLines.map(line => String(getVal(line, ["LINE_ID", "ID"])).trim()); 

            const validSequences = arrSeq.filter(seq => {
                const seqLineId = String(getVal(seq, ["LINE_ID", "LINE"])).trim();
                return validLineIds.includes(seqLineId);
            }); 


            // --- VẼ TUYẾN CÁP MRT ---
            const linesGroup = {};
            validSequences.forEach(item => {
                const lId = String(getVal(item, ["LINE_ID", "LINE"])).trim();
                if (!linesGroup[lId]) linesGroup[lId] = [];
                linesGroup[lId].push(item);
            });

            for (const lineId in linesGroup) {
                const sortedStations = linesGroup[lineId].sort((a, b) => {
                    return Number(getVal(a, ["STOP_SEQUENCE", "SEQUENCE"])) - Number(getVal(b, ["STOP_SEQUENCE", "SEQUENCE"]));
                });
                
                const lineInfo = validLines.find(l => String(getVal(l, ["LINE_ID", "ID"])).trim() === lineId);
                const colorValue = getVal(lineInfo, ["COLOR"]);
                const lineColor = colorValue ? `#${colorValue}` : '#333333';

                const pathCoords = [];
                sortedStations.forEach(seq => {
                    const stId = String(getVal(seq, ["STATION_ID", "STATION"])).trim();
                    const station = mrtStations.find(s => String(s.stop_id).trim() === stId);
                    if (station) {
                        const lat = parseFloat(station.stop_lat);
                        const lon = parseFloat(station.stop_lon);
                        if (lat && lon) pathCoords.push([lat, lon]);
                    }
                });

                if (pathCoords.length > 0) {
                    L.polyline(pathCoords, { color: lineColor, weight: 5, opacity: 0.8 }).addTo(window.map);
                }
            }

            // --- VẼ CÁC TRẠM MRT ---
            mrtStations.forEach(station => {
                const lat = parseFloat(station.stop_lat);
                const lon = parseFloat(station.stop_lon);
                const stationName = station.stop_name;

                if (lat && lon) {
                    L.circleMarker([lat, lon], {
                        radius: 4, fillColor: "#ffffff", color: "#000000", weight: 2, fillOpacity: 1
                    }).bindTooltip(`<b>${stationName}</b>`).addTo(window.map);
                }
            });

            // --- HÀM TÌM TRẠM MRT GẦN NHẤT ---
            function getNearestMRTStop(clickedLatLng) {
                let nearestStop = null;
                let minDistance = Infinity;

                mrtStations.forEach(stop => {
                    const lat = parseFloat(stop.stop_lat);
                    const lon = parseFloat(stop.stop_lon);
                    
                    if (lat && lon) {
                        const stopLatLng = L.latLng(lat, lon);
                        const distance = window.map.distance(clickedLatLng, stopLatLng);

                        if (distance < minDistance) {
                            minDistance = distance;
                            nearestStop = stop;
                        }
                    }
                });
                return nearestStop;
            }

        // --- BẮT SỰ KIỆN CLICK LÊN BẢN ĐỒ ---
        window.map.on('click', function(e) {
            if (window.startData && window.endData) {
                alert("Đã đủ 2 điểm. Bấm Clear Route bên trái để chọn lại!");
                return;
            }

            const clickedLatLng = e.latlng;
            
            // Tìm trạm MRT gần nhất
            const nearestStop = getNearestMRTStop(clickedLatLng);
            
            if (!nearestStop) return;

            const stopName = nearestStop.stop_name;
            const stopLat = parseFloat(nearestStop.stop_lat);
            const stopLon = parseFloat(nearestStop.stop_lon);

            // 1. CHỌN ĐIỂM ĐI
            if (!window.startData) {
                window.startData = nearestStop;
                
                // Vẽ Pin xanh lá tại vị trí của điểm dừng vừa tìm được
                const startPin = L.circleMarker([stopLat, stopLon], { 
                    radius: 6, fillColor: "#10b981", color: "#047857", weight: 2, fillOpacity: 1 
                }).bindTooltip(`<b>Bắt đầu: ${stopName}</b>`, { permanent: true, direction: 'right' }).addTo(window.map);
                
                clickMarkers.push(startPin);
                
                document.getElementById('start-station').value = stopName;
                document.getElementById('route-text').innerText = "Đã chọn điểm đi. Hãy click để chọn điểm đến.";
            } 
            // 2. CHỌN ĐIỂM ĐẾN
            else if (!window.endData) {
                window.endData = nearestStop;
                
                // Vẽ Pin đỏ tại vị trí của điểm dừng vừa tìm được
                const endPin = L.circleMarker([stopLat, stopLon], { 
                    radius: 6, fillColor: "#ef4444", color: "#b91c1c", weight: 2, fillOpacity: 1 
                }).bindTooltip(`<b>Kết thúc: ${stopName}</b>`, { permanent: true, direction: 'right' }).addTo(window.map);
                
                clickMarkers.push(endPin);

                document.getElementById('end-station').value = stopName;
                document.getElementById('route-text').innerText = "Sẵn sàng! Hãy bấm nút Find Route.";
            }
        });

        });  // Closes Promise.all
    }  // Closes initializeMap

    // --- LOGIC NÚT CLEAR ---
    document.getElementById('clear-btn').addEventListener('click', () => {
        // Xóa các pin
        clickMarkers.forEach(m => window.map.removeLayer(m));
        clickMarkers = [];
        
        window.startData = null;
        window.endData = null;
        
        document.getElementById('start-station').value = "";
        document.getElementById('end-station').value = "";
        document.getElementById('route-text').innerText = "Select two stations on the map to find route.";

        if (window.currentRouteLine) {
            window.map.removeLayer(window.currentRouteLine);
            window.currentRouteLine = null;
        }
    });
});