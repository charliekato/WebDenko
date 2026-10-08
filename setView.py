#!/usr/bin/env python
import sys
import pyodbc
import xml.etree.ElementTree as ET
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


tree = ET.parse("webdenko.config")
root = tree.getroot()
connectionStr = root.find("connectionStr").text

sql="""
CREATE FUNCTION dbo.fn_タイム秒 (@ゴール nvarchar(9))
RETURNS decimal(10,2)
AS
BEGIN
    RETURN
        CASE
            WHEN NULLIF(@ゴール,'') IS NULL THEN NULL
            WHEN CHARINDEX(':', @ゴール) > 0 THEN
                TRY_CAST(LEFT(@ゴール, CHARINDEX(':', @ゴール) - 1) AS decimal(10,2)) * 60
              + TRY_CAST(SUBSTRING(@ゴール, CHARINDEX(':', @ゴール) + 1, 10) AS decimal(10,2))
            ELSE
                TRY_CAST(@ゴール AS decimal(10,2))
        END;
END;
"""
try:
    execute(sql)
except:
    print("fn_タイム秒はすでにinstallされています。")


sql = """
IF OBJECT_ID('[dbo].v記録', 'V') IS NOT NULL
	DROP VIEW v記録
"""
execute(sql)
sql="""

CREATE VIEW v記録 AS

    SELECT 
	r.大会番号,
	プログラム.表示用競技番号 as 表示用競技番号,
	プログラム.競技番号 as 競技番号,
	r.組,
	r.水路,
	r.新記録判定クラス as クラス番号,
	case r.新記録判定クラス
	    when 0 then ''
		else 	クラス.クラス名称
	end as クラス名称,
	r.FINAポイント,
	資格級,
	case プログラム.性別コード
	    when 1 then '男子'
	    when 2 then '女子'
	    when 3 then '混成'
	    when 4 then '混合'
	end as 性別,
	プログラム.性別コード,
    距離.距離 ,
	プログラム.距離コード,
    種目.種目,
	プログラム.種目コード,
	予決.予決,
	case 予決.予決
	　when '予選' then 使用水路予選
	  when 'タイム決勝' then 使用水路タイム決勝
	  when '準決勝' then 使用水路準決勝
	  else 使用水路タイム決勝
	end as MAXLANE,
	ゼロコース使用,
		case タッチ板
	  when 2 then 100
	  when 3 then 25
	  else 50
	end as LAPUNIT,
	事由表示,
	r.オープン,
	棄権印刷マーク,
	リレーチーム.チーム名 as 氏名,
	選手1.氏名 as 第1泳者, 
	選手2.氏名 as 第2泳者,
	選手3.氏名 as 第3泳者,
	選手4.氏名 as 第4泳者, 
	所属.所属名 as 所属名,

        r.ゴール, 
        r.新記録印刷マーク,  
	中間新記録マーク,
	    [25m], [50m], [75m], [100m], [125m], [150m], [175m], [200m],
	   [225m], [250m], [275m], [300m], [325m], [350m], [375m], [400m], 
	   [425m], [450m], [475m], [500m], [525m], [550m], [575m], [600m],
	   [625m], [650m], [675m], [700m], [725m], [750m], [775m], [800m],
	   [825m], [850m], [875m], [900m], [925m], [950m], [975m], [1000m],
	   [1025m],[1050m],[1075m],[1100m],[1125m],[1150m],[1175m],[1200m],
	   [1225m],[1250m],[1275m],[1300m],[1325m],[1350m],[1375m],[1400m],
	   [1425m],[1450m],[1475m],[1500m],
	   dbo.fn_タイム秒(ゴール) as タイム秒,
	   r.予備

   from 記録 r 
    inner join 大会設定 on 大会設定.大会番号=r.大会番号
    inner join リレーチーム on リレーチーム.チーム番号 = r.選手番号 and リレーチーム.大会番号 =r.大会番号
    LEFT JOIN 選手 as 選手1 ON 選手1.選手番号 = r.第１泳者 and 選手1.大会番号=r.大会番号
    LEFT join 選手 as 選手2 on 選手2.選手番号 = r.第２泳者 and 選手2.大会番号=r.大会番号
    LEFT join 選手 as 選手3 on 選手3.選手番号 = r.第３泳者 and 選手3.大会番号=r.大会番号
    LEFT join 選手 as 選手4 on 選手4.選手番号 = r.第４泳者 and 選手4.大会番号=r.大会番号
    inner join プログラム on プログラム.競技番号=r.競技番号 and プログラム.大会番号=  r.大会番号
    inner join 距離 on 距離.距離コード=プログラム.距離コード
    inner join 種目 on 種目.種目コード=プログラム.種目コード
    inner join ラップ on ラップ.大会番号=r.大会番号　
	     and ラップ.競技番号=r.競技番号
	     and ラップ.組=r.組
	     and ラップ.水路=r.水路
    LEFT join クラス on クラス.大会番号=r.大会番号
	     and クラス.クラス番号=r.新記録判定クラス
    inner join 予決 on 予決.予決コード = プログラム.予決コード
    inner join 所属 on 所属.所属番号= リレーチーム.所属番号
       and 所属.大会番号=r.大会番号
    WHERE /*記録.事由表示 = 0 and*/ 

    　　プログラム.種目コード>5 
	 and ラップ.ラップ区分=0
union all
SELECT 
	r.大会番号,
	プログラム.表示用競技番号 as 表示用競技番号, 
	プログラム.競技番号 as 競技番号,
	r.組,
	r.水路,
	r.新記録判定クラス as クラス番号,
	ISNULL(クラス.クラス名称,'') AS クラス名称,    
	r.FINAポイント,
	資格級,
	case プログラム.性別コード 
	      when 1 then '男子'
	      when 2 then '女子'
	      when 3 then '混成'
	      when 4 then '混合'
	end as 性別,
	プログラム.性別コード,
	距離.距離,
	プログラム.距離コード,
	種目.種目,
	プログラム.種目コード,
	予決.予決,	
	case 予決.予決
	　when '予選' then 使用水路予選
	  when 'タイム決勝' then 使用水路タイム決勝
	  when '準決勝' then 使用水路準決勝
	  else 使用水路タイム決勝
	end as MAXLANE,
	ゼロコース使用,
	case タッチ板
	  when 2 then 100
	  when 3 then 25
	  else 50
	end as LAPUNIT,
	事由表示,
	オープン,
	棄権印刷マーク,
	選手.氏名  as 氏名,
	'' as 第1泳者,
	'' as 第2泳者,
	'' as 第3泳者,
	'' as 第4泳者,
	case 選手.主所属
	    when 2 then 選手.所属名称2
	    when 3 then 選手.所属名称3
	    else 選手.所属名称1
	end as 所属 ,
	ゴール, 
	新記録印刷マーク, 
	中間新記録マーク,
	[25m], [50m], [75m], [100m], [125m], [150m], [175m], [200m],
        [225m], [250m], [275m], [300m], [325m], [350m], [375m], [400m], 
	[425m], [450m], [475m], [500m], [525m], [550m], [575m], [600m],
	[625m], [650m], [675m], [700m], [725m], [750m], [775m], [800m],
	[825m], [850m], [875m], [900m], [925m], [950m], [975m], [1000m],
	[1025m],[1050m],[1075m],[1100m],[1125m],[1150m],[1175m],[1200m],
	[1225m],[1250m],[1275m],[1300m],[1325m],[1350m],[1375m],[1400m],
	[1425m],[1450m],[1475m],[1500m],
	dbo.fn_タイム秒(ゴール) as タイム秒,
	r.予備
	
       from 記録 r
        inner join 大会設定 on 大会設定.大会番号=r.大会番号
        INNER JOIN 選手 ON 選手.選手番号 = r.選手番号 
             and 選手.大会番号=r.大会番号
        inner join プログラム on プログラム.競技番号=r.競技番号 
             and プログラム.大会番号=r.大会番号
        inner join 距離 on 距離.距離コード=プログラム.距離コード
        inner join 種目 on 種目.種目コード=プログラム.種目コード
        inner join ラップ on ラップ.大会番号=r.大会番号　
	     and ラップ.競技番号=r.競技番号
	     and ラップ.組=r.組
	     and ラップ.水路=r.水路

        LEFT join クラス on クラス.大会番号=r.大会番号       
	     and クラス.クラス番号=r.新記録判定クラス  
        inner join 予決 on 予決.予決コード = プログラム.予決コード
     WHERE   
        ラップ.ラップ区分=0
	 and プログラム.種目コード<6 
	 """
            

execute(sql)



