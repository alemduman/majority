from majority import cli


def test_cli_research_approve_costs(env, capsys, monkeypatch):
    assert cli.main(["research", "Вагонетка летит на пятерых. Переведёшь стрелку, чтобы погиб один?"]) == 0
    out = capsys.readouterr().out
    assert "card_ready" in out and "81%" in out and "уровень A" in out
    # без --yes в неинтерактивном режиме не подтверждает
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["approve", "1"]) == 4
    assert cli.main(["approve", "1", "--yes"]) == 0
    assert cli.main(["costs"]) == 0
    assert "Итого" in capsys.readouterr().out


def test_failed_card_cannot_be_approved(env):
    cli.main(["research", "Чай или кофе (тест неверной цифры)"])
    assert cli.main(["approve", "1", "--yes"]) == 3


def test_later_stages_locked(env):
    assert cli.main(["render", "1"]) == 5
    assert cli.main(["publish", "1", "--publish"]) == 5
