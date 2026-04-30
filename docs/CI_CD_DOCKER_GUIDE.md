# Hướng dẫn thiết lập CI/CD và Docker Hub với GitHub Actions

Tài liệu này hướng dẫn bạn cách sử dụng hệ thống CI/CD (Kiểm thử liên tục và Triển khai liên tục) vừa được thiết lập thông qua GitHub Actions cho dự án Invoice Collector.

## 1. Hệ thống test tự động (CI - Continuous Integration)

Quy trình tự động kiểm thử (`pipeline.yml`) sẽ được tự động kích hoạt mỗi khi:
- Bạn tạo một Pull Request hướng vào nhánh `main`.
- Bạn Push code trực tiếp lên nhánh `main`.

**Cấu hình:**
- Workflow sẽ thiết lập môi trường `Python 3.12`.
- Cài đặt `Poetry` và cài đặt các dependencies (sử dụng cache để tối ưu tốc độ).
- Chạy lệnh `poetry run pytest tests/` để xác nhận mọi tính năng của Hệ thống xử lý hóa đơn đều hoạt động ổn định.
- Nếu bài kiểm tra lỗi, GitHub sẽ từ chối hoặc cảnh báo PR/Commit của bạn. Không cần cài đặt gì thêm cho workflow này.

## 2. Hệ thống Push Image & Release (CD - Continuous Deployment)

Bất kỳ khi nào codebase ở trên nhánh `main` được cập nhật, hoặc có một Tag Release mới (ví dụ: `v1.0.0`), hệ thống sẽ tự động kích hoạt workflow `docker-publish.yml` đóng gói Code thành Docker Image và Push lên Docker Hub.

**Quy trình xuất bản:**
- Build docker image sử dụng `Dockerfile.prod`.
- Gắn thẻ `latest` nếu được merge vào trực tiếp nhánh `main`.
- Gắn thẻ theo version (`v1.0.0`, `v1.0.1`) nếu bạn push thư mục tag đó lên git.
- Tự động đẩy (Push) image đã build lên Docker Hub.

### 2.1 Cài đặt Credentials Docker Hub vào GitHub
Để action có thể tự động Push được image lên trang Docker Hub của bạn cho người dùng sử dụng, bạn **BẮT BUỘC** phải cấu hình Secrets Repository trong GitHub:

1. Chuyển đến giao diện repository của bạn trên [GitHub](https://github.com/).
2. Chọn mục **Settings** (ở thanh menu nằm trên danh sách code).
3. Tại menu bên trái, phần **Security**, chọn dropdown **Secrets and variables** -> **Actions**.
4. Nhấn nút xanh lục `New repository secret`.
5. Bổ sung liên tiếp 2 secrets sau:
   - Secret thứ nhất:
     - **Name:** `DOCKER_USERNAME`
     - **Secret:** `[Tên đăng nhập Docker Hub của bạn]`
   - Secret thứ hai:
     - **Name:** `DOCKER_PASSWORD`
     - **Secret:** `[Mật khẩu Docker Hub, hoặc Access Token (khuyên dùng)]`

> **Mẹo:** Bạn nên sinh Personal Access Token trong phần Account Settings của Docker Hub thay vì sử dụng Mật khẩu gốc để bảo mật.

### 2.2 Ship Image tới người dùng/khách hàng
Với luồng CI/CD như trên, người dùng cuối (client) của bạn không cần quan tâm đến mã nguồn. Họ chỉ cần chạy lệnh tải về trực tiếp Docker Image mới nhất bằng cách:

```bash
docker pull <Tên_Docker_Hub_Của_Bạn>/collect_invoice:latest
```

Hoặc họ có thể tích hợp thẳng vào file `docker-compose.yml` cực kỳ đơn giản:

```yaml
services:
  app:
    image: <Tên_Docker_Hub_Của_Bạn>/collect_invoice:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./exports:/app/exports
```
Người dùng chỉ cần gõ `docker-compose up -d` là đã có sản phẩm chạy, tối giản hóa quá trình bàn giao!
