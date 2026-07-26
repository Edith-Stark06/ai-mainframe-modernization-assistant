       IDENTIFICATION DIVISION.
       PROGRAM-ID. INVALID-SYNTAX.
       
       PROCEDURE DIVISION.
           MOVE 5 TO WS-COUNT
           IF WS-COUNT >
               DISPLAY "MISSING RIGHT OPERAND"
           END-IF.
           STOP RUN.
