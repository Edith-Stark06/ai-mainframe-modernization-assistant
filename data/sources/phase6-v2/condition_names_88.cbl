       IDENTIFICATION DIVISION.
       PROGRAM-ID. COND8801.
       AUTHOR. SYNTHETIC-CORPUS.
      * CATEGORY B: DATA FEATURES - LEVEL 88 CONDITION NAMES
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  TRANSACTION-STATUS-RECORD.
           05  TX-TYPE-CODE        PIC X(1) VALUE 'D'.
               88  TX-DEPOSIT      VALUE 'D'.
               88  TX-WITHDRAWAL   VALUE 'W'.
               88  TX-TRANSFER     VALUE 'T'.
               88  TX-FEE          VALUE 'F'.
               88  TX-VALID-KIND   VALUES 'D' 'W' 'T' 'F'.
           05  TX-STATUS-FLAG      PIC X(1) VALUE 'P'.
               88  TX-PENDING      VALUE 'P'.
               88  TX-APPROVED     VALUE 'A'.
               88  TX-REJECTED     VALUE 'R'.
               88  TX-SETTLED      VALUE 'S'.
           05  CHANNEL-ORIGIN      PIC X(3) VALUE 'ATM'.
               88  ONLINE-CHANNEL  VALUES 'WEB' 'MOB' 'API'.
               88  PHYSICAL-BRANCH VALUES 'BRN' 'ATM'.
           05  TX-AMOUNT           PIC 9(7)V99 VALUE 0002500.00.
       01  PROCESSING-OUTCOME.
           05  OUTCOME-ACTION      PIC X(15) VALUE SPACES.
           05  FEES-LEVIED         PIC 9(5)V99 VALUE 00000.00.

       PROCEDURE DIVISION.
       0000-PROCESS-TRANSACTION.
           PERFORM 1000-VALIDATE-TX-TYPE
           PERFORM 2000-ROUTE-BY-STATUS
           GOBACK.

       1000-VALIDATE-TX-TYPE.
           IF NOT TX-VALID-KIND
               MOVE 'REJECT-BAD-KIND' TO OUTCOME-ACTION
               MOVE 'R' TO TX-STATUS-FLAG
           ELSE
               IF TX-DEPOSIT
                   MOVE 'CREDIT-ACCOUNT' TO OUTCOME-ACTION
               ELSE
                   IF TX-WITHDRAWAL
                       MOVE 'DEBIT-ACCOUNT' TO OUTCOME-ACTION
                   ELSE
                       IF TX-TRANSFER
                           MOVE 'XFER-ACCOUNT' TO OUTCOME-ACTION
                       ELSE
                           MOVE 'FEE-ASSESSMENT' TO OUTCOME-ACTION
                       END-IF
                   END-IF
               END-IF
           END-IF.

       2000-ROUTE-BY-STATUS.
           IF PHYSICAL-BRANCH AND TX-WITHDRAWAL
               IF TX-AMOUNT > 1000.00
                   MOVE 5.00 TO FEES-LEVIED
               ELSE
                   MOVE 0.00 TO FEES-LEVIED
               END-IF
           END-IF
           IF ONLINE-CHANNEL
               MOVE 0.00 TO FEES-LEVIED
           END-IF.
