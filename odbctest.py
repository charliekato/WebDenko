#!/usr/bin/env python3

import pyodbc
#linux(raspi) の場合
#connectionStr="""
#　　　DRIVER=FreeTDS;SERVER=Olivia.local;PORT=1433;UID=sw;DATABASE=sw;PWD=StrongPassword123!;TDS_Version=7.4;
#"""
#windows localhostの場合
connectionStr="""DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;
                DATABASE=sw;TrustServerCertificate=yes;Trusted_Connection=yes;
		"""
 
eventNo=4
prgNo=1
kumi=1

print("program started")

def get_UID_from_prgNo(prgNumber) -> int:
    sql = """
    	SELECT 競技番号 from プログラム 
	  WHERE 大会番号=? 
	  AND 表示用競技番号=?
	  """
    row=execute(sql,eventNo, prgNumber,fetch="one")
    return row[0] if row else 0
def get_last_occupied_lane() -> int:
    uid = get_UID_from_prgNo(prgNo)
    sql = """
	SELECT MAX(水路) as MaxLane
	 FROM v記録 WHERE 組=? AND 表示用競技番号=?
	 AND 選手番号>0  AND 大会番号=?
	 """
    row=execute(sql,eventNo, uid,fetch="one")
    return row[0] if row else 0
def get_first_occupied_lane(thisprgNo) -> int:
    uid = get_UID_from_prgNo(thisprgNo)
    sql = """
	SELECT MIN(水路) as MinLane
	 FROM v記録 WHERE 組=? AND 表示用競技番号=?
	 AND 選手番号>0  AND 大会番号=?
	 """
    row=execute(sql,eventNo, uid,fetch="one")
    return row[0] if row else 0


# ===== SQL SERVER ====
def execute(sql, *params, fetch="none"):
    with pyodbc.connect(connectionStr) as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)

        if fetch == "one":
            return cur.fetchone()

        if fetch == "all":
            return cur.fetchall()

        conn.commit()

for i in range (1, 20, 1) :
    uid = get_UID_from_prgNo(i)
    print(f"UID => { uid }     prgNo => {i}")

