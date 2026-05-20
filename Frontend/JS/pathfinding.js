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

        const startLat = window.startData.lat;
        const startLon = window.startData.lng;
        const endLat = window.endData.lat;
        const endLon = window.endData.lng;

        routeText.innerHTML = "<span style='color: #2563eb; font-weight: bold;'>Đang tính toán hành trình tối ưu...</span>";
        findRouteBtn.disabled = true;
        findRouteBtn.innerText = "Calculating...";

        try {
            const response = await fetch('http://127.0.0.1:5000/api/find_route', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    start_lat: startLat, 
                    start_lng: startLon, 
                    end_lat: endLat, 
                    end_lng: endLon 
                }) // Đã đổi sang truyền Tọa độ
            });

            const resultData = await response.json();
            
            if (!response.ok) {
                
                throw new Error(resultData.error || resultData.message || "Máy chủ AI từ chối trả lời");
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
            drawRouteOnMap(resultData.path_details, resultData.path);

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

// --- HÀM PHỤ: Tìm tên trạm tàu từ tọa độ (để gắn nhãn cho đẹp) ---
function getStationNameByCoords(lat, lon) {
    if (!window.nodeLayers) return "Trạm tàu";
    for (const stId in window.nodeLayers) {
        const layer = window.nodeLayers[stId].layer;
        const stLatLng = layer.getLatLng();
        // Kiểm tra tọa độ trùng khớp (với sai số cực nhỏ do sai số float)
        if (Math.abs(stLatLng.lat - lat) < 0.0001 && Math.abs(stLatLng.lng - lon) < 0.0001) {
            return window.nodeLayers[stId].name;
        }
    }
    return "Trạm tàu";
}

// --- 3. HÀM VẼ ĐƯỜNG ĐA PHƯƠNG THỨC LÊN BẢN ĐỒ ---
function drawRouteOnMap(pathDetails, pathIds) {
    if (currentRouteLine && window.map) {
        window.map.removeLayer(currentRouteLine);
    }

    currentRouteLine = L.featureGroup().addTo(window.map);

    if (!pathDetails || !Array.isArray(pathDetails) || pathDetails.length === 0) {
        console.error("Lỗi: Dữ liệu lộ trình không hợp lệ!");
        return;
    }

    let prevType = null; // Biến ghi nhớ trạng thái (Đang đi bộ hay đang đi tàu)

    pathDetails.forEach((segment, index) => {
        const latA = segment.latA;
        const lonA = segment.lonA;
        const latB = segment.latB;
        const lonB = segment.lonB;

        if (latA !== undefined && lonA !== undefined && latB !== undefined && lonB !== undefined) {
            
            // -----------------------------------------------------------
            // A. VẼ ĐƯỜNG (POLYLINE) CÓ NÉT ĐỨT CHO PHẦN ĐI BỘ
            // -----------------------------------------------------------
            if (segment.type === 'walk' || segment.type === 'transfer') {
                // 🚶 ĐI BỘ / TRUNG CHUYỂN: Màu xám đen, vẽ bằng NÉT ĐỨT ('8, 8')
                L.polyline([[latA, lonA], [latB, lonB]], {
                    color: '#475569',    
                    weight: 5,           
                    dashArray: '8, 8', // Nét đứt rõ ràng (8px dash, 8px gap)
                    opacity: 0.9,
                    lineJoin: 'round'
                }).addTo(currentRouteLine);
            } else if (segment.type === 'rail') {
                // 🚇 ĐI TÀU: Màu cam, NÉT LIỀN
                L.polyline([[latA, lonA], [latB, lonB]], {
                    color: '#f97316',    
                    weight: 7,
                    opacity: 1,
                    lineJoin: 'round'
                }).addTo(currentRouteLine);
            }

            // -----------------------------------------------------------
            // B. NHẬN DIỆN CÁC ĐIỂM LÊN/XUỐNG TÀU & TRUNG CHUYỂN
            // -----------------------------------------------------------
            
            // 1. NHẬN DIỆN GA LÊN TÀU (Trạng thái trước đó không phải Rail -> Giờ là Rail)
            if (prevType !== 'rail' && segment.type === 'rail') {
                const stName = getStationNameByCoords(latA, lonA);
                let label = prevType === 'transfer' ? `Chuyển tàu tại: ${stName}` : `Lên tàu: ${stName}`;
                
                L.circleMarker([latA, lonA], {
                    radius: 7, fillColor: "#10b981", color: "#047857", weight: 3, fillOpacity: 1
                }).bindTooltip(`<b>🟢 ${label}</b>`, { permanent: false, direction: 'top', className: 'mini-tooltip', offset: [0, -5] })
                  .addTo(currentRouteLine);
            }

            // 2. NHẬN DIỆN GA XUỐNG TÀU (Trạng thái trước đó là Rail -> Giờ chuyển sang Walk/Transfer)
            if (prevType === 'rail' && segment.type !== 'rail') {
                const stName = getStationNameByCoords(latA, lonA); // Vị trí A của đoạn đi bộ này chính là điểm xuống tàu
                let label = segment.type === 'transfer' ? `Đổi tàu tại: ${stName}` : `Xuống tàu: ${stName}`;
                
                L.circleMarker([latA, lonA], {
                    radius: 7, fillColor: "#ef4444", color: "#b91c1c", weight: 3, fillOpacity: 1
                }).bindTooltip(`<b>🔴 ${label}</b>`, { permanent: false, direction: 'top', className: 'mini-tooltip', offset: [0, -5] })
                  .addTo(currentRouteLine);
            }
            
            // 3. CHỐT CHẶN (Nếu chặng cuối cùng của cả hành trình vẫn là đi tàu)
            if (index === pathDetails.length - 1 && segment.type === 'rail') {
                const stName = getStationNameByCoords(latB, lonB);
                L.circleMarker([latB, lonB], {
                    radius: 7, fillColor: "#ef4444", color: "#b91c1c", weight: 3, fillOpacity: 1
                }).bindTooltip(`<b>🔴 Đích: ${stName}</b>`, { permanent: true, direction: 'top', className: 'mini-tooltip', offset: [0, -5] })
                  .addTo(currentRouteLine);
            }
        }
        
        // Cập nhật trạng thái để đối chiếu cho vòng lặp tiếp theo
        prevType = segment.type;
    });

    // Căn chỉnh màn hình vừa vặn với toàn bộ lộ trình
    if (currentRouteLine.getLayers().length > 0 && window.map) {
        window.map.fitBounds(currentRouteLine.getBounds(), { padding: [50, 50] });
    }
}