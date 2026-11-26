from shelftest.group import demo_sessions
from shelftest.interview import BANNED, TASTED


def test_sessions_preserve_the_panel_and_link_only_prior_fgd_turns():
    demo = demo_sessions()
    participants = {person["id"]: person for person in demo["participants"]}
    assert set(participants) == {f"p{i}" for i in range(1, 7)}
    assert {person["picked"] for person in participants.values()} == {True, False}

    for mode, session in demo["modes"].items():
        turns = session["turns"]
        rounds = [1] if mode == "fgi" else [1, 2]
        assert [turn["round"] for turn in turns] == [number for number in rounds for _ in participants]
        earlier = {}
        for number in rounds:
            batch = [turn for turn in turns if turn["round"] == number]
            assert {turn["person"] for turn in batch} == set(participants)
            assert {turn["topic"] for turn in batch} == {"price", "form", "flavor"}
            for turn in batch:
                assert not BANNED.search(turn["text"])
                assert not TASTED.search(turn["text"])
                assert turn["id"] not in earlier
                if number == 1:
                    assert "replyTo" not in turn
                    assert participants[turn["person"]]["choice"] in turn["text"]
                else:
                    cited = earlier[turn["replyTo"]]
                    assert cited["round"] == 1
                    assert cited["person"] != turn["person"]
                    assert cited["topic"] == turn["topic"]
                earlier[turn["id"]] = turn
        for summary in session["summary"]:
            assert summary["turnIds"]
            assert set(summary["turnIds"]) <= set(earlier)

    fgd = demo["modes"]["fgd"]
    assert [item["turnIds"] for item in fgd["summary"]] == [
        ["fgd-2-p1", "fgd-2-p6"],
        ["fgd-1-p3", "fgd-1-p4", "fgd-2-p3"],
        ["fgd-1-p5", "fgd-1-p2", "fgd-2-p5"],
    ]
