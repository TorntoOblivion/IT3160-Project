// 1. KHỞI TẠO BẢN ĐỒ
var map = L.map('map').setView([13.7563, 100.5018], 12);

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 20
}).addTo(map);

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

// 2. LOGIC NÚT BẤM SIDEBAR
document.getElementById('btn-node-outage').onclick = () => {
    currentMode = 'NODE';
    statusMsg.innerText = "Chế độ ĐÓNG TRẠM: Click vào các trạm (chấm tròn) trên bản đồ.";
    statusMsg.style.color = "blue";
    btnOk.style.display = blockedNodes.length > 0 ? 'inline-block' : 'none';
};

document.getElementById('btn-edge-outage').onclick = () => {
    currentMode = 'EDGE';
    statusMsg.innerText = "Chế độ CHẶN RAY: Click vào đường nối giữa 2 trạm.";
    statusMsg.style.color = "#d35400"; // Màu cam đậm
    btnOk.style.display = blockedEdges.length > 0 ? 'inline-block' : 'none';
};

// Gộp chung logic hiển thị cho Transfer
function setTransferMode(severity, color, text) {
    currentMode = 'TRANSFER';
    currentSeverity = severity;
    statusMsg.innerText = `Chế độ LỖI ${text}: Click trạm để áp dụng.`;
    statusMsg.style.color = color;
    btnOk.style.display = Object.keys(transferIssues).length > 0 ? 'inline-block' : 'none';
}

document.getElementById('btn-transfer-light').onclick = () => setTransferMode('light', '#f1c40f', 'NHẸ (Vàng)');
document.getElementById('btn-transfer-heavy').onclick = () => setTransferMode('heavy', '#e67e22', 'NẶNG (Cam)');
document.getElementById('btn-transfer-extreme').onclick = () => setTransferMode('extreme', '#8e44ad', 'NGHIÊM TRỌNG (Tím)');

document.getElementById('btn-clear-all').onclick = () => {
    location.reload(); 
};



// 3. TẢI DỮ LIỆU VÀ VẼ BẢN ĐỒ
Promise.all([
    fetch('../data/stops_raw.json').then(res => res.json()), 
    fetch('../data/lines_clean.json').then(res => res.json()),
    fetch('../data/station_line_clean.json').then(res => res.json())
]).then(([stopsData, linesData, sequenceData]) => {

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
                    // Tạo ID định danh duy nhất cho đoạn ray này (VD: Line1_StationA_StationB)
                    const edgeId = `${lineId}_${stIdA}_${stIdB}`;
                    const nameA = getVal(stA, ["stop_name", "NAME"]);
                    const nameB = getVal(stB, ["stop_name", "NAME"]);

                    // Vẽ đoạn ray
                    const edgeSegment = L.polyline([[latA, lonA], [latB, lonB]], { 
                        color: lineColor, 
                        weight: 6, 
                        opacity: 0.8 
                    }).addTo(map);

                    // Thêm tooltip báo tên 2 trạm nối nhau
                    edgeSegment.bindTooltip(`Tuyến: ${lineId} <br>Đoạn: <b>${nameA} ↔ ${nameB}</b>`);

                    // ⚡ LOGIC CLICK CHẶN RAY ⚡
                    edgeSegment.on('click', function() {
                        if (currentMode === 'EDGE') {
                            if (blockedEdges.includes(edgeId)) {
                                // Mở lại đoạn ray (trả về màu gốc, nét liền)
                                blockedEdges = blockedEdges.filter(eId => eId !== edgeId);
                                this.setStyle({ color: lineColor, weight: 6, dashArray: null }); 
                                statusMsg.innerText = `Đã MỞ LẠI đoạn: ${nameA} ↔ ${nameB}`;
                                statusMsg.style.color = "green";
                            } else {
                                // Chặn đoạn ray (đổi sang màu đỏ, nét đứt cảnh báo)
                                blockedEdges.push(edgeId);
                                this.setStyle({ color: "#ff0000", weight: 8, dashArray: '10, 10' }); 
                                statusMsg.innerText = `Đã CHẶN đoạn: ${nameA} ↔ ${nameB}`;
                                statusMsg.style.color = "red";
                            }

                            // Hiện nút OK nếu có ít nhất 1 cạnh bị chặn
                            btnOk.style.display = blockedEdges.length > 0 ? 'inline-block' : 'none';
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
                    btnOk.style.display = blockedNodes.length > 0 ? 'inline-block' : 'none';
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
                    btnOk.style.display = Object.keys(transferIssues).length > 0 ? 'inline-block' : 'none';
                }
            });
        }
    });

    // === BƯỚC 4: XỬ LÝ SỰ KIỆN NÚT OK ===
    btnOk.onclick = async () => {
        if (currentMode === 'NODE') {
            const confirmMsg = `Xác nhận tạo kịch bản đóng ${blockedNodes.length} trạm?\n\nID các trạm: ${blockedNodes.join(", ")}`;
            if (confirm(confirmMsg)) {
                console.log("Dữ liệu gửi đi Backend:", { type: 'NODE_OUTAGE', affected_nodes: blockedNodes });
                statusMsg.innerText = "✅ Đã lưu kịch bản ĐÓNG TRẠM thành công!";
                statusMsg.style.color = "green";
                currentMode = null; 
                btnOk.style.display = 'none';
            }
        } 
        else if (currentMode === 'EDGE') {
            const confirmMsg = `Xác nhận tạo kịch bản chặn ${blockedEdges.length} đoạn ray?\n\nID các đoạn: \n${blockedEdges.join("\n")}`;
            if (confirm(confirmMsg)) {
                console.log("Dữ liệu gửi đi Backend:", { type: 'EDGE_OUTAGE', affected_edges: blockedEdges });
                statusMsg.innerText = "✅ Đã lưu kịch bản CHẶN RAY thành công!";
                statusMsg.style.color = "green";
                currentMode = null; 
                btnOk.style.display = 'none';
            }
        }
        else if (currentMode === 'TRANSFER') {
            const count = Object.keys(transferIssues).length;
            const confirmMsg = `Xác nhận tạo kịch bản Lỗi đổi tuyến cho ${count} trạm?`;
            
            if (confirm(confirmMsg)) {
                // Backend của bạn sẽ nhận được 1 Object hoàn hảo như sau: 
                // { "trạm_1": "light", "trạm_2": "extreme" }
                console.log("Dữ liệu gửi đi Backend:", { 
                    type: 'TRANSFER_ISSUE', 
                    affected_nodes: transferIssues 
                });
                
                statusMsg.innerText = "✅ Đã lưu kịch bản LỖI ĐỔI TUYẾN thành công!";
                statusMsg.style.color = "green";
                currentMode = null; 
                btnOk.style.display = 'none';
            }
        }
    };

}).catch(err => {
    console.error("Lỗi nghiêm trọng khi nạp dữ liệu Admin:", err);
    alert("Không thể tải dữ liệu map Admin. Hãy kiểm tra Console (F12) và đường dẫn file JSON.");
});