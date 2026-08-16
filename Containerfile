FROM registry.access.redhat.com/ubi10:1785332448

USER 0

WORKDIR /app

ENV KUBEOPTIX_UID=1001 \
    LOG_DIR=/app/logs \
    DATA_DIR=/app/data \
    VENV_DIR=/app/.venv \
    HOME=/tmp \
    KUBECONFIG=/tmp/.kube/config \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KUBEOPTIX_API_HOST=0.0.0.0 \
    KUBEOPTIX_API_PORT=8000 \
    KUBEOPTIX_METADATA_DIR=/app/data/assessment \
    KUBEOPTIX_OUTPUT_DIR=/app/data/reports

ENV PATH=/app/.venv/bin:$PATH

RUN dnf install -y \
    python3 \
    python3-pip \
    && dnf update -y \
    && dnf clean all \
    && groupadd -g "$KUBEOPTIX_UID" kubeoptix \
    && useradd -u "$KUBEOPTIX_UID" -g kubeoptix -m -s /bin/bash kubeoptix \
    && mkdir -p "$LOG_DIR" "$DATA_DIR" /tmp/.kube \
    && chown -R kubeoptix:kubeoptix "$LOG_DIR" "$DATA_DIR" /tmp/.kube \
    && chmod -R 777 /tmp

COPY requirements.txt pyproject.toml ./
COPY src/ ./src/
COPY api.py run-ocp.sh ./

RUN find ./src -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" -o -name ".cache" \) -prune -exec rm -rf {} + \
    && find ./src -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*~" -o -name ".DS_Store" \) -delete \
    && python3 -m venv "$VENV_DIR" \
    && "$VENV_DIR/bin/pip" install --upgrade pip \
    && "$VENV_DIR/bin/pip" install --no-cache-dir -r requirements.txt \
    && chmod +x run-ocp.sh \
    && chown -R kubeoptix:kubeoptix /app \
    && chmod -R u+rwX /app

USER kubeoptix

EXPOSE 8000

CMD ["python", "api.py"]
