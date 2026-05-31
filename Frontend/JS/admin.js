// 1. KHỞI TẠO BẢN ĐỒ (Đã thêm giới hạn Bangkok)
const bangkokBounds = L.latLngBounds(
    [13.3000, 100.1000], // Góc dưới cùng bên trái (Tây Nam)
    [14.3000, 101.0000]  // Góc trên cùng bên phải (Đông Bắc)
);

var map = L.map('map', {
    center: [13.7563, 100.5018], // Trọng tâm Bangkok
    zoom: 12,                    // Mức zoom mặc định
    minZoom: 10,                 // Không cho phép zoom out quá nhỏ ra ngoài Bangkok
    maxBounds: bangkokBounds,    // Giăng bức tường ảo
    maxBoundsViscosity: 1.0      // Độ cứng của bức tường
});

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 20
}).addTo(map);

// Mẹo chống lỗi hiển thị với Flexbox khi load trang
setTimeout(() => { map.invalidateSize(); }, 100);

// Biến quản lý trạng thái Admin
let currentMode = null; 
let currentSeverity = null; // Biến lưu mức độ hiện tại: 'light', 'heavy', 'extreme'
let blockedNodes = [];
let blockedEdges = []; 

// Dùng Object {} thay vì Array [] để lưu cả ID trạm LẪN mức độ lỗi
let transferIssues = {};

// Khai báo các thành phần UI
const btnOk = document.getElementById('btn-confirm-ok');
const statusMsg = document.getElementById('status-msg');

// 2. LOGIC NÚT BẤM SIDEBAR VÀ HIỆU ỨNG GIAO DIỆN

// Khai báo danh sách ID của tất cả các nút kịch bản
const allScenarioBtns = [
    'btn-node-outage', 'btn-edge-outage', 
    'btn-transfer-light', 'btn-transfer-heavy', 'btn-transfer-extreme'
];

// Hàm làm nổi bật nút đang được chọn, reset các nút khác
function highlightButton(activeId, borderColor, bgColor) {
    // Bước 1: Trả tất cả các nút về trạng thái bình thường
    allScenarioBtns.forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.style.border = "1px solid #dee2e6"; // Viền xám nhạt mặc định
            btn.style.backgroundColor = "#ffffff";  // Nền trắng
            btn.style.transform = "scale(1)";       // Kích thước chuẩn
            btn.style.boxShadow = "none";
            btn.style.fontWeight = "normal";
        }
    });

    // Bước 2: Nhấn mạnh nút đang được click
    if (activeId) {
        const activeBtn = document.getElementById(activeId);
        if (activeBtn) {
            activeBtn.style.border = `2px solid ${borderColor}`; // Đổi màu viền
            activeBtn.style.backgroundColor = bgColor;           // Đổi màu nền
            activeBtn.style.transform = "scale(1.02)";           // Phóng to nhẹ 2%
            activeBtn.style.boxShadow = "0 4px 6px rgba(0,0,0,0.1)"; // Đổ bóng
            activeBtn.style.fontWeight = "bold";                 // In đậm chữ
        }
    }
}

document.getElementById('btn-node-outage').onclick = () => {
    currentMode = 'NODE';
    statusMsg.innerText = "Chế độ ĐÓNG TRẠM: Click vào các trạm (chấm tròn) trên bản đồ.";
    statusMsg.style.color = "blue";
    btnOk.style.display = 'inline-block';
    
    // Đổi màu nút Node: Viền xanh, nền xanh nhạt
    highlightButton('btn-node-outage', 'blue', '#e6f2ff'); 
};

document.getElementById('btn-edge-outage').onclick = () => {
    currentMode = 'EDGE';
    statusMsg.innerText = "Chế độ CHẶN RAY: Click vào đường nối giữa 2 trạm.";
    statusMsg.style.color = "#d35400"; 
    btnOk.style.display = 'inline-block';
    
    // Đổi màu nút Edge: Viền cam đậm, nền cam nhạt
    highlightButton('btn-edge-outage', '#d35400', '#fdebd0');
};

// Cập nhật hàm setTransferMode để nhận thêm thông số ID nút bấm và Màu nền
function setTransferMode(severity, color, bgColor, text, btnId) {
    currentMode = 'TRANSFER';
    currentSeverity = severity;
    statusMsg.innerText = `Chế độ LỖI ${text}: Click trạm để áp dụng.`;
    statusMsg.style.color = color;
    btnOk.style.display = 'inline-block';
    
    // Highlight nút vừa bấm
    highlightButton(btnId, color, bgColor);
}

document.getElementById('btn-transfer-light').onclick = () => setTransferMode('light', '#f1c40f', '#fcf3cf', 'NHẸ (Vàng)', 'btn-transfer-light');
document.getElementById('btn-transfer-heavy').onclick = () => setTransferMode('heavy', '#e67e22', '#fae5d3', 'NẶNG (Cam)', 'btn-transfer-heavy');
document.getElementById('btn-transfer-extreme').onclick = () => setTransferMode('extreme', '#8e44ad', '#f4ecf7', 'NGHIÊM TRỌNG (Tím)', 'btn-transfer-extreme');

document.getElementById('btn-clear-all').onclick = () => {
    if (confirm("Bạn có chắc chắn muốn xóa toàn bộ kịch bản và mở lại toàn bộ hệ thống?")) {
        fetch('http://127.0.0.1:5000/api/admin/clear', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                alert("Hệ thống đã được khôi phục trạng thái bình thường!");
                location.reload(); 
            })
            .catch(err => console.error("Lỗi khi xóa kịch bản:", err));
    }
};



// 3. TẢI DỮ LIỆU VÀ VẼ BẢN ĐỒ
// 3. TẢI DỮ LIỆU VÀ VẼ BẢN ĐỒ (Đã bổ sung đồng bộ trạng thái cũ khi reload)
Promise.all([
    fetch('../data/stops_raw.json').then(res => res.json()), 
    fetch('../data/lines_clean.json').then(res => res.json()),
    fetch('../data/station_line_clean.json').then(res => res.json()),
    // Gọi thêm API để lấy các kịch bản đang chạy trên Backend
    fetch('http://127.0.0.1:5000/api/admin/status').then(res => res.json()).catch(() => ({ blocked_nodes: [], blocked_edges: [], transfer_issues: {} }))
]).then(([stopsData, linesData, sequenceData, statusData]) => {

    // Nạp lại dữ liệu cũ từ server vào các biến toàn cục để không bị mất khi reload trang
    blockedNodes = statusData.blocked_nodes || [];
    transferIssues = statusData.transfer_issues || {};

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

    // === BƯỚC 1: LỌC DỮ LIỆU ===
    const validLines = arrLines.filter(line => {
        const type = String(getVal(line, ["TYPEE", "TYPE"]) || "").trim().toUpperCase();
        return type === "MRT"; 
    });
    
    const validLineIds = validLines.map(line => String(getVal(line, ["LINE_ID", "ID"])).trim()); 
    const validSequences = arrSeq.filter(seq => validLineIds.includes(String(getVal(seq, ["LINE_ID", "LINE"])).trim()));
    const validStationIds = validSequences.map(seq => String(getVal(seq, ["STATION_ID", "STATION"])).trim());
    const validStops = arrStops.filter(stop => validStationIds.includes(String(getVal(stop, ["stop_id", "ID"])).trim()));


    // === BƯỚC 2: VẼ ĐƯỜNG RAY (EDGES) TỪNG ĐOẠN & LOGIC CLICK ===
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
        const rawColor = getVal(lineInfo, ["COLOR"]);
        const lineColor = rawColor ? `#${String(rawColor).trim().replace('#', '')}` : '#333333';

        // Lặp qua từng cặp trạm kề nhau để vẽ đoạn ray
        for (let i = 0; i < sortedStations.length - 1; i++) {
            const seqA = sortedStations[i];
            const seqB = sortedStations[i+1];

            const stIdA = String(getVal(seqA, ["STATION_ID", "STATION"])).trim();
            const stIdB = String(getVal(seqB, ["STATION_ID", "STATION"])).trim();

            const stA = validStops.find(s => String(getVal(s, ["stop_id", "ID"])).trim() === stIdA);
            const stB = validStops.find(s => String(getVal(s, ["stop_id", "ID"])).trim() === stIdB);

            if (stA && stB) {
                const latA = parseFloat(getVal(stA, ["stop_lat", "LAT"]));
                const lonA = parseFloat(getVal(stA, ["stop_lon", "LON"]));
                const latB = parseFloat(getVal(stB, ["stop_lat", "LAT"]));
                const lonB = parseFloat(getVal(stB, ["stop_lon", "LON"]));

                if (latA && lonA && latB && lonB) {
                    const edgeId = `${lineId}_${stIdA}_${stIdB}`;
                    const nameA = getVal(stA, ["stop_name", "NAME"]);
                    const nameB = getVal(stB, ["stop_name", "NAME"]);

                    // KIỂM TRA XEM ĐOẠN RAY CÓ ĐANG BỊ CHẶN TRÊN SERVER KHÔNG
                    const isInitiallyBlocked = (statusData.blocked_edges || []).some(eStr => {
                        const parts = eStr.split('_');
                        return (parts[0] === stIdA && parts[1] === stIdB) || (parts[0] === stIdB && parts[1] === stIdA);
                    });

                    let initialColor = lineColor;
                    let initialWeight = 6;
                    let initialDash = null;

                    if (isInitiallyBlocked) {
                        initialColor = "#ff0000";
                        initialWeight = 8;
                        initialDash = '10, 10';
                        if (!blockedEdges.includes(edgeId)) {
                            blockedEdges.push(edgeId); // Giữ lại trạng thái để click mở lại được
                        }
                    }

                    // Vẽ đoạn ray với màu sắc ban đầu chính xác
                    const edgeSegment = L.polyline([[latA, lonA], [latB, lonB]], { 
                        color: initialColor, 
                        weight: initialWeight, 
                        dashArray: initialDash,
                        opacity: 0.8 
                    }).addTo(map);

                    edgeSegment.bindTooltip(`Tuyến: ${lineId} <br>Đoạn: <b>${nameA} ↔ ${nameB}</b>`);

                    edgeSegment.on('click', function() {
                        if (currentMode === 'EDGE') {
                            if (blockedEdges.includes(edgeId)) {
                                blockedEdges = blockedEdges.filter(eId => eId !== edgeId);
                                this.setStyle({ color: lineColor, weight: 6, dashArray: null }); 
                                statusMsg.innerText = `Đã MỞ LẠI đoạn: ${nameA} ↔ ${nameB}`;
                                statusMsg.style.color = "green";
                            } else {
                                blockedEdges.push(edgeId);
                                this.setStyle({ color: "#ff0000", weight: 8, dashArray: '10, 10' }); 
                                statusMsg.innerText = `Đã CHẶN đoạn: ${nameA} ↔ ${nameB}`;
                                statusMsg.style.color = "red";
                            }
                            btnOk.style.display = 'inline-block';
                        }
                    });
                }
            }
        }
    }

    // === BƯỚC 3: VẼ TRẠM (NODES) VÀ LOGIC ADMIN ===
    validStops.forEach(station => {
        const lat = parseFloat(getVal(station, ["stop_lat", "LAT"]));
        const lon = parseFloat(getVal(station, ["stop_lon", "LON"]));
        const name = getVal(station, ["stop_name", "NAME"]);
        const id = String(getVal(station, ["stop_id", "ID"])).trim();

        if (lat && lon) {
            // KIỂM TRA TRẠNG THÁI TRẠM TỪ BACKEND ĐỂ ĐỔI MÀU KHI RE-LOAD
            const isClosed = (statusData.blocked_nodes || []).includes(id);
            const transferSeverity = (statusData.transfer_issues || {})[id];

            let initialFillColor = "#ffffff";
            let initialRadius = 4;

            if (isClosed) {
                initialFillColor = "#ff0000";
                initialRadius = 7;
            } else if (transferSeverity) {
                initialFillColor = transferSeverity === 'light' ? '#f1c40f' : (transferSeverity === 'heavy' ? '#e67e22' : '#8e44ad');
                initialRadius = transferSeverity === 'light' ? 6 : (transferSeverity === 'heavy' ? 7 : 8);
            }

            const marker = L.circleMarker([lat, lon], {
                radius: initialRadius,
                fillColor: initialFillColor,
                color: "#000",
                weight: 2,
                fillOpacity: 1
            }).addTo(map);

            marker.bindTooltip(`<b>${name}</b>`);

            marker.on('click', function() {
                if (currentMode === 'NODE') {
                    if (blockedNodes.includes(id)) {
                        blockedNodes = blockedNodes.filter(nId => nId !== id);
                        this.setStyle({ fillColor: "#ffffff", radius: 4 }); 
                        statusMsg.innerText = `Đã MỞ LẠI trạm: ${name}`;
                        statusMsg.style.color = "green";
                    } else {
                        blockedNodes.push(id);
                        this.setStyle({ fillColor: "#ff0000", radius: 7 }); 
                        statusMsg.innerText = `Đã ĐÓNG trạm: ${name}`;
                        statusMsg.style.color = "red";
                    }
                    btnOk.style.display = 'inline-block';
                }
                else if (currentMode === 'TRANSFER') {
                    if (transferIssues[id] === currentSeverity) {
                        delete transferIssues[id]; 
                        this.setStyle({ fillColor: "#ffffff", radius: 4 }); 
                        statusMsg.innerText = `Đã HỦY lỗi tại: ${name}`;
                        statusMsg.style.color = "green";
                    } 
                    else {
                        transferIssues[id] = currentSeverity; 
                        const tColor = currentSeverity === 'light' ? '#f1c40f' : (currentSeverity === 'heavy' ? '#e67e22' : '#8e44ad');
                        const tRadius = currentSeverity === 'light' ? 6 : (currentSeverity === 'heavy' ? 7 : 8);
                        this.setStyle({ fillColor: tColor, radius: tRadius }); 
                        statusMsg.innerText = `Đã đặt lỗi ${currentSeverity.toUpperCase()} tại: ${name}`;
                    }
                    btnOk.style.display = 'inline-block';
                }
            });
        }
    });

    // === BƯỚC 3: VẼ TRẠM (NODES) VÀ LOGIC ADMIN ===
    validStops.forEach(station => {
        const lat = parseFloat(getVal(station, ["stop_lat", "LAT"]));
        const lon = parseFloat(getVal(station, ["stop_lon", "LON"]));
        const name = getVal(station, ["stop_name", "NAME"]);
        const id = String(getVal(station, ["stop_id", "ID"])).trim();

        if (lat && lon) {
            const marker = L.circleMarker([lat, lon], {
                radius: 4,
                fillColor: "#ffffff",
                color: "#000",
                weight: 2,
                fillOpacity: 1
            }).addTo(map);

            marker.bindTooltip(`<b>${name}</b>`);

            marker.on('click', function() {
                if (currentMode === 'NODE') {
                    if (blockedNodes.includes(id)) {
                        blockedNodes = blockedNodes.filter(nId => nId !== id);
                        this.setStyle({ fillColor: "#ffffff", radius: 4 }); 
                        statusMsg.innerText = `Đã MỞ LẠI trạm: ${name}`;
                        statusMsg.style.color = "green";
                    } else {
                        blockedNodes.push(id);
                        this.setStyle({ fillColor: "#ff0000", radius: 7 }); 
                        statusMsg.innerText = `Đã ĐÓNG trạm: ${name}`;
                        statusMsg.style.color = "red";
                    }
                    btnOk.style.display = 'inline-block';
                }
                else if (currentMode === 'TRANSFER') {
                    // Nếu trạm đã bị lỗi và Admin click lại cùng một mức độ -> Hủy lỗi (Trả về màu trắng)
                    if (transferIssues[id] === currentSeverity) {
                        delete transferIssues[id]; // Xóa khỏi object
                        this.setStyle({ fillColor: "#ffffff", radius: 4 }); 
                        statusMsg.innerText = `Đã HỦY lỗi tại: ${name}`;
                        statusMsg.style.color = "green";
                    } 
                    // Nếu trạm chưa có lỗi, HOẶC Admin muốn ghi đè mức độ khác lên (VD: từ Light lên Extreme)
                    else {
                        transferIssues[id] = currentSeverity; // Lưu vào object
                        
                        // Chọn màu và kích thước theo mức độ
                        const tColor = currentSeverity === 'light' ? '#f1c40f' : (currentSeverity === 'heavy' ? '#e67e22' : '#8e44ad');
                        const tRadius = currentSeverity === 'light' ? 6 : (currentSeverity === 'heavy' ? 7 : 8);
                        
                        this.setStyle({ fillColor: tColor, radius: tRadius }); 
                        statusMsg.innerText = `Đã đặt lỗi ${currentSeverity.toUpperCase()} tại: ${name}`;
                    }

                    // Hiện nút OK nếu có ít nhất 1 key trong Object
                    btnOk.style.display = 'inline-block';
                }
            });
        }
    });

    // === BƯỚC 4: XỬ LÝ SỰ KIỆN NÚT OK ===
    // === BƯỚC 4: XỬ LÝ SỰ KIỆN NÚT OK ===
    btnOk.onclick = async () => {
        // Cập nhật hàm gửi API để nhận tham số URL tương ứng với từng Backend Route
        const sendScenario = (url, payload, successText) => {
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => {
                if (!res.ok) throw new Error("Lỗi API"); // Bắt lỗi 404 nếu sai đường dẫn
                return res.json();
            })
            .then(data => {
                statusMsg.innerText = `✅ ${successText}`;
                statusMsg.style.color = "green";
                currentMode = null; 
                btnOk.style.display = 'none';
            })
            .catch(err => {
                statusMsg.innerText = "❌ Lỗi kết nối: Backend Python chưa bật hoặc sai đường dẫn!";
                statusMsg.style.color = "red";
                console.error("Lỗi đồng bộ:", err);
            });
        };

        if (currentMode === 'NODE') {
            if (confirm(`Xác nhận ĐÓNG ${blockedNodes.length} trạm?`)) {
                sendScenario(
                    'http://127.0.0.1:5000/api/admin/node_outage', // Gọi đúng API Đóng Trạm
                    { affected_nodes: blockedNodes }, 
                    "Đã đồng bộ kịch bản ĐÓNG TRẠM lên Server!"
                );
            }
        }
        else if (currentMode === 'EDGE') {
            if (confirm(`Xác nhận tạo kịch bản chặn ${blockedEdges.length} đoạn ray?`)) {
                sendScenario(
                    'http://127.0.0.1:5000/api/admin/edge_outage', // Gọi đúng API Chặn Ray
                    { affected_edges: blockedEdges }, 
                    "Đã đồng bộ kịch bản CHẶN RAY lên Server!"
                );
            }
        }
        else if (currentMode === 'TRANSFER') {
            if (confirm(`Xác nhận tạo kịch bản Lỗi đổi tuyến cho ${Object.keys(transferIssues).length} trạm?`)) {
                sendScenario(
                    'http://127.0.0.1:5000/api/admin/transfer_issue', // Gọi đúng API Lỗi Tuyến
                    { affected_nodes: transferIssues }, 
                    "Đã đồng bộ kịch bản LỖI ĐỔI TUYẾN lên Server!"
                );
            }
        }
    };

}).catch(err => {
    console.error("Lỗi nghiêm trọng khi nạp dữ liệu Admin:", err);
    alert("Không thể tải dữ liệu map Admin. Hãy kiểm tra Console (F12) và đường dẫn file JSON.");
});
document.getElementById('logout-btn').addEventListener('click', () => {
    if (confirm("Bạn có chắc chắn muốn đăng xuất khỏi Trạm điều hành?")) {
        // Tịch thu thẻ
        sessionStorage.removeItem("isAdminLoggedIn");
        
        // Đá về trang đăng nhập
        window.location.href = "login.html";
    }
});