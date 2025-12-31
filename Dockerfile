# Change v1.40.0 to v1.57.0
FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

# Install FFmpeg for video processing
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Start the API
CMD ["gunicorn", "-b", "0.0.0.0:10000", "api:api_app"]
