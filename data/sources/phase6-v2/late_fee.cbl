       IDENTIFICATION DIVISION.
       PROGRAM-ID. LATEFEE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DAYS-LATE  PIC 9(4) VALUE 0.
       01 WS-FEE        PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM RATE-FEE.
           DISPLAY WS-FEE.
           STOP RUN.
       RATE-FEE.
           IF WS-DAYS-LATE > 30
               MOVE 5000 TO WS-FEE
           ELSE
               IF WS-DAYS-LATE > 7
                   MOVE 1500 TO WS-FEE
               ELSE
                   MOVE 0 TO WS-FEE
               END-IF
           END-IF.
