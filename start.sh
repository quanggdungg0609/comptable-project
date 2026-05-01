#!/bin/bash

# Detect Host IP (MacOS/Linux)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # MacOS
    HOST_IP=$(ipconfig getifaddr en0 || ipconfig getifaddr en1)
else
    # Linux
    HOST_IP=$(hostname -I | awk '{print $1}')
fi

if [ -z "$HOST_IP" ]; then
    echo "❌ Không thể phát hiện địa chỉ IP của máy."
    exit 1
fi

echo "✅ Đã phát hiện IP máy chủ: $HOST_IP"

# Update .env file
if [ -f .env ]; then
    # Use sed to update APP_BASE_URL
    # MacOS sed needs an empty string for the -i extension
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|APP_BASE_URL=.*|APP_BASE_URL=http://$HOST_IP:8000|" .env
        sed -i '' "s|RUSTFS_PUBLIC_ENDPOINT=.*|RUSTFS_PUBLIC_ENDPOINT=http://$HOST_IP:9000|" .env
    else
        sed -i "s|APP_BASE_URL=.*|APP_BASE_URL=http://$HOST_IP:8000|" .env
        sed -i "s|RUSTFS_PUBLIC_ENDPOINT=.*|RUSTFS_PUBLIC_ENDPOINT=http://$HOST_IP:9000|" .env
    fi
    echo "📝 Đã cập nhật APP_BASE_URL và RUSTFS_PUBLIC_ENDPOINT trong .env"
else
    echo "⚠️ Không tìm thấy file .env"
fi

# Start Docker Compose
echo "🚀 Đang khởi động Docker..."
docker-compose -f docker-compose.yml up -d --build
