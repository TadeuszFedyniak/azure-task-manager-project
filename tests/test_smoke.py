from pathlib import Path


def test_app_has_health_route():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert '@app.get("/health")' in source
    assert "pwd_context.hash(password)" in source
    assert "owned_task(task_id, user, db)" in source
