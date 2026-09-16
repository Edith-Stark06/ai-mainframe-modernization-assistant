       IDENTIFICATION DIVISION.
       PROGRAM-ID. ELIGIBILITY.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-AGE          PIC 9(3) VALUE 0.
       01 WS-STATUS       PIC X VALUE SPACE.
       01 WS-RESULT       PIC X(10) VALUE SPACE.
       01 WS-AMOUNT       PIC 9(7) VALUE 0.
       01 WS-FEE          PIC 9(5) VALUE 0.
       01 WS-TOTAL        PIC 9(9) VALUE 0.
       01 WS-REVIEW       PIC X(10) VALUE SPACE.
       01 WS-ERROR-FLAG   PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM CHECK-ELIGIBILITY
           PERFORM CALCULATE-TOTAL
           PERFORM REVIEW-AMOUNT
           STOP RUN.
       CHECK-ELIGIBILITY.
           IF WS-AGE >= 18
               MOVE 'ELIGIBLE' TO WS-RESULT
           ELSE
               MOVE 'DENIED' TO WS-RESULT
           END-IF.
       CALCULATE-TOTAL.
           IF WS-STATUS = 'A'
               ADD WS-FEE TO WS-TOTAL
               MOVE 'VALID' TO WS-RESULT
           END-IF.
       REVIEW-AMOUNT.
           IF WS-AMOUNT > 50000
               MOVE 'FLAG' TO WS-REVIEW
               MOVE 'INVALID' TO WS-ERROR-FLAG
           END-IF.
       STATUS-STEP.
           IF WS-STATUS = 'P'
               MOVE 'A' TO WS-STATUS
           END-IF.
