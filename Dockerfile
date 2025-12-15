FROM ghcr.io/astral-sh/uv:python3.13-bookworm

WORKDIR /app

# Install dependencies based on the lockfile and pyproject
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# Copy the rest of the source code
COPY . .
RUN uv sync --locked

EXPOSE 8000

CMD ["uv", "run", "python", "-m", "src.main"]


