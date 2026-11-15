FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/mpl
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "bot.main"]
