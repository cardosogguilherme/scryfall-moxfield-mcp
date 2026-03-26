FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY scryfallmcp/ scryfallmcp/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Bind to all interfaces when running in HTTP mode (sse/streamable-http)
ENV FASTMCP_HOST=0.0.0.0
EXPOSE 8000

# credentials.json is NOT baked into the image — mount it at runtime
# MCP_TRANSPORT defaults to "stdio"; set to "streamable-http" or "sse" for network mode

CMD ["python", "-m", "scryfallmcp.server"]
