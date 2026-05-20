document.addEventListener('DOMContentLoaded', () => {
    // 1. KHỞI TẠO BẢN ĐỒ
    const bangkokBounds = L.latLngBounds(
        [13.3000, 100.1000], // Góc dưới cùng bên trái (Tây Nam)
        [14.3000, 101.0000]  // Góc trên cùng bên phải (Đông Bắc)
    );

    window.map = L.map('map', {
        center: [13.7563, 100.5018], // Trọng tâm Bangkok
        zoom: 12,                    // Mức zoom mặc định
        minZoom: 10,                 // BẮT BUỘC: Không cho phép zoom out quá nhỏ ra ngoài Bangkok
        maxBounds: bangkokBounds,    // Giăng bức tường ảo
        maxBoundsViscosity: 1.0      // Độ "cứng" của bức tường
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(window.map);

    setTimeout(() => { window.map.invalidateSize(); }, 100);

    // --- CÁC BIẾN QUẢN LÝ TÌM ĐƯỜNG & ĐỒNG BỘ ---
    window.startData = null; 
    window.endData = null;   
    let clickMarkers = []; 
    window.globalStops = []; 
    window.activeScenarios = { NODE_OUTAGE: [], EDGE_OUTAGE: [], TRANSFER_ISSUE: {} };
    
    // Lưu trữ các layer để cập nhật Real-time
    window.nodeLayers = {}; 
    window.edgeLayers = {}; 

    // 2. TẢI DỮ LIỆU ĐỒNG THỜI
    Promise.all([
    fetch('../Data/stops_raw.json').then(res => res.json()),
    fetch('../Data/lines_clean.json').then(res => res.json()),
    fetch('../Data/station_line_clean.json').then(res => res.json()),
    // Đổi đường dẫn thành /api/admin/status và chuyển đổi định dạng dữ liệu trả về phù hợp với Frontend
    fetch('http://127.0.0.1:5000/api/admin/status').then(res => res.json()).then(status => ({
        NODE_OUTAGE: status.blocked_nodes || [],
        EDGE_OUTAGE: status.blocked_edges || [],
        TRANSFER_ISSUE: status.transfer_issues || {}
    })).catch(() => ({ NODE_OUTAGE: [], EDGE_OUTAGE: [], TRANSFER_ISSUE: {} }))
]).then(([stopsData, linesData, sequenceData, scenariosData]) => {
        
        window.activeScenarios = scenariosData || { NODE_OUTAGE: [], EDGE_OUTAGE: [], TRANSFER_ISSUE: {} };

        function getVal(obj, possibleNames) {
            if (!obj) return null;
            const keys = Object.keys(obj);
            for (let name of possibleNames) {
                const foundKey = keys.find(k => k.toUpperCase().includes(name.toUpperCase()));
                if (foundKey) return obj[foundKey];
            }
            return null;
        }

        const arrStops = Array.isArray(stopsData) ? stopsData : Object.values(stopsData)[0];
        const arrLines = Array.isArray(linesData) ? linesData : Object.values(linesData)[0];
        const arrSeq = Array.isArray(sequenceData) ? sequenceData : Object.values(sequenceData)[0];

        // Lọc lấy MRT
        const validLines = arrLines.filter(line => ["MRT"].includes(String(getVal(line, ["TYPEE", "TYPE"]) || "").trim().toUpperCase()));
        const validLineIds = validLines.map(line => String(getVal(line, ["LINE_ID", "ID"])).trim()); 
        const validSequences = arrSeq.filter(seq => validLineIds.includes(String(getVal(seq, ["LINE_ID", "LINE"])).trim()));
        const validStationIds = validSequences.map(seq => String(getVal(seq, ["STATION_ID", "STATION"])).trim());
        const validStops = arrStops.filter(stop => validStationIds.includes(String(getVal(stop, ["stop_id", "ID"])).trim()));
        
        window.globalStops = validStops; 

        // --- 3. VẼ TUYẾN CÁP MRT (LƯU VÀO EDGELAYERS) ---
        const linesGroup = {};
        validSequences.forEach(item => {
            const lId = String(getVal(item, ["LINE_ID", "LINE"])).trim();
            if (!linesGroup[lId]) linesGroup[lId] = [];
            linesGroup[lId].push(item);
        });

        for (const lineId in linesGroup) {
            const sortedStations = linesGroup[lineId].sort((a, b) => Number(getVal(a, ["STOP_SEQUENCE", "SEQUENCE"])) - Number(getVal(b, ["STOP_SEQUENCE", "SEQUENCE"])));
            const lineInfo = validLines.find(l => String(getVal(l, ["LINE_ID", "ID"])).trim() === lineId);
            const lineColor = getVal(lineInfo, ["COLOR"]) ? `#${getVal(lineInfo, ["COLOR"])}` : '#333333';

            for (let i = 0; i < sortedStations.length - 1; i++) {
                const stIdA = String(getVal(sortedStations[i], ["STATION_ID", "STATION"])).trim();
                const stIdB = String(getVal(sortedStations[i+1], ["STATION_ID", "STATION"])).trim();
                const stA = validStops.find(s => String(getVal(s, ["stop_id", "ID"])).trim() === stIdA);
                const stB = validStops.find(s => String(getVal(s, ["stop_id", "ID"])).trim() === stIdB);

                if (stA && stB) {
                    const latA = parseFloat(getVal(stA, ["stop_lat", "LAT"]));
                    const lonA = parseFloat(getVal(stA, ["stop_lon", "LON"]));
                    const latB = parseFloat(getVal(stB, ["stop_lat", "LAT"]));
                    const lonB = parseFloat(getVal(stB, ["stop_lon", "LON"]));

                    if (latA && lonA && latB && lonB) {
                        const edgeId1 = `${lineId}_${stIdA}_${stIdB}`;
                        const edgeId2 = `${lineId}_${stIdB}_${stIdA}`;
                        
                        const polyline = L.polyline([[latA, lonA], [latB, lonB]], { 
                            color: lineColor, weight: 5, opacity: 0.8 
                        }).addTo(window.map);

                        // Lưu lại để hàm update sau này gọi
                        window.edgeLayers[edgeId1] = { layer: polyline, color: lineColor };
                    }
                }
            }
        }

        // --- 4. VẼ CÁC TRẠM MRT (LƯU VÀO NODELAYERS) ---
        validStops.forEach(station => {
            const lat = parseFloat(getVal(station, ["stop_lat", "LAT"]));
            const lon = parseFloat(getVal(station, ["stop_lon", "LON"]));
            const stationName = getVal(station, ["stop_name", "NAME"]);
            const stId = String(getVal(station, ["stop_id", "ID"])).trim();

            if (lat && lon) {
                const marker = L.circleMarker([lat, lon], {
                    radius: 4, fillColor: "#ffffff", color: "#000", weight: 2, fillOpacity: 1
                }).bindTooltip(`<b>${stationName}</b>`).addTo(window.map);
                
                // Lưu lại để hàm update sau này gọi
                window.nodeLayers[stId] = { layer: marker, name: stationName };
            }
        });

        // Kích hoạt đồng bộ giao diện ngay sau khi vẽ xong
        syncUI();

        // --- 5. LOGIC CLICK TỰ DO TRÊN BẢN ĐỒ ---
        function getNearestRawStop(clickedLatLng) {
    let nearestStop = null;
    let minDistance = Infinity;
    // Đổi arrStops thành window.globalStops để chỉ bắt các ga MRT hợp lệ
    window.globalStops.forEach(stop => { 
        const lat = parseFloat(getVal(stop, ["stop_lat", "LAT"]));
        const lon = parseFloat(getVal(stop, ["stop_lon", "LON"]));
        if (lat && lon) {
            const distance = window.map.distance(clickedLatLng, L.latLng(lat, lon));
            if (distance < minDistance) { minDistance = distance; nearestStop = stop; }
        }
    });
    return nearestStop;
}

        window.map.on('click', function(e) {
            if (window.startData && window.endData) {
                alert("Đã đủ 2 điểm. Bấm Clear Route bên trái để chọn lại!");
                return;
            }

            const clickLat = e.latlng.lat;
            const clickLon = e.latlng.lng;

            if (!window.startData) {
                window.startData = { lat: clickLat, lng: clickLon }; // Chỉ lưu tọa độ
                
                const startClickPin = L.circleMarker([clickLat, clickLon], { 
                    radius: 6, fillColor: "#10b981", color: "#047857", weight: 2, fillOpacity: 1 
                }).bindTooltip(`<b>🟢 Điểm đi</b>`, { permanent: true, direction: 'top', className: 'mini-tooltip', offset: [0, -5] }).addTo(window.map);
                clickMarkers.push(startClickPin);

                document.getElementById('start-station').value = "Tọa độ đã chọn";
                document.getElementById('route-text').innerText = "Đã chọn điểm đi. Hãy click để chọn điểm đến.";
                
            } else if (!window.endData) {
                window.endData = { lat: clickLat, lng: clickLon }; // Chỉ lưu tọa độ
                
                const endClickPin = L.circleMarker([clickLat, clickLon], { 
                    radius: 6, fillColor: "#ef4444", color: "#b91c1c", weight: 2, fillOpacity: 1 
                }).bindTooltip(`<b>🔴 Điểm đến</b>`, { permanent: true, direction: 'top', className: 'mini-tooltip', offset: [0, -5] }).addTo(window.map);
                clickMarkers.push(endClickPin);

                document.getElementById('end-station').value = "Tọa độ đã chọn";
                document.getElementById('route-text').innerText = "Sẵn sàng! Hãy bấm nút Find Route.";
            }
        });
    });

    // --- 6. LOGIC ĐỒNG BỘ HÓA REAL-TIME (POLLING) ---
    function syncUI() {
        // Sửa lại đường dẫn endpoint cho đúng với app.py công bố
        fetch('http://127.0.0.1:5000/api/admin/status')
            .then(res => res.json())
            .then(status => {
                // Map lại cấu trúc object từ Backend sang Frontend
                window.activeScenarios = {
                    NODE_OUTAGE: status.blocked_nodes || [],
                    EDGE_OUTAGE: status.blocked_edges || [],
                    TRANSFER_ISSUE: status.transfer_issues || {}
                };

                // 6.1. Cập nhật Trạm (Nodes)
                for (const stId in window.nodeLayers) {
                    const { layer, name } = window.nodeLayers[stId];
                    const isClosed = window.activeScenarios.NODE_OUTAGE.includes(stId);
                    const transferSeverity = window.activeScenarios.TRANSFER_ISSUE ? window.activeScenarios.TRANSFER_ISSUE[stId] : null;

                    if (isClosed) {
                        layer.setStyle({ fillColor: "#333333", color: "#ff0000", radius: 6 });
                        layer.setTooltipContent(`<b>⚠️ ĐÓNG CỬA: ${name}</b>`);
                    } else if (transferSeverity) {
                        let tColor = '#f1c40f'; let tRadius = 6; let delayText = '+5 phút';
                        if (transferSeverity === 'heavy') { tColor = '#e67e22'; tRadius = 7; delayText = '+15 phút'; } 
                        else if (transferSeverity === 'extreme') { tColor = '#8e44ad'; tRadius = 8; delayText = '+30 phút'; }
                        layer.setStyle({ fillColor: tColor, color: "#000", radius: tRadius });
                        layer.setTooltipContent(`<b>⚠️ ÙN TẮC (${delayText}): ${name}</b>`);
                    } else {
                        layer.setStyle({ fillColor: "#ffffff", color: "#000", radius: 4 });
                        layer.setTooltipContent(`<b>${name}</b>`);
                    }
                }

                // 6.2. Cập nhật Tuyến (Edges)
                for (const edgeId in window.edgeLayers) {
                    const { layer, color } = window.edgeLayers[edgeId];
                    const parts = edgeId.split('_'); // parts = [LineId, Trạm A, Trạm B]
                    
                    // Tạo lại chuỗi format giống hệt Backend trả về (Chỉ có IDTrạmA_IDTrạmB)
                    const backendEdge1 = `${parts[1]}_${parts[2]}`;
                    const backendEdge2 = `${parts[2]}_${parts[1]}`;
                    
                    // So sánh với mảng EDGE_OUTAGE
                    const isBlocked = window.activeScenarios.EDGE_OUTAGE.includes(backendEdge1) || window.activeScenarios.EDGE_OUTAGE.includes(backendEdge2);

                    if (isBlocked) {
                        layer.setStyle({ color: "#ff0000", weight: 6, dashArray: '10, 10' });
                        layer.bindTooltip(`<b>⚠️ ĐOẠN RAY BỊ CHẶN</b>`);
                    } else {
                        layer.setStyle({ color: color, weight: 5, dashArray: null });
                        layer.unbindTooltip();
                    }
                }
            }).catch(err => console.log("Đang chờ Backend kết nối..."));
    }

    // Tự động gọi hàm syncUI mỗi 3 giây
    setInterval(syncUI, 3000);

    // --- 7. LOGIC NÚT CLEAR BẢN ĐỒ USER ---
    document.getElementById('clear-btn').addEventListener('click', () => {
        clickMarkers.forEach(m => window.map.removeLayer(m));
        clickMarkers = [];
        window.startData = null; window.endData = null;
        document.getElementById('start-station').value = "";
        document.getElementById('end-station').value = "";
        document.getElementById('route-text').innerText = "Select two stations on the map to find route.";
        if (window.currentRouteLine) { window.map.removeLayer(window.currentRouteLine); window.currentRouteLine = null; }
    });
});