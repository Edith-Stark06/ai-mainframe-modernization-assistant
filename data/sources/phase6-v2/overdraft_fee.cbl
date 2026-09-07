       IDENTIFICATION DIVISION.
       PROGRAM-ID. OVERDRFT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-BALANCE  PIC S9(7) VALUE 0.
       01 WS-OD-DAYS  PIC 9(3) VALUE 0.
       01 WS-FEE      PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM ASSESS-FEE.
           DISPLAY WS-FEE.
           STOP RUN.
       ASSESS-FEE.
           IF WS-BALANCE < 0
               MOVE 35 TO WS-FEE
               IF WS-OD-DAYS > 5
                   ADD 25 TO WS-FEE
               END-IF
           END-IF.
