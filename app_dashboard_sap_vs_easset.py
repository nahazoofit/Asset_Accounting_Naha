import re
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


# =========================================================
# KONFIGURASI HALAMAN
# =========================================================
st.set_page_config(
    page_title="Dashboard SAP vs E-Asset",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp { background-color: #f4f7fb; }
        [data-testid="stSidebar"] { background: #132238; }
        [data-testid="stSidebar"] * { color: #ffffff; }
        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stMultiSelect label {
            color: #ffffff !important;
            font-weight: 700;
        }
        /* Pastikan tulisan dalam kotak filter jelas */
        [data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #132238 !important;
        }
        [data-testid="stSidebar"] div[data-baseweb="select"] *,
        [data-testid="stSidebar"] div[data-baseweb="select"] input,
        [data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] p {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        /* Teks pilihan semasa dalam filter Kategori Aset */
        [data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        [data-testid="stSidebar"] div[data-baseweb="select"] svg {
            color: #000000 !important;
            fill: #000000 !important;
        }
        div[data-baseweb="popover"] *,
        ul[role="listbox"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        [data-testid="stSidebar"] div[data-baseweb="tag"] {
            background-color: #dceaf7 !important;
        }
        [data-testid="stSidebar"] div[data-baseweb="tag"] span {
            color: #132238 !important;
        }
        .hero {
            padding: 1.20rem 1.45rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #102a43 0%, #1f5f8b 100%);
            color: white;
            margin-bottom: 1rem;
            box-shadow: 0 10px 28px rgba(16, 42, 67, 0.16);
        }
        .hero h1 { margin: 0; font-size: 2rem; }
        .hero p { margin: .35rem 0 0; opacity: .86; }
        .kpi-card {
            background: white;
            border: 1px solid #e6edf5;
            border-radius: 16px;
            padding: 1.10rem 1.20rem;
            box-shadow: 0 6px 20px rgba(15, 40, 65, 0.07);
            min-height: 128px;
        }
        .kpi-label {
            color: #60758a;
            font-size: .88rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .03em;
        }
        .kpi-value {
            color: #132238;
            font-size: 2.15rem;
            font-weight: 800;
            line-height: 1.2;
            margin-top: .4rem;
        }
        .kpi-note { color: #7b8fa3; font-size: .82rem; margin-top: .35rem; }
        .section-title {
            font-size: 1.15rem;
            font-weight: 800;
            color: #183b56;
            margin: .7rem 0 .5rem;
        }
        div[data-testid="stDataFrame"] {
            background: white;
            padding: .4rem;
            border-radius: 14px;
            border: 1px solid #e6edf5;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# FUNGSI UTILITI
# =========================================================
def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


def find_column(df: pd.DataFrame, candidates: list[str]) -> str:
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lookup:
            return lookup[key]
    raise KeyError(
        f"Kolum tidak ditemui. Kolum diperlukan: {', '.join(candidates)}. "
        f"Kolum tersedia: {', '.join(map(str, df.columns))}"
    )


def normalize_asset_no(series: pd.Series) -> pd.Series:
    """Standardkan nombor aset supaya 100000004.0 menjadi 100000004."""
    out = series.astype("string").str.strip()
    out = out.str.replace(r"\.0$", "", regex=True)
    out = out.str.replace(r"\s+", "", regex=True)
    out = out.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "<NA>": pd.NA})
    return out


def normalize_eval_group(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip().str.upper()
    return out.replace({"": pd.NA, "NAN": pd.NA, "NONE": pd.NA, "<NA>": pd.NA})


def asset_category(asset_no: pd.Series) -> pd.Series:
    """Klasifikasi aset berdasarkan nombor aset SAP.

    Aset Tak Alih  : nombor aset 299999999 dan ke bawah.
    Aset Alih      : nombor aset 300000000 hingga 799999999.
    Aset Tak Ketara: nombor aset 800000000 hingga 999999999.
    """
    numeric = pd.to_numeric(asset_no, errors="coerce")
    category = pd.Series("Lain-lain", index=asset_no.index, dtype="string")

    category.loc[numeric.between(0, 299_999_999, inclusive="both")] = "Aset Tak Alih"
    category.loc[numeric.between(300_000_000, 799_999_999, inclusive="both")] = "Aset Alih"
    category.loc[numeric.between(800_000_000, 999_999_999, inclusive="both")] = "Aset Tak Ketara"
    return category


def deduplicate_assets(df: pd.DataFrame, asset_col: str, eval_col: str) -> pd.DataFrame:
    """Ambil satu rekod bagi setiap nombor aset secara pantas."""
    if df.empty:
        return df.copy()
    result = df.drop_duplicates(subset=[asset_col], keep="first").copy()
    result[asset_col] = normalize_asset_no(result[asset_col])
    result[eval_col] = normalize_eval_group(result[eval_col])
    return result


@st.cache_data(show_spinner=False)
def load_excel(file_path: str, modified_time: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    del modified_time
    book = pd.ExcelFile(file_path)
    required = ["Aset_SAP_Raw", "E_Aset_Raw", "DIM Eva grp 1"]
    missing = [sheet for sheet in required if sheet not in book.sheet_names]
    if missing:
        raise ValueError(f"Sheet berikut tiada dalam Excel: {', '.join(missing)}")

    sap = clean_column_names(pd.read_excel(file_path, sheet_name="Aset_SAP_Raw"))
    easset = clean_column_names(pd.read_excel(file_path, sheet_name="E_Aset_Raw"))
    dim = clean_column_names(pd.read_excel(file_path, sheet_name="DIM Eva grp 1"))
    return sap, easset, dim


def prepare_data(sap: pd.DataFrame, easset: pd.DataFrame, dim: pd.DataFrame):
    sap_asset_col = find_column(sap, ["No. Aset SAP", "No Aset SAP"])
    sap_eval_col = find_column(sap, ["Eval Group 1", "Eval. Group 1"])
    easset_asset_col = find_column(easset, ["No. Aset SAP", "No Aset SAP"])
    easset_eval_col = find_column(easset, ["Eval Group 1", "Eval. Group 1"])
    dim_eval_col = find_column(dim, ["Eval Group 1", "Eval. Group 1"])
    dim_ptj_col = find_column(dim, ["Detail 3", "PTJ"])

    sap = sap.copy()
    easset = easset.copy()
    dim = dim.copy()

    sap["No. Aset SAP"] = normalize_asset_no(sap[sap_asset_col])
    sap["Eval Group 1"] = normalize_eval_group(sap[sap_eval_col])
    easset["No. Aset SAP"] = normalize_asset_no(easset[easset_asset_col])
    easset["Eval Group 1"] = normalize_eval_group(easset[easset_eval_col])

    # Nama aset diseragamkan untuk dipaparkan dalam semua jadual perbandingan.
    if "Asset Description" in sap.columns:
        sap["Nama Aset"] = sap["Asset Description"].astype("string").str.strip()
        if "Asset Description_1" in sap.columns:
            tambahan = sap["Asset Description_1"].astype("string").str.strip()
            sap["Nama Aset"] = (
                sap["Nama Aset"].fillna("") + " " + tambahan.fillna("")
            ).str.replace(r"\s+", " ", regex=True).str.strip()
    else:
        sap["Nama Aset"] = pd.NA

    if "Jenis" in easset.columns:
        easset["Nama Aset"] = easset["Jenis"].astype("string").str.strip()
        if "Jenama" in easset.columns:
            jenama = easset["Jenama"].astype("string").str.strip()
            easset["Nama Aset"] = (
                easset["Nama Aset"].fillna("") + " - " + jenama.fillna("")
            ).str.replace(r"\s+-\s*$", "", regex=True).str.strip()
    else:
        easset["Nama Aset"] = pd.NA

    # Buang rekod tanpa nombor aset.
    sap = sap[sap["No. Aset SAP"].notna()].copy()
    easset = easset[easset["No. Aset SAP"].notna()].copy()

    dim["Eval Group 1"] = normalize_eval_group(dim[dim_eval_col])
    dim["PTJ"] = dim[dim_ptj_col].astype("string").str.strip()
    ptj_map = (
        dim.dropna(subset=["Eval Group 1"])
        .drop_duplicates("Eval Group 1")
        .set_index("Eval Group 1")["PTJ"]
        .to_dict()
    )

    sap["Kategori Aset"] = asset_category(sap["No. Aset SAP"])
    easset["Kategori Aset"] = asset_category(easset["No. Aset SAP"])
    sap["PTJ"] = sap["Eval Group 1"].map(ptj_map).fillna("Tidak Dipetakan")
    easset["PTJ"] = easset["Eval Group 1"].map(ptj_map).fillna("Tidak Dipetakan")

    sap_unique = deduplicate_assets(sap, "No. Aset SAP", "Eval Group 1")
    easset_unique = deduplicate_assets(easset, "No. Aset SAP", "Eval Group 1")

    return sap_unique, easset_unique


def filter_source(df: pd.DataFrame, category: str, selected_ptj: list[str]) -> pd.DataFrame:
    result = df.copy()
    if category != "Semua":
        result = result[result["Kategori Aset"] == category]
    if selected_ptj:
        result = result[result["PTJ"].isin(selected_ptj)]
    return result


def build_comparison(sap: pd.DataFrame, easset: pd.DataFrame):
    sap_ids = set(sap["No. Aset SAP"].dropna())
    easset_ids = set(easset["No. Aset SAP"].dropna())

    only_sap = sap[sap["No. Aset SAP"].isin(sap_ids - easset_ids)].copy()
    only_easset = easset[easset["No. Aset SAP"].isin(easset_ids - sap_ids)].copy()

    sap_location = sap[["No. Aset SAP", "Nama Aset", "Eval Group 1", "PTJ", "Kategori Aset"]].rename(
        columns={
            "Nama Aset": "Nama Aset SAP",
            "Eval Group 1": "Eval Group SAP",
            "PTJ": "PTJ SAP",
        }
    )
    easset_location = easset[["No. Aset SAP", "Nama Aset", "Eval Group 1", "PTJ"]].rename(
        columns={
            "Nama Aset": "Nama Aset E-Asset",
            "Eval Group 1": "Eval Group E-Asset",
            "PTJ": "PTJ E-Asset",
        }
    )

    matched = sap_location.merge(easset_location, on="No. Aset SAP", how="inner")
    different_location = matched[
        matched["Eval Group SAP"].fillna("") != matched["Eval Group E-Asset"].fillna("")
    ].copy()

    return only_sap, only_easset, different_location


def kpi_card(label: str, value: int, note: str, icon: str):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{icon} {label}</div>
            <div class="kpi-value">{value:,}</div>
            <div class="kpi-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def count_by_column(df: pd.DataFrame, column: str, value_name: str = "Jumlah Aset") -> pd.DataFrame:
    """Sediakan ringkasan bilangan aset bagi tujuan graf."""
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=[value_name])

    chart_data = (
        df[column]
        .fillna("Tidak Dipetakan")
        .astype(str)
        .value_counts()
        .rename(value_name)
        .to_frame()
    )
    chart_data.index.name = column
    return chart_data


def show_empty_chart_message():
    st.info("Tiada data untuk dipaparkan dalam graf berdasarkan tapisan semasa.")


def _extract_selection_rows(event, selection_name: str) -> list[dict]:
    """Baca selection Altair dengan selamat untuk pelbagai versi Streamlit."""
    try:
        selection = event.selection.get(selection_name, [])
    except Exception:
        try:
            selection = event.get("selection", {}).get(selection_name, [])
        except Exception:
            return []

    if selection is None:
        return []

    # Bentuk biasa: [{"PTJ": "..."}]
    if isinstance(selection, list):
        return [row for row in selection if isinstance(row, dict)]

    # Sesetengah versi memulangkan {"PTJ": ["..."]}
    if isinstance(selection, dict):
        keys = list(selection.keys())
        if not keys:
            return []
        max_len = max(
            len(v) if isinstance(v, list) else 1
            for v in selection.values()
        )
        rows = []
        for i in range(max_len):
            row = {}
            for key, value in selection.items():
                if isinstance(value, list):
                    if i < len(value):
                        row[key] = value[i]
                else:
                    row[key] = value
            rows.append(row)
        return rows

    return []


def interactive_ptj_chart(
    df: pd.DataFrame,
    ptj_column: str,
    chart_key: str,
    title: str,
    series_label: str = "Jumlah Aset",
    ptj_label_color: str = "#132238",
):
    """Papar graf PTJ yang boleh diklik dan pulangkan PTJ yang dipilih."""
    if df.empty or ptj_column not in df.columns:
        show_empty_chart_message()
        return None

    chart_df = (
        df[ptj_column]
        .fillna("Tidak Dipetakan")
        .astype(str)
        .value_counts()
        .rename_axis("PTJ")
        .reset_index(name="Jumlah Aset")
        .sort_values("Jumlah Aset", ascending=False)
    )

    selection_name = f"{chart_key}_selection"
    selector = alt.selection_point(
        name=selection_name,
        fields=["PTJ"],
        clear="dblclick",
    )

    chart = (
        alt.Chart(chart_df)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X(
                "PTJ:N",
                sort="-y",
                title="PTJ",
                axis=alt.Axis(
                    labelAngle=-45,
                    labelColor=ptj_label_color,
                    titleColor=ptj_label_color,
                    labelFontWeight="bold",
                    labelOverlap=False,
                    labelLimit=0,
                    labelBound=False,
                ),
            ),
            y=alt.Y("Jumlah Aset:Q", title=series_label),
            opacity=alt.condition(selector, alt.value(1.0), alt.value(0.45)),
            tooltip=[
                alt.Tooltip("PTJ:N", title="PTJ"),
                alt.Tooltip("Jumlah Aset:Q", title=series_label, format=","),
            ],
        )
        .add_params(selector)
        .properties(title=title, height=390)
    )

    event = st.altair_chart(
        chart,
        use_container_width=True,
        key=chart_key,
        on_select="rerun",
        selection_mode=selection_name,
    )

    rows = _extract_selection_rows(event, selection_name)
    if rows:
        selected_ptj = rows[0].get("PTJ")
        if selected_ptj is not None:
            return str(selected_ptj)
    return None


def interactive_location_chart(df: pd.DataFrame, chart_key: str):
    """Graf lokasi interaktif; klik bar untuk tapis ikut PTJ dan sumber lokasi."""
    if df.empty:
        show_empty_chart_message()
        return None, None

    sap_chart = (
        df["PTJ SAP"]
        .fillna("Tidak Dipetakan")
        .astype(str)
        .value_counts()
        .rename_axis("PTJ")
        .reset_index(name="Jumlah Aset")
    )
    sap_chart["Sumber Lokasi"] = "Lokasi dalam SAP"

    easset_chart = (
        df["PTJ E-Asset"]
        .fillna("Tidak Dipetakan")
        .astype(str)
        .value_counts()
        .rename_axis("PTJ")
        .reset_index(name="Jumlah Aset")
    )
    easset_chart["Sumber Lokasi"] = "Lokasi dalam E-Asset"

    chart_df = pd.concat([sap_chart, easset_chart], ignore_index=True)

    selection_name = f"{chart_key}_selection"
    selector = alt.selection_point(
        name=selection_name,
        fields=["PTJ", "Sumber Lokasi"],
        clear="dblclick",
    )

    chart = (
        alt.Chart(chart_df)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X(
                "PTJ:N",
                sort="-y",
                title="PTJ",
                axis=alt.Axis(
                    labelAngle=-45,
                    labelOverlap=False,
                    labelLimit=0,
                    labelBound=False,
                ),
            ),
            y=alt.Y("Jumlah Aset:Q", title="Jumlah Aset"),
            xOffset=alt.XOffset("Sumber Lokasi:N"),
            color=alt.Color("Sumber Lokasi:N", title="Sumber Lokasi"),
            opacity=alt.condition(selector, alt.value(1.0), alt.value(0.45)),
            tooltip=[
                alt.Tooltip("PTJ:N", title="PTJ"),
                alt.Tooltip("Sumber Lokasi:N", title="Sumber"),
                alt.Tooltip("Jumlah Aset:Q", title="Jumlah Aset", format=","),
            ],
        )
        .add_params(selector)
        .properties(title="Aset Berlainan Lokasi Mengikut PTJ", height=420)
    )

    event = st.altair_chart(
        chart,
        use_container_width=True,
        key=chart_key,
        on_select="rerun",
        selection_mode=selection_name,
    )

    rows = _extract_selection_rows(event, selection_name)
    if rows:
        point = rows[0]
        selected_ptj = point.get("PTJ")
        selected_source = point.get("Sumber Lokasi")
        if selected_ptj is not None and selected_source is not None:
            return str(selected_ptj), str(selected_source)
    return None, None


# =========================================================
# SUMBER FAIL DAN PROSES DATA
# =========================================================
APP_DIR = Path(__file__).resolve().parent
EXCEL_FILE = APP_DIR / "Working Laporan Asset SAP_EAsset.xlsx"

with st.sidebar:
    st.markdown("## 📊 Dashboard Aset")
    st.caption("Perbandingan rekod SAP dan E-Asset")

if not EXCEL_FILE.exists():
    st.error(
        "Fail Excel tidak ditemui. Pastikan fail "
        "`Working Laporan Asset SAP_EAsset.xlsx` berada dalam folder GitHub "
        "yang sama dengan fail aplikasi Python."
    )
    st.stop()

try:
    with st.spinner("Memproses data aset..."):
        sap_raw, easset_raw, dim_raw = load_excel(
            str(EXCEL_FILE), EXCEL_FILE.stat().st_mtime
        )
        sap_data, easset_data = prepare_data(sap_raw, easset_raw, dim_raw)
except Exception as exc:
    st.exception(exc)
    st.stop()


# =========================================================
# FILTER SIDEBAR
# =========================================================
all_ptj = sorted(
    set(sap_data["PTJ"].dropna().astype(str))
    | set(easset_data["PTJ"].dropna().astype(str))
)

with st.sidebar:
    st.markdown("---")
    category_filter = st.selectbox(
        "Kategori Aset",
        ["Semua", "Aset Tak Alih", "Aset Alih", "Aset Tak Ketara"],
        index=0,
    )
    ptj_filter = st.multiselect(
        "PTJ",
        options=all_ptj,
        placeholder="Semua PTJ",
    )
    st.markdown("---")
    st.caption("Sumber: Aset_SAP_Raw, E_Aset_Raw dan DIM Eva grp 1")

sap_filtered = filter_source(sap_data, category_filter, ptj_filter)
easset_filtered = filter_source(easset_data, category_filter, ptj_filter)
only_sap, only_easset, different_location = build_comparison(sap_filtered, easset_filtered)


# =========================================================
# PAPARAN UTAMA
# =========================================================
st.markdown(
    """
    <div class="hero">
        <h1>Dashboard SAP vs E-Asset</h1>
        <p>Analisis kesepadanan aset berdasarkan nombor aset, lokasi dan PTJ.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

active_filters = [f"Kategori: {category_filter}"]
active_filters.append(f"PTJ: {', '.join(ptj_filter)}" if ptj_filter else "PTJ: Semua")
st.caption(" | ".join(active_filters))

col1, col2, col3 = st.columns(3)
with col1:
    kpi_card("Hanya di SAP", len(only_sap), "Wujud dalam SAP tetapi tiada dalam E-Asset", "🟦")
with col2:
    kpi_card("Hanya di E-Asset", len(only_easset), "Wujud dalam E-Asset tetapi tiada dalam SAP", "🟩")
with col3:
    kpi_card(
        "Aset Berlainan Lokasi",
        len(different_location),
        "Nombor aset sama tetapi Eval Group 1 berbeza",
        "🟧",
    )

st.markdown("<div class='section-title'>Ringkasan Data Ditapis</div>", unsafe_allow_html=True)
summary1, summary2 = st.columns(2)
summary1.metric("Jumlah Aset SAP", f"{len(sap_filtered):,}")
summary2.metric("Jumlah Aset E-Asset", f"{len(easset_filtered):,}")

st.markdown("<div class='section-title'>Graf Ringkasan Laporan</div>", unsafe_allow_html=True)
overall_chart = pd.DataFrame(
    {
        "Jenis Laporan": ["Hanya di SAP", "Hanya di E-Asset", "Berlainan Lokasi"],
        "Jumlah Aset": [len(only_sap), len(only_easset), len(different_location)],
    }
).set_index("Jenis Laporan")
st.bar_chart(overall_chart, use_container_width=True, height=360)

st.markdown("<div class='section-title'>Butiran Perbandingan</div>", unsafe_allow_html=True)
tab_sap, tab_easset, tab_location = st.tabs(
    [
        f"Hanya di SAP ({len(only_sap):,})",
        f"Hanya di E-Asset ({len(only_easset):,})",
        f"Berlainan Lokasi ({len(different_location):,})",
    ]
)

with tab_sap:
    st.markdown("#### Graf Hanya di SAP Mengikut PTJ")
    selected_sap_ptj = interactive_ptj_chart(
        only_sap,
        "PTJ",
        "chart_only_sap_ptj",
        "Hanya di SAP Mengikut PTJ",
        ptj_label_color="#d62828",
    )

    sap_report = only_sap.copy()
    if selected_sap_ptj:
        sap_report = sap_report[
            sap_report["PTJ"].fillna("Tidak Dipetakan").astype(str) == selected_sap_ptj
        ].copy()
        st.success(f"Paparan ditapis mengikut PTJ: **{selected_sap_ptj}**")
        st.caption("Klik dua kali pada graf untuk membuang pilihan PTJ.")

    preferred = [
        "No. Aset SAP", "Nama Aset", "Eval Group 1", "PTJ", "Kategori Aset",
        "Acquis.val.", "Book val."
    ]
    columns = [c for c in preferred if c in sap_report.columns]
    st.caption(f"Jumlah rekod dipaparkan: {len(sap_report):,}")
    st.dataframe(sap_report[columns], use_container_width=True, hide_index=True, height=470)
    st.download_button(
        "Muat turun CSV — Hanya di SAP",
        sap_report[columns].to_csv(index=False).encode("utf-8-sig"),
        file_name=(
            f"hanya_di_sap_{selected_sap_ptj}.csv"
            if selected_sap_ptj else "hanya_di_sap.csv"
        ),
        mime="text/csv",
    )

with tab_easset:
    st.markdown("#### Graf Hanya di E-Asset Mengikut PTJ")
    selected_easset_ptj = interactive_ptj_chart(
        only_easset,
        "PTJ",
        "chart_only_easset_ptj",
        "Hanya di E-Asset Mengikut PTJ",
    )

    easset_report = only_easset.copy()
    if selected_easset_ptj:
        easset_report = easset_report[
            easset_report["PTJ"].fillna("Tidak Dipetakan").astype(str) == selected_easset_ptj
        ].copy()
        st.success(f"Paparan ditapis mengikut PTJ: **{selected_easset_ptj}**")
        st.caption("Klik dua kali pada graf untuk membuang pilihan PTJ.")

    preferred = [
        "No. Aset SAP", "Nama Aset", "No. Siri Pendaftaran", "Eval Group 1", "PTJ",
        "Kategori Aset", "Lokasi", "Pegawai Penempatan", "Harga (RM)"
    ]
    columns = [c for c in preferred if c in easset_report.columns]
    st.caption(f"Jumlah rekod dipaparkan: {len(easset_report):,}")
    st.dataframe(easset_report[columns], use_container_width=True, hide_index=True, height=470)
    st.download_button(
        "Muat turun CSV — Hanya di E-Asset",
        easset_report[columns].to_csv(index=False).encode("utf-8-sig"),
        file_name=(
            f"hanya_di_easset_{selected_easset_ptj}.csv"
            if selected_easset_ptj else "hanya_di_easset.csv"
        ),
        mime="text/csv",
    )

with tab_location:
    st.markdown("#### Graf Aset Berlainan Lokasi Mengikut PTJ")
    selected_location_ptj, selected_location_source = interactive_location_chart(
        different_location,
        "chart_different_location_ptj",
    )

    location_report = different_location.copy()
    if selected_location_ptj and selected_location_source:
        filter_column = (
            "PTJ SAP"
            if selected_location_source == "Lokasi dalam SAP"
            else "PTJ E-Asset"
        )
        location_report = location_report[
            location_report[filter_column]
            .fillna("Tidak Dipetakan")
            .astype(str)
            == selected_location_ptj
        ].copy()
        st.success(
            f"Paparan ditapis: **{selected_location_ptj}** — "
            f"{selected_location_source}"
        )
        st.caption("Klik dua kali pada graf untuk membuang pilihan PTJ.")

    location_columns = [
        "No. Aset SAP", "Nama Aset E-Asset", "Kategori Aset",
        "Eval Group SAP", "PTJ SAP", "Eval Group E-Asset", "PTJ E-Asset"
    ]
    st.caption(f"Jumlah rekod dipaparkan: {len(location_report):,}")
    st.dataframe(
        location_report[location_columns],
        use_container_width=True,
        hide_index=True,
        height=470,
    )
    st.download_button(
        "Muat turun CSV — Aset Berlainan Lokasi",
        location_report[location_columns].to_csv(index=False).encode("utf-8-sig"),
        file_name=(
            f"aset_berlainan_lokasi_{selected_location_ptj}.csv"
            if selected_location_ptj else "aset_berlainan_lokasi.csv"
        ),
        mime="text/csv",
    )
