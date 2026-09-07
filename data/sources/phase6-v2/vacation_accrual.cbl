       IDENTIFICATION DIVISION.
       PROGRAM-ID. VACACCR.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-YEARS    PIC 9(2) VALUE 0.
       01 WS-DAYS     PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM ACCRUE.
           DISPLAY WS-DAYS.
           STOP RUN.
       ACCRUE.
           IF WS-YEARS >= 10
               MOVE 25 TO WS-DAYS
           ELSE
               IF WS-YEARS >= 5
                   MOVE 18 TO WS-DAYS
               ELSE
                   MOVE 12 TO WS-DAYS
               END-IF
           END-IF.
