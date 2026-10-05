FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install canvastekk-workflow-sdk \
    --index-url https://pypi.pkg.github.com/betekk/

COPY handler.py .

EXPOSE 8001

CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8001"]
