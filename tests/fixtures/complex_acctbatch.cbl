       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTBATCH.
       AUTHOR. AI-MODERNIZATION-TEST.
       DATE-WRITTEN. 2026-09-02.
       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-Z.
       OBJECT-COMPUTER. IBM-Z.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCOUNT-FILE ASSIGN TO ACCTIN
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-ACCT-STATUS.
           SELECT TXN-FILE ASSIGN TO TXNIN
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-TXN-STATUS.
           SELECT CUSTOMER-FILE ASSIGN TO CUSTIN
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-CUST-STATUS.
           SELECT REPORT-FILE ASSIGN TO RPTOUT
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-RPT-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD ACCOUNT-FILE.
       01 ACCOUNT-RECORD.
           05 AR-ACCOUNT-ID       PIC X(10).
           05 AR-CUSTOMER-ID      PIC X(10).
           05 AR-BRANCH-CODE      PIC X(05).
           05 AR-ACCOUNT-TYPE     PIC X(02).
           05 AR-STATUS           PIC X(01).
           05 AR-BALANCE          PIC S9(11)V99 COMP-3.
           05 AR-CREDIT-LIMIT     PIC S9(11)V99 COMP-3.
           05 AR-LAST-ACTIVITY    PIC 9(08).
           05 AR-OPEN-DATE        PIC 9(08).
           05 AR-RISK-CODE        PIC X(02).
           05 AR-PADDING          PIC X(20).

       FD TXN-FILE.
       01 TXN-RECORD.
           05 TR-TXN-ID           PIC X(14).
           05 TR-ACCOUNT-ID       PIC X(10).
           05 TR-TXN-TYPE         PIC X(02).
           05 TR-AMOUNT           PIC S9(11)V99 COMP-3.
           05 TR-DATE             PIC 9(08).
           05 TR-CHANNEL          PIC X(02).
           05 TR-MERCHANT-CODE    PIC X(06).
           05 TR-CURRENCY         PIC X(03).
           05 TR-REVERSAL-FLAG    PIC X(01).
           05 TR-DESCRIPTION      PIC X(30).

       FD CUSTOMER-FILE.
       01 CUSTOMER-RECORD.
           05 CR-CUSTOMER-ID      PIC X(10).
           05 CR-FIRST-NAME       PIC X(20).
           05 CR-LAST-NAME        PIC X(25).
           05 CR-SEGMENT          PIC X(02).
           05 CR-STATE            PIC X(02).
           05 CR-COUNTRY          PIC X(03).
           05 CR-CREDIT-SCORE     PIC 9(03).
           05 CR-STATUS           PIC X(01).
           05 CR-EMAIL            PIC X(50).
           05 CR-PHONE            PIC X(15).

       FD REPORT-FILE.
       01 REPORT-LINE PIC X(132).

       WORKING-STORAGE SECTION.
       01 WS-FILE-STATUS.
           05 WS-ACCT-STATUS      PIC XX.
           05 WS-TXN-STATUS       PIC XX.
           05 WS-CUST-STATUS      PIC XX.
           05 WS-RPT-STATUS       PIC XX.

       01 WS-FLAGS.
           05 WS-EOF-ACCOUNT      PIC X VALUE 'N'.
           05 WS-EOF-TXN          PIC X VALUE 'N'.
           05 WS-EOF-CUSTOMER     PIC X VALUE 'N'.
           05 WS-ERROR-FLAG       PIC X VALUE 'N'.
           05 WS-CURRENT-MODE     PIC X(12) VALUE 'INITIAL'.

       01 WS-COUNTERS.
           05 WS-ACCOUNT-COUNT    PIC 9(09) VALUE ZERO.
           05 WS-TXN-COUNT        PIC 9(09) VALUE ZERO.
           05 WS-CUSTOMER-COUNT   PIC 9(09) VALUE ZERO.
           05 WS-POSTED-COUNT     PIC 9(09) VALUE ZERO.
           05 WS-REVERSED-COUNT   PIC 9(09) VALUE ZERO.
           05 WS-REJECTED-COUNT   PIC 9(09) VALUE ZERO.
           05 WS-SUSPICIOUS-COUNT PIC 9(09) VALUE ZERO.
           05 WS-ERROR-COUNT      PIC 9(09) VALUE ZERO.
           05 WS-REPORT-COUNT     PIC 9(09) VALUE ZERO.

       01 WS-AMOUNTS.
           05 WS-TOTAL-DEBITS     PIC S9(13)V99 COMP-3 VALUE ZERO.
           05 WS-TOTAL-CREDITS    PIC S9(13)V99 COMP-3 VALUE ZERO.
           05 WS-TOTAL-FEES       PIC S9(13)V99 COMP-3 VALUE ZERO.
           05 WS-TOTAL-REVERSALS  PIC S9(13)V99 COMP-3 VALUE ZERO.
           05 WS-TOTAL-EXPOSURE   PIC S9(13)V99 COMP-3 VALUE ZERO.
           05 WS-TOTAL-AVAILABLE  PIC S9(13)V99 COMP-3 VALUE ZERO.

       01 WS-CURRENT.
           05 WS-CURRENT-CUSTOMER PIC X(10).
           05 WS-CURRENT-ACCOUNT  PIC X(10).
           05 WS-CURRENT-RISK     PIC X(02).
           05 WS-CURRENT-SEGMENT  PIC X(02).
           05 WS-CURRENT-SCORE    PIC 9(03) VALUE ZERO.
           05 WS-CURRENT-LIMIT    PIC S9(11)V99 COMP-3.
           05 WS-CURRENT-BALANCE  PIC S9(11)V99 COMP-3.
           05 WS-CURRENT-FEE      PIC S9(09)V99 COMP-3.
           05 WS-CURRENT-DELTA    PIC S9(11)V99 COMP-3.

       01 WS-WORK.
           05 WS-IDX              PIC 9(04) VALUE ZERO.
           05 WS-IDX2             PIC 9(04) VALUE ZERO.
           05 WS-DAYS             PIC 9(04) VALUE ZERO.
           05 WS-MONTH            PIC 99 VALUE ZERO.
           05 WS-DATE-NUM         PIC 9(08) VALUE ZERO.
           05 WS-RATE             PIC 9V9999 VALUE ZERO.
           05 WS-COMPUTED         PIC S9(13)V99 COMP-3 VALUE ZERO.
           05 WS-EDIT-AMOUNT      PIC $$$,$$$,$$$,$$9.99.
           05 WS-EDIT-COUNT       PIC ZZZ,ZZZ,ZZ9.
           05 WS-REPORT-TEXT      PIC X(120).
           05 WS-ERROR-TEXT       PIC X(100).

       01 WS-CUSTOMER-TABLE.
           05 WS-CUSTOMER-ENTRY OCCURS 25 TIMES.
              10 WT-CUSTOMER-ID   PIC X(10).
              10 WT-SEGMENT       PIC X(02).
              10 WT-SCORE         PIC 9(03).
              10 WT-STATUS        PIC X.
              10 WT-RISK          PIC X(02).

       01 WS-ACCOUNT-TABLE.
           05 WS-ACCOUNT-ENTRY OCCURS 50 TIMES.
              10 WA-ACCOUNT-ID    PIC X(10).
              10 WA-CUSTOMER-ID   PIC X(10).
              10 WA-BALANCE       PIC S9(11)V99 COMP-3.
              10 WA-LIMIT         PIC S9(11)V99 COMP-3.
              10 WA-RISK          PIC X(02).
              10 WA-STATUS        PIC X.

       01 WS-AUDIT-RECORD.
           05 AUDIT-TXN-ID        PIC X(14).
           05 AUDIT-ACTION        PIC X(12).
           05 AUDIT-RESULT        PIC X(12).
           05 AUDIT-AMOUNT        PIC S9(11)V99 COMP-3.
           05 AUDIT-REASON        PIC X(40).

       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INITIALIZE
           PERFORM 2000-LOAD-CUSTOMERS
           PERFORM 3000-LOAD-ACCOUNTS
           PERFORM 4000-PROCESS-TRANSACTIONS
           PERFORM 5000-CALCULATE-EXPOSURE
           PERFORM 6000-GENERATE-REPORT
           PERFORM 7000-CLOSE-FILES
           PERFORM 8000-DISPLAY-SUMMARY
           GOBACK.

       1000-INITIALIZE.
           MOVE 'INITIALIZE' TO WS-CURRENT-MODE
           OPEN INPUT CUSTOMER-FILE
           IF WS-CUST-STATUS NOT = '00'
               MOVE 'Y' TO WS-ERROR-FLAG
               ADD 1 TO WS-ERROR-COUNT
               DISPLAY 'CUSTOMER OPEN ERROR: ' WS-CUST-STATUS
           END-IF
           OPEN INPUT ACCOUNT-FILE
           IF WS-ACCT-STATUS NOT = '00'
               MOVE 'Y' TO WS-ERROR-FLAG
               ADD 1 TO WS-ERROR-COUNT
           END-IF
           OPEN INPUT TXN-FILE
           IF WS-TXN-STATUS NOT = '00'
               MOVE 'Y' TO WS-ERROR-FLAG
               ADD 1 TO WS-ERROR-COUNT
           END-IF
           OPEN OUTPUT REPORT-FILE
           IF WS-RPT-STATUS NOT = '00'
               MOVE 'Y' TO WS-ERROR-FLAG
               ADD 1 TO WS-ERROR-COUNT
           END-IF
           MOVE 'N' TO WS-EOF-ACCOUNT
           MOVE 'N' TO WS-EOF-TXN
           MOVE 'N' TO WS-EOF-CUSTOMER.

       2000-LOAD-CUSTOMERS.
           MOVE 'CUSTOMERS' TO WS-CURRENT-MODE
           PERFORM UNTIL WS-EOF-CUSTOMER = 'Y'
               READ CUSTOMER-FILE
                   AT END
                       MOVE 'Y' TO WS-EOF-CUSTOMER
                   NOT AT END
                       ADD 1 TO WS-CUSTOMER-COUNT
                       IF WS-CUSTOMER-COUNT <= 25
                           MOVE CR-CUSTOMER-ID
                             TO WT-CUSTOMER-ID(WS-CUSTOMER-COUNT)
                           MOVE CR-SEGMENT
                             TO WT-SEGMENT(WS-CUSTOMER-COUNT)
                           MOVE CR-CREDIT-SCORE
                             TO WT-SCORE(WS-CUSTOMER-COUNT)
                           MOVE CR-STATUS
                             TO WT-STATUS(WS-CUSTOMER-COUNT)
                           PERFORM 2100-ASSIGN-CUSTOMER-RISK
                       ELSE
                           ADD 1 TO WS-ERROR-COUNT
                       END-IF
               END-READ
           END-PERFORM.

       2100-ASSIGN-CUSTOMER-RISK.
           EVALUATE TRUE
               WHEN WT-SCORE(WS-CUSTOMER-COUNT) >= 800
                   MOVE 'L1' TO WT-RISK(WS-CUSTOMER-COUNT)
               WHEN WT-SCORE(WS-CUSTOMER-COUNT) >= 700
                   MOVE 'L2' TO WT-RISK(WS-CUSTOMER-COUNT)
               WHEN WT-SCORE(WS-CUSTOMER-COUNT) >= 600
                   MOVE 'M1' TO WT-RISK(WS-CUSTOMER-COUNT)
               WHEN WT-SCORE(WS-CUSTOMER-COUNT) >= 500
                   MOVE 'H1' TO WT-RISK(WS-CUSTOMER-COUNT)
               WHEN OTHER
                   MOVE 'H2' TO WT-RISK(WS-CUSTOMER-COUNT)
           END-EVALUATE.

       3000-LOAD-ACCOUNTS.
           MOVE 'ACCOUNTS' TO WS-CURRENT-MODE
           PERFORM UNTIL WS-EOF-ACCOUNT = 'Y'
               READ ACCOUNT-FILE
                   AT END
                       MOVE 'Y' TO WS-EOF-ACCOUNT
                   NOT AT END
                       ADD 1 TO WS-ACCOUNT-COUNT
                       IF WS-ACCOUNT-COUNT <= 50
                           MOVE AR-ACCOUNT-ID
                             TO WA-ACCOUNT-ID(WS-ACCOUNT-COUNT)
                           MOVE AR-CUSTOMER-ID
                             TO WA-CUSTOMER-ID(WS-ACCOUNT-COUNT)
                           MOVE AR-BALANCE
                             TO WA-BALANCE(WS-ACCOUNT-COUNT)
                           MOVE AR-CREDIT-LIMIT
                             TO WA-LIMIT(WS-ACCOUNT-COUNT)
                           MOVE AR-RISK-CODE
                             TO WA-RISK(WS-ACCOUNT-COUNT)
                           MOVE AR-STATUS
                             TO WA-STATUS(WS-ACCOUNT-COUNT)
                       ELSE
                           ADD 1 TO WS-ERROR-COUNT
                       END-IF
               END-READ
           END-PERFORM.

       4000-PROCESS-TRANSACTIONS.
           MOVE 'TRANSACTIONS' TO WS-CURRENT-MODE
           PERFORM UNTIL WS-EOF-TXN = 'Y'
               READ TXN-FILE
                   AT END
                       MOVE 'Y' TO WS-EOF-TXN
                   NOT AT END
                       ADD 1 TO WS-TXN-COUNT
                       MOVE 'N' TO WS-ERROR-FLAG
                       PERFORM 4100-FIND-ACCOUNT
                       IF WS-CURRENT-ACCOUNT NOT = SPACES
                           PERFORM 4200-FIND-CUSTOMER
                           PERFORM 4300-VALIDATE-TRANSACTION
                           IF WS-ERROR-FLAG = 'N'
                               PERFORM 4400-POST-TRANSACTION
                           ELSE
                               ADD 1 TO WS-REJECTED-COUNT
                               PERFORM 4500-WRITE-AUDIT
                           END-IF
                       ELSE
                           MOVE 'ACCOUNT NOT FOUND' TO WS-ERROR-TEXT
                           MOVE 'Y' TO WS-ERROR-FLAG
                           ADD 1 TO WS-REJECTED-COUNT
                           PERFORM 4500-WRITE-AUDIT
                       END-IF
               END-READ
           END-PERFORM.

       4100-FIND-ACCOUNT.
           MOVE SPACES TO WS-CURRENT-ACCOUNT
           MOVE ZERO TO WS-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > 50
               IF WA-ACCOUNT-ID(WS-IDX) = TR-ACCOUNT-ID
                   MOVE WA-ACCOUNT-ID(WS-IDX) TO WS-CURRENT-ACCOUNT
                   MOVE WA-CUSTOMER-ID(WS-IDX) TO WS-CURRENT-CUSTOMER
                   MOVE WA-BALANCE(WS-IDX) TO WS-CURRENT-BALANCE
                   MOVE WA-LIMIT(WS-IDX) TO WS-CURRENT-LIMIT
                   MOVE WA-RISK(WS-IDX) TO WS-CURRENT-RISK
                   EXIT PERFORM
               END-IF
           END-PERFORM.

       4200-FIND-CUSTOMER.
           MOVE '00' TO WS-CURRENT-SEGMENT
           MOVE ZERO TO WS-CURRENT-SCORE
           PERFORM VARYING WS-IDX2 FROM 1 BY 1
               UNTIL WS-IDX2 > 25
               IF WT-CUSTOMER-ID(WS-IDX2) = WS-CURRENT-CUSTOMER
                   MOVE WT-SEGMENT(WS-IDX2) TO WS-CURRENT-SEGMENT
                   MOVE WT-SCORE(WS-IDX2) TO WS-CURRENT-SCORE
                   EXIT PERFORM
               END-IF
           END-PERFORM.

       4300-VALIDATE-TRANSACTION.
           IF TR-AMOUNT = ZERO
               MOVE 'ZERO AMOUNT' TO WS-ERROR-TEXT
               MOVE 'Y' TO WS-ERROR-FLAG
           END-IF
           IF TR-AMOUNT < ZERO
               MOVE 'NEGATIVE AMOUNT' TO WS-ERROR-TEXT
               MOVE 'Y' TO WS-ERROR-FLAG
           END-IF
           IF TR-CURRENCY NOT = 'USD'
               AND TR-CURRENCY NOT = 'EUR'
               AND TR-CURRENCY NOT = 'GBP'
               MOVE 'UNSUPPORTED CURRENCY' TO WS-ERROR-TEXT
               MOVE 'Y' TO WS-ERROR-FLAG
           END-IF
           IF WA-STATUS(WS-IDX) = 'C'
               MOVE 'CLOSED ACCOUNT' TO WS-ERROR-TEXT
               MOVE 'Y' TO WS-ERROR-FLAG
           END-IF
           IF TR-REVERSAL-FLAG = 'Y'
               ADD 1 TO WS-REVERSED-COUNT
               ADD TR-AMOUNT TO WS-TOTAL-REVERSALS
           END-IF
           PERFORM 4310-CHECK-LIMIT
           PERFORM 4320-CHECK-FRAUD
           PERFORM 4330-CHECK-DATE.

       4310-CHECK-LIMIT.
           COMPUTE WS-CURRENT-DELTA =
               WS-CURRENT-BALANCE + TR-AMOUNT
           IF TR-TXN-TYPE = 'CR'
               COMPUTE WS-CURRENT-DELTA =
                   WS-CURRENT-BALANCE - TR-AMOUNT
           END-IF
           IF WS-CURRENT-DELTA > WS-CURRENT-LIMIT
               MOVE 'CREDIT LIMIT EXCEEDED' TO WS-ERROR-TEXT
               MOVE 'Y' TO WS-ERROR-FLAG
           END-IF.

       4320-CHECK-FRAUD.
           IF TR-AMOUNT > 10000
               ADD 1 TO WS-SUSPICIOUS-COUNT
               IF WS-CURRENT-SCORE < 650
                   MOVE 'HIGH VALUE LOW SCORE' TO WS-ERROR-TEXT
                   MOVE 'Y' TO WS-ERROR-FLAG
               END-IF
           END-IF
           IF TR-CHANNEL = 'IN' AND TR-AMOUNT > 5000
               ADD 1 TO WS-SUSPICIOUS-COUNT
           END-IF
           IF TR-MERCHANT-CODE = 'ATM999'
               IF TR-AMOUNT > 2000
                   MOVE 'ATM THRESHOLD' TO WS-ERROR-TEXT
                   MOVE 'Y' TO WS-ERROR-FLAG
               END-IF
           END-IF.

       4330-CHECK-DATE.
           MOVE TR-DATE TO WS-DATE-NUM
           COMPUTE WS-MONTH = FUNCTION MOD(WS-DATE-NUM / 100, 100)
           IF WS-MONTH < 1 OR WS-MONTH > 12
               MOVE 'INVALID DATE' TO WS-ERROR-TEXT
               MOVE 'Y' TO WS-ERROR-FLAG
               ADD 1 TO WS-ERROR-COUNT
           END-IF.

       4400-POST-TRANSACTION.
           EVALUATE TR-TXN-TYPE
               WHEN 'DR'
                   SUBTRACT TR-AMOUNT FROM WS-CURRENT-BALANCE
                   ADD TR-AMOUNT TO WS-TOTAL-DEBITS
                   ADD 1 TO WS-POSTED-COUNT
               WHEN 'CR'
                   ADD TR-AMOUNT TO WS-CURRENT-BALANCE
                   ADD TR-AMOUNT TO WS-TOTAL-CREDITS
                   ADD 1 TO WS-POSTED-COUNT
               WHEN 'FE'
                   ADD TR-AMOUNT TO WS-TOTAL-FEES
                   SUBTRACT TR-AMOUNT FROM WS-CURRENT-BALANCE
                   ADD 1 TO WS-POSTED-COUNT
               WHEN OTHER
                   MOVE 'UNKNOWN TXN TYPE' TO WS-ERROR-TEXT
                   MOVE 'Y' TO WS-ERROR-FLAG
                   ADD 1 TO WS-REJECTED-COUNT
           END-EVALUATE
           IF WS-ERROR-FLAG = 'N'
               PERFORM 4410-CALCULATE-FEE
               PERFORM 4420-UPDATE-ACCOUNT-TABLE
           END-IF
           PERFORM 4500-WRITE-AUDIT.

       4410-CALCULATE-FEE.
           MOVE ZERO TO WS-CURRENT-FEE
           EVALUATE WS-CURRENT-SEGMENT
               WHEN 'PR'
                   MOVE 0.0025 TO WS-RATE
               WHEN 'BU'
                   MOVE 0.0035 TO WS-RATE
               WHEN 'RE'
                   MOVE 0.0050 TO WS-RATE
               WHEN OTHER
                   MOVE 0.0075 TO WS-RATE
           END-EVALUATE
           IF TR-TXN-TYPE = 'DR'
               COMPUTE WS-CURRENT-FEE ROUNDED =
                   TR-AMOUNT * WS-RATE
           ELSE
               MOVE ZERO TO WS-CURRENT-FEE
           END-IF
           ADD WS-CURRENT-FEE TO WS-TOTAL-FEES.

       4420-UPDATE-ACCOUNT-TABLE.
           IF WS-IDX > 0 AND WS-IDX <= 50
               MOVE WS-CURRENT-BALANCE TO WA-BALANCE(WS-IDX)
           END-IF
           COMPUTE WS-TOTAL-AVAILABLE =
               WS-TOTAL-AVAILABLE + WS-CURRENT-LIMIT
               - WS-CURRENT-BALANCE.

       4500-WRITE-AUDIT.
           MOVE TR-TXN-ID TO AUDIT-TXN-ID
           MOVE TR-AMOUNT TO AUDIT-AMOUNT
           IF WS-ERROR-FLAG = 'Y'
               MOVE 'REJECTED' TO AUDIT-ACTION
               MOVE 'FAILED' TO AUDIT-RESULT
               MOVE WS-ERROR-TEXT TO AUDIT-REASON
           ELSE
               MOVE 'POST' TO AUDIT-ACTION
               MOVE 'SUCCESS' TO AUDIT-RESULT
               MOVE 'TRANSACTION ACCEPTED' TO AUDIT-REASON
           END-IF
           PERFORM 4510-FORMAT-AUDIT
           MOVE WS-REPORT-TEXT TO REPORT-LINE
           WRITE REPORT-LINE
           ADD 1 TO WS-REPORT-COUNT.

       4510-FORMAT-AUDIT.
           MOVE SPACES TO WS-REPORT-TEXT
           STRING AUDIT-TXN-ID DELIMITED BY SIZE
               SPACE
               AUDIT-ACTION DELIMITED BY SIZE
               SPACE
               AUDIT-RESULT DELIMITED BY SIZE
               SPACE
               AUDIT-REASON DELIMITED BY SIZE
               INTO WS-REPORT-TEXT
           END-STRING.

       5000-CALCULATE-EXPOSURE.
           MOVE 'EXPOSURE' TO WS-CURRENT-MODE
           MOVE ZERO TO WS-TOTAL-EXPOSURE
           MOVE ZERO TO WS-TOTAL-AVAILABLE
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > 50
               IF WA-STATUS(WS-IDX) NOT = 'C'
                   ADD WA-BALANCE(WS-IDX) TO WS-TOTAL-EXPOSURE
                   COMPUTE WS-TOTAL-AVAILABLE =
                       WS-TOTAL-AVAILABLE + WA-LIMIT(WS-IDX)
                       - WA-BALANCE(WS-IDX)
               END-IF
           END-PERFORM
           PERFORM 5100-RISK-AGGREGATION.

       5100-RISK-AGGREGATION.
           PERFORM VARYING WS-IDX2 FROM 1 BY 1
               UNTIL WS-IDX2 > 25
               IF WT-RISK(WS-IDX2) = 'H2'
                   ADD 1 TO WS-SUSPICIOUS-COUNT
               ELSE
                   IF WT-RISK(WS-IDX2) = 'H1'
                       AND WT-STATUS(WS-IDX2) = 'A'
                       ADD 1 TO WS-SUSPICIOUS-COUNT
                   END-IF
               END-IF
           END-PERFORM.

       6000-GENERATE-REPORT.
           MOVE 'REPORT' TO WS-CURRENT-MODE
           MOVE SPACES TO REPORT-LINE
           MOVE 'ACCOUNT TRANSACTION REPORT' TO REPORT-LINE
           WRITE REPORT-LINE
           MOVE ALL '-' TO REPORT-LINE
           WRITE REPORT-LINE
           MOVE ALL '=' TO REPORT-LINE
           WRITE REPORT-LINE.

       7000-CLOSE-FILES.
           MOVE 'CLOSE' TO WS-CURRENT-MODE
           CLOSE CUSTOMER-FILE
           CLOSE ACCOUNT-FILE
           CLOSE TXN-FILE
           CLOSE REPORT-FILE.

