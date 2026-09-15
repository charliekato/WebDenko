シリアルポートから来るtimer の data の仕様
  16byte で１つのパケット。先頭バイトがSTX(=\02) 終端バイトがETX(=\03)
  15byte目で lap, goal, 引継ぎ, reaction が決まる
  　　'L' -- lap
      'G' -- goal
      'K' -- 引継ぎ
      'J' -- リアクション
      上記以外 -- running timer (実際は spaceだが見る必要はない) または、reset信号

  2byte目 が 'R' なら running timer (もしくは、reset)
  running timerの時(2byte目が'R'の時)
     7byte目～13byte目が時間を示している 12byte目は常に'.'(小数点) 
     7byte目 -- 10分
     8       --  1分
     9       -- ':' (1分未満ではspace)
     10      -- 10秒
     11      --  1秒
     12      -- '.'
     13      -- 1/10秒
     14 (使用せず) 常に' ' (スペース)

     10byte目は1分以上の時は常に':' それ以外は' '(space)
     running timer は 1/10 秒まで 1/100秒の桁はない

  lap, goal の時は 
     7byte目～14byte目が時間を示している(
     3byte目と5byte目が着順 (実際には5byte目を見ている 3byte目は無視)
     4byte目はレーン番号 (0レーン使用時はそのまま使い、そうでないときは -1 が正しいレーン番号
  リアクションの時は
     10byte目～13byte目がタイム。10秒以上がどう表現されるか不明。　11byte目は常に'.'(小数点)
      (lap,goal,running timerと1byte左にずれる)
  　 4byte目はレーン番号　lap, goal の時と同じ
     
  引継ぎ時は
  　 4byte目はレーン番号　lap, goal の時と同じ


  1byte目 STX = \x02
  2byte目 常に 'A'
  3byte目 R は running timer 
  　　　　数字 -- LAPと Goalの時は着順のようだが、使用していない(don't care)
  4byte目 数字 -- レーン番号　(lap, 引継ぎ, リアクションタイム, Goal)
          space -- running timer
　5byte目 数字 -- Lap と Goalの時は着順
          0    -- 引継ぎの時は 0 のようだが、使っていない
         space -- リアクションタイムまたはrunning timer (使わない = don't care)

　byte 長　1 packet = 16 byte
   b'\x02AR    1:46.0  \x03'  <-- 通常の running timer \x02=STX, \x03=ETX

        123456789abcdefg
   b'\x02A 4  S0S0.69 J\x03'  <-- リアクションタイム　(どうも10秒以上は表現できないみたい)
   　　　             ^--- J が リアクションを表す　　

   ラップのデータ
   b'\x02A222  1:22.82L\x03'
                      ^ <--  Lap を表す (15byte目) ここが G なら goal
                      
   b'\x02A343  1:23.41L\x03'
              ^^^^^^^^ <--- タイム(STXが1byte目として7byte目～14byte目)

   b'\x02A454  1:29.30L\x03'
            ^----- 着順　この例では 4位 (5byte目)

   b'\x02A454  1:29.30L\x03'
           ^----- レーン番号　この例では 5レーン (4byte目)

   b'\x02A454  1:29.30L\x03'
          ^-----  これも着順(これは使っていない) (3byte目)



   b'\x02A0502 0+0.63 K\x03'  <-- 引継ぎ
   b'\x02A0202 0+0.51 K\x03'
   b'\x02A0402 0+0.54 K\x03'
  

How to run
1. activate virtual environment.
  In PowerShell do ;
.\.venv\Scripts\Activate.ps1
 
