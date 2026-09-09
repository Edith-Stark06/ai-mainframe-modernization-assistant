       IDENTIFICATION DIVISION.
       PROGRAM-ID. CREDLIM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-INCOME   PIC 9(7) VALUE 0.
       01 WS-SCORE    PIC 9(3) VALUE 0.
       01 WS-LIMIT    PIC 9(7) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM DECIDE-LIMIT.
           DISPLAY WS-LIMIT.
           STOP RUN.
       DECIDE-LIMIT.
           IF WS-SCORE >= 700
               IF WS-INCOME > 60000
                   MOVE 20000 TO WS-LIMIT
               ELSE
                   MOVE 8000 TO WS-LIMIT
               END-IF
           ELSE
               MOVE 1000 TO WS-LIMIT
           END-IF.
