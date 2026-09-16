       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTVAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-ACCT-OK    PIC X VALUE SPACE.
       01 WS-FRAUD-OK   PIC X VALUE SPACE.
       01 WS-RESULT     PIC X(8) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL "CHKDIGIT".
           CALL "FRAUDCHK".
           PERFORM DECIDE.
           STOP RUN.
       DECIDE.
           IF WS-ACCT-OK = 'Y'
               IF WS-FRAUD-OK = 'Y'
                   MOVE 'ACCEPT' TO WS-RESULT
               ELSE
                   MOVE 'HOLD' TO WS-RESULT
               END-IF
           ELSE
               MOVE 'REJECT' TO WS-RESULT
           END-IF.
           DISPLAY WS-RESULT.
