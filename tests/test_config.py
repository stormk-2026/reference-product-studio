from studio.config import load_settings


def test_project_env_secrets_are_not_serialized(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        'MOONSHOT_API_KEY="dummy-kimi-secret"\nARK_API_KEY="dummy-ark-secret"\nSTUDIO_DATA_DIR=./storage\n',
        encoding="utf-8",
    )
    settings = load_settings(env, environ={})
    assert settings.moonshot_api_key.get_secret_value() == "dummy-kimi-secret"
    assert settings.ark_api_key.get_secret_value() == "dummy-ark-secret"
    assert "dummy-" not in repr(settings)
    assert "dummy-" not in settings.model_dump_json()
    assert settings.storage_dir == tmp_path / "storage"
    assert settings.mode == "fixture"


def test_environment_precedence_no_interpolation_or_parent_search(tmp_path):
    (tmp_path / ".env").write_text("MOONSHOT_API_KEY=parent-secret")
    child = tmp_path / "child"
    child.mkdir()
    assert not load_settings(child / ".env", environ={}).moonshot_api_key.get_secret_value()
    env = child / ".env"
    env.write_text('MOONSHOT_API_KEY=file-key\nARK_API_KEY="literal-${HOME}"')
    settings = load_settings(env, environ={"MOONSHOT_API_KEY": "environment-key"})
    assert settings.moonshot_api_key.get_secret_value() == "environment-key"
    assert settings.ark_api_key.get_secret_value() == "literal-${HOME}"
