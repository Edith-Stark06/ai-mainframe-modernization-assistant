       IDENTIFICATION DIVISION.
       PROGRAM-ID. COMPLEXPROC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-STATUS  PIC X VALUE SPACE.
       01 WS-AGE     PIC 9(3) VALUE 0.
       01 WS-AMOUNT  PIC 9(7) VALUE 0.
       01 WS-TOTAL   PIC 9(9) VALUE 0.
       01 WS-RESULT  PIC X(10) VALUE SPACE.
       01 WS-IDX     PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM VALIDATE-PARA.
           PERFORM ACCUMULATE-PARA.
           PERFORM CLASSIFY-PARA.
           STOP RUN.
       VALIDATE-PARA.
           IF WS-AGE >= 18
               IF WS-STATUS = 'A'
                   MOVE 'ELIGIBLE' TO WS-RESULT
               END-IF
           END-IF.
       ACCUMULATE-PARA.
           PERFORM UNTIL WS-IDX > 10
               ADD WS-AMOUNT TO WS-TOTAL
               ADD 1 TO WS-IDX
           END-PERFORM.
       CLASSIFY-PARA.
           IF WS-TOTAL > 50000
               MOVE 'HIGH' TO WS-RESULT
           ELSE
               MOVE 'LOW' TO WS-RESULT
           END-IF.
