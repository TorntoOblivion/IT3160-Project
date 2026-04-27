// Đợi toàn bộ HTML tải xong mới chạy code JS
document.addEventListener('DOMContentLoaded', () => {
    
    // 1. Lấy các phần tử cần thiết từ giao diện
    const loginForm = document.querySelector('form');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');

    // Thông tin đăng nhập giả lập (Mock Credentials)
    const MOCK_USER = "admin";
    const MOCK_PASS = "hust2026"; // Mật khẩu của một sinh viên Bách Khoa

    // 2. Bắt sự kiện khi người dùng nhấn nút Submit (Login)
    loginForm.addEventListener('submit', (event) => {
        // Ngăn chặn trang web tải lại (hành động mặc định của form)
        event.preventDefault();

        const enteredUser = usernameInput.value.trim();
        const enteredPass = passwordInput.value.trim();

        console.log("Đang kiểm tra thông tin đăng nhập...");

        // 3. Logic kiểm tra
        if (enteredUser === MOCK_USER && enteredPass === MOCK_PASS) {
            alert("Đăng nhập thành công! Chào mừng bạn.");

            // Lưu trạng thái đăng nhập vào Local Storage của trình duyệt
            // Điều này giúp trang admin.html biết bạn đã vượt qua cửa bảo vệ
            localStorage.setItem('isLoggedIn', 'true');
            localStorage.setItem('adminUser', enteredUser);

            // 4. Chuyển hướng sang trang quản trị
            // Đường dẫn này tùy thuộc vào vị trí file của bạn
            window.location.href = "admin.html"; 
        } else {
            // Hiển thị thông báo nếu sai thông tin
            alert("Tên đăng nhập hoặc mật khẩu không đúng. Vui lòng kiểm tra lại!");
            
            // Xóa trắng ô mật khẩu để nhập lại
            passwordInput.value = "";
            passwordInput.focus();
        }
    });
});