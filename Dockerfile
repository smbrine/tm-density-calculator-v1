FROM --platform=linux/amd64 python:3.11-bookworm

# Set working directory
WORKDIR /app

# Copy only the necessary files to minimize cache busting
COPY pyproject.toml poetry.lock ./

# Environment variables
ENV PYTHONPATH=./
ENV PYTHONUNBUFFERED=True
ARG BIND_PORT
ENV BIND_PORT=$BIND_PORT

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && python -m ensurepip --upgrade && pip install --upgrade pip \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Copy the rest of the application code
COPY . .

# Expose the gRPC port
EXPOSE $BIND_PORT

# Command to run the application
CMD ["python", "-m", "app.main"]
