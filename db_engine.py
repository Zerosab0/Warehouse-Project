"""
db_engine.py - Smart Kos Data Warehouse Engine (DuckDB)
=========================================================
Fokus: Monitoring Biaya & Nutrisi Makanan Mahasiswa Kos.
  1. Skema Snowflake (Fakta + Dimensi)
  2. ELT Pipeline
  3. Materialized Views
  4. Bitmap Index & Partition Pruning
  5. Data Governance
  6. Saran Nutrisi Bulanan
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
# 1. SKEMA SNOWFLAKE
# =============================================================================

def create_snowflake_schema(con):
    """Membuat skema Snowflake untuk monitoring biaya & nutrisi makanan."""

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_kategori_nutrisi (
            id_kategori_nutrisi INTEGER PRIMARY KEY,
            nama_kategori_nutrisi VARCHAR NOT NULL,
            deskripsi VARCHAR
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_kategori_produk (
            id_kategori_produk INTEGER PRIMARY KEY,
            nama_kategori VARCHAR NOT NULL,
            deskripsi VARCHAR
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_produk (
            id_produk INTEGER PRIMARY KEY,
            nama_produk VARCHAR NOT NULL,
            id_kategori_produk INTEGER REFERENCES dim_kategori_produk(id_kategori_produk),
            id_kategori_nutrisi INTEGER REFERENCES dim_kategori_nutrisi(id_kategori_nutrisi),
            kalori_per_porsi FLOAT DEFAULT 0,
            protein_gram FLOAT DEFAULT 0,
            karbohidrat_gram FLOAT DEFAULT 0,
            lemak_gram FLOAT DEFAULT 0,
            kalsium_mg FLOAT DEFAULT 0,
            zat_besi_mg FLOAT DEFAULT 0,
            vitamin_c_mg FLOAT DEFAULT 0,
            serat_gram FLOAT DEFAULT 0
        );
    """)

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

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_transaksi (
            id_transaksi INTEGER PRIMARY KEY,
            id_waktu INTEGER REFERENCES dim_waktu(id_waktu),
            id_produk INTEGER REFERENCES dim_produk(id_produk),
            jumlah_item INTEGER NOT NULL,
            harga_satuan FLOAT NOT NULL,
            jumlah_bayar FLOAT NOT NULL,
            catatan VARCHAR
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS staging_raw_log (
            log_id INTEGER,
            tanggal_transaksi DATE,
            nama_produk VARCHAR,
            kategori VARCHAR,
            jumlah INTEGER,
            harga FLOAT,
            total FLOAT,
            catatan VARCHAR,
            loaded_at TIMESTAMP DEFAULT current_timestamp
        );
    """)


# =============================================================================
# 2. ELT
# =============================================================================

def elt_extract_raw_data(con, raw_df: pd.DataFrame):
    """EXTRACT & LOAD: Memasukkan data mentah ke staging area."""
    con.execute("DELETE FROM staging_raw_log")
    con.register("raw_input", raw_df)
    con.execute("""
        INSERT INTO staging_raw_log (
            log_id, tanggal_transaksi, nama_produk, kategori,
            jumlah, harga, total, catatan
        )
        SELECT
            log_id, tanggal_transaksi, nama_produk, kategori,
            jumlah, harga, total, catatan
        FROM raw_input
    """)
    con.unregister("raw_input")


def elt_transform_load(con):
    """TRANSFORM: Transformasi data dari staging ke skema dimensional."""

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

    con.execute("""
        INSERT OR IGNORE INTO fact_transaksi (
            id_transaksi, id_waktu, id_produk,
            jumlah_item, harga_satuan, jumlah_bayar, catatan
        )
        SELECT
            s.log_id,
            CAST(strftime(s.tanggal_transaksi, '%Y%m%d') AS INTEGER),
            p.id_produk,
            s.jumlah,
            s.harga,
            s.total,
            s.catatan
        FROM staging_raw_log s
        LEFT JOIN dim_produk p ON s.nama_produk = p.nama_produk
        WHERE s.log_id NOT IN (SELECT id_transaksi FROM fact_transaksi)
    """)


# =============================================================================
# 3. MATERIALIZED VIEWS
# =============================================================================

def create_materialized_views(con):
    """Membuat Materialized Views untuk KPI dashboard."""

    con.execute("DROP TABLE IF EXISTS mv_ringkasan_bulanan")
    con.execute("""
        CREATE TABLE mv_ringkasan_bulanan AS
        SELECT
            w.tahun, w.bulan, w.nama_bulan,
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

    con.execute("DROP TABLE IF EXISTS mv_ringkasan_harian")
    con.execute("""
        CREATE TABLE mv_ringkasan_harian AS
        SELECT
            w.tanggal, w.hari, w.nama_bulan,
            COUNT(f.id_transaksi) AS total_transaksi,
            SUM(f.jumlah_bayar) AS total_pengeluaran,
            AVG(f.jumlah_bayar) AS rata_rata_pengeluaran
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        GROUP BY w.tanggal, w.hari, w.nama_bulan
        ORDER BY w.tanggal
    """)

    con.execute("DROP TABLE IF EXISTS mv_nutrisi_harian")
    con.execute("""
        CREATE TABLE mv_nutrisi_harian AS
        SELECT
            w.tanggal,
            SUM(p.kalori_per_porsi * f.jumlah_item) AS total_kalori,
            SUM(p.protein_gram * f.jumlah_item) AS total_protein,
            SUM(p.karbohidrat_gram * f.jumlah_item) AS total_karbohidrat,
            SUM(p.lemak_gram * f.jumlah_item) AS total_lemak,
            SUM(p.kalsium_mg * f.jumlah_item) AS total_kalsium,
            SUM(p.zat_besi_mg * f.jumlah_item) AS total_zat_besi,
            SUM(p.vitamin_c_mg * f.jumlah_item) AS total_vitamin_c,
            SUM(p.serat_gram * f.jumlah_item) AS total_serat
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        JOIN dim_produk p ON f.id_produk = p.id_produk
        GROUP BY w.tanggal
        ORDER BY w.tanggal
    """)

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

    # MV: Nutrisi Bulanan (untuk saran)
    con.execute("DROP TABLE IF EXISTS mv_nutrisi_bulanan")
    con.execute("""
        CREATE TABLE mv_nutrisi_bulanan AS
        SELECT
            w.tahun, w.bulan, w.nama_bulan,
            COUNT(DISTINCT w.tanggal) AS jumlah_hari,
            SUM(p.kalori_per_porsi * f.jumlah_item) AS total_kalori,
            SUM(p.protein_gram * f.jumlah_item) AS total_protein,
            SUM(p.karbohidrat_gram * f.jumlah_item) AS total_karbohidrat,
            SUM(p.lemak_gram * f.jumlah_item) AS total_lemak,
            SUM(p.kalsium_mg * f.jumlah_item) AS total_kalsium,
            SUM(p.zat_besi_mg * f.jumlah_item) AS total_zat_besi,
            SUM(p.vitamin_c_mg * f.jumlah_item) AS total_vitamin_c,
            SUM(p.serat_gram * f.jumlah_item) AS total_serat
        FROM fact_transaksi f
        JOIN dim_waktu w ON f.id_waktu = w.id_waktu
        JOIN dim_produk p ON f.id_produk = p.id_produk
        GROUP BY w.tahun, w.bulan, w.nama_bulan
        ORDER BY w.tahun, w.bulan
    """)


# =============================================================================
# 4. BITMAP INDEX & PARTITION PRUNING
# =============================================================================

def create_bitmap_indexes(con):
    """Bitmap Index untuk kolom kategori produk (kardinalitas rendah)."""
    con.execute("DROP TABLE IF EXISTS idx_bitmap_kategori")
    con.execute("""
        CREATE TABLE idx_bitmap_kategori AS
        SELECT
            f.id_transaksi,
            CASE WHEN kp.nama_kategori = 'Makanan Pokok' THEN 1 ELSE 0 END AS is_makanan_pokok,
            CASE WHEN kp.nama_kategori = 'Lauk Pauk' THEN 1 ELSE 0 END AS is_lauk_pauk,
            CASE WHEN kp.nama_kategori = 'Jajanan & Snack' THEN 1 ELSE 0 END AS is_jajanan,
            CASE WHEN kp.nama_kategori = 'Minuman' THEN 1 ELSE 0 END AS is_minuman
        FROM fact_transaksi f
        JOIN dim_produk p ON f.id_produk = p.id_produk
        JOIN dim_kategori_produk kp ON p.id_kategori_produk = kp.id_kategori_produk
    """)


def query_with_partition_pruning(con, bulan: int, tahun: int):
    """Partition Pruning: Hanya membaca data pada partisi bulan/tahun tertentu."""
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
    """Data Profiling: Mendeteksi anomali di staging sebelum transformasi."""
    results = {}
    results["total_baris"] = con.execute("SELECT COUNT(*) FROM staging_raw_log").fetchone()[0]
    results["baris_null"] = con.execute("""
        SELECT COUNT(*) FROM staging_raw_log
        WHERE nama_produk IS NULL OR kategori IS NULL OR harga IS NULL OR total IS NULL
    """).fetchone()[0]
    results["duplikasi_id"] = con.execute("""
        SELECT COUNT(*) - COUNT(DISTINCT log_id) FROM staging_raw_log
    """).fetchone()[0]
    results["harga_anomali"] = con.execute("""
        SELECT COUNT(*) FROM staging_raw_log WHERE harga < 0 OR harga > 1000000
    """).fetchone()[0]
    results["jumlah_anomali"] = con.execute("""
        SELECT COUNT(*) FROM staging_raw_log WHERE jumlah <= 0 OR jumlah > 100
    """).fetchone()[0]
    stats = con.execute("""
        SELECT MIN(harga), MAX(harga), AVG(harga), STDDEV(harga) FROM staging_raw_log
    """).fetchone()
    results["stats_harga"] = {
        "min": stats[0], "max": stats[1],
        "avg": round(stats[2], 2) if stats[2] else 0,
        "stddev": round(stats[3], 2) if stats[3] else 0
    }
    return results


def get_data_lineage(con, id_transaksi: int):
    """Data Lineage: Melacak asal-usul angka di tabel fakta."""
    lineage = {}
    fact = con.execute("SELECT * FROM fact_transaksi WHERE id_transaksi = ?", [id_transaksi]).fetchdf()
    lineage["fact_transaksi"] = fact.to_dict("records") if not fact.empty else []
    raw = con.execute("SELECT * FROM staging_raw_log WHERE log_id = ?", [id_transaksi]).fetchdf()
    lineage["staging_raw_log"] = raw.to_dict("records") if not raw.empty else []
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
    return lineage


# =============================================================================
# 6. QUERY ANALITIK
# =============================================================================

def snowflake_join_kategori(con):
    """Snowflake Join: Fakta -> Produk -> Kategori Produk."""
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
    """Snowflake Join: Fakta -> Produk -> Kategori Nutrisi."""
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
    return con.execute("SELECT * FROM mv_ringkasan_harian ORDER BY tanggal").fetchdf()


def get_ringkasan_bulanan(con):
    return con.execute("SELECT * FROM mv_ringkasan_bulanan ORDER BY tahun, bulan").fetchdf()


def get_nutrisi_harian(con):
    return con.execute("SELECT * FROM mv_nutrisi_harian ORDER BY tanggal").fetchdf()


def get_nutrisi_bulanan(con):
    """Ambil data nutrisi bulanan dari MV."""
    return con.execute("SELECT * FROM mv_nutrisi_bulanan ORDER BY tahun, bulan").fetchdf()


def get_bitmap_index_demo(con, kategori: str):
    """Demo Bitmap Index untuk filter kategori makanan."""
    col_map = {
        "Makanan Pokok": "is_makanan_pokok",
        "Lauk Pauk": "is_lauk_pauk",
        "Jajanan & Snack": "is_jajanan",
        "Minuman": "is_minuman"
    }
    col = col_map.get(kategori, "is_makanan_pokok")
    return con.execute(f"""
        SELECT b.*, f.jumlah_bayar, p.nama_produk
        FROM idx_bitmap_kategori b
        JOIN fact_transaksi f ON b.id_transaksi = f.id_transaksi
        JOIN dim_produk p ON f.id_produk = p.id_produk
        WHERE b.{col} = 1
        LIMIT 20
    """).fetchdf()


# =============================================================================
# 7. SARAN NUTRISI BULANAN
# =============================================================================

def generate_monthly_nutrition_advice(con, bulan: int, tahun: int = 2025):
    """
    Menghasilkan saran nutrisi bulanan berdasarkan data konsumsi aktual.
    Membandingkan rata-rata harian dengan AKG (Angka Kecukupan Gizi) dewasa muda.
    """
    # AKG harian dewasa muda (19-29 tahun, laki-laki/perempuan rata-rata)
    akg = {
        "kalori": {"target": 2150, "unit": "kcal", "label": "Kalori"},
        "protein": {"target": 60, "unit": "g", "label": "Protein"},
        "karbohidrat": {"target": 300, "unit": "g", "label": "Karbohidrat"},
        "lemak": {"target": 65, "unit": "g", "label": "Lemak"},
        "kalsium": {"target": 1000, "unit": "mg", "label": "Kalsium"},
        "zat_besi": {"target": 15, "unit": "mg", "label": "Zat Besi"},
        "vitamin_c": {"target": 75, "unit": "mg", "label": "Vitamin C"},
        "serat": {"target": 30, "unit": "g", "label": "Serat"},
    }

    try:
        row = con.execute("""
            SELECT * FROM mv_nutrisi_bulanan WHERE bulan = ? AND tahun = ?
        """, [bulan, tahun]).fetchdf()
    except Exception:
        return [], {}

    if row.empty:
        return [], {}

    r = row.iloc[0]
    jumlah_hari = max(int(r["jumlah_hari"]), 1)

    avg_daily = {
        "kalori": float(r["total_kalori"]) / jumlah_hari,
        "protein": float(r["total_protein"]) / jumlah_hari,
        "karbohidrat": float(r["total_karbohidrat"]) / jumlah_hari,
        "lemak": float(r["total_lemak"]) / jumlah_hari,
        "kalsium": float(r["total_kalsium"]) / jumlah_hari,
        "zat_besi": float(r["total_zat_besi"]) / jumlah_hari,
        "vitamin_c": float(r["total_vitamin_c"]) / jumlah_hari,
        "serat": float(r["total_serat"]) / jumlah_hari,
    }

    saran = []
    detail = {}

    for key, info in akg.items():
        actual = avg_daily[key]
        target = info["target"]
        pct = (actual / target) * 100 if target > 0 else 0
        status = "baik" if 80 <= pct <= 120 else ("kurang" if pct < 80 else "berlebih")

        detail[key] = {
            "actual": round(actual, 1),
            "target": target,
            "pct": round(pct, 1),
            "unit": info["unit"],
            "label": info["label"],
            "status": status
        }

        if status == "kurang":
            tips = {
                "kalori": "Tambah porsi makanan pokok seperti nasi atau roti.",
                "protein": "Perbanyak lauk pauk seperti ayam, telur, tempe, atau ikan.",
                "karbohidrat": "Konsumsi lebih banyak nasi, mie, atau roti.",
                "lemak": "Tambahkan sumber lemak sehat seperti kacang atau alpukat.",
                "kalsium": "Tingkatkan konsumsi susu, tahu, tempe, atau sayur bayam.",
                "zat_besi": "Perbanyak makan sayur bayam, rendang, atau tempe goreng.",
                "vitamin_c": "Tambahkan buah-buahan segar atau jus ke menu harian.",
                "serat": "Perbanyak konsumsi sayuran dan buah-buahan segar.",
            }
            saran.append({
                "type": "warning",
                "icon": "⚠️",
                "nutrisi": info["label"],
                "message": f"Konsumsi {info['label']} kurang ({pct:.0f}% dari AKG).",
                "tip": tips.get(key, ""),
                "pct": pct
            })
        elif status == "berlebih":
            tips = {
                "kalori": "Kurangi porsi atau ganti camilan berat dengan buah.",
                "protein": "Kurangi porsi lauk, seimbangkan dengan sayur.",
                "karbohidrat": "Ganti sebagian nasi dengan sayuran.",
                "lemak": "Kurangi gorengan, pilih makanan rebus atau kukus.",
                "kalsium": "Kalsium umumnya aman berlebih, tetap jaga keseimbangan.",
                "zat_besi": "Kurangi konsumsi daging merah berlebihan.",
                "vitamin_c": "Vitamin C berlebih biasanya aman, tetap jaga variasi.",
                "serat": "Serat berlebih bisa ganggu pencernaan, kurangi sedikit.",
            }
            saran.append({
                "type": "info",
                "icon": "📊",
                "nutrisi": info["label"],
                "message": f"Konsumsi {info['label']} berlebih ({pct:.0f}% dari AKG).",
                "tip": tips.get(key, ""),
                "pct": pct
            })
        else:
            saran.append({
                "type": "success",
                "icon": "✅",
                "nutrisi": info["label"],
                "message": f"Konsumsi {info['label']} sudah baik ({pct:.0f}% dari AKG).",
                "tip": "Pertahankan pola makan saat ini!",
                "pct": pct
            })

    # Urutkan: kurang dulu, lalu berlebih, lalu baik
    order = {"warning": 0, "info": 1, "success": 2}
    saran.sort(key=lambda x: order.get(x["type"], 3))

    return saran, detail
