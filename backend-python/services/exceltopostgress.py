import os, re, sys, datetime as dt
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

POSTGRES_URI = os.getenv(
    "POSTGRES_URI",
    "dbname=data user=root password=Noclex1965 host=localhost port=5435"
)
TABLE_NAME  = os.getenv("POSTGRES_TABLE", "data_fiber")
XLSX_PATH   = os.getenv("CUSTOMERS_XLSX", "DATA FIBER LEXXADATA (2).xlsx")
BATCH_SIZE  = int(os.getenv("BATCH_SIZE", "1000"))

def parse_sheet_name(name: str):
    n = (name or "").strip()
    if not n or n.upper().startswith("TOTAL") or n.upper() in {"FIBER","SUMMARY","SHEET1"}:
        return None, None
    m = re.search(r"^(?P<olt>[A-Z]+)(?:\s+[A-Z0-9\s]+?)?(?:\s+PORT)?\s+(?P<port>[\d\.]+)\s*$", n, re.I)
    if not m:
        return n.upper(), None
    return m.group("olt").strip().upper(), m.group("port").strip()

def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=lambda c: str(c).strip().lower() if c else "")
    return df

CANDIDATE_COLS = {
    "name": ["nama","name","customer","pelanggan"],
    "pppoe": ["user pppoe","user_pppoe","pppoe","no internet","no. internet","internet","id internet"],
    "address": ["alamat","address","addr"],
    "onu_port": ["port onu","onu port","port","port_onu"],
    "onu_sn": ["no. sn","sn","serial","no sn","onu sn","serial number","serial_number"],
    "password": ["password","pppoe password","pw","pass"],
    "mac": ["mac","mac address","mac_address"],
    "paket": ["paket", "Paket", "PAKET"],
}

def pick(df: pd.DataFrame, keys: list[str]) -> str | None:
    for k in keys:
        if k in df.columns:
            return k
    return None

def docs_from_sheet(xl: pd.ExcelFile, sheet: str):
    olt_name, olt_port = parse_sheet_name(sheet)
    if not olt_name:
        return

    try:
        temp_df = xl.parse(sheet, header=None)
        header_row_index = -1

        for i, row in temp_df.head(20).iterrows():
            row_str = ' '.join(str(s).lower() for s in row.dropna())
            if "nama" in row_str and ("pppoe" in row_str or "alamat" in row_str):
                header_row_index = i
                break

        if header_row_index == -1:
            print(f"[WARN] Could not find a valid header in sheet '{sheet}'. Skipping.")
            return

        df = xl.parse(sheet, header=header_row_index, dtype=str).fillna("")

    except Exception as e:
        print(f"[WARN] Cannot read sheet '{sheet}': {e}")
        return

    df = norm_cols(df)
    cols = {k: pick(df, v) for k, v in CANDIDATE_COLS.items()}

    required_ok = (cols["name"] and (cols["pppoe"] or cols["address"]))
    if not required_ok:
        print(f"[INFO] Skip sheet '{sheet}' (missing essential columns after header detection)")
        return

    for _, r in df.iterrows():
        name = r.get(cols["name"], "").strip() if cols["name"] else ""
        pppoe = r.get(cols["pppoe"], "").strip() if cols["pppoe"] else ""
        addr = r.get(cols["address"], "").strip() if cols["address"] else ""
        paket = r.get(cols["paket"], "").strip() if cols["paket"] else ""
        if not (name or pppoe or addr):
            continue

        onu_port_val = (r.get(cols["onu_port"], "").strip() if cols["onu_port"]
else None) or None
        final_olt_port = olt_port
        onu_id_val = None

        if onu_port_val and ":" in onu_port_val:
            parts = onu_port_val.split(':', 1)
            final_olt_port = parts[0]
            if len(parts) > 1:
                onu_id_val = parts[1]

        yield {
            "user_pppoe": pppoe,
            "name": name,
            "alamat": addr,
            "olt_name": olt_name,
            "olt_port": final_olt_port,
            "onu_sn": (r.get(cols["onu_sn"], "").strip().upper() if cols["onu_sn"] else None) or None,
            "pppoe_password": (r.get(cols["password"], "").strip() if cols["password"] else None) or None,
            "interface": onu_port_val,
            "onu_id": onu_id_val,
            "sheet": sheet,
            "paket": paket,
            "updated_at": dt.datetime.utcnow(),
        }

def run():
    if not os.path.exists(XLSX_PATH):
        print(f"[ERROR] Excel file not found: {XLSX_PATH}")
        sys.exit(1)

    conn = psycopg2.connect(POSTGRES_URI)
    cur = conn.cursor()

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        user_pppoe TEXT PRIMARY KEY,
        name TEXT,
        alamat TEXT,
        olt_name TEXT,
        olt_port TEXT,
        onu_sn TEXT,
        pppoe_password TEXT,
        interface TEXT,
        onu_id TEXT,
        sheet TEXT,
        paket TEXT,
        updated_at TIMESTAMP
    );
    """)
    conn.commit()

    xl = pd.ExcelFile(XLSX_PATH)
    sheet_count = len(xl.sheet_names)
    print(f"Found {sheet_count} sheets. Starting import...")

    rows = []
    total = 0

    for i, sheet in enumerate(xl.sheet_names):
        print(f"[{i+1}/{sheet_count}] Processing sheet: {sheet}")
        for doc in docs_from_sheet(xl, sheet) or []:
            rows.append((
                doc["user_pppoe"], doc["name"], doc["alamat"], doc["olt_name"],
                doc["olt_port"], doc["onu_sn"], doc["pppoe_password"], doc["interface"],
                doc["onu_id"], doc["sheet"], doc["paket"], doc["updated_at"]
            ))
            if len(rows) >= BATCH_SIZE:
                upsert_rows(cur, rows)
                total += len(rows)
                rows.clear()
                conn.commit()
                print(f"... upserted {total} rows so far")

    if rows:
        upsert_rows(cur, rows)
        total += len(rows)
        conn.commit()

    print(f"[DONE] Import complete. Total rows upserted: {total}")
    cur.close()
    conn.close()

def upsert_rows(cur, rows):
    sql = f"""
    INSERT INTO {TABLE_NAME} (
        user_pppoe, name, alamat, olt_name, olt_port, onu_sn,
        pppoe_password, interface, onu_id, sheet, paket, updated_at
    )
    VALUES (
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
    )
    ON CONFLICT (user_pppoe)
    DO UPDATE SET
        name = EXCLUDED.name,
        alamat = EXCLUDED.alamat,
        olt_name = EXCLUDED.olt_name,
        olt_port = EXCLUDED.olt_port,
        onu_sn = EXCLUDED.onu_sn,
        pppoe_password = EXCLUDED.pppoe_password,
        interface = EXCLUDED.interface,
        onu_id = EXCLUDED.onu_id,
        sheet = EXCLUDED.sheet,
        paket = EXCLUDED.paket,
        updated_at = EXCLUDED.updated_at;
    """
    execute_batch(cur, sql, rows, page_size=1000)

if __name__ == "__main__":
    run()
