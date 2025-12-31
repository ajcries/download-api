# Use slim python (saves ~800MB vs the Playwright image)
FROM python:3.10-slim

# Install ffmpeg for the piping
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use 1 worker to stay inside the 512MB RAM limit
CMD ["gunicorn", "--workers", "1", "--timeout", "120", "-b", "0.0.0.0:10000", "api:api_app"]
