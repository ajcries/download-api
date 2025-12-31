# Use the official Playwright image which has ALL browsers and OS libs pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Install FFmpeg for the video downloading
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Start the API (Change api_app:api_app if your file/variable is named differently)
CMD ["gunicorn", "-b", "0.0.0.0:10000", "api:api_app"]