"""Testes do armazenamento e do cálculo de progresso das execuções."""

from __future__ import annotations

from kubeoptix_core_ai.api.progress import (
    PCT_COMPLETE,
    ExecutionStatus,
    ExecutionStore,
    RunProgress,
    clamp_progress,
)


def test_clamp_progress_never_exceeds_100() -> None:
    assert clamp_progress(150, allow_complete=True) == 100
    assert clamp_progress(150, allow_complete=False) == 99
    assert clamp_progress(-4) == 0


def test_store_create_and_get() -> None:
    store = ExecutionStore()
    created = store.create(["example-ns-prd"])

    assert created.status == ExecutionStatus.PENDING
    assert created.progress == 0
    assert store.get(created.execution_id) == created
    assert store.get("missing") is None


def test_store_ignores_updates_after_completed() -> None:
    store = ExecutionStore()
    created = store.create(["ns"])
    store.update(
        created.execution_id,
        status=ExecutionStatus.COMPLETED,
        progress=PCT_COMPLETE,
        allow_complete=True,
    )
    after = store.update(
        created.execution_id,
        status=ExecutionStatus.ERROR,
        progress=50,
        error="tardio",
    )

    assert after is not None
    assert after.status == ExecutionStatus.COMPLETED
    assert after.progress == 100
    assert after.error is None


def test_run_progress_reaches_100_only_on_completed() -> None:
    store = ExecutionStore()
    snapshot = store.create(["ns"])
    progress = RunProgress(store, snapshot.execution_id, 1)

    progress.set_running()
    progress.set_total(4)
    progress.begin_namespace(0, "ns")
    progress.yamls_identified(4)
    progress.yaml_read_started()
    for index in range(1, 5):
        progress.yaml_file_processed(index, 4)
    progress.yaml_read_finished()
    progress.analysis_step(1, 2, "CPU")
    progress.analysis_finished()
    progress.markdown_started()

    before_complete = store.get(snapshot.execution_id)
    assert before_complete is not None
    assert before_complete.progress == 90
    assert before_complete.status == ExecutionStatus.RUNNING

    progress.namespace_report_written("/tmp/ns.md")
    still_running = store.get(snapshot.execution_id)
    assert still_running is not None
    assert still_running.progress == 90

    progress.completed("/tmp/ns.md")
    done = store.get(snapshot.execution_id)
    assert done is not None
    assert done.status == ExecutionStatus.COMPLETED
    assert done.progress == 100
    assert done.report == "/tmp/ns.md"
    assert done.processed == 4
    assert done.total == 4


def test_run_progress_is_monotonic() -> None:
    store = ExecutionStore()
    snapshot = store.create(["ns"])
    progress = RunProgress(store, snapshot.execution_id, 1)
    values: list[int] = []

    progress.set_running()
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.yamls_identified(2)
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.yaml_read_started()
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.yaml_file_processed(1, 2)
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.yaml_file_processed(2, 2)
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.yaml_read_finished()
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.analysis_finished()
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.markdown_started()
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]
    progress.completed("/tmp/ns.md")
    values.append(store.get(snapshot.execution_id).progress)  # type: ignore[union-attr]

    assert values == sorted(values)
    assert values[0] == 0
    assert values[-1] == 100
    assert all(0 <= item <= 100 for item in values)


def test_failed_keeps_last_progress() -> None:
    store = ExecutionStore()
    snapshot = store.create(["ns"])
    progress = RunProgress(store, snapshot.execution_id, 1)
    progress.set_running()
    progress.yaml_read_started()
    progress.failed("Erro durante a análise dos YAMLs", "boom")

    current = store.get(snapshot.execution_id)
    assert current is not None
    assert current.status == ExecutionStatus.ERROR
    assert current.progress == 20
    assert current.error == "boom"
    assert current.message == "Erro durante a análise dos YAMLs"


def test_two_namespaces_split_progress_range() -> None:
    store = ExecutionStore()
    snapshot = store.create(["a", "b"])
    progress = RunProgress(store, snapshot.execution_id, 2)
    progress.set_running()
    progress.begin_namespace(0, "a")
    progress.markdown_started()
    progress.namespace_report_written("/tmp/a.md")
    first = store.get(snapshot.execution_id)
    assert first is not None
    assert first.progress == 50

    progress.begin_namespace(1, "b")
    progress.markdown_started()
    mid = store.get(snapshot.execution_id)
    assert mid is not None
    assert mid.progress == 95
    progress.completed("/tmp/b.md")
    done = store.get(snapshot.execution_id)
    assert done is not None
    assert done.progress == 100
    assert done.report == "/tmp/b.md"
