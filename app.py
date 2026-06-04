"""
app.py - Smart Kos Analytics Dashboard
Monitoring Biaya & Nutrisi Makanan Mahasiswa Kos
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from db_engine import (
    get_connection, create_materialized_views, create_bitmap_indexes,
    snowflake_join_kategori, snowflake_join_nutrisi,
    get_tren_harian, get_ringkasan_bulanan, get_nutrisi_harian,
    data_profiling, get_data_lineage,
    get_bitmap_index_demo, query_with_partition_pruning,
    generate_monthly_nutrition_advice
)
from data_generator import initialize_warehouse

# -- Config --
st.set_page_config(
    page_title="Smart Kos — Biaya & Nutrisi",
    page_icon="SK",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -- Minimal CSS --
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }

.main-header {
    background: #111827;
    padding: 1.8rem 2rem; border-radius: 10px; margin-bottom: 1.2rem;
    border: 1px solid #1f2937;
}
.main-header h1 {
    color: #f9fafb; font-size: 1.5rem; font-weight: 700; margin: 0 0 0.25rem 0;
}
.main-header p { color: #9ca3af; font-size: 0.85rem; margin: 0; }

.kpi-card {
    background: #111827; border: 1px solid #1f2937; border-radius: 10px;
    padding: 1.1rem 1.3rem; text-align: center;
}
.kpi-label { color: #9ca3af; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 0.3rem; }
.kpi-value { font-size: 1.4rem; font-weight: 700; color: #f9fafb; margin: 0.2rem 0; }
.kpi-sub { color: #6b7280; font-size: 0.72rem; }

.section-label {
    color: #d1d5db; font-size: 1rem; font-weight: 600;
    padding: 0.5rem 0; margin: 1rem 0 0.5rem 0;
    border-bottom: 1px solid #1f2937;
}

.note-box {
    background: #111827; color: #9ca3af;
    padding: 0.6rem 1rem; border-radius: 6px; font-size: 0.78rem;
    border-left: 3px solid #374151; margin: 0.4rem 0;
}

/* Saran nutrisi */
.saran-card {
    border-radius: 8px; padding: 0.9rem 1.1rem; margin: 0.4rem 0;
    border-left: 3px solid; font-size: 0.85rem;
}
.saran-kurang { background: rgba(245,158,11,0.06); border-color: #d97706; }
.saran-berlebih { background: rgba(139,92,246,0.06); border-color: #7c3aed; }
.saran-baik { background: rgba(16,185,129,0.06); border-color: #059669; }
.saran-msg { color: #e5e7eb; font-weight: 500; margin-bottom: 0.2rem; }
.saran-tip { color: #9ca3af; font-size: 0.78rem; }

.gauge-card {
    background: #111827; border: 1px solid #1f2937; border-radius: 8px;
    padding: 0.9rem 1rem; text-align: center; margin: 0.3rem 0;
}
.gauge-label { color: #9ca3af; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; }
.gauge-value { font-size: 1.15rem; font-weight: 700; color: #f9fafb; margin: 0.15rem 0; }
.gauge-pct { font-size: 0.7rem; }
.pct-low { color: #d97706; } .pct-ok { color: #10b981; } .pct-high { color: #8b5cf6; }

div[data-testid="stExpander"] {
    background: #0d1117; border: 1px solid #1f2937; border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)


# -- Init DB --
@st.cache_resource
def init_db():
    con = get_connection()
    try:
        count = con.execute("SELECT COUNT(*) FROM fact_transaksi").fetchone()[0]
        if count == 0:
            raise Exception("Empty")
    except:
        initialize_warehouse(con, "2025-01-01", "2025-06-30")
    return con

con = init_db()


# -- Sidebar --
with st.sidebar:
    st.markdown("### Smart Kos")
    st.caption("Monitoring Biaya & Nutrisi Makanan")
    st.markdown("---")

    tahun_list = con.execute(
        "SELECT DISTINCT tahun FROM dim_waktu ORDER BY tahun"
    ).fetchdf()

    if not tahun_list.empty:
        tahun_options = tahun_list["tahun"].tolist()
        tahun = st.selectbox("Tahun", tahun_options, index=len(tahun_options) - 1)
    else:
        tahun = 2025

    bulan_list = con.execute(
        "SELECT DISTINCT bulan, nama_bulan FROM dim_waktu WHERE tahun = ? ORDER BY bulan",
        [tahun]
    ).fetchdf()

    if not bulan_list.empty:
        bulan_options = dict(zip(bulan_list["nama_bulan"], bulan_list["bulan"]))
        selected_bulan_name = st.selectbox(
            "Bulan", list(bulan_options.keys()), index=len(bulan_options) - 1
        )
        selected_bulan = bulan_options[selected_bulan_name]
    else:
        selected_bulan, selected_bulan_name = 1, "January"

    st.markdown("---")
    st.caption("Arsitektur")
    st.markdown("""<div class="note-box">
        Engine: DuckDB | Model: Snowflake Schema<br>
        Pipeline: ELT | Fokus: Biaya & Nutrisi
    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("Refresh Data", use_container_width=True):
        create_materialized_views(con)
        create_bitmap_indexes(con)
        st.cache_resource.clear()
        st.success("Data berhasil di-refresh.")


# -- Header --
st.markdown("""<div class="main-header">
    <h1>Smart Kos — Monitoring Biaya & Nutrisi Makanan</h1>
    <p>Analisis pengeluaran makanan dan kecukupan gizi harian mahasiswa kos
    &nbsp;|&nbsp; Snowflake Schema &middot; ELT &middot; DuckDB</p>
</div>""", unsafe_allow_html=True)


# -- KPI --
st.markdown('<div class="section-label">Ringkasan Biaya Makanan</div>', unsafe_allow_html=True)

ringkasan = get_ringkasan_bulanan(con)
ringkasan = ringkasan[ringkasan["tahun"] == tahun]
bulan_data = ringkasan[ringkasan["bulan"] == selected_bulan]

if not bulan_data.empty:
    row = bulan_data.iloc[0]
    total_trx = int(row["total_transaksi"])
    total_spend = float(row["total_pengeluaran"])
    avg_spend = float(row["rata_rata_pengeluaran"])
    max_spend = float(row["maks_pengeluaran"])
else:
    total_trx, total_spend, avg_spend, max_spend = 0, 0, 0, 0

total_all = float(ringkasan["total_pengeluaran"].sum()) if not ringkasan.empty else 0

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Biaya Makan Bulan Ini</div>
        <div class="kpi-value">Rp {total_spend:,.0f}</div>
        <div class="kpi-sub">{total_trx} transaksi</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Rata-rata / Transaksi</div>
        <div class="kpi-value">Rp {avg_spend:,.0f}</div>
        <div class="kpi-sub">{selected_bulan_name}</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Transaksi Terbesar</div>
        <div class="kpi-value">Rp {max_spend:,.0f}</div>
        <div class="kpi-sub">{selected_bulan_name}</div>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Total Seluruh Periode</div>
        <div class="kpi-value">Rp {total_all:,.0f}</div>
        <div class="kpi-sub">Tahun {tahun}</div>
    </div>""", unsafe_allow_html=True)


# -- Saran Nutrisi Bulanan --
st.markdown('<div class="section-label">Saran Nutrisi Bulanan</div>', unsafe_allow_html=True)

saran_list, detail = generate_monthly_nutrition_advice(con, selected_bulan, tahun)

if detail:
    keys_row1 = ["kalori", "protein", "karbohidrat", "lemak"]
    keys_row2 = ["kalsium", "zat_besi", "vitamin_c", "serat"]

    for keys in [keys_row1, keys_row2]:
        cols = st.columns(4)
        for i, key in enumerate(keys):
            d = detail[key]
            pct_class = "pct-low" if d["status"] == "kurang" else (
                "pct-high" if d["status"] == "berlebih" else "pct-ok"
            )
            with cols[i]:
                st.markdown(f"""<div class="gauge-card">
                    <div class="gauge-label">{d['label']}</div>
                    <div class="gauge-value">{d['actual']:,.1f} {d['unit']}</div>
                    <div class="gauge-pct {pct_class}">{d['pct']:.0f}% dari AKG ({d['target']} {d['unit']}/hari)</div>
                </div>""", unsafe_allow_html=True)

    st.markdown("##### Rekomendasi")
    for s in saran_list:
        css = "saran-kurang" if s["type"] == "warning" else (
            "saran-berlebih" if s["type"] == "info" else "saran-baik"
        )
        st.markdown(f"""<div class="saran-card {css}">
            <div class="saran-msg">{s['message']}</div>
            <div class="saran-tip">{s['tip']}</div>
        </div>""", unsafe_allow_html=True)
else:
    st.info("Tidak ada data nutrisi untuk bulan ini.")


# -- Tren Pengeluaran --
st.markdown('<div class="section-label">Tren Pengeluaran Makanan</div>', unsafe_allow_html=True)

col_chart1, col_chart2 = st.columns([3, 2])

CHART_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font_color="#d1d5db", title_font_size=13,
    xaxis=dict(gridcolor="rgba(55,65,81,0.4)"),
    yaxis=dict(gridcolor="rgba(55,65,81,0.4)"),
    margin=dict(l=20, r=20, t=45, b=20)
)

with col_chart1:
    harian = get_tren_harian(con)
    harian_dt = pd.to_datetime(harian["tanggal"])
    harian_f = harian[(harian_dt.dt.month == selected_bulan) & (harian_dt.dt.year == tahun)]
    if not harian_f.empty:
        fig = px.area(harian_f, x="tanggal", y="total_pengeluaran",
            title=f"Pengeluaran Harian — {selected_bulan_name} {tahun}",
            labels={"tanggal": "Tanggal", "total_pengeluaran": "Total (Rp)"},
            color_discrete_sequence=["#6366f1"])
        fig.update_layout(**CHART_LAYOUT)
        fig.update_traces(fill="tozeroy", fillcolor="rgba(99,102,241,0.1)", line=dict(width=1.5))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Tidak ada data.")

with col_chart2:
    if not ringkasan.empty:
        fig = px.bar(ringkasan, x="nama_bulan", y="total_pengeluaran",
            title="Pengeluaran Bulanan",
            labels={"nama_bulan": "Bulan", "total_pengeluaran": "Total (Rp)"},
            color="total_pengeluaran",
            color_continuous_scale=["#1f2937", "#6366f1", "#10b981"])
        fig.update_layout(**CHART_LAYOUT, showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)


# -- Distribusi Kategori & Nutrisi --
st.markdown('<div class="section-label">Distribusi Pengeluaran & Nutrisi (Snowflake Join)</div>', unsafe_allow_html=True)

col_d1, col_d2 = st.columns(2)

with col_d1:
    kat_df = snowflake_join_kategori(con)
    if not kat_df.empty:
        fig = px.pie(kat_df, values="total_pengeluaran", names="nama_kategori",
            title="Per Kategori Makanan", hole=0.5,
            color_discrete_sequence=["#6366f1", "#10b981", "#f59e0b", "#ec4899"])
        fig.update_layout(**CHART_LAYOUT, legend=dict(font=dict(size=10)))
        fig.update_traces(textinfo="percent+label", textfont_size=10)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('<div class="note-box">Query: fact_transaksi → dim_produk → dim_kategori_produk</div>',
                    unsafe_allow_html=True)

with col_d2:
    nut_df = snowflake_join_nutrisi(con)
    if not nut_df.empty:
        fig = px.pie(nut_df, values="total_kalori", names="nama_kategori_nutrisi",
            title="Kalori per Kategori Nutrisi", hole=0.5,
            color_discrete_sequence=["#10b981", "#6366f1", "#f59e0b", "#ec4899", "#34d399"])
        fig.update_layout(**CHART_LAYOUT, legend=dict(font=dict(size=10)))
        fig.update_traces(textinfo="percent+label", textfont_size=10)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('<div class="note-box">Query: fact_transaksi → dim_produk → dim_kategori_nutrisi</div>',
                    unsafe_allow_html=True)


# -- Tren Gizi Harian --
st.markdown('<div class="section-label">Tren Konsumsi Gizi Harian</div>', unsafe_allow_html=True)

nutrisi = get_nutrisi_harian(con)
nutrisi_dt = pd.to_datetime(nutrisi["tanggal"])
nutrisi_f = nutrisi[(nutrisi_dt.dt.month == selected_bulan) & (nutrisi_dt.dt.year == tahun)]

if not nutrisi_f.empty:
    cn1, cn2, cn3, cn4 = st.columns(4)
    with cn1: st.metric("Kalori/Hari", f"{nutrisi_f['total_kalori'].mean():,.0f} kcal")
    with cn2: st.metric("Protein/Hari", f"{nutrisi_f['total_protein'].mean():,.1f} g")
    with cn3: st.metric("Karbo/Hari", f"{nutrisi_f['total_karbohidrat'].mean():,.1f} g")
    with cn4: st.metric("Lemak/Hari", f"{nutrisi_f['total_lemak'].mean():,.1f} g")

    fig = go.Figure()
    traces = {
        "total_kalori": ("#f59e0b", "Kalori (kcal)"),
        "total_protein": ("#6366f1", "Protein (g)"),
        "total_karbohidrat": ("#10b981", "Karbohidrat (g)"),
        "total_lemak": ("#ec4899", "Lemak (g)")
    }
    for col_name, (color, label) in traces.items():
        fig.add_trace(go.Scatter(
            x=nutrisi_f["tanggal"], y=nutrisi_f[col_name],
            name=label, line=dict(color=color, width=1.5), mode="lines"
        ))
    fig.update_layout(
        title=f"Tren Gizi — {selected_bulan_name} {tahun}", **CHART_LAYOUT,
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Tidak ada data nutrisi.")


# -- Optimasi DB --
st.markdown('<div class="section-label">Optimasi Fisik Database</div>', unsafe_allow_html=True)

tab_part, tab_bitmap = st.tabs(["Partition Pruning", "Bitmap Index"])

with tab_part:
    st.markdown("""<div class="note-box">
        Partition Pruning — hanya membaca partisi data bulan terpilih, mengabaikan sisanya.
    </div>""", unsafe_allow_html=True)
    pruned = query_with_partition_pruning(con, selected_bulan, tahun)
    if not pruned.empty:
        st.dataframe(
            pruned.style.format({"total_pengeluaran": "Rp {:,.0f}"}),
            use_container_width=True, height=300
        )

with tab_bitmap:
    st.markdown("""<div class="note-box">
        Bitmap Index — pemetaan 0/1 untuk kolom kategori makanan (kardinalitas rendah).
    </div>""", unsafe_allow_html=True)
    kat_sel = st.selectbox(
        "Filter Kategori",
        ["Makanan Pokok", "Lauk Pauk", "Jajanan & Snack", "Minuman"]
    )
    bitmap_result = get_bitmap_index_demo(con, kat_sel)
    if not bitmap_result.empty:
        st.dataframe(bitmap_result, use_container_width=True, height=300)


# -- Data Governance --
st.markdown('<div class="section-label">Tata Kelola Data</div>', unsafe_allow_html=True)

with st.expander("Data Profiling — Deteksi Anomali", expanded=False):
    profile = data_profiling(con)
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        st.metric("Total Baris Staging", f"{profile['total_baris']:,}")
        st.metric("Baris NULL", profile["baris_null"])
    with pc2:
        st.metric("Duplikasi ID", profile["duplikasi_id"])
        st.metric("Harga Anomali", profile["harga_anomali"])
    with pc3:
        st.metric("Jumlah Anomali", profile["jumlah_anomali"])
        st.metric("Avg Harga", f"Rp {profile['stats_harga']['avg']:,.0f}")

with st.expander("Data Lineage — Lacak Asal Data", expanded=False):
    max_id = con.execute("SELECT MAX(id_transaksi) FROM fact_transaksi").fetchone()[0] or 1
    trace_id = st.number_input("ID Transaksi", min_value=1, max_value=max_id, value=1)
    if st.button("Lacak"):
        lineage = get_data_lineage(con, trace_id)
        for table_name, records in lineage.items():
            st.markdown(f"**{table_name}**")
            if records:
                st.dataframe(pd.DataFrame(records), use_container_width=True)
            else:
                st.caption("Tidak ditemukan.")

with st.expander("Raw Transaction Log (Staging)", expanded=False):
    raw_log = con.execute(
        "SELECT * FROM staging_raw_log ORDER BY tanggal_transaksi DESC LIMIT 100"
    ).fetchdf()
    if not raw_log.empty:
        st.dataframe(raw_log, use_container_width=True, height=350)


# -- Footer --
st.markdown("---")
st.markdown("""<div style="text-align:center; color:#6b7280; font-size:0.75rem; padding:0.8rem 0;">
    Smart Kos — Monitoring Biaya & Nutrisi Makanan &nbsp;|&nbsp;
    DuckDB &middot; Snowflake Schema &middot; ELT<br>
    Final Project Data Warehouse 2025
</div>""", unsafe_allow_html=True)
