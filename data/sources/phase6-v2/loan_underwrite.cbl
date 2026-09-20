       IDENTIFICATION DIVISION.
       PROGRAM-ID. LNUNDRWT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CREDIT-SCORE   PIC 9(3) VALUE 720.
       01 WS-DTI-RATIO      PIC 9(2) VALUE 35.
       01 WS-COLLATERAL     PIC 9(7) VALUE 250000.
       01 WS-LOAN-AMOUNT    PIC 9(7) VALUE 200000.
       01 WS-DECISION       PIC X(12) VALUE SPACE.
       01 WS-INTEREST-RATE  PIC 9(2)V9(2) VALUE 05.50.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM ASSESS-CREDIT.
           PERFORM DETERMINE-RATE.
           DISPLAY WS-DECISION.
           DISPLAY WS-INTEREST-RATE.
           STOP RUN.
       ASSESS-CREDIT.
           IF WS-CREDIT-SCORE < 580
               MOVE 'REJECT_SCORE' TO WS-DECISION
           ELSE
               IF WS-DTI-RATIO > 45
                   MOVE 'REJECT_DTI' TO WS-DECISION
               ELSE
                   IF WS-COLLATERAL < WS-LOAN-AMOUNT
                       MOVE 'REJECT_COLL' TO WS-DECISION
                   ELSE
                       IF WS-CREDIT-SCORE >= 750
                           MOVE 'AUTO_APPROVE' TO WS-DECISION
                       ELSE
                           IF WS-CREDIT-SCORE >= 680
                               MOVE 'STD_APPROVE' TO WS-DECISION
                           ELSE
                               MOVE 'MANUAL_REV' TO WS-DECISION
                           END-IF
                       END-IF
                   END-IF
               END-IF
           END-IF.
       DETERMINE-RATE.
           IF WS-DECISION = 'AUTO_APPROVE'
               MOVE 04.25 TO WS-INTEREST-RATE
           ELSE
               IF WS-DECISION = 'STD_APPROVE'
                   MOVE 05.50 TO WS-INTEREST-RATE
               ELSE
                   IF WS-DECISION = 'MANUAL_REV'
                       MOVE 07.25 TO WS-INTEREST-RATE
                   ELSE
                       MOVE 00.00 TO WS-INTEREST-RATE
                   END-IF
               END-IF
           END-IF.
