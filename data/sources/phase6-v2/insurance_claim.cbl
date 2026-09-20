       IDENTIFICATION DIVISION.
       PROGRAM-ID. INCLM01.
       AUTHOR. SYNTHETIC-CORPUS.
      * CATEGORY A: RULE-DENSE BUSINESS LOGIC - INSURANCE CLAIMS
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  CLAIM-INPUTS.
           05  CLAIM-TYPE          PIC X(10) VALUE 'AUTO'.
           05  CLAIM-AMOUNT        PIC 9(7)V99 VALUE 0012500.00.
           05  POLICY-AGE-MONTHS   PIC 9(3) VALUE 024.
           05  PREVIOUS-CLAIMS     PIC 9(2) VALUE 01.
           05  POLICE-REPORT-FILED PIC X(1) VALUE 'Y'.
           05  DRIVER-AGE          PIC 9(3) VALUE 028.
           05  DEDUCTIBLE-PAID     PIC X(1) VALUE 'Y'.
       01  CLAIM-OUTPUTS.
           05  APPROVAL-STATUS     PIC X(10) VALUE 'PENDING'.
           05  PAYOUT-AMOUNT       PIC 9(7)V99 VALUE 0000000.00.
           05  FRAUD-RISK-SCORE    PIC 9(3) VALUE 000.
           05  REQUIRES-ADJUSTER   PIC X(1) VALUE 'N'.
           05  DENIAL-REASON       PIC X(30) VALUE SPACES.

       PROCEDURE DIVISION.
       0000-PROCESS-CLAIM.
           PERFORM 1000-EVALUATE-FRAUD-RISK
           PERFORM 2000-DETERMINE-ELIGIBILITY
           PERFORM 3000-CALCULATE-PAYOUT
           GOBACK.

       1000-EVALUATE-FRAUD-RISK.
           MOVE 0 TO FRAUD-RISK-SCORE
           IF POLICY-AGE-MONTHS < 6
               ADD 40 TO FRAUD-RISK-SCORE
           END-IF
           IF PREVIOUS-CLAIMS > 3
               ADD 30 TO FRAUD-RISK-SCORE
           END-IF
           IF POLICE-REPORT-FILED = 'N' AND CLAIM-AMOUNT > 5000.00
               ADD 25 TO FRAUD-RISK-SCORE
           END-IF
           IF DRIVER-AGE < 21 OR DRIVER-AGE > 75
               ADD 15 TO FRAUD-RISK-SCORE
           END-IF
           IF FRAUD-RISK-SCORE >= 50
               MOVE 'Y' TO REQUIRES-ADJUSTER
           END-IF.

       2000-DETERMINE-ELIGIBILITY.
           IF DEDUCTIBLE-PAID NOT = 'Y'
               MOVE 'DENIED' TO APPROVAL-STATUS
               MOVE 'UNPAID DEDUCTIBLE' TO DENIAL-REASON
           ELSE
               IF CLAIM-AMOUNT <= 0.00
                   MOVE 'DENIED' TO APPROVAL-STATUS
                   MOVE 'INVALID CLAIM AMOUNT' TO DENIAL-REASON
               ELSE
                   IF FRAUD-RISK-SCORE >= 70
                       MOVE 'REVIEW' TO APPROVAL-STATUS
                       MOVE 'HIGH FRAUD SCORE' TO DENIAL-REASON
                   ELSE
                       MOVE 'APPROVED' TO APPROVAL-STATUS
                   END-IF
               END-IF
           END-IF.

       3000-CALCULATE-PAYOUT.
           IF APPROVAL-STATUS = 'APPROVED'
               IF CLAIM-TYPE = 'AUTO'
                   IF CLAIM-AMOUNT > 20000.00
                       COMPUTE PAYOUT-AMOUNT = CLAIM-AMOUNT * 0.90
                   ELSE
                       COMPUTE PAYOUT-AMOUNT = CLAIM-AMOUNT * 0.95
                   END-IF
               ELSE
                   IF CLAIM-TYPE = 'PROPERTY'
                       COMPUTE PAYOUT-AMOUNT = CLAIM-AMOUNT * 0.85
                   ELSE
                       COMPUTE PAYOUT-AMOUNT = CLAIM-AMOUNT * 0.80
                   END-IF
               END-IF
           ELSE
               MOVE 0.00 TO PAYOUT-AMOUNT
           END-IF.
