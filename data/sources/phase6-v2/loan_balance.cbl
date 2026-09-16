       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOANBAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-BALANCE     PIC 9(7) VALUE 12000.
       01 WS-PAYMENT     PIC 9(5) VALUE 500.
       01 WS-MONTHS      PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM AMORTIZE.
           DISPLAY WS-MONTHS.
           STOP RUN.
       AMORTIZE.
           PERFORM UNTIL WS-BALANCE = 0
               IF WS-BALANCE < WS-PAYMENT
                   MOVE 0 TO WS-BALANCE
               ELSE
                   SUBTRACT WS-PAYMENT FROM WS-BALANCE
               END-IF
               ADD 1 TO WS-MONTHS
           END-PERFORM.
