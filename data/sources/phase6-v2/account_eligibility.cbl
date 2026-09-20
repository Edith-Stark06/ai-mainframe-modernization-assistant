       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCT01.
       AUTHOR. SYNTHETIC-CORPUS.
      * CATEGORY A: RULE-DENSE BUSINESS LOGIC - ACCOUNT ELIGIBILITY AND REWARDS
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  APPLICANT-DATA.
           05  AGE                 PIC 9(3) VALUE 035.
           05  CITIZENSHIP-STATUS  PIC X(10) VALUE 'CITIZEN'.
           05  ANNUAL-INCOME       PIC 9(8)V99 VALUE 00065000.00.
           05  EXISTING-ACCOUNTS   PIC 9(2) VALUE 01.
           05  DELINQUENT-DAYS     PIC 9(3) VALUE 000.
           05  REQUESTED-TIER      PIC X(10) VALUE 'PREMIUM'.
       01  DECISION-OUTPUTS.
           05  ELIGIBILITY-FLAG    PIC X(1) VALUE 'N'.
           05  MAX-OVERDRAFT-LIMIT PIC 9(6)V99 VALUE 000000.00.
           05  ANNUAL-FEE-WAIVED   PIC X(1) VALUE 'N'.
           05  REWARD-MULTIPLIER   PIC 9(1)V99 VALUE 1.00.
           05  REJECTION-CODE      PIC X(15) VALUE SPACES.

       PROCEDURE DIVISION.
       0000-PROCESS-ELIGIBILITY.
           PERFORM 1000-BASIC-QUALIFICATION
           PERFORM 2000-OVERDRAFT-LIMIT-RULES
           PERFORM 3000-REWARDS-AND-FEE-RULES
           GOBACK.

       1000-BASIC-QUALIFICATION.
           IF AGE < 18
               MOVE 'N' TO ELIGIBILITY-FLAG
               MOVE 'AGE-UNDER-18' TO REJECTION-CODE
           ELSE
               IF CITIZENSHIP-STATUS NOT = 'CITIZEN' AND CITIZENSHIP-STATUS NOT = 'RESIDENT'
                   MOVE 'N' TO ELIGIBILITY-FLAG
                   MOVE 'NON-RESIDENT' TO REJECTION-CODE
               ELSE
                   IF DELINQUENT-DAYS > 30
                       MOVE 'N' TO ELIGIBILITY-FLAG
                       MOVE 'DELINQUENT' TO REJECTION-CODE
                   ELSE
                       MOVE 'Y' TO ELIGIBILITY-FLAG
                   END-IF
               END-IF
           END-IF.

       2000-OVERDRAFT-LIMIT-RULES.
           IF ELIGIBILITY-FLAG = 'Y'
               IF ANNUAL-INCOME >= 100000.00
                   MOVE 5000.00 TO MAX-OVERDRAFT-LIMIT
               ELSE
                   IF ANNUAL-INCOME >= 50000.00
                       MOVE 2000.00 TO MAX-OVERDRAFT-LIMIT
                   ELSE
                       IF ANNUAL-INCOME >= 25000.00
                           MOVE 500.00 TO MAX-OVERDRAFT-LIMIT
                       ELSE
                           MOVE 0.00 TO MAX-OVERDRAFT-LIMIT
                       END-IF
                   END-IF
               END-IF
           ELSE
               MOVE 0.00 TO MAX-OVERDRAFT-LIMIT
           END-IF.

       3000-REWARDS-AND-FEE-RULES.
           IF ELIGIBILITY-FLAG = 'Y'
               IF EXISTING-ACCOUNTS >= 3 AND ANNUAL-INCOME > 75000.00
                   MOVE 'Y' TO ANNUAL-FEE-WAIVED
                   MOVE 2.00 TO REWARD-MULTIPLIER
               ELSE
                   IF REQUESTED-TIER = 'PREMIUM'
                       MOVE 'N' TO ANNUAL-FEE-WAIVED
                       MOVE 1.50 TO REWARD-MULTIPLIER
                   ELSE
                       MOVE 'Y' TO ANNUAL-FEE-WAIVED
                       MOVE 1.00 TO REWARD-MULTIPLIER
                   END-IF
               END-IF
           END-IF.
