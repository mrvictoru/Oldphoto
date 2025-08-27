FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
EXPOSE 8964
ENV APP_HOST=0.0.0.0:8964
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8964"]
