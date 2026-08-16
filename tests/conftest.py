"""Configuração global dos testes."""

from __future__ import annotations

import os

EXAMPLE_NAMESPACE = "example-ns-prd"

# BLAS multi-thread pode alterar resultados de K-Means entre execuções no mesmo processo.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
