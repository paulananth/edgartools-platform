"""EdgarTools Universe Dashboard — Streamlit + EDGARTOOLS_GOLD.

A six-section Plotly dashboard over the Snowflake gold layer produced by
``infra/snowflake/dbt/edgartools_gold``. See ``README.md`` in this directory
for setup (config.toml stanza, warehouse/role expectations, launch command).

Connects externally via ``snowflake-connector-python`` using the default
connection defined in ``~/.snowflake/config.toml``. The file is self-contained:
SEC place codes are embedded so no edgartools import is required, keeping the
example portable.
"""

from __future__ import annotations

import csv
import io
import os
import pathlib
import tomllib
from typing import Any

import pandas as pd
import plotly.express as px
import snowflake.connector
import streamlit as st


DEFAULT_DATABASE = os.environ.get("EDGARTOOLS_DATABASE", "EDGARTOOLS")
DEFAULT_SCHEMA = os.environ.get("EDGARTOOLS_SCHEMA", "EDGARTOOLS_GOLD")

# Bind %s placeholders predictably regardless of any global user config.
snowflake.connector.paramstyle = "pyformat"


# ---------------------------------------------------------------------------
# Embedded SEC place-code lookup (from edgar/reference/data/place_codes.csv).
# Kept inline so this example has no EdgarTools runtime dependency.
# ---------------------------------------------------------------------------
PLACE_CODES_CSV = """Code,Place,Type
"AL","ALABAMA","US"
"AK","ALASKA","US"
"AZ","ARIZONA","US"
"AR","ARKANSAS","US"
"CA","CALIFORNIA","US"
"CO","COLORADO","US"
"CT","CONNECTICUT","US"
"DE","DELAWARE","US"
"DC","DISTRICT OF COLUMBIA","US"
"FL","FLORIDA","US"
"GA","GEORGIA","US"
"HI","HAWAII","US"
"ID","IDAHO","US"
"IL","ILLINOIS","US"
"IN","INDIANA","US"
"IA","IOWA","US"
"KS","KANSAS","US"
"KY","KENTUCKY","US"
"LA","LOUISIANA","US"
"ME","MAINE","US"
"MD","MARYLAND","US"
"MA","MASSACHUSETTS","US"
"MI","MICHIGAN","US"
"MN","MINNESOTA","US"
"MS","MISSISSIPPI","US"
"MO","MISSOURI","US"
"MT","MONTANA","US"
"NE","NEBRASKA","US"
"NV","NEVADA","US"
"NH","NEW HAMPSHIRE","US"
"NJ","NEW JERSEY","US"
"NM","NEW MEXICO","US"
"NY","NEW YORK","US"
"NC","NORTH CAROLINA","US"
"ND","NORTH DAKOTA","US"
"OH","OHIO","US"
"OK","OKLAHOMA","US"
"OR","OREGON","US"
"PA","PENNSYLVANIA","US"
"RI","RHODE ISLAND","US"
"SC","SOUTH CAROLINA","US"
"SD","SOUTH DAKOTA","US"
"TN","TENNESSEE","US"
"TX","TEXAS","US"
"UT","UTAH","US"
"VT","VERMONT","US"
"VA","VIRGINIA","US"
"WA","WASHINGTON","US"
"WV","WEST VIRGINIA","US"
"WI","WISCONSIN","US"
"WY","WYOMING","US"
"GU","GUAM","US"
"PR","PUERTO RICO","US"
"VI","VIRGIN ISLANDS U.S.","US"
"X1","UNITED STATES","US"
"A0","ALBERTA CANADA","CANADIAN"
"A1","BRITISH COLUMBIA CANADA","CANADIAN"
"A2","MANITOBA CANADA","CANADIAN"
"A3","NEW BRUNSWICK CANADA","CANADIAN"
"A4","NEWFOUNDLAND CANADA","CANADIAN"
"A5","NOVA SCOTIA CANADA","CANADIAN"
"A6","ONTARIO CANADA","CANADIAN"
"A7","PRINCE EDWARD ISLAND CANADA","CANADIAN"
"A8","QUEBEC CANADA","CANADIAN"
"A9","SASKATCHEWAN CANADA","CANADIAN"
"B0","YUKON CANADA","CANADIAN"
"Z4","CANADA (FEDERAL LEVEL)","CANADIAN"
"B2","AFGHANISTAN","FOREIGN"
"Y6","ALAND ISLANDS","FOREIGN"
"B3","ALBANIA","FOREIGN"
"B4","ALGERIA","FOREIGN"
"B5","AMERICAN SAMOA","US"
"B6","ANDORRA","FOREIGN"
"B7","ANGOLA","FOREIGN"
"1A","ANGUILLA","FOREIGN"
"B8","ANTARCTICA","FOREIGN"
"B9","ANTIGUA AND BARBUDA","FOREIGN"
"C1","ARGENTINA","FOREIGN"
"1B","ARMENIA","FOREIGN"
"1C","ARUBA","FOREIGN"
"C3","AUSTRALIA","FOREIGN"
"C4","AUSTRIA","FOREIGN"
"1D","AZERBAIJAN","FOREIGN"
"C5","BAHAMAS","FOREIGN"
"C6","BAHRAIN","FOREIGN"
"C7","BANGLADESH","FOREIGN"
"C8","BARBADOS","FOREIGN"
"1F","BELARUS","FOREIGN"
"C9","BELGIUM","FOREIGN"
"D1","BELIZE","FOREIGN"
"G6","BENIN","FOREIGN"
"D0","BERMUDA","FOREIGN"
"D2","BHUTAN","FOREIGN"
"D3","BOLIVIA","FOREIGN"
"1E","BOSNIA AND HERZEGOVINA","FOREIGN"
"B1","BOTSWANA","FOREIGN"
"D4","BOUVET ISLAND","FOREIGN"
"D5","BRAZIL","FOREIGN"
"D6","BRITISH INDIAN OCEAN TERRITORY","FOREIGN"
"D9","BRUNEI DARUSSALAM","FOREIGN"
"E0","BULGARIA","FOREIGN"
"X2","BURKINA FASO","FOREIGN"
"E2","BURUNDI","FOREIGN"
"E3","CAMBODIA","FOREIGN"
"E4","CAMEROON","FOREIGN"
"E8","CAPE VERDE","FOREIGN"
"E9","CAYMAN ISLANDS","FOREIGN"
"F0","CENTRAL AFRICAN REPUBLIC","FOREIGN"
"F2","CHAD","FOREIGN"
"F3","CHILE","FOREIGN"
"F4","CHINA","FOREIGN"
"F6","CHRISTMAS ISLAND","FOREIGN"
"F7","COCOS (KEELING) ISLANDS","FOREIGN"
"F8","COLOMBIA","FOREIGN"
"F9","COMOROS","FOREIGN"
"G0","CONGO","FOREIGN"
"Y3","CONGO THE DEMOCRATIC REPUBLIC OF THE","FOREIGN"
"G1","COOK ISLANDS","FOREIGN"
"G2","COSTA RICA","FOREIGN"
"L7","COTE D'IVOIRE","FOREIGN"
"1M","CROATIA","FOREIGN"
"G3","CUBA","FOREIGN"
"G4","CYPRUS","FOREIGN"
"2N","CZECH REPUBLIC","FOREIGN"
"G7","DENMARK","FOREIGN"
"1G","DJIBOUTI","FOREIGN"
"G9","DOMINICA","FOREIGN"
"G8","DOMINICAN REPUBLIC","FOREIGN"
"H1","ECUADOR","FOREIGN"
"H2","EGYPT","FOREIGN"
"H3","EL SALVADOR","FOREIGN"
"H4","EQUATORIAL GUINEA","FOREIGN"
"1J","ERITREA","FOREIGN"
"1H","ESTONIA","FOREIGN"
"H5","ETHIOPIA","FOREIGN"
"H7","FALKLAND ISLANDS (MALVINAS)","FOREIGN"
"H6","FAROE ISLANDS","FOREIGN"
"H8","FIJI","FOREIGN"
"H9","FINLAND","FOREIGN"
"I0","FRANCE","FOREIGN"
"I3","FRENCH GUIANA","FOREIGN"
"I4","FRENCH POLYNESIA","FOREIGN"
"2C","FRENCH SOUTHERN TERRITORIES","FOREIGN"
"I5","GABON","FOREIGN"
"I6","GAMBIA","FOREIGN"
"2Q","GEORGIA","FOREIGN"
"2M","GERMANY","FOREIGN"
"J0","GHANA","FOREIGN"
"J1","GIBRALTAR","FOREIGN"
"J3","GREECE","FOREIGN"
"J4","GREENLAND","FOREIGN"
"J5","GRENADA","FOREIGN"
"J6","GUADELOUPE","FOREIGN"
"J8","GUATEMALA","FOREIGN"
"Y7","GUERNSEY","FOREIGN"
"J9","GUINEA","FOREIGN"
"S0","GUINEA-BISSAU","FOREIGN"
"K0","GUYANA","FOREIGN"
"K1","HAITI","FOREIGN"
"K4","HEARD ISLAND AND MCDONALD ISLANDS","FOREIGN"
"X4","HOLY SEE (VATICAN CITY STATE)","FOREIGN"
"K2","HONDURAS","FOREIGN"
"K3","HONG KONG","FOREIGN"
"K5","HUNGARY","FOREIGN"
"K6","ICELAND","FOREIGN"
"K7","INDIA","FOREIGN"
"K8","INDONESIA","FOREIGN"
"K9","IRAN ISLAMIC REPUBLIC OF","FOREIGN"
"L0","IRAQ","FOREIGN"
"L2","IRELAND","FOREIGN"
"Y8","ISLE OF MAN","FOREIGN"
"L3","ISRAEL","FOREIGN"
"L6","ITALY","FOREIGN"
"L8","JAMAICA","FOREIGN"
"M0","JAPAN","FOREIGN"
"Y9","JERSEY","FOREIGN"
"M2","JORDAN","FOREIGN"
"1P","KAZAKSTAN","FOREIGN"
"M3","KENYA","FOREIGN"
"J2","KIRIBATI","FOREIGN"
"M4","KOREA DEMOCRATIC PEOPLE'S REPUBLIC OF","FOREIGN"
"M5","KOREA REPUBLIC OF","FOREIGN"
"M6","KUWAIT","FOREIGN"
"1N","KYRGYZSTAN","FOREIGN"
"M7","LAO PEOPLE'S DEMOCRATIC REPUBLIC","FOREIGN"
"1R","LATVIA","FOREIGN"
"M8","LEBANON","FOREIGN"
"M9","LESOTHO","FOREIGN"
"N0","LIBERIA","FOREIGN"
"N1","LIBYAN ARAB JAMAHIRIYA","FOREIGN"
"N2","LIECHTENSTEIN","FOREIGN"
"1Q","LITHUANIA","FOREIGN"
"N4","LUXEMBOURG","FOREIGN"
"N5","MACAU","FOREIGN"
"1U","MACEDONIA THE FORMER YUGOSLAV REPUBLIC OF","FOREIGN"
"N6","MADAGASCAR","FOREIGN"
"N7","MALAWI","FOREIGN"
"N8","MALAYSIA","FOREIGN"
"N9","MALDIVES","FOREIGN"
"O0","MALI","FOREIGN"
"O1","MALTA","FOREIGN"
"1T","MARSHALL ISLANDS","FOREIGN"
"O2","MARTINIQUE","FOREIGN"
"O3","MAURITANIA","FOREIGN"
"O4","MAURITIUS","FOREIGN"
"2P","MAYOTTE","FOREIGN"
"O5","MEXICO","FOREIGN"
"1K","MICRONESIA FEDERATED STATES OF","FOREIGN"
"1S","MOLDOVA REPUBLIC OF","FOREIGN"
"O9","MONACO","FOREIGN"
"P0","MONGOLIA","FOREIGN"
"Z5","MONTENEGRO","FOREIGN"
"P1","MONTSERRAT","FOREIGN"
"P2","MOROCCO","FOREIGN"
"P3","MOZAMBIQUE","FOREIGN"
"E1","MYANMAR","FOREIGN"
"T6","NAMIBIA","FOREIGN"
"P5","NAURU","FOREIGN"
"P6","NEPAL","FOREIGN"
"P7","NETHERLANDS","FOREIGN"
"P8","NETHERLANDS ANTILLES","FOREIGN"
"1W","NEW CALEDONIA","FOREIGN"
"Q2","NEW ZEALAND","FOREIGN"
"Q3","NICARAGUA","FOREIGN"
"Q4","NIGER","FOREIGN"
"Q5","NIGERIA","FOREIGN"
"Q6","NIUE","FOREIGN"
"Q7","NORFOLK ISLAND","FOREIGN"
"1V","NORTHERN MARIANA ISLANDS","US"
"Q8","NORWAY","FOREIGN"
"P4","OMAN","FOREIGN"
"R0","PAKISTAN","FOREIGN"
"1Y","PALAU","FOREIGN"
"1X","PALESTINIAN TERRITORY OCCUPIED","FOREIGN"
"R1","PANAMA","FOREIGN"
"R2","PAPUA NEW GUINEA","FOREIGN"
"R4","PARAGUAY","FOREIGN"
"R5","PERU","FOREIGN"
"R6","PHILIPPINES","FOREIGN"
"R8","PITCAIRN","FOREIGN"
"R9","POLAND","FOREIGN"
"S1","PORTUGAL","FOREIGN"
"S3","QATAR","FOREIGN"
"S4","REUNION","FOREIGN"
"S5","ROMANIA","FOREIGN"
"1Z","RUSSIAN FEDERATION","FOREIGN"
"S6","RWANDA","FOREIGN"
"Z0","SAINT BARTHELEMY","FOREIGN"
"U8","SAINT HELENA","FOREIGN"
"U7","SAINT KITTS AND NEVIS","FOREIGN"
"U9","SAINT LUCIA","FOREIGN"
"Z1","SAINT MARTIN","FOREIGN"
"V0","SAINT PIERRE AND MIQUELON","FOREIGN"
"V1","SAINT VINCENT AND THE GRENADINES","FOREIGN"
"Y0","SAMOA","FOREIGN"
"S8","SAN MARINO","FOREIGN"
"S9","SAO TOME AND PRINCIPE","FOREIGN"
"T0","SAUDI ARABIA","FOREIGN"
"T1","SENEGAL","FOREIGN"
"Z2","SERBIA","FOREIGN"
"T2","SEYCHELLES","FOREIGN"
"T8","SIERRA LEONE","FOREIGN"
"U0","SINGAPORE","FOREIGN"
"2B","SLOVAKIA","FOREIGN"
"2A","SLOVENIA","FOREIGN"
"D7","SOLOMON ISLANDS","FOREIGN"
"U1","SOMALIA","FOREIGN"
"T3","SOUTH AFRICA","FOREIGN"
"1L","SOUTH GEORGIA AND THE SOUTH SANDWICH ISLANDS","FOREIGN"
"U3","SPAIN","FOREIGN"
"F1","SRI LANKA","FOREIGN"
"V2","SUDAN","FOREIGN"
"V3","SURINAME","FOREIGN"
"L9","SVALBARD AND JAN MAYEN","FOREIGN"
"V6","SWAZILAND","FOREIGN"
"V7","SWEDEN","FOREIGN"
"V8","SWITZERLAND","FOREIGN"
"V9","SYRIAN ARAB REPUBLIC","FOREIGN"
"F5","TAIWAN","FOREIGN"
"2D","TAJIKISTAN","FOREIGN"
"W0","TANZANIA UNITED REPUBLIC OF","FOREIGN"
"W1","THAILAND","FOREIGN"
"Z3","TIMOR-LESTE","FOREIGN"
"W2","TOGO","FOREIGN"
"W3","TOKELAU","FOREIGN"
"W4","TONGA","FOREIGN"
"W5","TRINIDAD AND TOBAGO","FOREIGN"
"W6","TUNISIA","FOREIGN"
"W8","TURKEY","FOREIGN"
"2E","TURKMENISTAN","FOREIGN"
"W7","TURKS AND CAICOS ISLANDS","FOREIGN"
"2G","TUVALU","FOREIGN"
"W9","UGANDA","FOREIGN"
"2H","UKRAINE","FOREIGN"
"C0","UNITED ARAB EMIRATES","FOREIGN"
"X0","UNITED KINGDOM","FOREIGN"
"2J","UNITED STATES MINOR OUTLYING ISLANDS","US"
"X3","URUGUAY","FOREIGN"
"2K","UZBEKISTAN","FOREIGN"
"2L","VANUATU","FOREIGN"
"X5","VENEZUELA","FOREIGN"
"Q1","VIET NAM","FOREIGN"
"D8","VIRGIN ISLANDS BRITISH","FOREIGN"
"X8","WALLIS AND FUTUNA","FOREIGN"
"U5","WESTERN SAHARA","FOREIGN"
"T7","YEMEN","FOREIGN"
"Y4","ZAMBIA","FOREIGN"
"Y5","ZIMBABWE","FOREIGN"
"XX","UNKNOWN","UNKNOWN"
"""


# SEC place-name → Plotly `locationmode='country names'` renderable name.
COUNTRY_NAME_OVERRIDES: dict[str, str] = {
    "KOREA REPUBLIC OF": "South Korea",
    "KOREA DEMOCRATIC PEOPLE'S REPUBLIC OF": "North Korea",
    "IRAN ISLAMIC REPUBLIC OF": "Iran",
    "CONGO THE DEMOCRATIC REPUBLIC OF THE": "Democratic Republic of the Congo",
    "RUSSIAN FEDERATION": "Russia",
    "TANZANIA UNITED REPUBLIC OF": "Tanzania",
    "VIET NAM": "Vietnam",
    "MACEDONIA THE FORMER YUGOSLAV REPUBLIC OF": "North Macedonia",
    "LIBYAN ARAB JAMAHIRIYA": "Libya",
    "SYRIAN ARAB REPUBLIC": "Syria",
    "MOLDOVA REPUBLIC OF": "Moldova",
    "HOLY SEE (VATICAN CITY STATE)": "Vatican",
    "LAO PEOPLE'S DEMOCRATIC REPUBLIC": "Laos",
    "FALKLAND ISLANDS (MALVINAS)": "Falkland Islands",
    "VIRGIN ISLANDS BRITISH": "British Virgin Islands",
    "VIRGIN ISLANDS U.S.": "United States Virgin Islands",
    "BRUNEI DARUSSALAM": "Brunei",
    "COTE D'IVOIRE": "Ivory Coast",
    "MACAU": "Macao",
    "PALESTINIAN TERRITORY OCCUPIED": "Palestine",
    "MICRONESIA FEDERATED STATES OF": "Micronesia",
    "CANADA (FEDERAL LEVEL)": "Canada",
    "KAZAKSTAN": "Kazakhstan",
}


def _build_place_tables() -> tuple[dict[str, dict[str, str]], set[str]]:
    reader = csv.DictReader(io.StringIO(PLACE_CODES_CSV))
    lookup: dict[str, dict[str, str]] = {}
    us_states = set()
    for row in reader:
        code = row["Code"].strip().upper()
        place = row["Place"].strip()
        place_type = row["Type"].strip().upper()
        lookup[code] = {"place": place, "type": place_type}
        # Two-letter US state codes (not territories) for the US choropleth.
        if place_type == "US" and len(code) == 2 and code.isalpha() and code not in {"GU", "PR", "VI", "X1"}:
            us_states.add(code)
    return lookup, us_states


PLACE_LOOKUP, US_STATE_CODES = _build_place_tables()


def resolve_place_name(code: str | None) -> str:
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return "—"
    key = str(code).strip().upper()
    if not key:
        return "—"
    entry = PLACE_LOOKUP.get(key)
    if entry is None:
        return f"{key} (unrecognized)"
    return entry["place"].title()


def code_to_country_name(code: str | None) -> str | None:
    """Collapse a SEC place code to a Plotly country-names compatible label."""
    if code is None:
        return None
    key = str(code).strip().upper()
    if not key:
        return None
    entry = PLACE_LOOKUP.get(key)
    if entry is None:
        return None
    place_type = entry["type"]
    if place_type == "US":
        return "United States"
    if place_type == "CANADIAN":
        return "Canada"
    if place_type == "FOREIGN":
        place = entry["place"]
        return COUNTRY_NAME_OVERRIDES.get(place, place.title())
    return None  # UNKNOWN


# ---------------------------------------------------------------------------
# Snowflake connection
# ---------------------------------------------------------------------------


def _read_config() -> dict[str, Any] | None:
    cfg_path = pathlib.Path.home() / ".snowflake" / "config.toml"
    if not cfg_path.exists():
        return None
    with open(cfg_path, "rb") as fh:
        toml = tomllib.load(fh)
    conn_name = toml.get("default_connection_name")
    if not conn_name:
        connections = toml.get("connections") or {}
        if not connections:
            return None
        conn_name = next(iter(connections))
    connections = toml.get("connections") or {}
    cfg = connections.get(conn_name)
    if cfg is None:
        return None
    return {"name": conn_name, **cfg}


@st.cache_resource
def get_conn() -> snowflake.connector.SnowflakeConnection:
    cfg = _read_config()
    if cfg is None:
        raise RuntimeError(
            "No Snowflake connection found. Create ~/.snowflake/config.toml with a "
            "[connections.<name>] block and set default_connection_name. See "
            "examples/dashboard/README.md for the expected stanza."
        )
    kwargs: dict[str, Any] = {
        "account": cfg["account"],
        "user": cfg["user"],
        "database": cfg.get("database", DEFAULT_DATABASE),
        "schema": cfg.get("schema", DEFAULT_SCHEMA),
    }
    for key in ("password", "role", "warehouse", "authenticator", "private_key_path", "private_key"):
        if cfg.get(key):
            kwargs[key] = cfg[key]
    return snowflake.connector.connect(**kwargs)


def is_missing_object_error(exc: BaseException) -> bool:
    """True when Snowflake reports a missing object or column: SQLSTATE 42S02/42000 / codes 002003, 000904."""
    msg = str(exc)
    return (
        "does not exist or not authorized" in msg
        or "002003" in msg
        or "invalid identifier" in msg
        or "000904" in msg
    )


def is_auth_error(exc: BaseException) -> bool:
    """True when the Snowflake session/token has expired (390114 / 08001)."""
    msg = str(exc)
    return "390114" in msg or "Authentication token has expired" in msg or "08001" in msg


@st.cache_data(ttl=3600, show_spinner=False)
def q(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """Run SQL, auto-reconnecting once if the cached session token has expired."""
    conn = get_conn()
    for attempt in range(2):
        cur = conn.cursor()
        try:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description]
        except Exception as exc:
            cur.close()
            if attempt == 0 and is_auth_error(exc):
                get_conn.clear()
                q.clear()
                conn = get_conn()
                continue
            raise
        else:
            cur.close()
        df = pd.DataFrame(rows, columns=cols)
        df.columns = df.columns.str.lower()
        return df
    raise RuntimeError("unreachable")  # pragma: no cover


def q_optional(sql: str, params: tuple | None = None) -> pd.DataFrame | None:
    """Like ``q`` but returns None when the target object is missing/unauthorized."""
    try:
        return q(sql, params)
    except Exception as exc:  # noqa: BLE001 — we want to narrow only on the specific Snowflake error
        if is_missing_object_error(exc):
            return None
        raise


def _cfg_summary() -> str:
    cfg = _read_config()
    if cfg is None:
        return "not configured"
    db = cfg.get("database", DEFAULT_DATABASE)
    schema = cfg.get("schema", DEFAULT_SCHEMA)
    wh = cfg.get("warehouse", "—")
    return f"{cfg['name']} · {db}.{schema} · warehouse={wh}"


def qualified(table: str) -> str:
    cfg = _read_config() or {}
    db = cfg.get("database", DEFAULT_DATABASE)
    schema = cfg.get("schema", DEFAULT_SCHEMA)
    return f"{db}.{schema}.{table}"


# ---------------------------------------------------------------------------
# Section: Overview
# ---------------------------------------------------------------------------


def _table_count(table: str) -> int | None:
    df = q_optional(f"select count(*) as c from {qualified(table)}")
    if df is None or df.empty:
        return None
    val = df.iloc[0]["c"]
    return int(val) if val is not None else 0


def _latest_filing_date() -> Any | None:
    df = q_optional(f"select max(filing_date) as d from {qualified('FILING_ACTIVITY')}")
    if df is None or df.empty:
        return None
    return df.iloc[0]["d"]


def _freshness() -> pd.DataFrame | None:
    # The status table's column set varies across gold-schema versions, so we
    # select * and tolerate missing order-by columns. Preference: order by
    # updated_at when present; otherwise just grab any row.
    ordered = q_optional(
        f"select * from {qualified('EDGARTOOLS_GOLD_STATUS')} order by updated_at desc limit 1"
    )
    if ordered is not None:
        return ordered
    return q_optional(f"select * from {qualified('EDGARTOOLS_GOLD_STATUS')} limit 1")


def _top_sic(limit: int = 15) -> pd.DataFrame:
    return q(
        f"""
        select coalesce(nullif(sic_description, ''), 'Unclassified') as industry,
               count(*) as companies
        from {qualified('COMPANY')}
        group by industry
        order by companies desc
        limit {int(limit)}
        """
    )


def _entity_type_mix() -> pd.DataFrame:
    return q(
        f"""
        select coalesce(nullif(entity_type, ''), 'Unknown') as entity_type,
               count(*) as companies
        from {qualified('COMPANY')}
        group by entity_type
        order by companies desc
        """
    )


def render_overview() -> None:
    st.header("📊 Overview")

    # Probe tables individually so missing/unauthorized ones show "—" without
    # hiding the rest of the section.
    try:
        counts = {name: _table_count(name) for name in (
            "COMPANY", "FILING_ACTIVITY", "OWNERSHIP_ACTIVITY", "PRIVATE_FUNDS", "TICKER_REFERENCE",
        )}
    except Exception as exc:
        st.error(f"Unable to query {qualified('COMPANY')}: {exc}")
        st.info("Check your ~/.snowflake/config.toml and the role's grants on EDGARTOOLS_GOLD.")
        return

    missing = [name for name, count in counts.items() if count is None]
    if missing:
        st.warning(
            "Missing or unauthorized tables — showing partial data: "
            + ", ".join(missing)
        )

    def _fmt(n: int | None) -> str:
        return f"{n:,}" if n is not None else "—"

    cols = st.columns(5)
    cols[0].metric("Companies", _fmt(counts["COMPANY"]))
    cols[1].metric("Filings", _fmt(counts["FILING_ACTIVITY"]))
    cols[2].metric("Insider txns", _fmt(counts["OWNERSHIP_ACTIVITY"]))
    cols[3].metric("Private funds", _fmt(counts["PRIVATE_FUNDS"]))
    cols[4].metric("Tickers", _fmt(counts["TICKER_REFERENCE"]))

    latest = _latest_filing_date() if counts["FILING_ACTIVITY"] is not None else None
    st.caption(f"Latest filing date: **{latest if latest is not None else '—'}**")

    fresh = _freshness()
    if fresh is not None and not fresh.empty:
        fr = fresh.iloc[0].to_dict()
        parts = [
            f"{label}={fr[key]}"
            for label, key in (
                ("env", "environment"),
                ("status", "status"),
                ("updated_at", "updated_at"),
                ("business_date", "business_date"),
            )
            if key in fr and fr[key] is not None
        ]
        if parts:
            st.caption("Gold freshness · " + " · ".join(parts))

    st.divider()

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Top industries (SIC)")
        sic = _top_sic()
        if sic.empty:
            st.info("No SIC data.")
        else:
            fig = px.bar(
                sic.sort_values("companies"),
                x="companies",
                y="industry",
                orientation="h",
                color="companies",
                color_continuous_scale="Blues",
                text="companies",
            )
            fig.update_traces(texttemplate="%{text:,}", textposition="outside")
            fig.update_layout(yaxis_title="", xaxis_title="Companies", height=520, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Entity types")
        et = _entity_type_mix()
        if et.empty:
            st.info("No entity type data.")
        else:
            fig = px.pie(et, names="entity_type", values="companies", hole=0.4)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=520, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section: World map
# ---------------------------------------------------------------------------


def _companies_by_state_code() -> pd.DataFrame:
    return q(
        f"""
        select upper(trim(coalesce(state_of_incorporation, ''))) as code,
               count(*) as companies
        from {qualified('COMPANY')}
        group by code
        """
    )


def render_world_map() -> None:
    st.header("🗺️ World & US Map")
    st.info(
        "Locations are derived from **state of incorporation**, not company headquarters. "
        "Many US companies incorporate in **Delaware** for legal reasons regardless of where "
        "they actually operate — a caveat worth remembering when interpreting this map."
    )

    try:
        df = _companies_by_state_code()
    except Exception as exc:
        st.error(f"Unable to read COMPANY: {exc}")
        return

    if df.empty:
        st.info("No companies recorded.")
        return

    df = df.copy()
    df["country"] = df["code"].apply(code_to_country_name)
    missing = df.loc[df["country"].isna(), "companies"].sum()

    world = (
        df.dropna(subset=["country"])
        .groupby("country", as_index=False)["companies"].sum()
        .sort_values("companies", ascending=False)
    )

    st.subheader("World — companies by country of incorporation")
    if world.empty:
        st.info("No resolvable country data.")
    else:
        fig = px.choropleth(
            world,
            locations="country",
            locationmode="country names",
            color="companies",
            color_continuous_scale="Blues",
            hover_data={"companies": ":,"},
        )
        fig.update_layout(
            height=520,
            margin=dict(l=0, r=0, t=10, b=0),
            coloraxis_colorbar=dict(title="Companies"),
        )
        st.plotly_chart(fig, use_container_width=True)

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Top 20 countries")
        top_countries = world.head(20)
        if top_countries.empty:
            st.info("—")
        else:
            fig = px.bar(
                top_countries.sort_values("companies"),
                x="companies",
                y="country",
                orientation="h",
                color="companies",
                color_continuous_scale="Blues",
                text="companies",
            )
            fig.update_traces(texttemplate="%{text:,}", textposition="outside")
            fig.update_layout(yaxis_title="", xaxis_title="Companies", height=560, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with colB:
        st.subheader("Summary")
        total = int(world["companies"].sum()) + int(missing or 0)
        us_row = world.loc[world["country"] == "United States", "companies"]
        us_count = int(us_row.iloc[0]) if not us_row.empty else 0
        foreign_count = int(world.loc[world["country"] != "United States", "companies"].sum())
        st.metric("Total companies", f"{total:,}")
        st.metric("US-incorporated", f"{us_count:,}")
        st.metric("Foreign-incorporated", f"{foreign_count:,}")
        if missing:
            st.caption(f"ℹ️ {int(missing):,} companies have no/unrecognized place code and are excluded from the map.")

    st.divider()

    st.subheader("United States — companies by state of incorporation")
    us = df[df["code"].isin(US_STATE_CODES)].copy()
    if us.empty:
        st.info("No US state data.")
        return
    us["state_name"] = us["code"].apply(resolve_place_name)
    fig = px.choropleth(
        us,
        locations="code",
        locationmode="USA-states",
        color="companies",
        scope="usa",
        color_continuous_scale="Reds",
        hover_data={"state_name": True, "companies": ":,", "code": False},
    )
    fig.update_layout(height=480, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

    top_states = us.sort_values("companies", ascending=False).head(15)
    if not top_states.empty:
        fig = px.bar(
            top_states.sort_values("companies"),
            x="companies",
            y="state_name",
            orientation="h",
            color="companies",
            color_continuous_scale="Reds",
            text="companies",
        )
        fig.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig.update_layout(
            title="Top 15 US states of incorporation",
            yaxis_title="",
            xaxis_title="Companies",
            height=450,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section: Industry & Entity
# ---------------------------------------------------------------------------


def render_industry() -> None:
    st.header("🏭 Industry & Entity")

    sic_top = q(
        f"""
        select coalesce(nullif(sic_description, ''), 'Unclassified') as industry,
               sic,
               count(*) as companies
        from {qualified('COMPANY')}
        group by industry, sic
        order by companies desc
        limit 25
        """
    )

    entity = _entity_type_mix()

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Top 25 industries (SIC)")
        if sic_top.empty:
            st.info("No SIC data.")
        else:
            fig = px.bar(
                sic_top.sort_values("companies"),
                x="companies",
                y="industry",
                orientation="h",
                color="companies",
                color_continuous_scale="Teal",
                text="companies",
                hover_data={"sic": True},
            )
            fig.update_traces(texttemplate="%{text:,}", textposition="outside")
            fig.update_layout(yaxis_title="", xaxis_title="Companies", height=720, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Entity type mix")
        if entity.empty:
            st.info("No entity type data.")
        else:
            fig = px.pie(entity, names="entity_type", values="companies", hole=0.4)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        st.caption("Entity types are filer-reported classifications (corporation, trust, LLC, etc.).")

    st.divider()

    st.subheader("Industry × entity type heatmap (top 15 × top 6)")
    heat = q(
        f"""
        with top_ind as (
          select coalesce(nullif(sic_description, ''), 'Unclassified') as industry, count(*) as c
          from {qualified('COMPANY')}
          group by industry order by c desc limit 15
        ),
        top_ent as (
          select coalesce(nullif(entity_type, ''), 'Unknown') as entity_type, count(*) as c
          from {qualified('COMPANY')}
          group by entity_type order by c desc limit 6
        )
        select i.industry,
               e.entity_type,
               count(c.company_key) as companies
        from top_ind i
        cross join top_ent e
        left join {qualified('COMPANY')} c
          on coalesce(nullif(c.sic_description, ''), 'Unclassified') = i.industry
         and coalesce(nullif(c.entity_type, ''), 'Unknown') = e.entity_type
        group by i.industry, e.entity_type
        """
    )
    if heat.empty:
        st.info("No data for heatmap.")
        return
    pivot = heat.pivot(index="industry", columns="entity_type", values="companies").fillna(0)
    fig = px.imshow(
        pivot,
        color_continuous_scale="Blues",
        aspect="auto",
        labels=dict(color="Companies"),
    )
    fig.update_layout(height=560, xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section: Filing Activity
# ---------------------------------------------------------------------------


def render_filings() -> None:
    st.header("📈 Filing Activity")

    monthly = q_optional(
        f"""
        select date_trunc('month', filing_date) as month, count(*) as filings
        from {qualified('FILING_ACTIVITY')}
        where filing_date is not null
          and filing_date >= dateadd(year, -5, current_date)
        group by month
        order by month
        """
    )

    forms = q_optional(
        f"""
        select form, count(*) as filings
        from {qualified('FILING_ACTIVITY')}
        group by form
        order by filings desc
        limit 20
        """
    )

    xbrl = q_optional(
        f"""
        select date_trunc('month', filing_date) as month,
               sum(case when is_xbrl then 1 else 0 end) as xbrl_filings,
               count(*) as total_filings
        from {qualified('FILING_ACTIVITY')}
        where filing_date is not null
          and filing_date >= dateadd(year, -5, current_date)
        group by month
        order by month
        """
    )

    top_filers = q_optional(
        f"""
        select c.entity_name, count(*) as filings
        from {qualified('FILING_ACTIVITY')} f
        join {qualified('COMPANY')} c on c.company_key = f.company_key
        group by c.entity_name
        order by filings desc
        limit 15
        """
    )

    if monthly is None:
        st.warning("FILING_ACTIVITY is missing or unauthorized — this section cannot render.")
        return

    st.subheader("Monthly filing volume (last 5 years)")
    if monthly.empty:
        st.info("No filings recorded.")
    else:
        fig = px.area(monthly, x="month", y="filings")
        fig.update_layout(xaxis_title="Month", yaxis_title="Filings", height=320)
        st.plotly_chart(fig, use_container_width=True)

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Top 20 forms")
        if forms is None or forms.empty:
            st.info("—")
        else:
            fig = px.bar(
                forms.sort_values("filings"),
                x="filings",
                y="form",
                orientation="h",
                color="filings",
                color_continuous_scale="Greens",
                text="filings",
            )
            fig.update_traces(texttemplate="%{text:,}", textposition="outside")
            fig.update_layout(yaxis_title="", xaxis_title="Filings", height=560, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with colB:
        st.subheader("Top 15 filers (all time)")
        if top_filers is None or top_filers.empty:
            st.info("—")
        else:
            fig = px.bar(
                top_filers.sort_values("filings"),
                x="filings",
                y="entity_name",
                orientation="h",
                color="filings",
                color_continuous_scale="Purples",
                text="filings",
            )
            fig.update_traces(texttemplate="%{text:,}", textposition="outside")
            fig.update_layout(yaxis_title="", xaxis_title="Filings", height=560, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("XBRL adoption rate (share of monthly filings flagged is_xbrl)")
    if xbrl is None or xbrl.empty:
        st.info("No XBRL data.")
    else:
        xbrl = xbrl.copy()
        xbrl["xbrl_pct"] = (xbrl["xbrl_filings"] / xbrl["total_filings"].replace({0: pd.NA})) * 100
        fig = px.line(xbrl, x="month", y="xbrl_pct", markers=True)
        fig.update_layout(xaxis_title="Month", yaxis_title="% XBRL", height=320, yaxis=dict(ticksuffix="%"))
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section: Ownership & Funds
# ---------------------------------------------------------------------------


def render_ownership() -> None:
    st.header("💼 Ownership & Funds")

    top_insider = q_optional(
        f"""
        select c.entity_name, count(*) as txns,
               sum(coalesce(o.transaction_shares, 0)) as total_shares_reported
        from {qualified('OWNERSHIP_ACTIVITY')} o
        join {qualified('COMPANY')} c on c.company_key = o.company_key
        group by c.entity_name
        order by txns desc
        limit 20
        """
    )

    recent_txns = q_optional(
        f"""
        select f.filing_date as txn_date,
               c.entity_name,
               o.transaction_code,
               o.transaction_shares,
               o.transaction_price,
               o.shares_owned_after,
               o.is_derivative,
               o.accession_number
        from {qualified('OWNERSHIP_ACTIVITY')} o
        join {qualified('COMPANY')} c on c.company_key = o.company_key
        join {qualified('FILING_ACTIVITY')} f on f.accession_number = o.accession_number
        where f.filing_date >= dateadd(day, -90, current_date)
        order by f.filing_date desc, c.entity_name
        limit 250
        """
    )

    aum = q_optional(
        f"""
        select aum_amount
        from {qualified('PRIVATE_FUNDS')}
        where aum_amount is not null and aum_amount > 0
        """
    )

    top_advisers = q_optional(
        f"""
        select c.entity_name, count(distinct p.private_fund_key) as funds,
               sum(coalesce(p.aum_amount, 0)) as total_aum
        from {qualified('PRIVATE_FUNDS')} p
        join {qualified('COMPANY')} c on c.company_key = p.company_key
        group by c.entity_name
        order by funds desc
        limit 15
        """
    )

    unavailable = []
    if top_insider is None or recent_txns is None:
        unavailable.append("OWNERSHIP_ACTIVITY")
    if aum is None or top_advisers is None:
        unavailable.append("PRIVATE_FUNDS")
    if unavailable:
        st.warning(
            "The following tables are missing or unauthorized for this role — related charts are skipped: "
            + ", ".join(sorted(set(unavailable)))
        )

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Top 20 companies by insider transaction count")
        if top_insider is None:
            st.info("OWNERSHIP_ACTIVITY not available.")
        elif top_insider.empty:
            st.info("No insider activity.")
        else:
            fig = px.bar(
                top_insider.sort_values("txns"),
                x="txns",
                y="entity_name",
                orientation="h",
                color="txns",
                color_continuous_scale="Oranges",
                text="txns",
            )
            fig.update_traces(texttemplate="%{text:,}", textposition="outside")
            fig.update_layout(yaxis_title="", xaxis_title="Transactions", height=620, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with colB:
        st.subheader("Private fund AUM distribution (log scale)")
        if aum is None:
            st.info("PRIVATE_FUNDS not available.")
        elif aum.empty:
            st.info("No AUM data.")
        else:
            aum_pos = aum[aum["aum_amount"] > 0].copy()
            fig = px.histogram(aum_pos, x="aum_amount", nbins=60, log_x=True, log_y=True)
            fig.update_layout(
                xaxis_title="AUM ($, log)",
                yaxis_title="Funds (log)",
                height=620,
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Top 15 advisers by reported private fund count")
    if top_advisers is None:
        st.info("PRIVATE_FUNDS not available.")
    elif top_advisers.empty:
        st.info("No adviser data.")
    else:
        display = top_advisers.copy()
        display["total_aum_b"] = display["total_aum"].astype(float) / 1e9
        fig = px.bar(
            display.sort_values("funds"),
            x="funds",
            y="entity_name",
            orientation="h",
            color="total_aum_b",
            color_continuous_scale="Viridis",
            text="funds",
            hover_data={"total_aum_b": ":.2f", "funds": ":,"},
            labels={"total_aum_b": "AUM ($B)"},
        )
        fig.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig.update_layout(yaxis_title="", xaxis_title="Reported funds", height=560)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Recent insider transactions (last 90 days)")
    if recent_txns is None:
        st.info("OWNERSHIP_ACTIVITY not available.")
    elif recent_txns.empty:
        st.info("No insider transactions in the last 90 days.")
    else:
        st.dataframe(recent_txns, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Section: Company Lookup
# ---------------------------------------------------------------------------


def _lookup_companies(query_str: str) -> pd.DataFrame:
    pattern = f"%{query_str}%"
    return q(
        f"""
        select distinct c.company_key, c.cik, c.entity_name, c.sic_description,
               c.state_of_incorporation
        from {qualified('COMPANY')} c
        left join {qualified('TICKER_REFERENCE')} t on t.cik = c.cik
        where c.entity_name ilike %s
           or t.ticker ilike %s
        order by c.entity_name
        limit 25
        """,
        params=(pattern, pattern),
    )


def _company_metadata(company_key: int) -> pd.DataFrame:
    return q(
        f"""
        select c.cik, c.entity_name, c.entity_type, c.sic, c.sic_description,
               c.state_of_incorporation, c.fiscal_year_end,
               listagg(distinct t.ticker, ', ') within group (order by t.ticker) as tickers,
               listagg(distinct t.exchange, ', ') within group (order by t.exchange) as exchanges
        from {qualified('COMPANY')} c
        left join {qualified('TICKER_REFERENCE')} t on t.cik = c.cik
        where c.company_key = %s
        group by c.cik, c.entity_name, c.entity_type, c.sic, c.sic_description,
                 c.state_of_incorporation, c.fiscal_year_end
        """,
        params=(int(company_key),),
    )


def _company_form_counts(company_key: int) -> pd.DataFrame:
    return q(
        f"""
        select form, count(*) as filings
        from {qualified('FILING_ACTIVITY')}
        where company_key = %s
        group by form
        order by filings desc
        """,
        params=(int(company_key),),
    )


def _company_timeline(company_key: int) -> pd.DataFrame:
    return q(
        f"""
        select date_trunc('month', filing_date) as month, count(*) as filings
        from {qualified('FILING_ACTIVITY')}
        where company_key = %s and filing_date is not null
        group by month
        order by month
        """,
        params=(int(company_key),),
    )


def _company_recent_filings(company_key: int, limit: int = 250) -> pd.DataFrame:
    return q(
        f"""
        select filing_date, form, accession_number, report_date, is_xbrl
        from {qualified('FILING_ACTIVITY')}
        where company_key = %s
        order by filing_date desc nulls last
        limit {int(limit)}
        """,
        params=(int(company_key),),
    )


def render_lookup() -> None:
    st.header("🔎 Company Lookup")
    query_str = st.text_input("Search by ticker or company name", placeholder="e.g. AAPL or Apple")
    if not query_str.strip():
        st.info("Enter a ticker symbol or part of a company name to start.")
        return

    matches = _lookup_companies(query_str.strip())
    if matches.empty:
        st.warning(f"No companies matched '{query_str}'.")
        return

    matches = matches.copy()
    matches["label"] = matches.apply(
        lambda r: f"{r['entity_name']} — CIK {int(r['cik'])}", axis=1
    )
    label = st.selectbox("Matches", matches["label"].tolist())
    selected = matches.loc[matches["label"] == label].iloc[0]
    company_key = int(selected["company_key"])

    meta = _company_metadata(company_key)
    if meta.empty:
        st.error("Selected company not found.")
        return
    row = meta.iloc[0]

    st.subheader(row["entity_name"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CIK", int(row["cik"]))
    c2.metric("Tickers", row["tickers"] or "—")
    c3.metric("Exchanges", row["exchanges"] or "—")
    c4.metric("Entity type", row["entity_type"] or "—")

    state_code = row["state_of_incorporation"]
    with st.expander("Metadata", expanded=True):
        st.write(
            {
                "SIC": row["sic"] or "—",
                "SIC description": row["sic_description"] or "—",
                "State of incorporation": f"{state_code or '—'} — {resolve_place_name(state_code)}",
                "Fiscal year end": row["fiscal_year_end"] or "—",
            }
        )
    st.markdown(
        f"[🔗 View on SEC Edgar](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={int(row['cik']):010d})"
    )

    st.divider()
    colA, colB = st.columns(2)
    with colA:
        st.subheader("Filings by form")
        forms = _company_form_counts(company_key)
        if forms.empty:
            st.info("No filings recorded for this company.")
        else:
            fig = px.bar(forms, x="form", y="filings", color="filings", color_continuous_scale="Blues")
            fig.update_layout(xaxis_title="Form", yaxis_title="Filings", height=380, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with colB:
        st.subheader("Filing timeline")
        timeline = _company_timeline(company_key)
        if timeline.empty:
            st.info("No dated filings.")
        else:
            fig = px.line(timeline, x="month", y="filings", markers=True)
            fig.update_layout(xaxis_title="Month", yaxis_title="Filings", height=380)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Recent filings")
    recent = _company_recent_filings(company_key)
    if recent.empty:
        st.info("No filings to display.")
    else:
        st.dataframe(recent, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------


SECTIONS: dict[str, Any] = {
    "📊 Overview": render_overview,
    "🗺️ World & US Map": render_world_map,
    "🏭 Industry & Entity": render_industry,
    "📈 Filing Activity": render_filings,
    "💼 Ownership & Funds": render_ownership,
    "🔎 Company Lookup": render_lookup,
}


def main() -> None:
    st.set_page_config(
        page_title="EdgarTools Universe",
        page_icon="🌐",
        layout="wide",
    )
    st.sidebar.title("EdgarTools Universe")
    st.sidebar.caption("Streamlit over EDGARTOOLS_GOLD")
    section_name = st.sidebar.radio("Section", list(SECTIONS.keys()))
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh data", use_container_width=True):
        q.clear()
        st.rerun()
    st.sidebar.caption(f"Connection · {_cfg_summary()}")
    SECTIONS[section_name]()


if __name__ == "__main__":
    main()
