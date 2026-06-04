"""
app.py - Smart Kos Analytics Dashboard
========================================
Dashboard Streamlit untuk monitoring pengeluaran & gizi harian mahasiswa kos.
Dibangun di atas DuckDB Data Warehouse dengan arsitektur Snowflake Schema.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os

from db_engine import (
    get_connection, create_snowflake_schema,
    create_materialized_views, create_bitmap_indexes,
    snowflake_join_kategori, snowflake_join_nutrisi,
    get_tren_harian, get_ringkasan_bulanan, get_nutrisi_harian,
    data_profiling, apply_data_masking, get_data_lineage,
    get_bitmap_index_demo, query_with_partition_pruning
)
from data_generator import initialize_warehouse

# ── Konfigurasi Halaman ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Smart Kos Analytics",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }

.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 2rem 2.5rem; border-radius: 16px; margin-bottom: 1.5rem;
    border: 1px solid rgba(108, 99, 255, 0.2);
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.main-header h1 {
    color: #fff; font-size: 2rem; font-weight: 700; margin: 0 0 0.3rem 0;
    background: linear-gradient(90deg, #6C63FF, #48C9B0);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.main-header p { color: #94a3b8; font-size: 0.9rem; margin: 0; }

.kpi-card {
    background: linear-gradient(145deg, #1e2235, #252a40);
    border: 1px solid rgba(108,99,255,0.15); border-radius: 14px;
    padding: 1.3rem 1.5rem; text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 30px rgba(108,99,255,0.15);
}
.kpi-label { color: #94a3b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.4rem; }
.kpi-value { font-size: 1.6rem; font-weight: 700; margin: 0.2rem 0; }
.kpi-sub { color: #64748b; font-size: 0.75rem; }
.kpi-green { color: #48C9B0; }
.kpi-blue { color: #6C63FF; }
.kpi-orange { color: #F59E0B; }
.kpi-pink { color: #EC4899; }

.section-title {
    color: #e2e8f0; font-size: 1.15rem; font-weight: 600;
    padding: 0.6rem 0; margin: 1.2rem 0 0.6rem 0;
    border-bottom: 2px solid rgba(108,99,255,0.3);
    display: flex; align-items: center; gap: 0.5rem;
}

.info-badge {
    background: rgba(108,99,255,0.12); color: #a5b4fc;
    padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.8rem;
    border-left: 3px solid #6C63FF; margin: 0.5rem 0;
}

.governance-card {
    background: linear-gradient(145deg, #1a2235, #1e2a40);
    border: 1px solid rgba(72,201,176,0.15); border-radius: 12px;
    padding: 1.2rem; margin: 0.5rem 0;
}

div[data-testid="stExpander"] {
    background: rgba(30,34,53,0.6); border: 1px solid rgba(108,99,255,0.1);
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)


# ── Inisialisasi Database ─────────────────────────────────────────────────────
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


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏠 Smart Kos DW")
    st.markdown("---")

    st.markdown("### 📊 Filter Analitik")
    bulan_list = con.execute("SELECT DISTINCT bulan, nama_bulan FROM dim_waktu ORDER BY bulan").fetchdf()
    if not bulan_list.empty:
        bulan_options = dict(zip(bulan_list["nama_bulan"], bulan_list["bulan"]))
        selected_bulan_name = st.selectbox("Pilih Bulan", list(bulan_options.keys()), index=len(bulan_options)-1)
        selected_bulan = bulan_options[selected_bulan_name]
    else:
        selected_bulan = 1

    tahun = 2025

    st.markdown("---")
    st.markdown("### 🏗️ Arsitektur Sistem")
    st.markdown("""
    <div class="info-badge">
        <strong>Engine:</strong> DuckDB<br>
        <strong>Model:</strong> Snowflake Schema<br>
        <strong>Pipeline:</strong> ELT<br>
        <strong>Optimasi:</strong> Materialized Views
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🔄 Refresh Data")
    if st.button("🔄 Rebuild Materialized Views", use_container_width=True):
        create_materialized_views(con)
        create_bitmap_indexes(con)
        st.cache_resource.clear()
        st.success("✅ Views & Index berhasil di-refresh!")


# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🏠 Smart Kos Analytics Dashboard</h1>
    <p>Data Warehouse untuk Monitoring Pengeluaran & Gizi Harian Mahasiswa Kos &nbsp;|&nbsp;
    Dibangun dengan pendekatan <strong>ELT</strong> &amp; model <strong>Snowflake Schema</strong> di atas engine <strong>DuckDB</strong></p>
</div>
""", unsafe_allow_html=True)


# ── KPI CARDS (dari Materialized Views) ──────────────────────────────────────
st.markdown('<div class="section-title">📈 Ringkasan Indikator Keuangan (Materialized Views)</div>', unsafe_allow_html=True)

ringkasan = get_ringkasan_bulanan(con)
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
        <div class="kpi-label">Total Pengeluaran Bulan Ini</div>
        <div class="kpi-value kpi-green">Rp {total_spend:,.0f}</div>
        <div class="kpi-sub">{total_trx} transaksi</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Rata-rata per Transaksi</div>
        <div class="kpi-value kpi-blue">Rp {avg_spend:,.0f}</div>
        <div class="kpi-sub">bulan {selected_bulan_name}</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Transaksi Terbesar</div>
        <div class="kpi-value kpi-orange">Rp {max_spend:,.0f}</div>
        <div class="kpi-sub">bulan {selected_bulan_name}</div>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Total Seluruh Periode</div>
        <div class="kpi-value kpi-pink">Rp {total_all:,.0f}</div>
        <div class="kpi-sub">Jan - Jun 2025</div>
    </div>""", unsafe_allow_html=True)


# ── TREN HARIAN & BULANAN ────────────────────────────────────────────────────
st.markdown('<div class="section-title">📊 Tren Pengeluaran Harian & Bulanan</div>', unsafe_allow_html=True)

col_chart1, col_chart2 = st.columns([3, 2])

with col_chart1:
    harian = get_tren_harian(con)
    harian_filtered = harian[pd.to_datetime(harian["tanggal"]).dt.month == selected_bulan]
    if not harian_filtered.empty:
        fig_line = px.area(
            harian_filtered, x="tanggal", y="total_pengeluaran",
            title=f"Pengeluaran Harian — {selected_bulan_name} 2025",
            labels={"tanggal": "Tanggal", "total_pengeluaran": "Total (Rp)"},
            color_discrete_sequence=["#6C63FF"]
        )
        fig_line.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", title_font_size=14,
            xaxis=dict(gridcolor="rgba(100,100,140,0.15)"),
            yaxis=dict(gridcolor="rgba(100,100,140,0.15)"),
            margin=dict(l=20, r=20, t=50, b=20)
        )
        fig_line.update_traces(
            fill="tozeroy",
            fillcolor="rgba(108,99,255,0.15)",
            line=dict(width=2)
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Tidak ada data untuk bulan yang dipilih.")

with col_chart2:
    if not ringkasan.empty:
        fig_bar = px.bar(
            ringkasan, x="nama_bulan", y="total_pengeluaran",
            title="Ringkasan Pengeluaran Bulanan",
            labels={"nama_bulan": "Bulan", "total_pengeluaran": "Total (Rp)"},
            color="total_pengeluaran",
            color_continuous_scale=["#1e2235", "#6C63FF", "#48C9B0"]
        )
        fig_bar.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", title_font_size=14, showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_bar, use_container_width=True)


# ── SNOWFLAKE JOIN: KATEGORI & NUTRISI ────────────────────────────────────────
st.markdown('<div class="section-title">🔗 Demonstrasi Snowflake Join (Fakta ➔ Produk ➔ Kategori/Nutrisi)</div>', unsafe_allow_html=True)

col_donut1, col_donut2 = st.columns(2)

with col_donut1:
    kat_df = snowflake_join_kategori(con)
    if not kat_df.empty:
        fig_kat = px.pie(
            kat_df, values="total_pengeluaran", names="nama_kategori",
            title="Distribusi Pengeluaran per Kategori Produk",
            hole=0.5,
            color_discrete_sequence=["#6C63FF", "#48C9B0", "#F59E0B", "#EC4899", "#8B5CF6"]
        )
        fig_kat.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", title_font_size=14,
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(font=dict(size=11))
        )
        fig_kat.update_traces(textinfo="percent+label", textfont_size=11)
        st.plotly_chart(fig_kat, use_container_width=True)

        st.markdown("""<div class="info-badge">
            <strong>Query Path:</strong> fact_transaksi → dim_produk → dim_kategori_produk<br>
            <em>Multi-hop JOIN khas Snowflake Schema</em>
        </div>""", unsafe_allow_html=True)

with col_donut2:
    nut_df = snowflake_join_nutrisi(con)
    if not nut_df.empty:
        fig_nut = px.pie(
            nut_df, values="total_kalori", names="nama_kategori_nutrisi",
            title="Distribusi Konsumsi Kalori per Kategori Nutrisi",
            hole=0.5,
            color_discrete_sequence=["#48C9B0", "#6C63FF", "#F59E0B", "#EC4899", "#34D399"]
        )
        fig_nut.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", title_font_size=14,
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(font=dict(size=11))
        )
        fig_nut.update_traces(textinfo="percent+label", textfont_size=11)
        st.plotly_chart(fig_nut, use_container_width=True)

        st.markdown("""<div class="info-badge">
            <strong>Query Path:</strong> fact_transaksi → dim_produk → dim_kategori_nutrisi<br>
            <em>Normalized sub-dimension JOIN</em>
        </div>""", unsafe_allow_html=True)


# ── NUTRISI HARIAN ────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🥗 Monitoring Konsumsi Gizi Harian</div>', unsafe_allow_html=True)

nutrisi = get_nutrisi_harian(con)
nutrisi_filtered = nutrisi[pd.to_datetime(nutrisi["tanggal"]).dt.month == selected_bulan]

if not nutrisi_filtered.empty:
    cn1, cn2, cn3, cn4 = st.columns(4)
    avg_kal = nutrisi_filtered["total_kalori"].mean()
    avg_pro = nutrisi_filtered["total_protein"].mean()
    avg_kar = nutrisi_filtered["total_karbohidrat"].mean()
    avg_lem = nutrisi_filtered["total_lemak"].mean()

    with cn1:
        st.metric("🔥 Rata-rata Kalori/Hari", f"{avg_kal:,.0f} kcal")
    with cn2:
        st.metric("🥩 Rata-rata Protein/Hari", f"{avg_pro:,.1f} g")
    with cn3:
        st.metric("🍚 Rata-rata Karbo/Hari", f"{avg_kar:,.1f} g")
    with cn4:
        st.metric("🧈 Rata-rata Lemak/Hari", f"{avg_lem:,.1f} g")

    fig_nut_line = go.Figure()
    colors = {"total_kalori": "#F59E0B", "total_protein": "#6C63FF",
              "total_karbohidrat": "#48C9B0", "total_lemak": "#EC4899"}
    labels = {"total_kalori": "Kalori (kcal)", "total_protein": "Protein (g)",
              "total_karbohidrat": "Karbohidrat (g)", "total_lemak": "Lemak (g)"}

    for col_name, color in colors.items():
        fig_nut_line.add_trace(go.Scatter(
            x=nutrisi_filtered["tanggal"], y=nutrisi_filtered[col_name],
            name=labels[col_name], line=dict(color=color, width=2),
            mode="lines"
        ))
    fig_nut_line.update_layout(
        title=f"Tren Konsumsi Gizi Harian — {selected_bulan_name} 2025",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e2e8f0", title_font_size=14,
        xaxis=dict(gridcolor="rgba(100,100,140,0.15)", title="Tanggal"),
        yaxis=dict(gridcolor="rgba(100,100,140,0.15)", title="Nilai"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=60, b=20)
    )
    st.plotly_chart(fig_nut_line, use_container_width=True)
else:
    st.info("Tidak ada data nutrisi untuk bulan yang dipilih.")


# ── OPTIMASI: PARTITION PRUNING & BITMAP INDEX ───────────────────────────────
st.markdown('<div class="section-title">⚡ Demonstrasi Optimasi Fisik Database</div>', unsafe_allow_html=True)

tab_part, tab_bitmap = st.tabs(["📂 Partition Pruning", "🗂️ Bitmap Index"])

with tab_part:
    st.markdown("""
    <div class="info-badge">
        <strong>Partition Pruning:</strong> Hanya membaca partisi data bulan yang dipilih.
        Database mengabaikan partisi bulan lain → query lebih cepat.
    </div>
    """, unsafe_allow_html=True)
    pruned = query_with_partition_pruning(con, selected_bulan, tahun)
    if not pruned.empty:
        st.dataframe(pruned.style.format({"total_pengeluaran": "Rp {:,.0f}"}),
                      use_container_width=True, height=300)
    else:
        st.info("Tidak ada data.")

with tab_bitmap:
    st.markdown("""
    <div class="info-badge">
        <strong>Bitmap Index:</strong> Pemetaan 0/1 untuk kolom kardinalitas rendah (metode bayar).
        Sangat efisien untuk filter pada kolom dengan sedikit nilai unik.
    </div>
    """, unsafe_allow_html=True)
    metode_sel = st.selectbox("Filter Metode Bayar", ["Cash", "QRIS", "Transfer", "E-Wallet"])
    bitmap_result = get_bitmap_index_demo(con, metode_sel)
    if not bitmap_result.empty:
        st.dataframe(bitmap_result, use_container_width=True, height=300)


# ── DATA GOVERNANCE ───────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🛡️ Tata Kelola Data (Data Governance)</div>', unsafe_allow_html=True)

with st.expander("📋 Data Profiling — Deteksi Anomali Staging", expanded=False):
    st.markdown("""<div class="info-badge">
        Mendeteksi anomali input di staging sebelum masuk ke analitik.
    </div>""", unsafe_allow_html=True)
    profile = data_profiling(con)
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        st.metric("Total Baris Staging", f"{profile['total_baris']:,}")
        st.metric("Baris dengan NULL", profile["baris_null"])
    with pc2:
        st.metric("Duplikasi ID", profile["duplikasi_id"])
        st.metric("Harga Anomali", profile["harga_anomali"])
    with pc3:
        st.metric("Jumlah Anomali", profile["jumlah_anomali"])
        stats = profile["stats_harga"]
        st.metric("Avg Harga", f"Rp {stats['avg']:,.0f}")

with st.expander("🔒 Security & Privacy — Data Masking", expanded=False):
    st.markdown("""<div class="info-badge">
        Informasi sensitif (metode bayar & catatan) disamarkan untuk keamanan audit.
    </div>""", unsafe_allow_html=True)
    masked = apply_data_masking(con)
    if not masked.empty:
        st.dataframe(masked.style.format({"jumlah_bayar": "Rp {:,.0f}"}),
                      use_container_width=True, height=350)

with st.expander("🔍 Data Lineage — Lacak Asal-Usul Data", expanded=False):
    st.markdown("""<div class="info-badge">
        Melacak jalur data: Staging (Raw) → Dimensi → Tabel Fakta.
    </div>""", unsafe_allow_html=True)
    max_id = con.execute("SELECT MAX(id_transaksi) FROM fact_transaksi").fetchone()[0] or 1
    trace_id = st.number_input("Masukkan ID Transaksi", min_value=1, max_value=max_id, value=1)
    if st.button("🔍 Lacak Lineage"):
        lineage = get_data_lineage(con, trace_id)
        for table_name, records in lineage.items():
            st.markdown(f"**📌 {table_name}**")
            if records:
                st.dataframe(pd.DataFrame(records), use_container_width=True)
            else:
                st.caption("Tidak ditemukan.")

with st.expander("📜 Raw Transaction Log (Staging Area)", expanded=False):
    st.markdown("""<div class="info-badge">
        <strong>Progressive Disclosure:</strong> Detail mentah log transaksional disembunyikan dari pandangan utama.
        Data asli tetap tersimpan di staging untuk keperluan transformasi ulang.
    </div>""", unsafe_allow_html=True)
    raw_log = con.execute("SELECT * FROM staging_raw_log ORDER BY tanggal_transaksi DESC LIMIT 100").fetchdf()
    if not raw_log.empty:
        st.dataframe(raw_log, use_container_width=True, height=350)


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center; color:#64748b; font-size:0.8rem; padding:1rem 0;">
    <strong>Smart Kos Data Warehouse</strong> &nbsp;|&nbsp;
    Engine: DuckDB &nbsp;|&nbsp; Model: Snowflake Schema &nbsp;|&nbsp; Pipeline: ELT &nbsp;|&nbsp;
    Optimasi: Materialized Views, Partition Pruning, Bitmap Index<br>
    © 2025 — Final Project Data Warehouse
</div>
""", unsafe_allow_html=True)
