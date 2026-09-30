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
 
print("program started")

def get_last_prgNo(eventNo) -> int:
    sql = """
     	Select MAX(表示用競技番号) from プログラム 
	  where 大会番号=?
	  """
    row=execute(sql,eventNo, fetch="one")
    return row[0] if row else 0

def get_UID_from_prgNo(prgNo,eventNo) -> int:
    sql = """
    	SELECT 競技番号 from プログラム 
	  WHERE 大会番号=? 
	  AND 表示用競技番号=?
	  """
    row=execute(sql,eventNo, prgNo,fetch="one")
    return row[0] if row else 0
def get_last_occupied_lane(prgNo, kumi,eventNo) -> int:
    uid = get_UID_from_prgNo(prgNo,eventNo)
    sql = """
	SELECT MAX(水路) as MaxLane
	 FROM 記録 WHERE 組=? AND 競技番号=?
	 AND 選手番号>0  AND 大会番号=?
	 """
    row=execute(sql,kumi,uid,eventNo,fetch="one")
    return row[0] if row else 0
def get_first_occupied_lane(prgNo,kumi,eventNo) -> int:
    uid = get_UID_from_prgNo(prgNo,eventNo)
    sql = """
	SELECT MIN(水路) as MinLane
	 FROM 記録 WHERE 組=? AND 競技番号=?
	 AND 選手番号>0  AND 大会番号=?
	 """
    row=execute(sql,kumi,uid, eventNo,fetch="one")
    return row[0] if row else 0

def get_last_kumi(prgNo,eventNo) -> int:
    uid = get_UID_from_prgNo(prgNo,eventNo)
    sql = """
     SELECT MAX(組) from 記録 where 大会番号=?
      AND 競技番号=?
     """
    row = execute(sql,eventNo, uid,fetch="one")
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

eventNo=36
prgNo=1
kumi=1

lastPrgNo = get_last_prgNo(eventNo)

for prgNo in range (1, lastPrgNo+1, 1) :
    lastkumi = get_last_kumi(prgNo,eventNo)
    for kumi in range(1, lastkumi+1, 1) :
        firstlane = get_first_occupied_lane(prgNo,kumi,eventNo)
        lastlane = get_last_occupied_lane(prgNo,kumi,eventNo)
        print(f"prgNo {prgNo} kumi {kumi} first lane: {firstlane}  last lane {lastlane}")


