import pyodbc
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn
import xml.etree.ElementTree as ET

from swlib.select_event import get_event_no

tree = ET.parse("WebReport.config")
root = tree.getroot()
connectionStr = root.find("connectionStr").text
app = FastAPI()

eventNo = get_event_no(connectionStr)


def execute(sql, *params, fetch="all"):
    with pyodbc.connect(connectionStr) as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)

        if fetch == "one":
            return cur.fetchone()

        if fetch == "all":
            return cur.fetchall()

        conn.commit()

def get_lap_unit() :
    sql = """
        SELECT タッチ板 as touchBoard 
        from 大会設定
        where 大会番号=?
        """
    row=execute(sql, eventNo, fetch="one")
    if row.touchBoard == 3 :
        return 25
    if row.touchBoard == 2 :
        return 100
    return 50

    

@app.get("/", response_class=HTMLResponse)
def index():
    lapUnit = get_lap_unit()
    query = r"""
    SELECT
        表示用競技番号 AS prgNo,
        組 AS kumi,
        水路 AS lane,
        氏名 AS name,
        ゴール AS goal,
        """
    for i in range(lapUnit,1500,lapUnit):
        query += f"[{i}m] as m{i},"
    query += """
        [1500m] as m1500
        FROM v記録
        WHERE 大会番号=?
        ORDER BY prgNo, kumi, lane
        """

    rows = execute(query, eventNo, fetch="all")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>競技結果</title>
        <style>
            .table-container {
                height: 500px;
                overflow-y: auto;
            }
            table {
                border-collapse: collapse;
            }
            td {
                border: 1px solid black;
                padding: 5px 10px;
                }
            th {
                border: 1px solid black;
                padding: 5px 10px;
                position: sticky;
                top: 0;
                background: white;
                z-index: 1;
            }
        </style>
    </head>
    <body>

    <h1>競技結果</h1>
    <div class="table-container">

    <table width="200%">
    <thead>
        <tr>
            <th>競技番号</th>
            <th>組</th>
            <th>水路</th>
            <th>氏名</th>
            <th>ゴール</th>
    """
    for i in range (lapUnit, 1501, lapUnit):
        html += f"<th>{i}</th>"
    html += """
            </tr>
            </thead>
            <tbody>
            """
    for row in rows:
        html += f"""
        <tr>
            <td>{row.prgNo}</td>
            <td>{row.kumi}</td>
            <td>{row.lane}</td>
            <td>{row.name}</td>
            <td>{row.goal}</td>
            """
        for i in range(lapUnit, 1501, lapUnit) :
            html += f"<td>{getattr(row,f'm{i}')}</td>"

    html += """
    </tr>
    </tbody>
    </table>
    </div>

    </body>
    </html>
    """

    return html


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
