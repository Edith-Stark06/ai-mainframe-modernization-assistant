       IDENTIFICATION DIVISION.
       PROGRAM-ID. BONUSCALC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SALES    PIC 9(7) VALUE 0.
       01 WS-BONUS    PIC 9(6) VALUE 0.
       01 WS-RATING   PIC X(4) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM GRADE-SALES.
           PERFORM PAY-BONUS.
           STOP RUN.
       GRADE-SALES.
           IF WS-SALES > 100000
               MOVE 'GOLD' TO WS-RATING
           ELSE
               MOVE 'BASE' TO WS-RATING
           END-IF.
       PAY-BONUS.
           IF WS-RATING = 'GOLD'
               MOVE 5000 TO WS-BONUS
           ELSE
               MOVE 1000 TO WS-BONUS
           END-IF.
           DISPLAY WS-BONUS.
