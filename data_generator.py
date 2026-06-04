"""
data_generator.py - Generator Data Realistis Kos Mahasiswa
============================================================
Menghasilkan data simulasi pengeluaran harian mahasiswa kos
selama rentang waktu tertentu. Data meliputi:
  - Makanan & minuman harian (warung, kantin, minimarket)
  - Kebutuhan utilitas (listrik, air, internet)
  - Kebutuhan pribadi (laundry, toiletries, dll.)
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta


def generate_dimension_data():
    """Menghasilkan data dimensi yang realistis untuk kehidupan kos."""

    # --- Kategori Nutrisi ---
    kategori_nutrisi = pd.DataFrame({
        "id_kategori_nutrisi": [1, 2, 3, 4, 5],
        "nama_kategori_nutrisi": [
            "Karbohidrat", "Protein", "Serat & Vitamin",
            "Lemak & Minyak", "Minuman"
        ],
        "deskripsi": [
            "Sumber energi utama: nasi, mie, roti",
            "Pembangun otot: ayam, telur, tempe, tahu",
            "Sumber vitamin & mineral: sayur, buah",
            "Sumber lemak: gorengan, santan",
            "Asupan cairan: air, teh, kopi, jus"
        ]
    })

    # --- Kategori Produk ---
    kategori_produk = pd.DataFrame({
        "id_kategori_produk": [1, 2, 3, 4, 5],
        "nama_kategori": [
            "Makanan Pokok", "Lauk Pauk", "Jajanan & Snack",
            "Minuman", "Utilitas & Lainnya"
        ],
        "deskripsi": [
            "Makanan utama sehari-hari",
            "Pendamping makanan pokok",
            "Camilan dan makanan ringan",
            "Minuman harian",
            "Tagihan listrik, air, internet, laundry"
        ]
    })

    # --- Produk (dengan detail nutrisi) ---
    produk_data = [
        # Makanan Pokok (kat_produk=1)
        (1, "Nasi Putih", 1, 1, 180, 4.0, 40.0, 0.3),
        (2, "Mie Instan", 1, 1, 350, 8.0, 45.0, 14.0),
        (3, "Nasi Goreng", 1, 1, 400, 10.0, 55.0, 15.0),
        (4, "Nasi Uduk", 1, 1, 390, 8.0, 50.0, 16.0),
        (5, "Lontong Sayur", 1, 1, 280, 6.0, 35.0, 12.0),
        (6, "Bubur Ayam", 1, 2, 300, 15.0, 30.0, 10.0),
        # Lauk Pauk (kat_produk=2)
        (7, "Ayam Goreng", 2, 2, 260, 25.0, 5.0, 15.0),
        (8, "Telur Dadar", 2, 2, 150, 11.0, 1.0, 11.0),
        (9, "Tempe Goreng", 2, 2, 160, 12.0, 8.0, 10.0),
        (10, "Tahu Goreng", 2, 2, 130, 9.0, 4.0, 9.0),
        (11, "Ikan Goreng", 2, 2, 200, 22.0, 2.0, 11.0),
        (12, "Rendang", 2, 4, 250, 20.0, 5.0, 17.0),
        (13, "Soto Ayam", 2, 2, 220, 18.0, 12.0, 10.0),
        # Jajanan & Snack (kat_produk=3)
        (14, "Gorengan", 3, 4, 200, 3.0, 20.0, 12.0),
        (15, "Bakso", 3, 2, 250, 14.0, 20.0, 12.0),
        (16, "Siomay", 3, 2, 180, 10.0, 15.0, 8.0),
        (17, "Roti Bakar", 3, 1, 280, 6.0, 35.0, 13.0),
        (18, "Martabak Manis", 3, 1, 450, 8.0, 55.0, 22.0),
        (19, "Pisang Goreng", 3, 4, 170, 2.0, 25.0, 8.0),
        # Minuman (kat_produk=4)
        (20, "Es Teh Manis", 4, 5, 80, 0.0, 20.0, 0.0),
        (21, "Kopi Sachet", 4, 5, 60, 1.0, 12.0, 1.0),
        (22, "Air Mineral", 4, 5, 0, 0.0, 0.0, 0.0),
        (23, "Jus Buah", 4, 5, 120, 1.0, 28.0, 0.5),
        (24, "Es Jeruk", 4, 5, 90, 0.5, 22.0, 0.0),
        (25, "Susu Kotak", 4, 5, 140, 5.0, 18.0, 5.0),
        # Utilitas (kat_produk=5)
        (26, "Token Listrik", 5, None, 0, 0, 0, 0),
        (27, "Tagihan Air", 5, None, 0, 0, 0, 0),
        (28, "Internet/WiFi", 5, None, 0, 0, 0, 0),
        (29, "Laundry Kiloan", 5, None, 0, 0, 0, 0),
        (30, "Sabun & Toiletries", 5, None, 0, 0, 0, 0),
    ]

    produk = pd.DataFrame(produk_data, columns=[
        "id_produk", "nama_produk", "id_kategori_produk",
        "id_kategori_nutrisi", "kalori_per_porsi", "protein_gram",
        "karbohidrat_gram", "lemak_gram"
    ])
    # id_kategori_nutrisi bisa None untuk utilitas
    produk["id_kategori_nutrisi"] = produk["id_kategori_nutrisi"].astype("Int64")

    # --- Metode Pembayaran ---
    metode_bayar = pd.DataFrame({
        "id_metode": [1, 2, 3, 4],
        "nama_metode": ["Cash", "QRIS", "Transfer", "E-Wallet"],
        "provider": ["Tunai", "QRIS Nasional", "Bank BCA/BRI", "GoPay/OVO/Dana"]
    })

    return kategori_nutrisi, kategori_produk, produk, metode_bayar


def generate_raw_transactions(start_date: str, end_date: str, seed: int = 42):
    """
    Menghasilkan log transaksi mentah harian yang realistis.
    Pola pengeluaran:
      - Mahasiswa makan 2-3x sehari + 1-2 snack/minuman
      - Utilitas dibayar 1-2x sebulan
      - Pengeluaran weekend sedikit lebih bervariasi
    """
    np.random.seed(seed)
    random.seed(seed)

    _, _, produk_df, _ = generate_dimension_data()

    # Harga realistis per produk (Rupiah)
    harga_map = {
        "Nasi Putih": (3000, 5000), "Mie Instan": (3000, 5000),
        "Nasi Goreng": (10000, 18000), "Nasi Uduk": (8000, 12000),
        "Lontong Sayur": (8000, 13000), "Bubur Ayam": (10000, 15000),
        "Ayam Goreng": (8000, 15000), "Telur Dadar": (3000, 5000),
        "Tempe Goreng": (2000, 4000), "Tahu Goreng": (1000, 3000),
        "Ikan Goreng": (10000, 18000), "Rendang": (12000, 20000),
        "Soto Ayam": (12000, 18000),
        "Gorengan": (1000, 3000), "Bakso": (10000, 18000),
        "Siomay": (8000, 15000), "Roti Bakar": (8000, 15000),
        "Martabak Manis": (15000, 35000), "Pisang Goreng": (2000, 5000),
        "Es Teh Manis": (3000, 5000), "Kopi Sachet": (2000, 4000),
        "Air Mineral": (3000, 5000), "Jus Buah": (8000, 15000),
        "Es Jeruk": (5000, 8000), "Susu Kotak": (5000, 8000),
        "Token Listrik": (50000, 100000), "Tagihan Air": (25000, 50000),
        "Internet/WiFi": (50000, 100000), "Laundry Kiloan": (15000, 30000),
        "Sabun & Toiletries": (10000, 30000),
    }

    kategori_map = dict(zip(
        produk_df["nama_produk"],
        produk_df["id_kategori_produk"].map({
            1: "Makanan Pokok", 2: "Lauk Pauk", 3: "Jajanan & Snack",
            4: "Minuman", 5: "Utilitas & Lainnya"
        })
    ))

    makanan_produk = produk_df[produk_df["id_kategori_produk"].isin([1, 2, 3])]["nama_produk"].tolist()
    minuman_produk = produk_df[produk_df["id_kategori_produk"] == 4]["nama_produk"].tolist()
    utilitas_produk = produk_df[produk_df["id_kategori_produk"] == 5]["nama_produk"].tolist()

    metode_list = ["Cash", "QRIS", "Transfer", "E-Wallet"]
    metode_weights = [0.4, 0.3, 0.15, 0.15]

    catatan_options = [
        "Sarapan", "Makan siang", "Makan malam", "Ngemil sore",
        "Beli di kantin", "Beli di warung", "Order online",
        "Belanja minimarket", "Bayar bulanan", "Stok mingguan",
        "", ""  # beberapa tanpa catatan
    ]

    transactions = []
    log_id = 1
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        is_weekend = current.weekday() >= 5

        # Jumlah transaksi makanan per hari (2-4, lebih di weekend)
        n_makanan = np.random.randint(2, 5 if is_weekend else 4)
        for _ in range(n_makanan):
            produk_name = random.choice(makanan_produk)
            harga_range = harga_map.get(produk_name, (5000, 15000))
            harga = random.randint(harga_range[0] // 1000, harga_range[1] // 1000) * 1000
            jumlah = random.choices([1, 2, 3], weights=[0.7, 0.25, 0.05])[0]

            transactions.append({
                "log_id": log_id,
                "tanggal_transaksi": current.date(),
                "nama_produk": produk_name,
                "kategori": kategori_map.get(produk_name, "Lainnya"),
                "jumlah": jumlah,
                "harga": float(harga),
                "total": float(harga * jumlah),
                "metode_bayar": random.choices(metode_list, weights=metode_weights)[0],
                "catatan": random.choice(catatan_options)
            })
            log_id += 1

        # Jumlah transaksi minuman per hari (1-3)
        n_minuman = np.random.randint(1, 4)
        for _ in range(n_minuman):
            produk_name = random.choice(minuman_produk)
            harga_range = harga_map.get(produk_name, (3000, 8000))
            harga = random.randint(harga_range[0] // 1000, harga_range[1] // 1000) * 1000
            jumlah = 1

            transactions.append({
                "log_id": log_id,
                "tanggal_transaksi": current.date(),
                "nama_produk": produk_name,
                "kategori": kategori_map.get(produk_name, "Lainnya"),
                "jumlah": jumlah,
                "harga": float(harga),
                "total": float(harga * jumlah),
                "metode_bayar": random.choices(metode_list, weights=metode_weights)[0],
                "catatan": random.choice(catatan_options)
            })
            log_id += 1

        # Utilitas: sekitar tanggal 1-5 dan 15-20 tiap bulan
        if current.day in range(1, 6) or current.day in range(15, 21):
            if random.random() < 0.3:  # ~30% chance per hari di range ini
                produk_name = random.choice(utilitas_produk)
                harga_range = harga_map.get(produk_name, (20000, 50000))
                harga = random.randint(harga_range[0] // 1000, harga_range[1] // 1000) * 1000

                transactions.append({
                    "log_id": log_id,
                    "tanggal_transaksi": current.date(),
                    "nama_produk": produk_name,
                    "kategori": "Utilitas & Lainnya",
                    "jumlah": 1,
                    "harga": float(harga),
                    "total": float(harga),
                    "metode_bayar": random.choices(
                        ["Transfer", "E-Wallet", "Cash"],
                        weights=[0.5, 0.3, 0.2]
                    )[0],
                    "catatan": "Bayar bulanan"
                })
                log_id += 1

        current += timedelta(days=1)

    return pd.DataFrame(transactions)


def initialize_warehouse(con, start_date="2025-01-01", end_date="2025-06-30"):
    """
    Pipeline utama: inisialisasi seluruh data warehouse.
    1. Buat skema Snowflake
    2. Load dimensi
    3. Generate & load raw data (Extract + Load)
    4. Transform ke skema dimensional
    5. Buat materialized views & indexes
    """
    from db_engine import create_snowflake_schema, elt_extract_raw_data, elt_transform_load
    from db_engine import create_materialized_views, create_bitmap_indexes

    # 1. Buat skema
    create_snowflake_schema(con)

    # 2. Load dimensi
    kat_nutrisi, kat_produk, produk, metode = generate_dimension_data()

    con.register("df_kn", kat_nutrisi)
    con.execute("INSERT OR IGNORE INTO dim_kategori_nutrisi SELECT * FROM df_kn")
    con.unregister("df_kn")

    con.register("df_kp", kat_produk)
    con.execute("INSERT OR IGNORE INTO dim_kategori_produk SELECT * FROM df_kp")
    con.unregister("df_kp")

    con.register("df_p", produk)
    con.execute("INSERT OR IGNORE INTO dim_produk SELECT * FROM df_p")
    con.unregister("df_p")

    con.register("df_m", metode)
    con.execute("INSERT OR IGNORE INTO dim_metode_bayar SELECT * FROM df_m")
    con.unregister("df_m")

    # 3. Generate raw data (Extract + Load)
    raw_df = generate_raw_transactions(start_date, end_date)
    elt_extract_raw_data(con, raw_df)

    # 4. Transform
    elt_transform_load(con)

    # 5. Materialized Views & Bitmap Index
    create_materialized_views(con)
    create_bitmap_indexes(con)

    return raw_df
