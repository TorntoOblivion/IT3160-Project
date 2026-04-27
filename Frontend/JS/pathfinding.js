// Biến toàn cục để lưu trữ đường nét đứt (Polyline) trên bản đồ
let currentRouteLine = null;

document.addEventListener('DOMContentLoaded', () => {
    const findRouteBtn = document.getElementById('find-route-btn');
    const routeText = document.getElementById('route-text');
    const clearBtn = document.getElementById('clear-btn');

    // --- 1. LẮNG NGHE NÚT TÌM ĐƯỜNG ---
    findRouteBtn.addEventListener('click', async () => {
        // 👉 SỬA LỖI 1: Đổi thành startData và endData cho khớp với map.js
        if (!window.startData || !window.endData) {
            alert("Vui lòng click chọn điểm đi và điểm đến trên bản đồ!");
            return;
        }

        // Lấy ID trạm từ 2 biến mới
        const startId = String(window.startData.stop_id || window.startData.ID).trim();
        const endId = String(window.endData.stop_id || window.endData.ID).trim();

        routeText.innerText = "Đang nhờ AI tìm đường ngắn nhất...";
        findRouteBtn.disabled = true;
        findRouteBtn.innerText = "Calculating...";

        try {
            const response = await fetch('http://127.0.0.1:5000/api/find_route', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ start: startId, end: endId })
            });

            const resultData = await response.json();
            
            if (!response.ok) {
                throw new Error(resultData.error || "Máy chủ AI từ chối trả lời");
            }
            
            // Cập nhật thông tin ra Sidebar
            routeText.innerHTML = `
                <div style="margin-top: 10px; padding: 10px; background: #fff7ed; border-radius: 8px; border: 1px solid #ffedd5;">
                    <strong style="color: #c2410c;">📍 Kết quả tìm đường:</strong><br>
                    • <b>Từ:</b> ${resultData.start}<br>
                    • <b>Đến:</b> ${resultData.end}<br>
                    • <b>Số trạm:</b> ${resultData.path.length} trạm<br>
                    • <b>Quãng đường:</b> ${resultData.distance} km<br>
                    • <b>Dự kiến:</b> <span style="font-size: 1.2em; color: #ea580c;">${resultData.estimated_time} phút</span>
                </div>
            `;

            // Gọi hàm vẽ đường đi chi tiết lên bản đồ
            drawRouteOnMap(resultData.path);

        } catch (error) {
            console.error("Lỗi:", error);
            routeText.innerText = "Lỗi: " + error.message;
        } finally {
            findRouteBtn.disabled = false;
            findRouteBtn.innerText = "Find Route";
        }
    });

    // --- 2. BỔ SUNG LỆNH XÓA ĐƯỜNG VẼ CHO NÚT CLEAR ---
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (currentRouteLine) {
                // 👉 SỬA LỖI 2: Dùng window.map thay vì map
                window.map.removeLayer(currentRouteLine);
                currentRouteLine = null;
            }
        });
    }
});

// --- 3. HÀM VẼ ĐƯỜNG (CORE UI LOGIC) ---
function drawRouteOnMap(pathNodeIds) {
    if (currentRouteLine) {
        // 👉 Dùng window.map
        window.map.removeLayer(currentRouteLine);
    }

    const routeCoords = [];
    
    pathNodeIds.forEach(nodeId => {
        const station = window.globalStops.find(s => {
            const sId = String(s.stop_id || s.ID).trim();
            return sId === String(nodeId).trim();
        });

        if (station) {
            const lat = parseFloat(station.stop_lat || station.LAT);
            const lon = parseFloat(station.stop_lon || station.LON);
            if (!isNaN(lat) && !isNaN(lon)) {
                routeCoords.push([lat, lon]);
            }
        }
    });

    if (routeCoords.length > 0) {
        // 👉 Dùng window.map
        currentRouteLine = L.polyline(routeCoords, {
            color: '#f97316',    
            weight: 6,           
            dashArray: '10, 10', 
            opacity: 0.9,
            lineJoin: 'round'    
        }).addTo(window.map);

        // 👉 Dùng window.map
        window.map.fitBounds(currentRouteLine.getBounds(), { padding: [50, 50] });
    }
}