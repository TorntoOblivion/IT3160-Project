// Biến toàn cục để lưu trữ đường nét đứt (Polyline) kết quả tìm đường
let currentRouteLine = null;

document.addEventListener('DOMContentLoaded', () => {
    const findRouteBtn = document.getElementById('find-route-btn');
    const routeText = document.getElementById('route-text');
    const clearBtn = document.getElementById('clear-btn');

    // --- 1. LẮNG NGHE NÚT TÌM ĐƯỜNG ---
    findRouteBtn.addEventListener('click', async () => {
        if (!window.startData || !window.endData) {
            alert("Vui lòng click chọn điểm đi và điểm đến trên bản đồ!");
            return;
        }

        const startId = String(window.startData.stop_id || window.startData.ID).trim();
        const endId = String(window.endData.stop_id || window.endData.ID).trim();

        routeText.innerHTML = "<span style='color: #2563eb; font-weight: bold;'>Đang tính toán hành trình tối ưu...</span>";
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
                throw new Error(resultData.message || "Máy chủ AI từ chối trả lời");
            }
            
            // --- XÂY DỰNG BẢNG HƯỚNG DẪN DI CHUYỂN (ITINERARY) ---
            let itineraryHtml = '';
            if (resultData.itinerary && resultData.itinerary.length > 0) {
                itineraryHtml = `
                    <table style="width: 100%; margin-top: 15px; border-collapse: collapse; font-size: 0.9em; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                        <thead style="background: #f8fafc; border-bottom: 2px solid #e2e8f0;">
                            <tr>
                                <th style="padding: 10px; text-align: left; color: #64748b;">Cách đi</th>
                                <th style="padding: 10px; text-align: left; color: #64748b;">Chi tiết chặng</th>
                            </tr>
                        </thead>
                        <tbody>
                `;

                resultData.itinerary.forEach(step => {
                    itineraryHtml += `
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 12px 10px; font-weight: bold; color: #334155; white-space: nowrap;">
                                ${step.icon} ${step.mode}
                            </td>
                            <td style="padding: 12px 10px; color: #475569;">
                                Từ <b>${step.from}</b><br>
                                đến <b>${step.to}</b>
                            </td>
                        </tr>
                    `;
                });

                itineraryHtml += `</tbody></table>`;
            }

            // --- CẬP NHẬT THÔNG TIN RA SIDEBAR (CÓ THANH CUỘN) ---
            routeText.innerHTML = `
                <div style="margin-top: 10px; padding: 15px; background: #f0fdf4; border-radius: 10px; border: 1px solid #dcfce7; max-height: 400px; overflow-y: auto;">
                    <strong style="color: #166534; font-size: 1.1em;">📍 Lộ trình đề xuất:</strong><br>
                    <div style="margin: 10px 0; display: flex; justify-content: space-between; font-size: 1.1em;">
                        <span style="color: #047857;">📏 <b>${resultData.distance} km</b></span>
                        <span style="color: #ea580c;">⏱ <b>${resultData.estimated_time} phút</b></span>
                    </div>
                    ${itineraryHtml}
                </div>
            `;

            // 👉 NGUỒN GỐC LỖI Ở ĐÂY: Gọi đúng biến path_details chứa tọa độ
            drawRouteOnMap(resultData.path_details);

        } catch (error) {
            console.error("Lỗi:", error);
            routeText.innerHTML = `<span style="color: red; font-weight: bold;">Lỗi: ${error.message}</span>`;
        } finally {
            findRouteBtn.disabled = false;
            findRouteBtn.innerText = "Find Route";
        }
    });

    // --- 2. HÀM XÓA ĐƯỜNG VẼ CHO NÚT CLEAR ---
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (currentRouteLine && window.map) {
                window.map.removeLayer(currentRouteLine);
                currentRouteLine = null;
            }
        });
    }
});

// --- 3. HÀM VẼ ĐƯỜNG ĐA PHƯƠNG THỨC LÊN BẢN ĐỒ ---
function drawRouteOnMap(pathDetails) {
    if (currentRouteLine && window.map) {
        window.map.removeLayer(currentRouteLine);
    }

    currentRouteLine = L.featureGroup().addTo(window.map);

    // Kiểm tra an toàn dữ liệu
    if (!pathDetails || !Array.isArray(pathDetails)) {
        console.error("Lỗi: Dữ liệu path_details không hợp lệ!");
        return;
    }

    pathDetails.forEach(segment => {
        // Lấy tọa độ trực tiếp từ Backend gửi sang
        const latA = segment.latA;
        const lonA = segment.lonA;
        const latB = segment.latB;
        const lonB = segment.lonB;

        // Đảm bảo tọa độ có tồn tại trước khi vẽ
        if (latA !== undefined && lonA !== undefined && latB !== undefined && lonB !== undefined) {
            if (segment.type === 'walk') {
                // 🚶 ĐI BỘ: Màu xám đen, nét đứt
                L.polyline([[latA, lonA], [latB, lonB]], {
                    color: '#475569',    
                    weight: 5,           
                    dashArray: '6, 8', 
                    opacity: 0.9,
                    lineJoin: 'round'
                }).addTo(currentRouteLine);
            } else {
                // 🚇 ĐI TÀU: Màu cam, nét liền
                L.polyline([[latA, lonA], [latB, lonB]], {
                    color: '#f97316',    
                    weight: 7,
                    opacity: 1,
                    lineJoin: 'round'
                }).addTo(currentRouteLine);
            }
        }
    });

    if (currentRouteLine.getLayers().length > 0 && window.map) {
        window.map.fitBounds(currentRouteLine.getBounds(), { padding: [50, 50] });
    }
}