"""
db_engine.py - Smart Kos Data Warehouse Engine (DuckDB)
=========================================================
Modul ini bertanggung jawab atas seluruh siklus hidup Data Warehouse:
  1. Pembuatan skema Snowflake (Tabel Fakta + Dimensi Ternormalisasi)
  2. Proses ELT (Extract, Load, Transform)
  3. Materialized Views untuk optimasi query
  4. Bitmap Index & Partition Pruning
  5. Data Governance (Profiling, Masking, Lineage)
"""

import duckdb
import pandas as pd
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_kos.duckdb")


def get_connection():
    """Mengembalikan koneksi DuckDB yang persisten."""
    return duckdb.connect(DB_PATH)


# =============================================================================
# 1. SKEMA SNOWFLAKE (Dimensi Ternormalisasi)
# =============================================================================

def create_snowflake_schema(con):
    """
    Membuat skema Snowflake yang terdiri dari:
      - Sub-dimensi: dim_kategori_nutrisi, dim_kategori_produk
      - Dimensi: dim_produk, dim_metode_bayar, dim_waktu
      - Fakta: fact_transaksi
    Tabel dimensi dinormalisasi -> hemat ruang penyimpanan.
    """

    # --- Sub-Dimensi: Kategori Nutrisi ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_kategori_nutrisi (
            id_kategori_nutrisi INTEGER PRIMARY KEY,
            nama_kategori_nutrisi VARCHAR NOT NULL,  -- e.g. Karbohidrat, Protein
            deskripsi VARCHAR
        );
    """)

    # --- Sub-Dimensi: Kategori Produk ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_kategori_produk (
            id_kategori_produk INTEGER PRIMARY KEY,
            nama_kategori VARCHAR NOT NULL,  -- e.g. Makanan, Minuman, Utilitas
            deskripsi VARCHAR
        );
    """)

    # --- Dimensi: Produk (terhubung ke sub-dimensi kategori & nutrisi) ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_produk (
            id_produk INTEGER PRIMARY KEY,
            nama_produk VARCHAR NOT NULL,
            id_kategori_produk INTEGER REFERENCES dim_kategori_produk(id_kategori_produk),
            id_kategori_nutrisi INTEGER REFERENCES dim_kategori_nutrisi(id_kategori_nutrisi),
            kalori_per_porsi FLOAT DEFAULT 0,
            protein_gram FLOAT DEFAULT 0,
            karbohidrat_gram FLOAT DEFAULT 0,
            lemak_gram FLOAT DEFAULT 0
        );
    """)

    # --- Dimensi: Metode Pembayaran ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_metode_bayar (
            id_metode INTEGER PRIMARY KEY,
            nama_metode VARCHAR NOT NULL,  -- Cash, QRIS, Transfer
            provider VARCHAR
        );
    """)

    # --- Dimensi: Waktu ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_waktu (
            id_waktu INTEGER PRIMARY KEY,
            tanggal DATE NOT NULL,
            hari VARCHAR,
            minggu_ke INTEGER,
            bulan INTEGER,
            nama_bulan VARCHAR,
            tahun INTEGER,
            kuartal INTEGER
        );
    """)

    # --- Tabel Fakta: Transaksi ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_transaksi (
            id_transaksi INTEGER PRIMARY KEY,
            id_waktu INTEGER REFERENCES dim_waktu(id_waktu),
            id_produk INTEGER REFERENCES dim_produk(id_produk),
            id_metode INTEGER REFERENCES dim_metode_bayar(id_metode),
            jumlah_item INTEGER NOT NULL,
            harga_satuan FLOAT NOT NULL,
            jumlah_bayar FLOAT NOT NULL,
            catatan VARCHAR
        );
    """)

    # --- Staging: Raw Log Transaksi (untuk ELT) ---
    con.execute("""
        CREATE TABLE IF NOT EXISTS staging_raw_log (
            log_id INTEGER,
            tanggal_transaksi DATE,
            nama_produk VARCHAR,
            kategori VARCHAR,
            jumlah INTEGER,
            harga FLOAT,
            total FLOAT,
            metode_bayar VARCHAR,
            catatan VARCHAR,
            loaded_at TIMESTAMP DEFAULT current_timestamp
        );
    """)


# =============================================================================
# 2. PROSES ELT (Extract, Load, Transform)
# =============================================================================

def elt_extract_raw_data(con, raw_df: pd.DataFrame):
    """
    EXTRACT & LOAD: Memasukkan data mentah ke staging area.
    Data mentah asli selalu disimpan untuk kemungkinan transformasi ulang.
    """
    con.execute("DELETE FROM staging_raw_log")
    con.register("raw_input", raw_df)
    con.execute("""
        INSERT INTO staging_raw_log (
            log_id, tanggal_transaksi, nama_produk, kategori,
            jumlah, harga, total, metode_bayar, catatan
        )
        SELECT
            log_id, tanggal_transaksi, nama_produk, kategori,
            jumlah, harga, total, metode_bayar, catatan
        FROM raw_input
    """)
    con.unregister("raw_input")


def elt_transform_load(con):
    """
    TRANSFORM: Transformasi data dari staging ke dalam skema dimensional.
    Proses ini memanfaatkan kekuatan komputasi di dalam DuckDB.
    """

    # --- Populate dim_waktu ---
    con.execute("""
        INSERT OR IGNORE INTO dim_waktu (id_waktu, tanggal, hari, minggu_ke, bulan, nama_bulan, tahun, kuartal)
        SELECT DISTINCT
            CAST(strftime(tanggal_transaksi, '%Y%m%d') AS INTEGER) AS id_waktu,
            tanggal_transaksi,
            dayname(tanggal_transaksi),
            weekofyear(tanggal_transaksi),
            month(tanggal_transaksi),
            monthname(tanggal_transaksi),
            year(tanggal_transaksi),
            quarter(tanggal_transaksi)
        FROM staging_raw_log
        WHERE tanggal_transaksi IS NOT NULL
    """)

    # --- Populate fact_transaksi (join dari staging + dimensi) ---
    con.execute("""
        INSERT OR IGNORE INTO fact_transaksi (
            id_transaksi, id_waktu, id_produk, id_metode,
            jumlah_item, harga_satuan, jumlah_bayar, catatan
        )
        SELECT
            s.log_id,
            CAST(strftime(s.tanggal_transaksi, '%Y%m%d') AS INTEGER),
            p.id_produk,
            m.id_metode,
            s.jumlah,
            s.harga,
            s.total,
            s.catatan
        FROM staging_raw_log s
        LEFT JOIN dim_produk p ON s.nama_produk = p.nama_produk
        LEFT JOIN dim_metode_bayar m ON s.metode_bayar = m.nama_metode
        WHERE s.log_id NOT IN (SELECT id_transaksi FROM fact_transaksi)
    """)


# =============================================================================
# 3. MATERIALIZED VIEWS (Optimasi Fisik)
# =============================================================================

def create_materialized_views(con):
    """
    Membuat Materialized Views untuk KPI dashboard.
    Hasil agregasi disimpan ke disk -> menghindari kalkulasi ulang.
    """

    # -- MV: Ringkasan Bulanan --
    con.execute("DROP TABLE IF EXISTS mv_ringkasan_bulanan")
    con.execute("""
        CREATE TABLE mv_ringkasan_bulanan AS
        SELECT
            w.tahun,
            w.bulan,
            w.nama_bulan,
            COUNT(f.id_transaksi) AS total_transaksi,
            SUM(f.jumlah_bayar) AS total_pengeluaran,
            AVG(f.jumlah_bayar) AS rata_rata_pengeluaran,
            MAX(f.jumlah_bayar) AS maks_pengeluaran,
            MIN(f.jumlah_bayar) AS min_pengeluaran
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        GROUP BY w.tahun, w.bulan, w.nama_bulan
        ORDER BY w.tahun, w.bulan
    """)

    # -- MV: Ringkasan Harian --
    con.execute("DROP TABLE IF EXISTS mv_ringkasan_harian")
    con.execute("""
        CREATE TABLE mv_ringkasan_harian AS
        SELECT
            w.tanggal,
            w.hari,
            w.nama_bulan,
            COUNT(f.id_transaksi) AS total_transaksi,
            SUM(f.jumlah_bayar) AS total_pengeluaran,
            AVG(f.jumlah_bayar) AS rata_rata_pengeluaran
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        GROUP BY w.tanggal, w.hari, w.nama_bulan
        ORDER BY w.tanggal
    """)

    # -- MV: Konsumsi Nutrisi Harian --
    con.execute("DROP TABLE IF EXISTS mv_nutrisi_harian")
    con.execute("""
        CREATE TABLE mv_nutrisi_harian AS
        SELECT
            w.tanggal,
            SUM(p.kalori_per_porsi * f.jumlah_item) AS total_kalori,
            SUM(p.protein_gram * f.jumlah_item) AS total_protein,
            SUM(p.karbohidrat_gram * f.jumlah_item) AS total_karbohidrat,
            SUM(p.lemak_gram * f.jumlah_item) AS total_lemak
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        JOIN dim_produk p ON f.id_produk = p.id_produk
        GROUP BY w.tanggal
        ORDER BY w.tanggal
    """)

    # -- MV: Pengeluaran per Kategori --
    con.execute("DROP TABLE IF EXISTS mv_pengeluaran_kategori")
    con.execute("""
        CREATE TABLE mv_pengeluaran_kategori AS
        SELECT
            kp.nama_kategori,
            SUM(f.jumlah_bayar) AS total_pengeluaran,
            COUNT(f.id_transaksi) AS total_transaksi,
            AVG(f.jumlah_bayar) AS rata_rata
        FROM fact_transaksi f
        JOIN dim_produk p ON f.id_produk = p.id_produk
        JOIN dim_kategori_produk kp ON p.id_kategori_produk = kp.id_kategori_produk
        GROUP BY kp.nama_kategori
    """)

    # -- MV: Pengeluaran per Nutrisi --
    con.execute("DROP TABLE IF EXISTS mv_pengeluaran_nutrisi")
    con.execute("""
        CREATE TABLE mv_pengeluaran_nutrisi AS
        SELECT
            kn.nama_kategori_nutrisi,
            SUM(f.jumlah_bayar) AS total_pengeluaran,
            COUNT(f.id_transaksi) AS total_transaksi
        FROM fact_transaksi f
        JOIN dim_produk p ON f.id_produk = p.id_produk
        JOIN dim_kategori_nutrisi kn ON p.id_kategori_nutrisi = kn.id_kategori_nutrisi
        GROUP BY kn.nama_kategori_nutrisi
    """)


# =============================================================================
# 4. BITMAP INDEX & PARTITION PRUNING
# =============================================================================

def create_bitmap_indexes(con):
    """
    Bitmap Index: Efisien untuk kolom kardinalitas rendah.
    DuckDB secara internal menggunakan Adaptive Radix Tree (ART) & min-max indexes.
    Kita membuat tabel bitmap manual sebagai demonstrasi konsep.
    """
    con.execute("DROP TABLE IF EXISTS idx_bitmap_metode_bayar")
    con.execute("""
        CREATE TABLE idx_bitmap_metode_bayar AS
        SELECT
            f.id_transaksi,
            CASE WHEN m.nama_metode = 'Cash' THEN 1 ELSE 0 END AS is_cash,
            CASE WHEN m.nama_metode = 'QRIS' THEN 1 ELSE 0 END AS is_qris,
            CASE WHEN m.nama_metode = 'Transfer' THEN 1 ELSE 0 END AS is_transfer,
            CASE WHEN m.nama_metode = 'E-Wallet' THEN 1 ELSE 0 END AS is_ewallet
        FROM fact_transaksi f
        JOIN dim_metode_bayar m ON f.id_metode = m.id_metode
    """)


def query_with_partition_pruning(con, bulan: int, tahun: int):
    """
    Partition Pruning: Hanya membaca data pada partisi bulan/tahun tertentu.
    Menggunakan filter WHERE yang memanfaatkan min-max index DuckDB.
    """
    return con.execute("""
        SELECT
            w.tanggal, w.hari,
            SUM(f.jumlah_bayar) AS total_pengeluaran,
            COUNT(f.id_transaksi) AS jumlah_transaksi
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        WHERE w.bulan = ? AND w.tahun = ?
        GROUP BY w.tanggal, w.hari
        ORDER BY w.tanggal
    """, [bulan, tahun]).fetchdf()


# =============================================================================
# 5. DATA GOVERNANCE
# =============================================================================

def data_profiling(con):
    """
    Data Profiling: Mendeteksi anomali di staging sebelum transformasi.
    Memeriksa: NULL, duplikasi, rentang harga tidak wajar, dll.
    """
    results = {}

    # Total baris
    results["total_baris"] = con.execute(
        "SELECT COUNT(*) FROM staging_raw_log"
    ).fetchone()[0]

    # Baris dengan NULL
    results["baris_null"] = con.execute("""
        SELECT COUNT(*) FROM staging_raw_log
        WHERE nama_produk IS NULL
           OR kategori IS NULL
           OR harga IS NULL
           OR total IS NULL
    """).fetchone()[0]

    # Duplikasi log_id
    results["duplikasi_id"] = con.execute("""
        SELECT COUNT(*) - COUNT(DISTINCT log_id) FROM staging_raw_log
    """).fetchone()[0]

    # Harga anomali (< 0 atau > 1.000.000)
    results["harga_anomali"] = con.execute("""
        SELECT COUNT(*) FROM staging_raw_log
        WHERE harga < 0 OR harga > 1000000
    """).fetchone()[0]

    # Jumlah anomali
    results["jumlah_anomali"] = con.execute("""
        SELECT COUNT(*) FROM staging_raw_log
        WHERE jumlah <= 0 OR jumlah > 100
    """).fetchone()[0]

    # Statistik deskriptif harga
    stats = con.execute("""
        SELECT
            MIN(harga) AS min_harga,
            MAX(harga) AS max_harga,
            AVG(harga) AS avg_harga,
            STDDEV(harga) AS stddev_harga
        FROM staging_raw_log
    """).fetchone()
    results["stats_harga"] = {
        "min": stats[0], "max": stats[1],
        "avg": round(stats[2], 2) if stats[2] else 0,
        "stddev": round(stats[3], 2) if stats[3] else 0
    }

    return results


def apply_data_masking(con):
    """
    Security & Privacy (Masking): Menyamarkan informasi sensitif.
    Mengembalikan tabel dengan kolom catatan & metode bayar di-mask.
    """
    return con.execute("""
        SELECT
            f.id_transaksi,
            w.tanggal,
            p.nama_produk,
            f.jumlah_item,
            f.jumlah_bayar,
            -- Masking: hanya tampilkan 3 huruf pertama metode bayar
            CONCAT(LEFT(m.nama_metode, 3), '***') AS metode_bayar_masked,
            -- Masking: sembunyikan catatan
            CASE
                WHEN f.catatan IS NOT NULL AND LENGTH(f.catatan) > 0
                THEN CONCAT(LEFT(f.catatan, 5), '...[MASKED]')
                ELSE '[NO DATA]'
            END AS catatan_masked
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        JOIN dim_produk p ON f.id_produk = p.id_produk
        JOIN dim_metode_bayar m ON f.id_metode = m.id_metode
        ORDER BY w.tanggal DESC
        LIMIT 50
    """).fetchdf()


def get_data_lineage(con, id_transaksi: int):
    """
    Data Lineage: Melacak asal-usul angka di tabel fakta.
    Menunjukkan jalur data dari staging -> dimensi -> fakta.
    """
    lineage = {}

    # Dari tabel fakta
    fact = con.execute("""
        SELECT * FROM fact_transaksi WHERE id_transaksi = ?
    """, [id_transaksi]).fetchdf()
    lineage["fact_transaksi"] = fact.to_dict("records") if not fact.empty else []

    # Dari staging (raw data asli)
    raw = con.execute("""
        SELECT * FROM staging_raw_log WHERE log_id = ?
    """, [id_transaksi]).fetchdf()
    lineage["staging_raw_log"] = raw.to_dict("records") if not raw.empty else []

    # Dimensi terkait
    if not fact.empty:
        row = fact.iloc[0]
        produk = con.execute(
            "SELECT * FROM dim_produk WHERE id_produk = ?",
            [int(row["id_produk"]) if pd.notna(row["id_produk"]) else -1]
        ).fetchdf()
        lineage["dim_produk"] = produk.to_dict("records") if not produk.empty else []

        waktu = con.execute(
            "SELECT * FROM dim_waktu WHERE id_waktu = ?",
            [int(row["id_waktu"]) if pd.notna(row["id_waktu"]) else -1]
        ).fetchdf()
        lineage["dim_waktu"] = waktu.to_dict("records") if not waktu.empty else []

        metode = con.execute(
            "SELECT * FROM dim_metode_bayar WHERE id_metode = ?",
            [int(row["id_metode"]) if pd.notna(row["id_metode"]) else -1]
        ).fetchdf()
        lineage["dim_metode_bayar"] = metode.to_dict("records") if not metode.empty else []

    return lineage


# =============================================================================
# 6. QUERY ANALITIK (Snowflake JOIN demonstrasi)
# =============================================================================

def snowflake_join_kategori(con):
    """
    Demonstrasi Snowflake Schema JOIN:
    Fakta ➔ Produk ➔ Kategori Produk (multi-hop join).
    """
    return con.execute("""
        SELECT
            kp.nama_kategori,
            SUM(f.jumlah_bayar) AS total_pengeluaran,
            COUNT(f.id_transaksi) AS total_transaksi
        FROM fact_transaksi f
        JOIN dim_produk p ON f.id_produk = p.id_produk
        JOIN dim_kategori_produk kp ON p.id_kategori_produk = kp.id_kategori_produk
        GROUP BY kp.nama_kategori
        ORDER BY total_pengeluaran DESC
    """).fetchdf()


def snowflake_join_nutrisi(con):
    """
    Demonstrasi Snowflake Schema JOIN:
    Fakta ➔ Produk ➔ Kategori Nutrisi (multi-hop join).
    """
    return con.execute("""
        SELECT
            kn.nama_kategori_nutrisi,
            SUM(p.kalori_per_porsi * f.jumlah_item) AS total_kalori,
            SUM(p.protein_gram * f.jumlah_item) AS total_protein_g,
            SUM(p.karbohidrat_gram * f.jumlah_item) AS total_karbo_g,
            SUM(p.lemak_gram * f.jumlah_item) AS total_lemak_g,
            SUM(f.jumlah_bayar) AS total_biaya
        FROM fact_transaksi f
        JOIN dim_produk p ON f.id_produk = p.id_produk
        JOIN dim_kategori_nutrisi kn ON p.id_kategori_nutrisi = kn.id_kategori_nutrisi
        GROUP BY kn.nama_kategori_nutrisi
        ORDER BY total_kalori DESC
    """).fetchdf()


def get_tren_harian(con):
    """Ambil data tren pengeluaran harian dari MV."""
    return con.execute("""
        SELECT * FROM mv_ringkasan_harian ORDER BY tanggal
    """).fetchdf()


def get_ringkasan_bulanan(con):
    """Ambil data ringkasan bulanan dari MV."""
    return con.execute("""
        SELECT * FROM mv_ringkasan_bulanan ORDER BY tahun, bulan
    """).fetchdf()


def get_nutrisi_harian(con):
    """Ambil data konsumsi nutrisi harian dari MV."""
    return con.execute("""
        SELECT * FROM mv_nutrisi_harian ORDER BY tanggal
    """).fetchdf()


def get_bitmap_index_demo(con, metode: str):
    """Demo penggunaan Bitmap Index untuk filter metode bayar."""
    col_map = {
        "Cash": "is_cash",
        "QRIS": "is_qris",
        "Transfer": "is_transfer",
        "E-Wallet": "is_ewallet"
    }
    col = col_map.get(metode, "is_cash")
    return con.execute(f"""
        SELECT b.*, f.jumlah_bayar, p.nama_produk
        FROM idx_bitmap_metode_bayar b
        JOIN fact_transaksi f ON b.id_transaksi = f.id_transaksi
        JOIN dim_produk p ON f.id_produk = p.id_produk
        WHERE b.{col} = 1
        LIMIT 20
    """).fetchdf()
