FROM python:3.11-slim

WORKDIR /app

# Cài đặt thư viện hệ thống cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn
COPY . .

# Tạo thư mục tạm và cấp toàn quyền ghi
RUN mkdir -p /tmp/gemini_downloads && chmod -R 777 /app /tmp

# Cổng mặc định của Hugging Face Spaces là 7860
ENV PORT=7860
EXPOSE 7860

CMD ["python", "server.py"]