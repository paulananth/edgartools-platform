from __future__ import annotations

from edgar_warehouse.silver_support.postgres_reader import bind_qmark, rewrite_count_if


def test_count_if_rewrites_nested_in_predicate() -> None:
    sql = (
        "SELECT cik FROM sec_company WHERE cik NOT IN ("
        "SELECT cik FROM sec_company_filing GROUP BY cik "
        "HAVING COUNT_IF(form NOT IN ('3','4','5')) = 0)"
    )
    rewritten = rewrite_count_if(sql)
    assert "COUNT_IF" not in rewritten.upper()
    assert "COUNT(*) FILTER (WHERE form NOT IN ('3','4','5'))" in rewritten


def test_sql_without_count_if_is_unchanged() -> None:
    sql = "SELECT * FROM sec_company WHERE cik IN (?, ?)"
    assert rewrite_count_if(sql) == sql


def test_bind_qmark_rewrites_placeholders_and_count_if() -> None:
    sql = (
        "SELECT * FROM sec_company WHERE cik IN (?, ?) "
        "AND cik NOT IN (SELECT cik FROM sec_company_filing "
        "GROUP BY cik HAVING COUNT_IF(form NOT IN ('3','4')) = 0)"
    )
    statement, mapping = bind_qmark(sql, [320193, 789019])
    rendered = str(statement)
    assert "?" not in rendered
    assert ":p0" in rendered and ":p1" in rendered
    assert "COUNT(*) FILTER (WHERE form NOT IN ('3','4'))" in rendered
    assert mapping == {"p0": 320193, "p1": 789019}


def test_bind_qmark_without_params_leaves_sql_as_text() -> None:
    statement, mapping = bind_qmark("SELECT COUNT(*) AS n FROM sec_company", None)
    assert mapping == {}
    assert "sec_company" in str(statement)
