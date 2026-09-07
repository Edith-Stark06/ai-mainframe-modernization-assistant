       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLLNP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-GROSS-PAY   PIC 9(7) VALUE 0.
       01 WS-TAX         PIC 9(7) VALUE 0.
       01 WS-NET-PAY     PIC 9(7) VALUE 0.
       01 WS-BRACKET     PIC X(6) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM CLASSIFY-BRACKET.
           PERFORM APPLY-TAX.
           PERFORM COMPUTE-NET.
           STOP RUN.
       CLASSIFY-BRACKET.
           IF WS-GROSS-PAY > 8000
               MOVE 'HIGH' TO WS-BRACKET
           ELSE
               MOVE 'LOW' TO WS-BRACKET
           END-IF.
       APPLY-TAX.
           IF WS-BRACKET = 'HIGH'
               MOVE 2400 TO WS-TAX
           ELSE
               MOVE 600 TO WS-TAX
           END-IF.
       COMPUTE-NET.
           MOVE WS-GROSS-PAY TO WS-NET-PAY.
           SUBTRACT WS-TAX FROM WS-NET-PAY.
           DISPLAY WS-NET-PAY.
