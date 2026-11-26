"""제공 자료 약속의 열과 자료형. 코드·날짜·월은 CSV에서 문자열로 보존한다."""

COLUMNS = {
    "pos_clean": "month region channel sku name brand category units amount promo is_own after_end",
    "sellin": "month channel sku name units",
    "temperature": "month region temp_c",
    "assets": "asset_id sku name brand category pack launched ended status concept peak_sales_100m reason note flags",
    "infra": "channel stores frozen_rate chilled_rate note",
    "past_tests": "product year category intent_top2 distribution_6m trial_12m ratio note",
    "survey_respondents": "rid gender birth_year age_band region job income buy_coffee buy_soda buy_juice main_channel novelty health price_sens seconds order weight",
    "survey_ratings": "rid concept understand like distinct intent price_ok wtp monthly shown_price price_format position comment leading",
    "population": "dimension age_band gender region share",
    "trend": "month keyword search_index search_raw sns_mentions sns_raw ad_share sns_organic",
    "trend_related": "keyword related share",
    "trend_volume": "keyword searches_at_100",
    "journeys_offline": "oid date store store_type age gender purpose seconds compared gaze_new_s chosen bought memo style",
    "journeys_online": "log_id session cookie ts_kst source event sku name dwell_s device promo is_bot",
}
CSV_COLUMNS = {name: tuple(columns.split()) for name, columns in COLUMNS.items()}
JSON_NAMES = ("survey_summary", "cleaning_report", "fgi", "concepts")
FILENAMES = {**{name: name + ".csv" for name in CSV_COLUMNS},
             **{name: name + ".json" for name in JSON_NAMES}}

INTEGER = set("""units amount year stores birth_year buy_coffee buy_soda buy_juice novelty health
                 price_sens seconds understand like distinct intent price_ok wtp monthly shown_price
                 position searches_at_100 compared session dwell_s sns_mentions sns_raw""".split())
DECIMAL = set("""temp_c peak_sales_100m frozen_rate chilled_rate intent_top2 distribution_6m
                 trial_12m ratio weight share search_index search_raw ad_share sns_organic gaze_new_s""".split())
BOOLEAN = {"is_own", "after_end", "leading", "is_bot"}
