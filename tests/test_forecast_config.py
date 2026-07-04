from forecast import config


def test_defaults_present_when_db_empty(monkeypatch):
    monkeypatch.setattr(config, "query", lambda *a, **k: [])
    p = config.get_params()
    assert p["coef_siguranta"] == 0.25
    assert p["fereastra_luni"] == 36.0


def test_db_overrides_default(monkeypatch):
    monkeypatch.setattr(
        config, "query",
        lambda *a, **k: [{"cheie": "coef_siguranta", "valoare": 0.4}],
    )
    assert config.get_params()["coef_siguranta"] == 0.4


def test_set_param_rejects_unknown_key():
    import pytest
    with pytest.raises(KeyError):
        config.set_param("nope", 1)
