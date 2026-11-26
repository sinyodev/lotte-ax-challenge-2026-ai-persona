from types import SimpleNamespace


def test_ten_roles_count_selection_once_and_keep_unmatched_reason(monkeypatch):
    from shelftest import catalog
    import ontology_roles as roles

    person = SimpleNamespace(uuid="p", sex="여자", band="19-29", text=(20, "", "지역", "", "합성", ""))
    need = {"번호": "N", "욕구": "휴대", "범위": "음료", "바라는 것(위층)": "편의",
            "매대에서 확인되는 것": "뚜껑", "근거 유형": "규칙"}
    occasion = {"번호": "D", "상황": "식사", "매대": "음료", "전체 비중(%)": 100, "마신 자리 수": 1}
    plan = SimpleNamespace(visits=[{"방문": "v", "uuid": "p", "상황 번호": "D"}], by_uuid={"p": person},
                           plain={"needs": [need], "occasions": {"D": occasion}, "strength": {"p": {"N": 2}}})
    product = SimpleNamespace(key="a", shelf="음료", row={}, is_own=False, kind="물", volume=100,
                              price=1000, promo="없음", fulfills={"N": "잘 채움"})
    monkeypatch.setattr(catalog, "current", lambda: [product])
    tables = {"occasion_needs.csv": [{"매대": "음료", "번호": "D", "욕구 번호": "N", "바뀌는 크기(-2~+2)": 1, "근거 종류": "모의"}],
              "occasion_weights.csv": [{"매대": "음료", "성별": "여자", "연령대": "19-29", "번호": "D", "비중(%)": 100}],
              "fulfills.csv": [{"매대": "음료", "상품명": "a", "욕구 번호": "N", "적용한 규칙": "뚜껑"}]}
    monkeypatch.setattr(roles.pilot, "read", tables.__getitem__)
    records = {"dev-first": {"v": {"product": "a", "needs": ["N", "미등록"]}},
               "dev-repeat": {"v": {"product": roles.study.method.NO_PURCHASE, "needs": []}}}
    report = roles.evaluate(plan, records, {})
    assert report["events"] == 2 and report["tables"]["choice"] == 3
    assert report["reproduced_occasions"] == report["with_occasion_shift"] == 1
    assert report["visits_with_faces"] == 1 and report["reason_mentions_for_purchases"] == 2
    assert report["recognized_need"] == report["positive_fulfills"] == 1
