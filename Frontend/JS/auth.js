// Đợi toàn bộ HTML tải xong mới chạy code JS
document.addEventListener('DOMContentLoaded', () => {
    
    // 1. Lấy các phần tử cần thiết từ giao diện theo đúng ID trong HTML
    const loginForm = document.getElementById('login-form');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');

    // Thông tin đăng nhập giả lập (Mật khẩu Admin chọn là admin hoặc 123456 tùy bạn sửa ở đây)
    const MOCK_ADMIN_USER = "admin";
    const MOCK_ADMIN_PASS = "admin"; 
    
    const MOCK_USER_USER = "user";
    const MOCK_USER_PASS = "user";

    // Kiểm tra bảo vệ đề phòng không tìm thấy form trong HTML
    if (!loginForm) {
        console.error("Không tìm thấy thẻ form có id='login-form'!");
        return;
    }

    // 2. Bắt sự kiện khi người dùng nhấn nút Đăng nhập (Submit Form)
    loginForm.addEventListener('submit', (event) => {
        // Ngăn chặn trang web tải lại (hành động mặc định của form)
        event.preventDefault();

        const enteredUser = usernameInput.value.trim();
        const enteredPass = passwordInput.value.trim();

        console.log("Hệ thống đang kiểm tra thông tin đăng nhập...");

        // 3. Logic phân quyền kiểm tra tài khoản
        
        // TRƯỜNG HỢP 1: QUẢN TRỊ VIÊN (ADMIN)
        if (enteredUser === MOCK_ADMIN_USER && enteredPass === MOCK_ADMIN_PASS) {
            alert("✅ Đăng nhập thành công! Chào mừng Quản trị viên.");

            // Đồng bộ bộ nhớ để cả bản cũ lẫn bản mới của admin.html đều nhận diện được
            localStorage.setItem('isLoggedIn', 'true');
            localStorage.setItem('adminUser', enteredUser);
            sessionStorage.setItem("isAdminLoggedIn", "true");

            // 4. Chuyển hướng sang trang quản trị
            // (Nếu admin.html nằm cùng thư mục với login.html thì giữ nguyên đường dẫn này)
            window.location.href = "admin.html"; 
        } 
        
        // TRƯỜNG HỢP 2: NGƯỜI DÙNG THƯỜNG (USER)
        else if (enteredUser === MOCK_USER_USER && enteredPass === MOCK_USER_PASS) {
            alert("✅ Đăng nhập thành công! Chào mừng bạn quay trở lại.");

            localStorage.setItem('isLoggedIn', 'true');
            localStorage.setItem('userUser', enteredUser);
            sessionStorage.setItem("isUserLoggedIn", "true");

            // Chuyển hướng sang trang tìm đường của người dùng
            window.location.href = "index.html";
        } 
        
        // TRƯỜNG HỢP 3: THÔNG TIN SAI
        else {
            alert("❌ Tên đăng nhập hoặc mật khẩu không đúng. Vui lòng kiểm tra lại!");
            
            // Xóa trắng ô mật khẩu để người dùng nhập lại tiện hơn
            passwordInput.value = "";
            passwordInput.focus();
        }
    });
});